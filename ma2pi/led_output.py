"""RGB LED output for the ASL MK2-E4B3 over raw ALSA MIDI.

Protocol observed from a ShowCockpit capture (MIDI-OX, 2026-11-25):

* ``9F 7F 7F`` – Note On, channel 16, note 127, velocity 127: enables LED
  control and clears all LEDs.  Without this frame the device ignores every
  colour update and keeps its power-on red.
* Per LED, one Note On per colour channel with the LED note number as note and
  the intensity as velocity: channel 1 = red, channel 2 = green,
  channel 3 = blue.
* ``9F 7F 7E`` – releases LED control again.

The port is kept open for the daemon lifetime: the device resets its LED state
when the raw MIDI port is opened and closed repeatedly.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("ma2pi.led")

ENABLE = bytes([0x9F, 0x7F, 0x7F])
DISABLE = bytes([0x9F, 0x7F, 0x7E])

CHANNEL_BASE = 0x90
COLOR_NAMES: dict[str, tuple[int, int, int]] = {
    "off": (0, 0, 0),
    "red": (127, 0, 0),
    "green": (0, 127, 0),
    "blue": (0, 0, 127),
    "amber": (127, 48, 0),
    "yellow": (127, 127, 0),
    "white": (127, 127, 127),
}


def parse_color(value: object) -> tuple[int, int, int]:
    """Accept a colour name or an ``[r, g, b]`` triple (0…127)."""
    if isinstance(value, str):
        try:
            return COLOR_NAMES[value.lower()]
        except KeyError as exc:
            raise ValueError(
                f"unbekannte Farbe {value!r} (erlaubt: {', '.join(sorted(COLOR_NAMES))})"
            ) from exc
    if isinstance(value, (list, tuple)) and len(value) == 3:
        rgb = tuple(int(part) for part in value)
        if any(not 0 <= part <= 127 for part in rgb):
            raise ValueError("RGB-Werte müssen zwischen 0 und 127 liegen")
        return rgb  # type: ignore[return-value]
    raise ValueError("Farbe muss ein Name oder [r, g, b] sein")


def note_on(channel: int, note: int, velocity: int) -> bytes:
    return bytes([CHANNEL_BASE | ((channel - 1) & 0x0F), note & 0x7F, velocity & 0x7F])


@dataclass(frozen=True, slots=True)
class LedSettings:
    enabled: bool = False
    device: str | None = None
    note: int = 9
    attribute_color: tuple[int, int, int] = (127, 0, 0)
    screen_color: tuple[int, int, int] = (0, 127, 0)
    red_channel: int = 1
    green_channel: int = 2
    blue_channel: int = 3


class LedOutput:
    """Writes RGB LED frames to one ASL button over a persistent MIDI handle."""

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
        """Take over the LEDs and clear them."""
        self._write(ENABLE)

    def set_color(self, rgb: tuple[int, int, int]) -> None:
        note = self.settings.note
        red, green, blue = rgb
        self._write(
            note_on(self.settings.red_channel, note, red)
            + note_on(self.settings.green_channel, note, green)
            + note_on(self.settings.blue_channel, note, blue)
        )

    def apply_mode(self, screen_mode: bool) -> None:
        self.set_color(
            self.settings.screen_color if screen_mode else self.settings.attribute_color
        )
