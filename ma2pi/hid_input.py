"""HID device discovery and normalisation.

The module has two layers:

* a small source abstraction so tests can supply fake devices without Linux or
  ``evdev``, and
* a reader that turns raw key/axis events into :class:`InputEvent` objects.

If ``evdev`` is unavailable (for example on a development Mac), importing this
module still works; only real device access reports a clear error.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Iterable, Mapping, Protocol

from .config import AppConfig, DeviceConfig, EncoderProfile, ProfileConfig
from .events import DeviceLost, InputEvent
from .mapping import ENCODER_PREFIX, encoder_control

LOGGER = logging.getLogger("ma2pi.hid")

try:  # pragma: no cover - depends on platform
    import evdev
    from evdev import ecodes
except Exception:  # pragma: no cover - macOS/dev machines
    evdev = None
    ecodes = None


UDEV_HINT = (
    "Fehlende Leserechte. Installiere deploy/99-ma2pi.rules, lade sie mit "
    "`udevadm control --reload && udevadm trigger` und prüfe die Gruppe ma2pi."
)


class ProfileError(RuntimeError):
    """A configured profile references a control the device does not provide."""


@dataclass(frozen=True, slots=True)
class RawEvent:
    """A raw event with a human-readable code name."""

    kind: str  # "key" | "abs" | "rel"
    code: str
    value: int
    abs_min: int | None = None
    abs_max: int | None = None


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    path: str
    name: str
    vendor_id: int
    product_id: int
    key_codes: frozenset[str] = frozenset()
    abs_codes: frozenset[str] = frozenset()
    rel_codes: frozenset[str] = frozenset()
    abs_ranges: Mapping[str, tuple[int, int]] = field(default_factory=dict)
    phys: str = ""
    readable: bool = True
    error: str | None = None
    backend: str = "evdev"
    midi_notes: frozenset[int] = frozenset()

    @property
    def keyboard_score(self) -> int:
        return len(self.key_codes)

    @property
    def input_score(self) -> int:
        return len(self.key_codes) + len(self.abs_codes) + len(self.rel_codes)


class DeviceHandle(Protocol):
    async def events(self) -> AsyncIterator[RawEvent]: ...
    async def close(self) -> None: ...


class DeviceSource(Protocol):
    def list_devices(self) -> list[DeviceInfo]: ...
    async def open(self, info: DeviceInfo) -> DeviceHandle: ...


class EvdevHandle:
    def __init__(self, device: "evdev.InputDevice") -> None:
        self._device = device

    async def events(self) -> AsyncIterator[RawEvent]:
        assert ecodes is not None
        try:
            async for event in self._device.async_read_loop():
                if event.type == ecodes.EV_KEY:
                    name = _name(ecodes.KEY, event.code)
                    if name:
                        yield RawEvent("key", name, event.value)
                elif event.type == ecodes.EV_ABS:
                    name = _name(ecodes.ABS, event.code)
                    if name:
                        info = self._device.absinfo(event.code)
                        yield RawEvent("abs", name, event.value, info.min, info.max)
                elif event.type == ecodes.EV_REL:
                    name = _name(ecodes.REL, event.code)
                    if name:
                        yield RawEvent("rel", name, event.value)
        finally:
            await self.close()

    async def close(self) -> None:
        try:
            self._device.close()
        except Exception:  # pragma: no cover - defensive
            pass


class EvdevSource:
    """Real Linux source; enumerates and opens ``/dev/input/event*``."""

    def list_devices(self) -> list[DeviceInfo]:
        if evdev is None or ecodes is None:
            raise RuntimeError(
                "evdev ist nicht verfügbar. Der Daemon benötigt Linux mit "
                "python-evdev und Zugriff auf /dev/input/event*."
            )
        result: list[DeviceInfo] = []
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
            except OSError as exc:
                LOGGER.warning("Gerät %s nicht lesbar: %s. %s", path, exc, UDEV_HINT)
                result.append(
                    DeviceInfo(
                        path=path,
                        name=path,
                        vendor_id=0,
                        product_id=0,
                        readable=False,
                        error=str(exc),
                    )
                )
                continue
            try:
                info = self._describe(device)
            finally:
                device.close()
            result.append(info)
        return result

    def _describe(self, device: "evdev.InputDevice") -> DeviceInfo:
        assert ecodes is not None
        keys: set[str] = set()
        absolutes: set[str] = set()
        relatives: set[str] = set()
        ranges: dict[str, tuple[int, int]] = {}
        capabilities = device.capabilities(absinfo=True)
        for code in capabilities.get(ecodes.EV_KEY, []):
            name = _name(ecodes.KEY, code)
            if name:
                keys.add(name)
        for entry in capabilities.get(ecodes.EV_ABS, []):
            try:
                code, absinfo = entry
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue
            name = _name(ecodes.ABS, code)
            if name:
                absolutes.add(name)
                ranges[name] = (absinfo.min, absinfo.max)
        for code in capabilities.get(ecodes.EV_REL, []):
            name = _name(ecodes.REL, code)
            if name:
                relatives.add(name)
        return DeviceInfo(
            path=device.path,
            name=device.name,
            vendor_id=device.info.vendor,
            product_id=device.info.product,
            key_codes=frozenset(keys),
            abs_codes=frozenset(absolutes),
            rel_codes=frozenset(relatives),
            abs_ranges=ranges,
            phys=device.phys or "",
        )

    async def open(self, info: DeviceInfo) -> DeviceHandle:
        if evdev is None:  # pragma: no cover
            raise RuntimeError("evdev ist nicht verfügbar")
        device = evdev.InputDevice(info.path)
        return EvdevHandle(device)


def _name(table: Mapping[int, str], code: int) -> str | None:
    value = table.get(code)
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def device_matches(device: DeviceConfig, info: DeviceInfo) -> bool:
    if not info.readable:
        return False
    if device.vendor_id and info.vendor_id != device.vendor_id:
        return False
    if device.product_id and info.product_id != device.product_id:
        return False
    if device.name_contains and device.name_contains.lower() not in info.name.lower():
        return False
    return True


def select_devices(
    config: AppConfig, devices: Iterable[DeviceInfo], *, backend: str = "evdev"
) -> dict[str, DeviceInfo]:
    """Pick one interface per configured device.

    For multiple interfaces the one with the most keyboard key codes wins; ties
    are broken by total input capability and then by path for determinism.
    Devices with another backend are skipped.
    """

    pool = list(devices)
    selected: dict[str, DeviceInfo] = {}
    for name, device_config in config.devices.items():
        if device_config.backend != backend:
            continue
        candidates = [info for info in pool if device_matches(device_config, info)]
        if not candidates:
            continue
        candidates.sort(
            key=lambda info: (-info.keyboard_score, -info.input_score, info.path)
        )
        selected[name] = candidates[0]
        for ignored in candidates[1:]:
            LOGGER.info(
                "Ignoriere zusätzliches Interface %s (%s) für %s",
                ignored.path,
                ignored.name,
                name,
            )
    return selected


def validate_profile(
    name: str,
    device: DeviceConfig,
    profile: ProfileConfig,
    info: DeviceInfo,
) -> None:
    """Fail fast when a profile references controls the device lacks."""

    missing: list[str] = []
    for control in sorted(profile.keys):
        if control not in info.key_codes:
            missing.append(f"Key {control}")
    for encoder in profile.encoders:
        if encoder.control not in info.abs_codes and encoder.control not in info.rel_codes:
            missing.append(f"Encoder {encoder.id} ({encoder.control})")
    if missing:
        raise ProfileError(
            f"Profil {device.profile!r} für Gerät {name!r} ({info.name}, "
            f"{info.vendor_id:04x}:{info.product_id:04x}) referenziert nicht "
            f"unterstützte Controls: {', '.join(missing)}"
        )


class EncoderDecoder:
    """Convert raw axis values to signed detent deltas."""

    def __init__(self, profile: EncoderProfile) -> None:
        self.profile = profile
        self._last_raw: int | None = None
        self._remainder: float = 0.0

    def reset(self) -> None:
        self._last_raw = None
        self._remainder = 0.0

    def feed(self, raw: RawEvent) -> int:
        if raw.kind == "rel":
            value = abs(raw.value)
            threshold = self.profile.threshold
            if threshold and value < threshold:
                return 0
            return int(round(raw.value)) * self.profile.direction
        if raw.kind != "abs":
            return 0

        limit_min = raw.abs_min
        limit_max = raw.abs_max
        if self._last_raw is None:
            self._last_raw = raw.value
            return 0

        span = (limit_max - limit_min + 1) if limit_min is not None and limit_max is not None else 0
        delta = raw.value - self._last_raw
        self._last_raw = raw.value

        if span > 0 and abs(delta) > span / 2:
            if delta > 0:
                delta -= span
            else:
                delta += span
        if abs(delta) < self.profile.threshold:
            return 0

        if span > 0:
            units = delta * self.profile.detents_per_revolution / span
        else:
            units = float(delta)
        total = self._remainder + units
        detents = int(total)
        self._remainder = total - detents
        return detents * self.profile.direction


@dataclass
class _OpenDevice:
    info: DeviceInfo
    handle: DeviceHandle
    task: asyncio.Task[None]


class HidManager:
    """Poll, open, read and reconcile all configured devices."""

    def __init__(
        self,
        config: AppConfig,
        *,
        source: DeviceSource | None = None,
        poll_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._source = source or EvdevSource()
        self._poll_interval = poll_interval
        self._clock = clock
        self._open: dict[str, _OpenDevice] = {}
        self._missing_warned: set[str] = set()
        self._noted_devices: set[tuple[str, int, int]] = set()
        self._unknown_codes: set[tuple[str, str]] = set()
        self._decoders: dict[tuple[str, str], EncoderDecoder] = {}
        self._retry: dict[str, tuple[float, float]] = {}
        self._scan_delay = poll_interval
        self._seen_any = False
        self._lock = asyncio.Lock()
        self._stopping = False

    @property
    def open_devices(self) -> dict[str, str]:
        return {name: entry.info.path for name, entry in self._open.items()}

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
        """Back off while *nothing* was ever found, then poll quickly again."""

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
                LOGGER.error("Geräte-Enumeration fehlgeschlagen: %s", exc)
                return
            selected = select_devices(self.config, infos)
            self._note_unmatched(infos)

            for name, info in selected.items():
                current = self._open.get(name)
                if current is not None and current.info.path == info.path and not current.task.done():
                    continue
                if current is not None:
                    await self._close_device(name, queue, "Interface gewechselt")

                device = self.config.devices[name]
                profile = self.config.profiles[device.profile]
                validate_profile(name, device, profile, info)

                now = self._clock()
                retry = self._retry.get(name)
                if retry is not None and now < retry[0]:
                    continue
                try:
                    handle = await self._source.open(info)
                except PermissionError as exc:
                    self._schedule_retry(name, now, f"keine Leserechte: {exc}. {UDEV_HINT}")
                    continue
                except OSError as exc:
                    self._schedule_retry(name, now, f"Öffnen fehlgeschlagen: {exc}")
                    continue
                self._retry.pop(name, None)
                task = asyncio.create_task(
                    self._read_device(name, info, handle, queue),
                    name=f"ma2pi-hid-{name}",
                )
                self._open[name] = _OpenDevice(info, handle, task)
                self._missing_warned.discard(name)
                self._seen_any = True
                LOGGER.info(
                    "Gerät %s geöffnet: %s (%04x:%04x, %s)",
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
                if device.backend != "evdev":
                    continue
                if name in self._open or name in selected:
                    continue
                if name not in self._missing_warned:
                    self._missing_warned.add(name)
                    LOGGER.warning(
                        "Konfiguriertes Gerät %s nicht gefunden (vendor=%04x product=%04x name~%r); suche weiter",
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
            LOGGER.error("Gerät %s: %s (nächster Versuch in %.0f s)", name, message, delay)
        else:
            LOGGER.debug("Gerät %s weiterhin nicht verfügbar (nächster Versuch in %.0f s)", name, delay)

    def _note_unmatched(self, infos: Iterable[DeviceInfo]) -> None:
        known: set[str] = set()
        for device in self.config.devices.values():
            if device.backend != "evdev":
                continue
            for info in infos:
                if device_matches(device, info):
                    known.add(info.path)
        for info in infos:
            if info.path in known or not info.readable:
                continue
            key = (info.path, info.vendor_id, info.product_id)
            if key in self._noted_devices:
                continue
            self._noted_devices.add(key)
            vendor_configured = any(
                device.backend == "evdev"
                and device.vendor_id == info.vendor_id
                and (device.product_id == 0 or device.product_id == info.product_id)
                for device in self.config.devices.values()
            )
            if vendor_configured:
                LOGGER.warning(
                    "Gerät %s (%04x:%04x, %r) passt zur Vendor-ID, aber nicht zu Name/Product "
                    "eines Profils; bleibt ungeöffnet",
                    info.path,
                    info.vendor_id,
                    info.product_id,
                    info.name,
                )
            else:
                LOGGER.debug(
                    "Unbekanntes Gerät ignoriert: %s (%04x:%04x, %r)",
                    info.path,
                    info.vendor_id,
                    info.product_id,
                    info.name,
                )

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
        LOGGER.warning("Gerät %s geschlossen: %s", name, reason)

    async def _read_device(
        self,
        name: str,
        info: DeviceInfo,
        handle: DeviceHandle,
        queue: "asyncio.Queue[InputEvent | DeviceLost]",
    ) -> None:
        profile = self.config.profiles[self.config.devices[name].profile]
        try:
            async for raw in handle.events():
                event = self._normalise(name, info, profile, raw)
                if event is not None:
                    await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.error("Lesefehler für %s: %s", name, exc)
        finally:
            await handle.close()
            if not self._stopping:
                await queue.put(DeviceLost(name, "Leseschleife beendet"))

    def _normalise(
        self,
        device: str,
        info: DeviceInfo,
        profile: ProfileConfig,
        raw: RawEvent,
    ) -> InputEvent | None:
        if raw.kind == "key":
            control = profile.keys.get(raw.code)
            if control is None:
                key = (device, raw.code)
                if key not in self._unknown_codes:
                    self._unknown_codes.add(key)
                    LOGGER.debug("Unbekannter Code %s auf %s ignoriert", raw.code, device)
                return None
            if raw.value == 2:  # autorepeat
                return None
            if raw.value not in (0, 1):
                return None
            return InputEvent("key", control, raw.value, device)

        encoder: EncoderProfile | None = None
        for candidate in profile.encoders:
            if candidate.control == raw.code:
                encoder = candidate
                break
        if encoder is None:
            key = (device, raw.code)
            if key not in self._unknown_codes:
                self._unknown_codes.add(key)
                LOGGER.debug("Unbekannte Achse %s auf %s ignoriert", raw.code, device)
            return None
        decoder_key = (device, raw.code)
        decoder = self._decoders.get(decoder_key)
        if decoder is None:
            decoder = EncoderDecoder(encoder)
            self._decoders[decoder_key] = decoder
        delta = decoder.feed(raw)
        if delta == 0:
            return None
        return InputEvent("encoder", encoder_control(encoder.id), delta, device)

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


def list_devices(source: DeviceSource | None = None) -> list[DeviceInfo]:
    return (source or EvdevSource()).list_devices()


def format_devices(devices: Iterable[DeviceInfo]) -> str:
    lines = []
    for info in devices:
        readable = "" if info.readable else " [nicht lesbar]"
        lines.append(
            f"{info.path}\n"
            f"  backend:  {info.backend}\n"
            f"  name:     {info.name}{readable}\n"
            f"  vendor:   0x{info.vendor_id:04x}\n"
            f"  product:  0x{info.product_id:04x}\n"
            f"  keys:     {len(info.key_codes)}\n"
            f"  abs:      {', '.join(sorted(info.abs_codes)) or '-'}\n"
            f"  rel:      {', '.join(sorted(info.rel_codes)) or '-'}"
        )
        if info.midi_notes:
            lines.append(
                "  notes:    " + ", ".join(str(note) for note in sorted(info.midi_notes))
            )
        if info.error:
            lines.append(f"  error:    {info.error}")
    return "\n".join(lines)
