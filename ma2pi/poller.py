"""Poll the Web Remote ``playbacks`` view once and serve every consumer.

The executor topology (wide executors) and the LED feedback need the same
answers.  Two readers of ``client.playback_responses`` would steal each other's
messages, so this poller is the single consumer: per cycle it requests one
block per ``(page, region)``, feeds the topology, diagnoses missing targets and
hands the answer to the LED feedback when that is active.

LED blocks and topology blocks are separate requests with separate clocks: the
LEDs need a fast, small poll, the topology only changes when somebody rewires
the show and needs a slow poll of the floating buttons the controls address.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .feedback import (
    PlaybackSnapshot,
    RequestBlock,
    _belongs_to_block,
    _block_key,
    blocks_from_ranges,
    parse_playbacks,
    resolve_playback_target,
)
from .topology import FLOATING_START, ExecutorTopology

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .config import AppConfig

LOGGER = logging.getLogger("ma2pi.poller")

BlockKey = tuple[int | str, int]
#: A request in flight is identified by its purpose and its block.
RequestKey = tuple[str, int | str, int]


@dataclass(frozen=True, slots=True)
class PlaybackTarget:
    """One executor a control can address, in any bank and of any kind."""

    control: str
    page: int | str
    executor: int
    kind: str


def build_playback_targets(config: "AppConfig") -> list[PlaybackTarget]:
    """Collect every playback target of every device and bank (buttons and faders)."""

    targets: list[PlaybackTarget] = []
    seen: set[tuple[str, int | str, int]] = set()
    for name, device in config.devices.items():
        profile = config.profiles[device.profile]
        settings = config.mapping.device_banks.get(name)
        banks = {1}
        banks.update(bank.number for bank in profile.banks)
        layers = settings.banks if settings is not None else {}
        banks.update(layers)
        controls = set(config.mapping.playbacks)
        for layer in layers.values():
            controls.update(layer.playbacks)
        owned = set(profile.control_names)
        for bank in sorted(banks):
            for control in sorted(controls & owned):
                resolved = resolve_playback_target(config, name, bank, control)
                if resolved is None:
                    continue
                page, executor, kind = resolved
                key = (control, page, executor)
                if key in seen:
                    continue
                seen.add(key)
                targets.append(PlaybackTarget(control, page, executor, kind))
    return targets


def _merge(first: RequestBlock | None, second: RequestBlock) -> RequestBlock:
    if first is None:
        return second
    start = min(first.start, second.start)
    end = max(first.start + first.count, second.start + second.count)
    return RequestBlock(first.page, start, end - start, first.items_type, first.view)


class PlaybackPoller:
    """Single consumer of the ``playbacks`` answers."""

    def __init__(
        self,
        config: "AppConfig",
        client: Any,
        topology: ExecutorTopology,
        *,
        on_answer: Callable[[PlaybackSnapshot, RequestBlock], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        timeout: float | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self._topology = topology
        self._on_answer = on_answer
        self._clock = clock
        self._timeout_override = timeout
        self._feedback_blocks: dict[BlockKey, RequestBlock] = {}
        self._target_blocks: dict[BlockKey, RequestBlock] = {}
        self._targets: dict[BlockKey, list[PlaybackTarget]] = {}
        self._pending: dict[RequestKey, float] = {}
        self._topology_due = 0.0
        self._warned: set[tuple[str, int | str, int]] = set()
        self.set_config(config, {})

    # -- state ---------------------------------------------------------

    def set_config(
        self, config: "AppConfig", feedback_blocks: Mapping[BlockKey, RequestBlock]
    ) -> None:
        """Adopt a configuration: new blocks, no topology, no old answers."""

        self.config = config
        self._feedback_blocks = dict(feedback_blocks)
        targets = build_playback_targets(config)
        ranges: dict[BlockKey, list[int]] = {}
        self._targets = {}
        for target in targets:
            # Only floating buttons are redirected to a wide executor; faders
            # keep their own slot, so their region is never polled for topology.
            if target.kind != "button" or target.executor < FLOATING_START:
                continue
            key = _block_key(target.page, target.executor)
            ranges.setdefault(key, []).append(target.executor)
            self._targets.setdefault(key, []).append(target)
        self._target_blocks = blocks_from_ranges(ranges)
        self.reset()
        self._warned.clear()

    def reset(self) -> None:
        """Forget topology and open requests, e.g. after a connection loss."""

        self._topology.invalidate()
        self._pending.clear()
        self._topology_due = 0.0
        self.drain()

    def drain(self) -> None:
        """Discard answers that belong to a previous connection or config."""

        queue = getattr(self._client, "playback_responses", None)
        if queue is None:
            return
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    # -- scheduling ----------------------------------------------------

    @property
    def feedback_active(self) -> bool:
        return self.config.feedback.enabled and bool(self._feedback_blocks)

    @property
    def topology_active(self) -> bool:
        return self.config.mapping.combined_executors == "auto" and bool(
            self._target_blocks
        )

    def blocks(self) -> dict[BlockKey, RequestBlock]:
        """Topology blocks: the floating buttons the controls address."""

        return dict(self._target_blocks) if self.topology_active else {}

    def interval(self) -> float:
        """Shortest period any active reader needs."""

        periods = []
        if self.feedback_active:
            periods.append(self.config.feedback.interval_ms / 1000.0)
        if self.topology_active or not periods:
            periods.append(self.config.mapping.topology_interval_ms / 1000.0)
        return max(0.1, min(periods))

    def _timeout(self) -> float:
        if self._timeout_override is not None:
            return self._timeout_override
        return max(2.0 * self.interval(), 1.0)

    # -- one cycle -----------------------------------------------------

    async def step(self) -> None:
        """Request every due block once and distribute the answers."""

        if not getattr(self._client, "authenticated", False):
            return
        if self.feedback_active:
            for key, block in self._feedback_blocks.items():
                await self._request_block(("led", *key), key, block)
        now = self._clock()
        if self.topology_active and now >= self._topology_due:
            self._topology_due = now + self.config.mapping.topology_interval_ms / 1000.0
            for key, block in self._target_blocks.items():
                await self._request_block(("topology", *key), key, block)

    async def _request_block(
        self, request: RequestKey, key: BlockKey, block: RequestBlock
    ) -> None:
        now = self._clock()
        deadline = self._pending.get(request)
        if deadline is not None and now < deadline:
            return
        timeout = self._timeout()
        self._pending[request] = now + timeout
        self.drain()
        self._client.request_playbacks(
            block.page, block.start, block.count, block.items_type, block.view
        )
        queue = self._client.playback_responses
        ends = now + timeout
        while True:
            remaining = ends - self._clock()
            if remaining <= 0:
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            snapshot = parse_playbacks(payload)
            if snapshot is None:
                LOGGER.debug("Playbacks-Antwort ohne Executor-Daten verworfen")
                continue
            if not _belongs_to_block(snapshot, block):
                LOGGER.debug(
                    "Playbacks-Antwort passt nicht zu %s.%s und wird verworfen",
                    block.page,
                    block.start,
                )
                continue
            self._pending.pop(request, None)
            self._distribute(request[0], key, block, snapshot)
            return
        self._pending.pop(request, None)
        LOGGER.debug(
            "Playbacks-Antwort für %s.%s ausgeblieben", block.page, block.start
        )

    def _distribute(
        self, kind: str, key: BlockKey, block: RequestBlock, snapshot: PlaybackSnapshot
    ) -> None:
        if kind == "topology":
            self._topology.update(
                block.page,
                key[1],
                snapshot.combined,
                snapshot.seen_executors,
                range(block.start + 1, block.start + block.count + 1),
            )
            self._diagnose(key, block)
        elif self._on_answer is not None and self.feedback_active:
            self._on_answer(snapshot, block)

    def _diagnose(self, key: BlockKey, block: RequestBlock) -> None:
        """Warn once per target whose executor the console does not have."""

        for target in self._targets.get(key, ()):
            warn_key = (target.control, target.page, target.executor)
            if warn_key in self._warned:
                continue
            if self._topology.status(block.page, target.executor) != "absent":
                continue
            self._warned.add(warn_key)
            LOGGER.warning(
                "Playback-Ziel %s (Page %s, Executor %d) existiert auf der MA nicht; "
                "Eingaben laufen ins Leere",
                target.control,
                target.page,
                target.executor,
            )
