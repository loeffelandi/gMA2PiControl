"""Normalised input events shared by HID, mapping and client layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EVENT_KEY = "key"
EVENT_ENCODER = "encoder"
EVENT_VALUE = "value"


@dataclass(frozen=True, slots=True)
class InputEvent:
    """A single normalised event from one configured HID device.

    ``kind`` is ``"key"``, ``"encoder"`` or ``"value"``.  For keys ``value`` is
    1 on press and 0 on release.  For encoders ``value`` is a signed detent
    delta.  For absolute values ``value`` is a float between 0.0 and 1.0.
    """

    kind: Literal["key", "encoder", "value"]
    control: str
    value: float
    device: str = ""
    bank: int = 1
    note: int | None = field(default=None, compare=False)


def format_input(event: InputEvent) -> str:
    """One-line form used by ``--dump-input`` including bank and MIDI note."""

    parts = [
        event.kind,
        event.control,
        f"value={event.value:g}",
        f"device={event.device}",
        f"bank={event.bank}",
    ]
    if event.note is not None:
        parts.append(f"note={event.note}")
    return " ".join(parts)


@dataclass(frozen=True, slots=True)
class DeviceLost:
    """Signals that a device disappeared and its held keys must be released."""

    device: str
    reason: str = "device lost"


@dataclass(frozen=True, slots=True)
class ConnectionLost:
    """Signals that the MA2 session ended; the engine clears without replay."""

    reason: str = "connection lost"
