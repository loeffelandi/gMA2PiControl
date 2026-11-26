"""Executor feedback: poll playback state and drive controller LEDs.

The MIDICRAFT controllers show an executor state as a note-on whose velocity
encodes mode and colour (manual §8):

* ``0``            off
* ``1–13``         static dark, palette index added
* ``15–27``        static bright, palette index added
* ``43–55``        flashing dark/off
* ``124–127``      colour defined in the device menu

This module only uses the first three ranges.  Colour and running state come
from the Web Remote ``playbacks`` response (``isRun``, ``bC``/``bdC``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .config import AppConfig

LOGGER = logging.getLogger("ma2pi.feedback")

#: Palette order of the MIDICRAFT firmware; the index is part of the velocity.
PALETTE: tuple[str, ...] = (
    "white",
    "red",
    "orange",
    "yellow",
    "yellowgreen",
    "green",
    "seagreen",
    "cyan",
    "lavender",
    "blue",
    "violet",
    "magenta",
    "pink",
)

PALETTE_RGB: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "orange": (255, 128, 0),
    "yellow": (255, 255, 0),
    "yellowgreen": (180, 255, 0),
    "green": (0, 255, 0),
    "seagreen": (0, 255, 128),
    "cyan": (0, 255, 255),
    "lavender": (128, 128, 255),
    "blue": (0, 0, 255),
    "violet": (128, 0, 255),
    "magenta": (255, 0, 255),
    "pink": (255, 128, 255),
}

#: Velocity base per LED mode.
MODE_BASE: dict[str, int] = {"off": 0, "dark": 1, "bright": 15}

#: MIDI status byte for note-on on channel 1.
NOTE_ON = 0x90


def palette_index(name: str) -> int:
    """Return the palette index for a configured colour name."""

    return PALETTE.index(name)


def nearest_color(value: Any) -> int | None:
    """Map a ``#rrggbb`` string to the closest palette index.

    Returns ``None`` for missing or malformed values so the caller can fall
    back to the configured colour.
    """

    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6:
        return None
    try:
        rgb = tuple(int(text[offset : offset + 2], 16) for offset in (0, 2, 4))
    except ValueError:
        return None
    if rgb == (0, 0, 0):
        # Black means "no appearance colour" for an LED rather than a colour.
        return None
    best_index = 0
    best_distance = float("inf")
    for index, name in enumerate(PALETTE):
        distance = sum(
            (channel - target) ** 2
            for channel, target in zip(rgb, PALETTE_RGB[name])
        )
        if distance < best_distance:
            best_distance = float(distance)
            best_index = index
    return best_index


def led_velocity(
    running: bool,
    color: int | None,
    off_state: str,
    fallback: int,
) -> int:
    """Return the velocity for one executor LED."""

    index = fallback if color is None else color
    if running:
        return MODE_BASE["bright"] + index
    if off_state == "off":
        return MODE_BASE["off"]
    return MODE_BASE["dark"] + index


@dataclass(frozen=True, slots=True)
class ExecutorState:
    running: bool
    color: int | None


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    """One decoded ``playbacks`` response.

    ``page`` is the raw ``iPage`` and therefore 0-based; a configured page is
    ``page + 1``.  ``executors`` is keyed by the 1-based executor number.
    """

    page: int
    items_type: int
    executors: dict[int, ExecutorState]


def _iter_items(items: Any) -> list[dict[str, Any]]:
    """Flatten the nested ``itemGroups[].items`` structure into executor items."""

    result: list[dict[str, Any]] = []

    def visit(entry: Any) -> None:
        if isinstance(entry, list):
            for child in entry:
                visit(child)
        elif isinstance(entry, dict):
            result.append(entry)

    visit(items)
    return result


def parse_playbacks(payload: dict[str, Any]) -> PlaybackSnapshot | None:
    """Turn one Web Remote ``playbacks`` response into executor states."""

    page = payload.get("iPage")
    if not isinstance(page, int):
        return None
    executors: dict[int, ExecutorState] = {}
    items_type = 0
    for group in payload.get("itemGroups") or []:
        if not isinstance(group, dict):
            continue
        items = _iter_items(group.get("items"))
        if items and not items_type:
            group_type = group.get("itemsType")
            items_type = group_type if isinstance(group_type, int) else 0
        for item in items:
            index = item.get("iExec")
            if not isinstance(index, int):
                continue
            running = item.get("isRun")
            if isinstance(running, bool):
                pass
            elif isinstance(running, int):
                running = bool(running)
            else:
                # Unknown state: keep the LED as it is instead of guessing.
                continue
            color = nearest_color(item.get("bC"))
            if color is None:
                color = nearest_color(item.get("bdC"))
            executors[index + 1] = ExecutorState(running, color)
    if not executors:
        return None
    return PlaybackSnapshot(page, items_type, executors)


@dataclass(frozen=True, slots=True)
class LedTarget:
    control: str
    device: str
    note: int
    page: int | str
    executor: int


@dataclass(frozen=True, slots=True)
class RequestBlock:
    page: int | str
    start: int
    count: int
    items_type: int
    view: int


def _block_key(page: int | str, executor: int) -> tuple[int | str, int]:
    # Executor 100 still belongs to the page blocks; floating executors start
    # at 101 and are addressed through the bottom-button view.
    return (page, 100 if executor > 100 else 0)


def _belongs_to_block(snapshot: PlaybackSnapshot, block: RequestBlock) -> bool:
    """Check that a response answers the given request block.

    Requests and responses are not correlated by the Web Remote, so a late
    answer can arrive after its block timed out.  Matching page, item type and
    the requested executor range keeps such answers from being applied.
    """

    if block.page != "current" and snapshot.page + 1 != block.page:
        return False
    if snapshot.items_type and snapshot.items_type != block.items_type:
        return False
    expected = range(block.start + 1, block.start + block.count + 1)
    return any(executor in snapshot.executors for executor in expected)


def build_feedback_targets(
    config: "AppConfig",
) -> tuple[list[LedTarget], dict[tuple[int | str, int], RequestBlock]]:
    """Collect the LED-capable button targets and their request blocks."""

    led_controls: dict[tuple[str, str], int] = {}
    for name, device in config.devices.items():
        if device.backend != "midi":
            continue
        profile = config.profiles[device.profile]
        feedback = profile.led_feedback
        if feedback is None:
            continue
        allowed = set(feedback.notes) if feedback.notes is not None else None
        note_pairs = list(profile.notes.items())
        for bank in profile.banks:
            note_pairs.extend(bank.notes.items())
        for note, control in note_pairs:
            if allowed is not None and note not in allowed:
                continue
            led_controls.setdefault((name, control), note)

    targets: list[LedTarget] = []
    ranges: dict[tuple[int | str, int], list[int]] = {}
    for (device, control), note in led_controls.items():
        playback = config.mapping.playbacks.get(control)
        if playback is None or playback.kind != "button":
            continue
        targets.append(
            LedTarget(control, device, note, playback.page, playback.executor)
        )
        ranges.setdefault(_block_key(playback.page, playback.executor), []).append(
            playback.executor
        )

    blocks: dict[tuple[int | str, int], RequestBlock] = {}
    for key, executors in ranges.items():
        page, boundary = key
        lowest = min(executors) - 1
        highest = max(executors) - 1
        start = (lowest // 5) * 5
        count = (highest // 5) * 5 - start + 5
        items_type = 3 if boundary else 2
        blocks[key] = RequestBlock(page, start, count, items_type, items_type)
    return targets, blocks


class ExecutorFeedback:
    """Poll executor states and translate them into controller LED frames."""

    def __init__(
        self,
        config: "AppConfig",
        client: Any,
        midi: Any,
        *,
        dry_run: bool = False,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float | None = None,
    ) -> None:
        self.config = config
        self._client = client
        self._midi = midi
        self._dry_run = dry_run
        self._clock = clock
        self._sleep = sleep
        self._timeout_override = timeout
        self._targets: list[LedTarget] = []
        self._blocks: dict[tuple[int | str, int], RequestBlock] = {}
        self._last: dict[tuple[str, int], int] = {}
        self._pending: dict[tuple[int | str, int], float] = {}
        self._devices: dict[str, str] = {}
        self.set_config(config)

    def set_config(self, config: "AppConfig") -> None:
        """Adopt a new configuration and drop all cached LED states."""

        self.config = config
        self._targets, self._blocks = build_feedback_targets(config)
        self._last.clear()
        self._pending.clear()
        self._drain_responses()

    def reset(self) -> None:
        """Forget cached states, e.g. after a connection loss."""

        self._last.clear()
        self._pending.clear()
        self._drain_responses()

    def _drain_responses(self) -> None:
        """Discard answers that belong to a previous connection or config."""

        queue = getattr(self._client, "playback_responses", None)
        if queue is None:
            return
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    @property
    def targets(self) -> tuple[LedTarget, ...]:
        return tuple(self._targets)

    def _interval(self) -> float:
        return max(0.1, self.config.feedback.interval_ms / 1000.0)

    def _timeout(self) -> float:
        if self._timeout_override is not None:
            return self._timeout_override
        return max(2.0 * self._interval(), 1.0)

    async def run(self) -> None:
        """Poll until cancelled, following later config reloads.

        The daemon always starts this task, so enabling ``[feedback]`` or adding
        targets at runtime takes effect without a restart.
        """

        active = False
        while True:
            enabled = self.config.feedback.enabled and bool(self._targets)
            if enabled != active:
                active = enabled
                if active:
                    LOGGER.info(
                        "Executor-Feedback aktiv: %d LEDs, %d Abfrageblöcke, %.0f ms",
                        len(self._targets),
                        len(self._blocks),
                        self.config.feedback.interval_ms,
                    )
                elif not self.config.feedback.enabled:
                    LOGGER.info("Executor-Feedback ist deaktiviert")
                else:
                    LOGGER.info(
                        "Executor-Feedback aktiv, aber kein LED-fähiges Button-Ziel"
                    )
            if active:
                try:
                    await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - defensive
                    LOGGER.exception("Executor-Feedback-Zyklus fehlgeschlagen")
            await self._sleep(self._interval())

    async def step(self) -> None:
        """Run one poll cycle: request open blocks and apply answers."""

        if not self.config.feedback.enabled or not self._targets:
            return
        if not getattr(self._client, "authenticated", False):
            return
        self._sync_devices()
        for key, block in list(self._blocks.items()):
            await self._request_block(key, block)

    def _sync_devices(self) -> None:
        devices = getattr(self._midi, "open_devices", {}) or {}
        if devices != self._devices:
            self._devices = dict(devices)
            self._last.clear()

    async def _request_block(
        self, key: tuple[int | str, int], block: RequestBlock
    ) -> None:
        now = self._clock()
        deadline = self._pending.get(key)
        if deadline is not None and now < deadline:
            return
        timeout = self._timeout()
        self._pending[key] = now + timeout
        # Only one request may be in flight, so anything already queued is a
        # late answer from an earlier cycle and must not be applied.
        self._drain_responses()
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
                # Keep waiting for our own answer instead of leaving the queue
                # one position out of step.
                LOGGER.debug(
                    "Playbacks-Antwort passt nicht zu %s.%s und wird verworfen",
                    block.page,
                    block.start,
                )
                continue
            self._pending.pop(key, None)
            self._apply(snapshot, block)
            return
        self._pending.pop(key, None)
        LOGGER.debug(
            "Playbacks-Antwort für %s.%s ausgeblieben", block.page, block.start
        )

    def _apply(self, snapshot: PlaybackSnapshot, block: RequestBlock) -> None:
        feedback = self.config.feedback
        fallback = palette_index(feedback.fallback_color)
        for target in self._targets:
            if target.page == "current":
                # Only a request for the current page reflects the master page;
                # answers for a fixed page must not drive ``current`` targets.
                if block.page != "current":
                    continue
            elif target.page != snapshot.page + 1:
                continue
            state = snapshot.executors.get(target.executor)
            if state is None:
                continue
            velocity = led_velocity(
                state.running, state.color, feedback.off_state, fallback
            )
            led = (target.device, target.note)
            if self._last.get(led) == velocity:
                continue
            if self._dry_run:
                LOGGER.info(
                    "dry-run: LED %s Note %d Velocity %d",
                    target.control,
                    target.note,
                    velocity,
                )
                self._last[led] = velocity
                continue
            frame = bytes((NOTE_ON, target.note, velocity))
            if self._midi.send(target.device, frame):
                self._last[led] = velocity
            else:
                LOGGER.debug(
                    "LED-Frame für %s konnte nicht gesendet werden", target.control
                )
