"""LED output for the ASL MK2-E4B3 over raw ALSA MIDI.

Protocol verified live on the device (2026-11-25), starting from a ShowCockpit
capture (MIDI-OX):

* ``9F 7F 7F`` – Note On, channel 16, note 127, velocity 127: switches the
  buttons from "react to keypress" into "react to MIDI" LED mode.
* Per LED, two Note On messages with the LED note number as note:
  channel 1 velocity = brightness (0…127), channel 2 velocity = colour index.
  Verified indices: 8 = green, 48 = red, 127 = white.
* ``9F 7F 7E`` – releases LED control; the buttons return to keypress mode.
  It MUST NOT be sent after colour updates, only when closing the port.

In the daemon, ``LedOutput`` sends through ``MidiManager.send`` so a single
non-blocking rawmidi descriptor serves both input and LED output without
competing for the ALSA output substream.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LOGGER = logging.getLogger("ma2pi.led")

#: Switches the buttons into MIDI LED mode.
ENABLE = bytes([0x9F, 0x7F, 0x7F])
#: Releases LED control (keypress mode again).  Only sent on close.
DISABLE = bytes([0x9F, 0x7F, 0x7E])

CHANNEL_BASE = 0x90
#: Colour indices verified on the device.  Other indices are untested.
COLOR_INDICES: dict[str, int] = {
    "green": 8,
    "red": 48,
    "white": 127,
}


def parse_color(value: object) -> int:
    """Accept a colour name or a raw colour index (0…127)."""
    if isinstance(value, str):
        try:
            return COLOR_INDICES[value.lower()]
        except KeyError as exc:
            raise ValueError(
                f"unbekannte Farbe {value!r} (erlaubt: {', '.join(sorted(COLOR_INDICES))})"
            ) from exc
    if isinstance(value, int) and not isinstance(value, bool):
        if not 0 <= value <= 127:
            raise ValueError("Farbindex muss zwischen 0 und 127 liegen")
        return value
    raise ValueError("Farbe muss ein Name oder ein Index (0…127) sein")


def note_on(channel: int, note: int, velocity: int) -> bytes:
    return bytes([CHANNEL_BASE | ((channel - 1) & 0x0F), note & 0x7F, velocity & 0x7F])


@dataclass(frozen=True, slots=True)
class LedSettings:
    enabled: bool = False
    device: str | None = None
    note: int = 9
    attribute_color: int = 48  # red
    screen_color: int = 8  # green
    brightness: int = 127
    brightness_channel: int = 1
    color_channel: int = 2
    nipple_note: int = 11
    nipple_idle_color: int = 121
    nipple_idle_brightness: int = 25
    nipple_pressed_color: int = 116
    nipple_pressed_brightness: int = 127
    fine_note: int = 10
    fine_color: int = 123
    fine_idle_brightness: int = 25
    fine_pressed_brightness: int = 127


class LedOutput:
    """Writes LED frames to ASL buttons via ``MidiManager`` or a non-blocking fd."""

    def __init__(
        self,
        path: str | Path,
        settings: LedSettings,
        *,
        sender: Callable[[bytes], bool] | None = None,
    ) -> None:
        self.path = Path(path)
        self.settings = settings
        self.device_name = settings.device or "asl"
        self._sender = sender
        self._active = False
        self._fd: int | None = None
        self.on_write: Callable[[str], None] | None = None

    @property
    def is_open(self) -> bool:
        return self._active if self._sender is not None else self._fd is not None

    def still_attached(self) -> bool:
        """True when the open handle still refers to the current device node."""
        if self._sender is not None:
            return self._active and self.path.exists()
        if self._fd is None:
            return False
        try:
            cur = os.stat(self.path)
            old = os.fstat(self._fd)
        except OSError:
            return False
        return (cur.st_dev, cur.st_ino) == (old.st_dev, old.st_ino)

    def open(self) -> None:
        if self._sender is not None:
            self._active = True
            LOGGER.debug("LED-Ausgabe über MidiManager verbunden: %s", self.path)
            return
        if self._fd is not None:
            return
        self._fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        LOGGER.debug("LED-Ausgabe geöffnet: %s", self.path)

    def close(self) -> None:
        if self._sender is not None:
            if not self._active:
                return
            try:
                self._write(DISABLE, "disable")
            finally:
                self._active = False
            return
        if self._fd is None:
            return
        try:
            self._write(DISABLE, "disable")
        finally:
            try:
                import time as _time
                from .midi_input import rawmidi_drop_output, rawmidi_output_free

                size = rawmidi_output_free(self._fd)
                if size is not None:
                    # Wait briefly if we can probe free space; if unconsumed, drop.
                    _time.sleep(0.005)
                    after = rawmidi_output_free(self._fd)
                    if after is not None and after < size:
                        try:
                            rawmidi_drop_output(self._fd)
                        except OSError:
                            pass
                os.close(self._fd)
            finally:
                self._fd = None

    def _write(self, payload: bytes, label: str = "led") -> None:
        if self._sender is not None:
            if not self._active:
                return
            if not self._sender(payload):
                LOGGER.debug("LED-Frame (%s) an %s nicht gesendet", label, self.path)
                return
        else:
            if self._fd is None:
                return
            try:
                os.write(self._fd, payload)
            except OSError as exc:
                LOGGER.warning("LED-Frame konnte nicht gesendet werden: %s", exc)
                return
        if self.on_write is not None:
            try:
                self.on_write(label)
            except Exception:  # pragma: no cover - a hook must not break output
                LOGGER.debug("LED-Hook fehlgeschlagen", exc_info=True)

    def enable(self) -> None:
        """Switch the buttons into MIDI LED mode."""
        self._write(ENABLE, "enable")

    def set_color(self, index: int) -> None:
        """Set brightness and colour index in one write; no release frame."""
        note = self.settings.note
        self._write(
            ENABLE
            + note_on(self.settings.brightness_channel, note, self.settings.brightness)
            + note_on(self.settings.color_channel, note, index),
            "color",
        )

    def set_button(self, note: int, color: int, brightness: int) -> None:
        """Set one button LED independently of the mode LED."""

        self._write(
            ENABLE
            + note_on(self.settings.brightness_channel, note, brightness)
            + note_on(self.settings.color_channel, note, color),
            "button",
        )

    def set_nipple(self, pressed: bool) -> None:
        cfg = self.settings
        if pressed:
            self.set_button(cfg.nipple_note, cfg.nipple_pressed_color, cfg.nipple_pressed_brightness)
        else:
            self.set_button(cfg.nipple_note, cfg.nipple_idle_color, cfg.nipple_idle_brightness)

    def set_fine(self, pressed: bool) -> None:
        cfg = self.settings
        brightness = cfg.fine_pressed_brightness if pressed else cfg.fine_idle_brightness
        self.set_button(cfg.fine_note, cfg.fine_color, brightness)

    def set_mode_color(self, screen_mode: bool) -> None:
        """Colour the mode LED green (screen) or red (attribute)."""

        self.set_color(
            self.settings.screen_color if screen_mode else self.settings.attribute_color
        )

    def apply_mode(self, screen_mode: bool) -> None:
        self.set_mode_color(screen_mode)
        self.set_nipple(False)
        self.set_fine(False)
