"""ALSA raw-MIDI input for the ASL MK2 E4B3 encoder panel.

The ASL identifies itself as a USB-MIDI device (``04d8:e817``) and exposes a
raw MIDI node such as ``/dev/snd/midiC3D0``.  It is not an evdev device, so the
encoder and button events are read from the MIDI byte stream and normalised to
the same :class:`~ma2pi.events.InputEvent` objects the mapping engine already
consumes.

The parser is deliberately small: it understands note-on/note-off messages and
ignores everything else.

Hardware capture (2026-11-25) showed this layout:

* notes 1-4: encoders 1-4, one note-on per detent, velocity ``127`` for
  clockwise and velocity ``1`` for counter-clockwise,
* notes 5-8: the encoder push buttons (note-on ``127``, release velocity ``0``),
* notes 9-11: the three standalone buttons (note-on ``127``, release velocity
  ``0``; velocity ``1`` is also accepted as a release).

Because the encoder notes encode direction in the velocity, a note-on with
velocity 1 on those notes is *not* a release.  Notes and encoder notes are
disjoint and validated by the config loader, so the two interpretations cannot
collide.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import AsyncIterator, Callable, Iterable, Protocol

from .config import AppConfig, DeviceConfig, ProfileConfig
from .events import EVENT_VALUE, DeviceLost, InputEvent
from .hid_input import DeviceInfo, ProfileError, RawEvent, device_matches
from .mapping import encoder_control

LOGGER = logging.getLogger("ma2pi.midi")

MIDI_HINT = (
    "Fehlende Leserechte auf dem MIDI-Gerät. Füge den Dienstbenutzer der "
    "Gruppe audio hinzu oder installiere deploy/99-ma2pi.rules."
)

_CARD_RE = re.compile(r"^\s*(\d+)\s+\[([^\]]+)\]:\s*(.*)$")


class MidiStreamParser:
    """Incremental 3-byte MIDI parser for note messages."""

    def __init__(self) -> None:
        self._status: int | None = None
        self._data: list[int] = []

    def feed(self, data: bytes) -> list[RawEvent]:
        events: list[RawEvent] = []
        for byte in data:
            if byte >= 0xF8:  # realtime messages may appear between data bytes
                continue
            if byte & 0x80:
                if byte >= 0xF0:  # system common: not used by the ASL
                    self._status = None
                    self._data.clear()
                    continue
                self._status = byte
                self._data.clear()
                continue
            if self._status is None:
                continue
            self._data.append(byte)
            kind = self._status & 0xF0
            needed = 1 if kind in (0xC0, 0xD0) else 2
            if len(self._data) >= needed:
                self._emit(self._status, self._data[:needed], events)
                self._data.clear()
        return events

    @staticmethod
    def _emit(status: int, data: list[int], events: list[RawEvent]) -> None:
        kind = status & 0xF0
        channel = (status & 0x0F) + 1
        if kind == 0x90:
            note, velocity = data
            # Keep the message type from the status byte.  A note-on with
            # velocity 0 is conventionally a release, but absolute values use
            # velocity 0 as their real zero position and must not be dropped.
            events.append(RawEvent("note_on", str(note), velocity, channel=channel))
        elif kind == 0x80:
            note, velocity = data
            events.append(RawEvent("note_off", str(note), velocity, channel=channel))
        elif kind == 0xB0:
            controller, value = data
            events.append(RawEvent("cc", str(controller), value, channel=channel))


class MidiHandle(Protocol):
    async def events(self) -> AsyncIterator[RawEvent]: ...
    async def close(self) -> None: ...


class MidiSource(Protocol):
    def list_devices(self) -> list[DeviceInfo]: ...
    async def open(self, info: DeviceInfo) -> MidiHandle: ...


def _usb_ids(card: int) -> tuple[int, int]:
    uevent = Path(f"/sys/class/sound/card{card}/device/uevent")
    try:
        text = uevent.read_text(encoding="utf-8")
    except OSError:
        return 0, 0
    for line in text.splitlines():
        if line.startswith("PRODUCT="):
            parts = line.split("=", 1)[1].split("/")
            if len(parts) >= 2:
                try:
                    return int(parts[0], 16), int(parts[1], 16)
                except ValueError:
                    return 0, 0
    return 0, 0


def list_midi_devices() -> list[DeviceInfo]:
    """Enumerate raw MIDI nodes and attach USB IDs from sysfs when possible."""

    cards = Path("/proc/asound/cards")
    try:
        lines = cards.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    result: list[DeviceInfo] = []
    for line in lines:
        match = _CARD_RE.match(line)
        if match is None:
            continue
        card = int(match.group(1))
        card_id = match.group(2).strip()
        rest = match.group(3).strip()
        name = rest.split(" - ", 1)[-1].strip() if " - " in rest else card_id
        vendor, product = _usb_ids(card)
        for path in sorted(Path("/dev/snd").glob(f"midiC{card}D*")):
            readable = os.access(path, os.R_OK)
            result.append(
                DeviceInfo(
                    path=str(path),
                    name=name,
                    vendor_id=vendor,
                    product_id=product,
                    readable=readable,
                    error=None if readable else "keine Leserechte",
                    backend="midi",
                )
            )
    return result


class RealMidiHandle:
    """Read and write a raw ALSA MIDI character device with ``add_reader``."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._writable = True
        try:
            self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            LOGGER.debug(
                "MIDI-Gerät %s lässt sich nicht duplex öffnen (%s); "
                "Ausgabe deaktiviert",
                path,
                exc,
            )
            self._writable = False
            self._fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self._queue: asyncio.Queue[RawEvent | BaseException | None] = asyncio.Queue()
        self._parser = MidiStreamParser()
        self._loop = asyncio.get_running_loop()
        self._loop.add_reader(self._fd, self._on_readable)
        self._closed = False
        self._write_warned = False

    def _on_readable(self) -> None:
        try:
            data = os.read(self._fd, 4096)
        except BlockingIOError:
            return
        except OSError as exc:
            self._queue.put_nowait(exc)
            return
        if not data:
            self._queue.put_nowait(None)
            return
        for event in self._parser.feed(data):
            self._queue.put_nowait(event)

    def write(self, data: bytes) -> bool:
        """Send one MIDI message; never blocks the loop and never raises."""

        if self._closed:
            return False
        if not self._writable:
            if not self._write_warned:
                self._write_warned = True
                LOGGER.warning(
                    "MIDI-Ausgabe an %s nicht möglich: Gerät ist nur lesbar geöffnet",
                    self._path,
                )
            return False
        try:
            os.write(self._fd, data)
            return True
        except BlockingIOError:
            return False
        except OSError as exc:
            if not self._write_warned:
                self._write_warned = True
                LOGGER.warning("MIDI-Ausgabe an %s fehlgeschlagen: %s", self._path, exc)
            return False

    async def events(self) -> AsyncIterator[RawEvent]:
        try:
            while True:
                item = await self._queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._loop.remove_reader(self._fd)
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            os.close(self._fd)
        except OSError:  # pragma: no cover - defensive
            pass


class AlsaMidiSource:
    def list_devices(self) -> list[DeviceInfo]:
        return list_midi_devices()

    async def open(self, info: DeviceInfo) -> MidiHandle:
        return RealMidiHandle(info.path)


def select_midi_devices(
    config: AppConfig, devices: Iterable[DeviceInfo]
) -> dict[str, DeviceInfo]:
    pool = list(devices)
    selected: dict[str, DeviceInfo] = {}
    for name, device_config in config.devices.items():
        if device_config.backend != "midi":
            continue
        candidates = [info for info in pool if device_matches(device_config, info)]
        if not candidates:
            continue
        candidates.sort(key=lambda info: info.path)
        selected[name] = candidates[0]
        for ignored in candidates[1:]:
            LOGGER.info(
                "Ignoriere zusätzliches MIDI-Interface %s (%s) für %s",
                ignored.path,
                ignored.name,
                name,
            )
    return selected


def validate_midi_profile(
    name: str,
    device: DeviceConfig,
    profile: ProfileConfig,
    info: DeviceInfo,
) -> None:
    if (
        not profile.notes
        and not profile.midi_encoders
        and not profile.midi_values
        and not profile.controls
        and not profile.banks
    ):
        raise ProfileError(
            f"Profil {device.profile!r} für MIDI-Gerät {name!r} ({info.name}, "
            f"{info.vendor_id:04x}:{info.product_id:04x}) enthält keine "
            "MIDI-Noten, MIDI-Encoder oder absoluten Werte"
        )


class _OpenMidi:
    def __init__(self, info: DeviceInfo, handle: MidiHandle, task: asyncio.Task[None]) -> None:
        self.info = info
        self.handle = handle
        self.task = task


class MidiManager:
    """Poll, open, read and reconcile configured raw-MIDI devices."""

    def __init__(
        self,
        config: AppConfig,
        *,
        source: MidiSource | None = None,
        poll_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._source = source or AlsaMidiSource()
        self._poll_interval = poll_interval
        self._clock = clock
        self._open: dict[str, _OpenMidi] = {}
        self._missing_warned: set[str] = set()
        self._unknown_notes: set[tuple[str, int]] = set()
        self._unknown_channels: set[tuple[str, int]] = set()
        self._raw_hook: Callable[[str, RawEvent], bool] | None = None
        self._retry: dict[str, tuple[float, float]] = {}
        self._scan_delay = poll_interval
        self._seen_any = False
        self._lock = asyncio.Lock()
        self._stopping = False

    @property
    def open_devices(self) -> dict[str, str]:
        return {name: entry.info.path for name, entry in self._open.items()}

    def set_config(self, config: AppConfig) -> None:
        """Adopt an applied configuration; readers look profiles up per event."""

        self.config = config
        self._unknown_notes.clear()
        self._unknown_channels.clear()
        self._missing_warned.clear()

    def set_raw_hook(self, hook: Callable[[str, RawEvent], bool] | None) -> None:
        """Tap raw events before normalisation; ``True`` consumes the event."""

        self._raw_hook = hook

    def send(self, device: str, data: bytes) -> bool:
        """Write raw MIDI bytes to an open configured device.

        Returns ``False`` when the device is unknown, not open or does not
        accept writes; callers can retry on the next cycle.
        """

        entry = self._open.get(device)
        if entry is None:
            return False
        write = getattr(entry.handle, "write", None)
        if write is None:
            return False
        return bool(write(data))

    async def run(self, queue: "asyncio.Queue[InputEvent | DeviceLost]") -> None:
        try:
            while not self._stopping:
                await self.reconcile(queue)
                await asyncio.sleep(self._next_delay())
        except asyncio.CancelledError:
            raise
        finally:
            await self.close()

    def _next_delay(self) -> float:
        if self._open or self._seen_any:
            self._scan_delay = self._poll_interval
        else:
            cap = max(self._poll_interval, 5.0)
            self._scan_delay = min(self._scan_delay * 2, cap)
        return self._scan_delay

    async def reconcile(self, queue: "asyncio.Queue[InputEvent | DeviceLost]") -> None:
        async with self._lock:
            try:
                infos = self._source.list_devices()
            except Exception as exc:
                LOGGER.error("MIDI-Enumeration fehlgeschlagen: %s", exc)
                return
            selected = select_midi_devices(self.config, infos)

            for name, info in selected.items():
                current = self._open.get(name)
                if (
                    current is not None
                    and current.info.path == info.path
                    and not current.task.done()
                ):
                    continue
                if current is not None:
                    await self._close_device(name, queue, "Interface gewechselt")

                device = self.config.devices[name]
                profile = self.config.profiles[device.profile]
                validate_midi_profile(name, device, profile, info)

                now = self._clock()
                retry = self._retry.get(name)
                if retry is not None and now < retry[0]:
                    continue
                try:
                    handle = await self._source.open(info)
                except PermissionError as exc:
                    self._schedule_retry(name, now, f"keine Leserechte: {exc}. {MIDI_HINT}")
                    continue
                except OSError as exc:
                    self._schedule_retry(name, now, f"Öffnen fehlgeschlagen: {exc}")
                    continue
                self._retry.pop(name, None)
                task = asyncio.create_task(
                    self._read_device(name, info, handle, queue),
                    name=f"ma2pi-midi-{name}",
                )
                self._open[name] = _OpenMidi(info, handle, task)
                self._missing_warned.discard(name)
                self._seen_any = True
                LOGGER.info(
                    "MIDI-Gerät %s geöffnet: %s (%04x:%04x, %s)",
                    name,
                    info.name,
                    info.vendor_id,
                    info.product_id,
                    info.path,
                )

            for name in list(self._open):
                if name not in selected:
                    await self._close_device(name, queue, "Gerät nicht mehr vorhanden")

            for name, device in self.config.devices.items():
                if device.backend != "midi":
                    continue
                if name in self._open or name in selected:
                    continue
                if name not in self._missing_warned:
                    self._missing_warned.add(name)
                    LOGGER.warning(
                        "Konfiguriertes MIDI-Gerät %s nicht gefunden "
                        "(vendor=%04x product=%04x name~%r); suche weiter",
                        name,
                        device.vendor_id,
                        device.product_id,
                        device.name_contains,
                    )

    def _schedule_retry(self, name: str, now: float, message: str) -> None:
        previous = self._retry.get(name)
        delay = 1.0 if previous is None else min(60.0, previous[1] * 2.0)
        self._retry[name] = (now + delay, delay)
        if previous is None:
            LOGGER.error("MIDI-Gerät %s: %s (nächster Versuch in %.0f s)", name, message, delay)
        else:
            LOGGER.debug("MIDI-Gerät %s weiterhin nicht verfügbar (nächster Versuch in %.0f s)", name, delay)

    async def _close_device(
        self,
        name: str,
        queue: "asyncio.Queue[InputEvent | DeviceLost]",
        reason: str,
    ) -> None:
        entry = self._open.pop(name, None)
        if entry is None:
            return
        entry.task.cancel()
        try:
            await entry.task
        except (asyncio.CancelledError, Exception):
            pass
        await entry.handle.close()
        LOGGER.warning("MIDI-Gerät %s geschlossen: %s", name, reason)

    async def _read_device(
        self,
        name: str,
        info: DeviceInfo,
        handle: MidiHandle,
        queue: "asyncio.Queue[InputEvent | DeviceLost]",
    ) -> None:
        try:
            async for raw in handle.events():
                if self._raw_hook is not None and self._raw_hook(name, raw):
                    continue
                device = self.config.devices.get(name)
                profile = (
                    self.config.profiles.get(device.profile)
                    if device is not None
                    else None
                )
                if profile is None:
                    continue
                event = self._normalise(name, profile, raw)
                if event is not None:
                    await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.error("MIDI-Lesefehler für %s: %s", name, exc)
        finally:
            await handle.close()
            if not self._stopping:
                await queue.put(DeviceLost(name, "MIDI-Leseschleife beendet"))

    def _normalise(
        self,
        device: str,
        profile: ProfileConfig,
        raw: RawEvent,
    ) -> InputEvent | None:
        if raw.kind not in ("note_on", "note_off"):
            return None
        try:
            note = int(raw.code)
        except ValueError:
            return None

        if profile.banks:
            bank = profile.bank_for_channel(raw.channel)
            if bank is None:
                key = (device, raw.channel)
                if key not in self._unknown_channels:
                    self._unknown_channels.add(key)
                    LOGGER.debug(
                        "Unbekannter MIDI-Kanal %d auf %s ignoriert",
                        raw.channel,
                        device,
                    )
                return None
            control = bank.notes.get(note)
            if control is None:
                self._log_unknown_note(device, note)
                return None
            kind = profile.control_kinds.get(control, "button")
            return self._control_event(
                kind, control, raw, device, bank.number, note
            )

        pressed = raw.kind == "note_on" and raw.value >= 2

        control = profile.notes.get(note)
        if control is not None:
            return InputEvent(
                "key", control, 1 if pressed else 0, device, note=note
            )

        # An encoder note carries the direction in the velocity.  Every
        # note-on is exactly one detent; the matching release is ignored.
        if raw.kind == "note_on":
            for encoder in profile.midi_encoders:
                if note != encoder.note:
                    continue
                if raw.value == encoder.cw_velocity:
                    delta = encoder.direction
                elif raw.value == encoder.ccw_velocity:
                    delta = -encoder.direction
                else:
                    return None
                return InputEvent(
                    "encoder", encoder_control(encoder.id), delta, device, note=note
                )

        # Absolute controls (faders and absolute encoders) carry the position
        # in the Note-On velocity.  Note-Off only terminates the message and
        # must not produce a key release.
        for value_control in profile.midi_values:
            if note != value_control.note:
                continue
            if raw.kind == "note_off":
                return None
            return InputEvent(
                EVENT_VALUE,
                value_control.control,
                raw.value / 127.0,
                device,
                note=note,
            )

        self._log_unknown_note(device, note)
        return None

    def _log_unknown_note(self, device: str, note: int) -> None:
        key = (device, note)
        if key not in self._unknown_notes:
            self._unknown_notes.add(key)
            LOGGER.debug("Unbekannte MIDI-Note %d auf %s ignoriert", note, device)

    @staticmethod
    def _control_event(
        kind: str,
        control: str,
        raw: RawEvent,
        device: str,
        bank: int,
        note: int,
    ) -> InputEvent | None:
        if kind == "button":
            pressed = raw.kind == "note_on" and raw.value >= 2
            return InputEvent(
                "key", control, 1 if pressed else 0, device, bank, note
            )
        if kind == "relative-encoder":
            if raw.kind != "note_on":
                return None
            if raw.value >= 64:
                delta = 1
            elif raw.value >= 1:
                delta = -1
            else:
                return None
            return InputEvent("encoder", control, delta, device, bank, note)
        if raw.kind == "note_off":
            return None
        return InputEvent(
            EVENT_VALUE, control, raw.value / 127.0, device, bank, note
        )

    async def close(self) -> None:
        self._stopping = True
        async with self._lock:
            for name in list(self._open):
                entry = self._open.pop(name)
                entry.task.cancel()
                try:
                    await entry.task
                except (asyncio.CancelledError, Exception):
                    pass
                await entry.handle.close()
