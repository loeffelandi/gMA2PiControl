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
from dataclasses import dataclass, field
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

#: Seconds a device may keep written bytes unconsumed before its LED output
#: is paused.  The kernel reports them through the rawmidi status.
OUTPUT_STALL_SECONDS = 2.0

#: Retry gap after a refused write, so a closed device cannot spin the pump.
_RETRY_SECONDS = 0.1

#: Frame gap used when a device has no ``led_feedback`` profile.
_DEFAULT_FRAME_INTERVAL = 0.02


def palette_index(name: str) -> int:
    """Return the palette index for a configured colour name."""

    return PALETTE.index(name)


def nearest_color(value: Any) -> int | None:
    """Map a ``#rrggbb`` string to the closest palette index."""

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
    """One decoded ``playbacks`` response."""

    page: int
    items_type: int
    executors: dict[int, ExecutorState]
    seen_executors: frozenset[int] = field(default_factory=frozenset)
    empty_executors: frozenset[int] = field(default_factory=frozenset)


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
    seen_executors: set[int] = set()
    empty_executors: set[int] = set()
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
            exec_num = index + 1
            seen_executors.add(exec_num)
            if item.get("isEmpty") is True:
                empty_executors.add(exec_num)
                continue
            running = item.get("isRun")
            if isinstance(running, bool):
                pass
            elif isinstance(running, int):
                running = bool(running)
            else:
                continue
            color = nearest_color(item.get("bC"))
            if color is None:
                color = nearest_color(item.get("bdC"))
            executors[exec_num] = ExecutorState(running, color)
    if not executors and not seen_executors:
        return None
    return PlaybackSnapshot(
        page,
        items_type,
        executors,
        frozenset(seen_executors),
        frozenset(empty_executors),
    )


@dataclass(frozen=True, slots=True)
class LedTarget:
    control: str
    device: str
    note: int
    page: int | str
    executor: int
    channel: int = 1


@dataclass(frozen=True, slots=True)
class RequestBlock:
    page: int | str
    start: int
    count: int
    items_type: int
    view: int


def _block_key(page: int | str, executor: int) -> tuple[int | str, int]:
    return (page, 100 if executor > 100 else 0)


def _belongs_to_block(
    snapshot: PlaybackSnapshot,
    block: RequestBlock,
    *,
    known_current_page: int | None = None,
    fixed_pages: frozenset[int] = frozenset(),
) -> bool:
    """Check that a response answers the given request block."""

    snap_page = snapshot.page + 1
    if block.page != "current":
        if snap_page != block.page:
            return False
    elif (
        known_current_page is not None
        and snap_page != known_current_page
        and snap_page in fixed_pages
    ):
        # Reject a late answer for a polled fixed page when current page differs.
        return False
    if snapshot.items_type and snapshot.items_type != block.items_type:
        return False
    expected = range(block.start + 1, block.start + block.count + 1)
    present = snapshot.executors or snapshot.seen_executors
    return any(executor in present for executor in expected)


def _frame_intervals(config: "AppConfig") -> dict[str, float]:
    """Minimum gap between two LED frames, per configured MIDI device."""

    result: dict[str, float] = {}
    for name, device in config.devices.items():
        if device.backend != "midi":
            continue
        feedback = config.profiles[device.profile].led_feedback
        if feedback is not None:
            result[name] = feedback.frame_interval_ms / 1000.0
    return result


def _default_bank_size(config: "AppConfig", device_name: str) -> int:
    settings = config.mapping.device_banks.get(device_name)
    if settings is not None and settings.bank_size is not None:
        return settings.bank_size
    device = config.devices.get(device_name)
    if device is None:
        return 1
    profile = config.profiles[device.profile]
    kinds = profile.control_kinds
    faders = sum(1 for kind in kinds.values() if kind == "fader")
    if faders:
        return faders
    buttons = sum(1 for kind in kinds.values() if kind == "button")
    return max(1, buttons)


def _resolve_playback_for_bank(
    config: "AppConfig", device_name: str, bank_num: int, control: str
) -> tuple[int | str, int] | None:
    settings = config.mapping.device_banks.get(device_name)
    layer = settings.banks.get(bank_num) if settings is not None else None
    if layer is not None and control in layer.keys:
        return None
    base = config.mapping.playbacks.get(control)
    override = layer.playbacks.get(control) if layer is not None else None
    if base is None and override is None:
        return None
    kind = (
        override.kind
        if override is not None and override.kind is not None
        else (base.kind if base is not None else "button")
    )
    if kind != "button":
        return None
    page = (
        override.page
        if override is not None and override.page is not None
        else (base.page if base is not None else None)
    )
    executor = (
        override.executor
        if override is not None and override.executor is not None
        else (base.executor if base is not None else None)
    )
    if page is None or executor is None:
        return None
    if (
        settings is not None
        and bank_num > 1
        and (override is None or override.executor is None)
        and (layer is None or layer.ma_page is None)
    ):
        executor += (bank_num - 1) * _default_bank_size(config, device_name)
    return page, executor


def build_feedback_targets(
    config: "AppConfig",
) -> tuple[list[LedTarget], dict[tuple[int | str, int], RequestBlock]]:
    """Collect LED-capable button targets (including banked channels/offsets)."""

    targets: list[LedTarget] = []
    seen_leds: set[tuple[str, int, int]] = set()
    ranges: dict[tuple[int | str, int], list[int]] = {}

    for name, device in config.devices.items():
        if device.backend != "midi":
            continue
        profile = config.profiles[device.profile]
        feedback = profile.led_feedback
        if feedback is None or not feedback.enabled:
            continue
        allowed = set(feedback.notes) if feedback.notes is not None else None

        if profile.banks:
            for bank in profile.banks:
                for note, control in bank.notes.items():
                    if allowed is not None and note not in allowed:
                        continue
                    led_id = (name, bank.channel, note)
                    if led_id in seen_leds:
                        continue
                    resolved = _resolve_playback_for_bank(
                        config, name, bank.number, control
                    )
                    if resolved is None:
                        continue
                    seen_leds.add(led_id)
                    page, executor = resolved
                    targets.append(
                        LedTarget(
                            control,
                            name,
                            note,
                            page,
                            executor,
                            channel=bank.channel,
                        )
                    )
                    ranges.setdefault(_block_key(page, executor), []).append(
                        executor
                    )
        else:
            for note, control in profile.notes.items():
                if allowed is not None and note not in allowed:
                    continue
                led_id = (name, 1, note)
                if led_id in seen_leds:
                    continue
                resolved = _resolve_playback_for_bank(config, name, 1, control)
                if resolved is None:
                    continue
                seen_leds.add(led_id)
                page, executor = resolved
                targets.append(
                    LedTarget(control, name, note, page, executor, channel=1)
                )
                ranges.setdefault(_block_key(page, executor), []).append(
                    executor
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


def _outbox_key(channel: int, note: int) -> int | tuple[int, int]:
    return note if channel == 1 else (channel, note)


def _unpack_outbox_key(key: int | tuple[int, int]) -> tuple[int, int]:
    if isinstance(key, tuple):
        return key
    return 1, int(key)


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
        self._fixed_pages: frozenset[int] = frozenset()
        self._known_current_page: int | None = None
        self._last: dict[tuple[str, int] | tuple[str, int, int], int] = {}
        self._pending: dict[tuple[int | str, int], float] = {}
        self._devices: dict[str, tuple[str, int]] = {}
        self._outbox: dict[str, dict[int | tuple[int, int], int]] = {}
        self._next_send: dict[str, float] = {}
        self._intervals: dict[str, float] = {}
        self._unconsumed_since: dict[str, float] = {}
        self._pending_after_send: dict[str, int] = {}
        self._stalled: set[str] = set()
        self._wake = asyncio.Event()
        self.set_config(config)

    def set_config(self, config: "AppConfig") -> None:
        """Adopt a new configuration and drop all cached LED states."""

        self.config = config
        self._targets, self._blocks = build_feedback_targets(config)
        self._fixed_pages = frozenset(
            int(page) for page, _ in self._blocks if isinstance(page, int)
        )
        self._known_current_page = None
        self._intervals = _frame_intervals(config)
        self._last.clear()
        self._pending.clear()
        self._clear_output(clear_stalled=True)
        self._drain_responses()

    def reset(self) -> None:
        """Forget cached states, e.g. after a connection loss."""

        self._last.clear()
        self._pending.clear()
        self._known_current_page = None
        self._clear_output()
        self._drain_responses()

    def _clear_output(self, *, clear_stalled: bool = False) -> None:
        self._outbox.clear()
        self._next_send.clear()
        self._unconsumed_since.clear()
        self._pending_after_send.clear()
        if clear_stalled:
            self._stalled.clear()

    def _reset_device(self, device: str) -> None:
        for key in [k for k in self._last if k[0] == device]:
            self._last.pop(key, None)
        self._outbox.pop(device, None)
        self._next_send.pop(device, None)
        self._unconsumed_since.pop(device, None)
        self._pending_after_send.pop(device, None)
        self._stalled.discard(device)

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
        """Poll until cancelled, following later config reloads."""

        pump = asyncio.create_task(self._pump_loop(), name="ma2pi-feedback-pump")
        active = False
        try:
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
        finally:
            pump.cancel()
            try:
                await pump
            except asyncio.CancelledError:
                pass

    async def _pump_loop(self) -> None:
        """Send queued LED frames at each device's own pace."""

        while True:
            try:
                delay = self.pump()
            except Exception:  # pragma: no cover - defensive
                LOGGER.exception("LED-Ausgabe fehlgeschlagen")
                delay = _RETRY_SECONDS
            if delay is None:
                self._wake.clear()
                await self._wake.wait()
            else:
                await self._sleep(delay)

    def _led_cache_key(
        self, device: str, channel: int, note: int
    ) -> tuple[str, int] | tuple[str, int, int]:
        return (device, note) if channel == 1 else (device, channel, note)

    def pump(self) -> float | None:
        """Send every frame that is due and return the wait for the next one."""

        now = self._clock()
        wait: float | None = None
        probe = getattr(self._midi, "output_pending", None)
        for device, outbox in self._outbox.items():
            if not outbox or device in self._stalled:
                continue
            due = self._next_send.get(device, 0.0)
            if now < due:
                wait = due - now if wait is None else min(wait, due - now)
                continue
            if self._output_stalled(device, now):
                continue
            raw_key, velocity = next(iter(outbox.items()))
            channel, note = _unpack_outbox_key(raw_key)
            status_byte = NOTE_ON | ((channel - 1) & 0x0F)
            interval = self._intervals.get(device, _DEFAULT_FRAME_INTERVAL)
            if self._midi.send(device, bytes((status_byte, note, velocity))):
                del outbox[raw_key]
                self._last[self._led_cache_key(device, channel, note)] = velocity
                if probe is not None:
                    after = probe(device)
                    if after is not None and after > 0:
                        self._pending_after_send[device] = after
                    else:
                        self._pending_after_send.pop(device, None)
            else:
                LOGGER.debug("LED-Frame für %s Note %d nicht gesendet", device, note)
                interval = max(interval, _RETRY_SECONDS)
            self._next_send[device] = now + interval
            if outbox:
                wait = interval if wait is None else min(wait, interval)
        return wait

    def _output_stalled(self, device: str, now: float) -> bool:
        """Pause a device whose written bytes make zero drain progress for 2 s."""

        probe = getattr(self._midi, "output_pending", None)
        pending = probe(device) if probe is not None else None
        if not pending:
            self._unconsumed_since.pop(device, None)
            self._pending_after_send.pop(device, None)
            return False
        prev_after = self._pending_after_send.get(device)
        if prev_after is not None and pending < prev_after:
            # At least (prev_after - pending) bytes were consumed since the
            # previous write, so output is actively draining.
            self._unconsumed_since[device] = now
            self._pending_after_send[device] = pending
            return False
        since = self._unconsumed_since.setdefault(device, now)
        if now - since < OUTPUT_STALL_SECONDS:
            return False
        self._stalled.add(device)
        LOGGER.warning(
            "MIDI-Ausgabe an %s gestaut (%d Bytes seit %.0f s nicht abgenommen); "
            "LED-Ausgabe für dieses Gerät pausiert bis zum erneuten Öffnen",
            device,
            pending,
            now - since,
        )
        return True

    async def step(self) -> None:
        """Run one poll cycle: request open blocks and apply answers."""

        if not self.config.feedback.enabled or not self._targets:
            return
        if not getattr(self._client, "authenticated", False):
            return
        self._sync_devices()
        for key, block in list(self._blocks.items()):
            await self._request_block(key, block)
        self.pump()

    def _sync_devices(self) -> None:
        paths = getattr(self._midi, "open_devices", {}) or {}
        gens = getattr(self._midi, "open_generations", None) or {}
        current = {
            name: (path, int(gens.get(name, 1))) for name, path in paths.items()
        }
        if current == self._devices:
            return
        changed = {
            name
            for name in (set(current) | set(self._devices))
            if current.get(name) != self._devices.get(name)
        }
        self._devices = current
        for name in changed:
            self._reset_device(name)

    async def _request_block(
        self, key: tuple[int | str, int], block: RequestBlock
    ) -> None:
        now = self._clock()
        deadline = self._pending.get(key)
        if deadline is not None and now < deadline:
            return
        timeout = self._timeout()
        self._pending[key] = now + timeout
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
            if not _belongs_to_block(
                snapshot,
                block,
                known_current_page=self._known_current_page,
                fixed_pages=self._fixed_pages,
            ):
                LOGGER.debug(
                    "Playbacks-Antwort passt nicht zu %s.%s und wird verworfen",
                    block.page,
                    block.start,
                )
                continue
            self._pending.pop(key, None)
            if block.page == "current":
                self._known_current_page = snapshot.page + 1
            self._apply(snapshot, block)
            return
        self._pending.pop(key, None)
        LOGGER.debug(
            "Playbacks-Antwort für %s.%s ausgeblieben", block.page, block.start
        )

    def _apply(self, snapshot: PlaybackSnapshot, block: RequestBlock) -> None:
        feedback = self.config.feedback
        fallback = palette_index(feedback.fallback_color)
        empty_page = not snapshot.executors and bool(snapshot.seen_executors)
        for target in self._targets:
            if target.page == "current":
                if block.page != "current":
                    continue
            elif target.page != snapshot.page + 1:
                continue
            state = snapshot.executors.get(target.executor)
            if state is not None:
                velocity = led_velocity(
                    state.running, state.color, feedback.off_state, fallback
                )
            elif target.executor in snapshot.empty_executors or (
                empty_page and target.executor in snapshot.seen_executors
            ):
                velocity = MODE_BASE["off"]
            else:
                continue
            led = self._led_cache_key(target.device, target.channel, target.note)
            out_key = _outbox_key(target.channel, target.note)
            waiting = self._outbox.get(target.device)
            if self._last.get(led) == velocity:
                if waiting is not None:
                    waiting.pop(out_key, None)
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
            self._outbox.setdefault(target.device, {})[out_key] = velocity
            self._wake.set()
