"""Executor feedback: poll playback state and drive controller LEDs.

Each MIDI profile picks its LED encoding with ``led_feedback.protocol``:

``midicraft-v2``
    One note-on whose velocity encodes mode and colour, as the official
    Midicraft plugin sends it and as measured on the ENC (2026-11-26):
    ``0`` off, ``1 + index`` static dark, ``17 + index`` static bright, with
    15 palette colours (index 0–14).  Flashing and complementary modes are
    not used.
``asl-mk2``
    ``9F 7F 7F`` once after opening, then per LED two note-ons: channel 1
    carries the brightness, channel 2 the device's colour index.

Colour and running state come from the Web Remote ``playbacks`` response
(``isRun``, ``bC``/``bdC``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping, Protocol

from .led_output import ENABLE as ASL_ENABLE

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .config import AppConfig, LedFeedbackProfile
    from .topology import ExecutorTopology

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
    "cto",
    "ctb",
)

#: Reference colours for matching an appearance colour; CTO stands for warm
#: white and CTB for cool white, so pure white stays white.
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
    "cto": (255, 200, 130),
    "ctb": (200, 225, 255),
}

#: Velocity base per LED mode (``midicraft-v2``).
MODE_BASE: dict[str, int] = {"off": 0, "dark": 1, "bright": 17}

#: ASL colour index per palette colour.  The index is RGB with two bits per
#: channel (``16·R + 4·G + B``, bit 6 is ignored); every entry was checked on
#: the device on 2026-11-26.
ASL_DEFAULT_COLORS: dict[str, int] = {
    "white": 127,
    "red": 48,
    "orange": 52,
    "yellow": 60,
    "yellowgreen": 44,
    "green": 12,
    "seagreen": 14,
    "cyan": 15,
    "lavender": 43,
    "blue": 3,
    "violet": 35,
    "magenta": 51,
    "pink": 59,
    "cto": 62,
    "ctb": 47,
}

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


#: What the feedback remembers per LED; compared to suppress repeats.
LedState = int | tuple[int, int]


class LedEncoder(Protocol):
    #: Sent once before the first frame after a device was (re)opened.
    preamble: bytes

    def state(
        self, running: bool, color: int | None, off_state: str, fallback: int
    ) -> LedState: ...

    def off(self) -> LedState: ...

    def frame(self, channel: int, note: int, state: LedState) -> bytes: ...


class MidicraftEncoder:
    """``midicraft-v2``: one note-on on the bank channel."""

    preamble = b""

    def state(
        self, running: bool, color: int | None, off_state: str, fallback: int
    ) -> LedState:
        return led_velocity(running, color, off_state, fallback)

    def off(self) -> LedState:
        return MODE_BASE["off"]

    def frame(self, channel: int, note: int, state: LedState) -> bytes:
        assert isinstance(state, int)
        return bytes((NOTE_ON | ((channel - 1) & 0x0F), note, state))


class AslEncoder:
    """``asl-mk2``: brightness on channel 1, colour index on channel 2."""

    preamble = ASL_ENABLE

    def __init__(self, bright: int, dark: int, colors: Mapping[str, int]) -> None:
        table = {**ASL_DEFAULT_COLORS, **colors}
        self._indices = tuple(table[name] for name in PALETTE)
        self._bright = bright
        self._dark = dark

    def state(
        self, running: bool, color: int | None, off_state: str, fallback: int
    ) -> LedState:
        index = self._indices[fallback if color is None else color]
        if running:
            return (self._bright, index)
        if off_state == "off":
            return (0, index)
        return (self._dark, index)

    def off(self) -> LedState:
        return (0, self._indices[0])

    def frame(self, channel: int, note: int, state: LedState) -> bytes:
        assert isinstance(state, tuple)
        brightness, index = state
        return bytes((NOTE_ON, note, brightness, NOTE_ON | 1, note, index))


_MIDICRAFT = MidicraftEncoder()


def encoder_for(feedback: "LedFeedbackProfile") -> LedEncoder:
    """Return the LED encoder for a profile's ``led_feedback`` table."""

    if feedback.protocol == "asl-mk2":
        return AslEncoder(
            feedback.bright_level, feedback.dark_level, dict(feedback.colors)
        )
    return _MIDICRAFT


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
    #: Leading executor -> width, for every ``combinedItems > 1`` in the answer.
    combined: Mapping[int, int] = field(default_factory=dict)

    def lead_of(self, executor: int) -> int | None:
        """Return the leading executor that covers ``executor``, if any.

        A slot is covered when a wide executor reaches over it and the answer
        has no item of its own for it.
        """

        if executor in self.seen_executors:
            return None
        for lead, width in self.combined.items():
            if lead < executor < lead + width:
                return lead
        return None


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


def _is_empty_item(item: dict[str, Any]) -> bool:
    """True for an executor slot without content.

    The onPC never sends ``isEmpty``; an unused slot arrives grey, with an
    empty title and without ``bottomButtons``.  Wide fader executors lack
    ``bottomButtons`` too, so the title decides.
    """

    if item.get("isEmpty") is True:
        return True
    title = item.get("tt")
    if isinstance(title, dict):
        title = title.get("t")
    return title == "" and "bottomButtons" not in item


def parse_playbacks(payload: dict[str, Any]) -> PlaybackSnapshot | None:
    """Turn one Web Remote ``playbacks`` response into executor states."""

    page = payload.get("iPage")
    if not isinstance(page, int):
        return None
    executors: dict[int, ExecutorState] = {}
    seen_executors: set[int] = set()
    empty_executors: set[int] = set()
    combined: dict[int, int] = {}
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
            width = item.get("combinedItems")
            if isinstance(width, int) and not isinstance(width, bool) and width > 1:
                combined[exec_num] = width
            if _is_empty_item(item):
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
        combined,
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


def response_page(page: int | str) -> int:
    """Return the ``iPage`` the console answers a request for ``page`` with.

    Measured on onPC 3.9: ``pageIndex N - 1`` (page ``N``) is answered with
    ``iPage = N``; ``pageIndex = -1`` ("current") returns the data of the active
    master page with the placeholder ``iPage = 0``.  The two ranges are disjoint,
    so one comparison separates the answers of "current" and fixed pages.
    """

    return 0 if page == "current" else int(page)


def _belongs_to_block(snapshot: PlaybackSnapshot, block: RequestBlock) -> bool:
    """Check that a response answers the given request block."""

    if snapshot.page != response_page(block.page):
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


def _encoders(config: "AppConfig") -> dict[str, LedEncoder]:
    """LED encoder per configured MIDI device with ``led_feedback``."""

    result: dict[str, LedEncoder] = {}
    for name, device in config.devices.items():
        if device.backend != "midi":
            continue
        feedback = config.profiles[device.profile].led_feedback
        if feedback is not None:
            result[name] = encoder_for(feedback)
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


def resolve_playback_target(
    config: "AppConfig", device_name: str, bank_num: int, control: str
) -> tuple[int | str, int, str] | None:
    """Return ``(page, executor, kind)`` of a control in one bank, if it has one."""

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
    return page, executor, kind


def _resolve_playback_for_bank(
    config: "AppConfig", device_name: str, bank_num: int, control: str
) -> tuple[int | str, int] | None:
    resolved = resolve_playback_target(config, device_name, bank_num, control)
    if resolved is None or resolved[2] != "button":
        return None
    return resolved[0], resolved[1]


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

    return targets, blocks_from_ranges(ranges)


@dataclass(frozen=True, slots=True)
class DarkLed:
    """An LED-capable note without a playback target; it is kept off."""

    device: str
    note: int
    channel: int = 1


def led_owned_notes(config: "AppConfig") -> set[tuple[str, int]]:
    """``(device, note)`` pairs whose LED a fixed ``[led]`` function drives."""

    led = config.led
    if not led.enabled:
        return set()
    device = led.device
    if device is None:
        midi_devices = [
            name for name, item in config.devices.items() if item.backend == "midi"
        ]
        if len(midi_devices) != 1:
            return set()
        device = midi_devices[0]
    return {(device, led.note), (device, led.fine_note), (device, led.nipple_note)}


def build_dark_leds(config: "AppConfig", targets: list[LedTarget]) -> list[DarkLed]:
    """LED notes (from ``led_notes``) of a bank that resolve to no button target.

    Without ``led_notes`` only notes with a target count as LED-capable, so
    such profiles have no dark LEDs.
    """

    lit = {(target.device, target.channel, target.note) for target in targets}
    owned = led_owned_notes(config)
    result: list[DarkLed] = []
    for name, device in config.devices.items():
        if device.backend != "midi":
            continue
        profile = config.profiles[device.profile]
        feedback = profile.led_feedback
        if feedback is None or not feedback.enabled or feedback.notes is None:
            continue
        banks = [(bank.channel, bank.notes) for bank in profile.banks] or [
            (1, profile.notes)
        ]
        seen: set[tuple[int, int]] = set()
        for channel, notes in banks:
            for note in feedback.notes:
                if (
                    note not in notes
                    or (channel, note) in seen
                    or (name, channel, note) in lit
                    or (name, note) in owned
                ):
                    continue
                seen.add((channel, note))
                result.append(DarkLed(name, note, channel))
    return result


def blocks_from_ranges(
    ranges: Mapping[tuple[int | str, int], list[int]],
) -> dict[tuple[int | str, int], RequestBlock]:
    """Cut executor numbers per ``(page, region)`` into 5-aligned request blocks."""

    blocks: dict[tuple[int | str, int], RequestBlock] = {}
    for key, executors in ranges.items():
        page, boundary = key
        lowest = min(executors) - 1
        highest = max(executors) - 1
        start = (lowest // 5) * 5
        count = (highest // 5) * 5 - start + 5
        items_type = 3 if boundary else 2
        blocks[key] = RequestBlock(page, start, count, items_type, items_type)
    return blocks


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
        topology: "ExecutorTopology | None" = None,
    ) -> None:
        from .poller import PlaybackPoller
        from .topology import ExecutorTopology

        self.config = config
        self._client = client
        self._midi = midi
        self._dry_run = dry_run
        self._clock = clock
        self._sleep = sleep
        self.topology = topology if topology is not None else ExecutorTopology()
        self._poller = PlaybackPoller(
            config,
            client,
            self.topology,
            on_answer=self._apply,
            clock=clock,
            timeout=timeout,
        )
        self._targets: list[LedTarget] = []
        self._dark: list[DarkLed] = []
        self._blocks: dict[tuple[int | str, int], RequestBlock] = {}
        self._last: dict[tuple[str, int] | tuple[str, int, int], LedState] = {}
        self._devices: dict[str, tuple[str, int]] = {}
        self._outbox: dict[str, dict[int | tuple[int, int], LedState]] = {}
        self._next_send: dict[str, float] = {}
        self._intervals: dict[str, float] = {}
        self._encoders: dict[str, LedEncoder] = {}
        self._preambled: set[str] = set()
        self._unconsumed_since: dict[str, float] = {}
        self._pending_after_send: dict[str, int] = {}
        self._stalled: set[str] = set()
        self._wake = asyncio.Event()
        self.set_config(config)

    def set_config(self, config: "AppConfig") -> None:
        """Adopt a new configuration and drop all cached LED states."""

        self.config = config
        self._targets, self._blocks = build_feedback_targets(config)
        self._dark = build_dark_leds(config, self._targets)
        self._intervals = _frame_intervals(config)
        self._encoders = _encoders(config)
        self._last.clear()
        self._poller.set_config(config, self._blocks)
        self._clear_output(clear_stalled=True)

    def reset(self) -> None:
        """Forget cached states, e.g. after a connection loss."""

        self._last.clear()
        self._poller.reset()
        self._clear_output()

    def _clear_output(self, *, clear_stalled: bool = False) -> None:
        self._outbox.clear()
        self._next_send.clear()
        self._unconsumed_since.clear()
        self._pending_after_send.clear()
        self._preambled.clear()
        if clear_stalled:
            self._stalled.clear()

    def resend_device(self, device: str) -> None:
        """Send the full LED state of one device again on the next poll."""

        self._reset_device(device)

    def _reset_device(self, device: str) -> None:
        for key in [k for k in self._last if k[0] == device]:
            self._last.pop(key, None)
        self._outbox.pop(device, None)
        self._next_send.pop(device, None)
        self._unconsumed_since.pop(device, None)
        self._pending_after_send.pop(device, None)
        self._preambled.discard(device)
        self._stalled.discard(device)

    @property
    def targets(self) -> tuple[LedTarget, ...]:
        return tuple(self._targets)

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
                try:
                    await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - defensive
                    LOGGER.exception("Executor-Feedback-Zyklus fehlgeschlagen")
                await self._sleep(self._poller.interval())
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
            raw_key, state = next(iter(outbox.items()))
            channel, note = _unpack_outbox_key(raw_key)
            encoder = self._encoders.get(device, _MIDICRAFT)
            payload = encoder.frame(channel, note, state)
            if encoder.preamble and device not in self._preambled:
                payload = encoder.preamble + payload
            interval = self._intervals.get(device, _DEFAULT_FRAME_INTERVAL)
            if self._midi.send(device, payload):
                del outbox[raw_key]
                self._preambled.add(device)
                self._last[self._led_cache_key(device, channel, note)] = state
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
        """Run one poll cycle: request open blocks and apply answers.

        The poller also serves the executor topology, so a cycle can run with
        LED feedback off; the LED-only parts then stay idle.
        """

        if not getattr(self._client, "authenticated", False):
            return
        led_active = self.config.feedback.enabled and bool(self._targets or self._dark)
        if led_active:
            self._sync_devices()
            self._queue_dark()
        await self._poller.step()
        if led_active:
            self.pump()

    def _queue_dark(self) -> None:
        """Queue the off state for LEDs without a target that is not shown yet."""

        for led in self._dark:
            if led.device not in self._devices:
                continue
            encoder = self._encoders.get(led.device, _MIDICRAFT)
            state = encoder.off()
            key = self._led_cache_key(led.device, led.channel, led.note)
            if self._last.get(key) == state:
                continue
            if self._dry_run:
                LOGGER.info(
                    "dry-run: LED ohne Ziel %s Note %d Frame %s",
                    led.device,
                    led.note,
                    encoder.frame(led.channel, led.note, state).hex(" "),
                )
                self._last[key] = state
                continue
            self._outbox.setdefault(led.device, {})[
                _outbox_key(led.channel, led.note)
            ] = state
            self._wake.set()

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

    def _apply(self, snapshot: PlaybackSnapshot, block: RequestBlock) -> None:
        feedback = self.config.feedback
        fallback = palette_index(feedback.fallback_color)
        empty_page = not snapshot.executors and bool(snapshot.seen_executors)
        mirror = self.config.mapping.combined_executors != "off"
        for target in self._targets:
            if snapshot.page != response_page(target.page):
                continue
            encoder = self._encoders.get(target.device, _MIDICRAFT)
            executor = snapshot.executors.get(target.executor)
            if executor is None and mirror:
                lead = snapshot.lead_of(target.executor)
                if lead is not None:
                    executor = snapshot.executors.get(lead)
            if executor is not None:
                state = encoder.state(
                    executor.running, executor.color, feedback.off_state, fallback
                )
            elif target.executor in snapshot.empty_executors or (
                empty_page and target.executor in snapshot.seen_executors
            ):
                state = encoder.off()
            else:
                continue
            led = self._led_cache_key(target.device, target.channel, target.note)
            out_key = _outbox_key(target.channel, target.note)
            waiting = self._outbox.get(target.device)
            if self._last.get(led) == state:
                if waiting is not None:
                    waiting.pop(out_key, None)
                continue
            if self._dry_run:
                LOGGER.info(
                    "dry-run: LED %s Note %d Frame %s",
                    target.control,
                    target.note,
                    encoder.frame(target.channel, target.note, state).hex(" "),
                )
                self._last[led] = state
                continue
            self._outbox.setdefault(target.device, {})[out_key] = state
            self._wake.set()
