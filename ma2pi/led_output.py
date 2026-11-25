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

The port is kept open for the daemon lifetime: opening and closing the raw
MIDI port repeatedly resets the LED state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

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


class LedOutput:
    """Writes LED frames to one ASL button over a persistent MIDI handle."""

    def __init__(self, path: str | Path, settings: LedSettings) -> None:
        self.path = Path(path)
        self.settings = settings
        self._fd: int | None = None

    @property
    def is_open(self) -> bool:
        return self._fd is not None

    def open(self) -> None:
        if self._fd is not None:
            return
        self._fd = os.open(self.path, os.O_WRONLY)
        LOGGER.debug("LED-Ausgabe geöffnet: %s", self.path)

    def close(self) -> None:
        if self._fd is None:
            return
        try:
            self._write(DISABLE)
        finally:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def _write(self, payload: bytes) -> None:
        if self._fd is None:
            return
        try:
            os.write(self._fd, payload)
        except OSError as exc:
            LOGGER.warning("LED-Frame konnte nicht gesendet werden: %s", exc)

    def enable(self) -> None:
        """Switch the buttons into MIDI LED mode."""
        self._write(ENABLE)

    def set_color(self, index: int) -> None:
        """Set brightness and colour index in one write; no release frame.

        Sending ``9F 7F 7E`` here would hand the LEDs back to keypress mode
        and the colour would never show.
        """
        note = self.settings.note
        self._write(
            ENABLE
            + note_on(self.settings.brightness_channel, note, self.settings.brightness)
            + note_on(self.settings.color_channel, note, index)
        )

    def apply_mode(self, screen_mode: bool) -> None:
        self.set_color(
            self.settings.screen_color if screen_mode else self.settings.attribute_color
        )