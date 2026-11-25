"""Normalised input events shared by HID, mapping and client layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EVENT_KEY = "key"
EVENT_ENCODER = "encoder"


@dataclass(frozen=True, slots=True)
class InputEvent:
    """A single normalised event from one configured HID device.

    ``kind`` is ``"key"`` or ``"encoder"``.  For keys ``value`` is 1 on press
    and 0 on release.  For encoders ``value`` is a signed detent delta.
    """

    kind: Literal["key", "encoder"]
    control: str
    value: int
    device: str = ""


@dataclass(frozen=True, slots=True)
class DeviceLost:
    """Signals that a device disappeared and its held keys must be released."""

    device: str
    reason: str = "device lost"


@dataclass(frozen=True, slots=True)
class ConnectionLost:
    """Signals that the MA2 session ended; the engine clears without replay."""

    reason: str = "connection lost"
