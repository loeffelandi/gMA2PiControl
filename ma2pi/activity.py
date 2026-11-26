"""Per-device input/output activity for the status page.

The tracker is deliberately small: counters, timestamps and a bounded ring of
log entries. Hooks call ``record_rx``/``record_tx`` from the event loop and from
MIDI threads, so every mutation happens under one lock and never awaits.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Callable

from .events import InputEvent

MAX_LOG = 100
MAX_PENDING = 500
MAX_FLUSH = 100
MAX_SUMMARY = 120
DIRECTIONS = ("rx", "tx")
# Recurring polling frames are counted but never written to the log; they would
# push real input out of the ring within about two minutes.
QUIET_FRAME_KINDS = frozenset({"playbacksRequest"})


@dataclass(frozen=True, slots=True)
class LogEntry:
    seq: int
    ts: float
    direction: str
    device: str
    kind: str
    summary: str


def _clean(text: str) -> str:
    """Collapse whitespace and cap the line so one event stays one row."""

    flat = " ".join(str(text).split())
    return flat[:MAX_SUMMARY]


def describe_input(event: InputEvent) -> str:
    """Short, credential-free description of one normalised input event."""

    parts = [event.control, f"value {event.value:g}"]
    if event.note is not None:
        parts.append(f"note {event.note}")
    parts.append(f"bank {event.bank}")
    return _clean(" · ".join(parts))


def describe_frame(kind: str, frame: dict[str, Any]) -> str:
    """Describe an onPC frame by kind and coarse target fields only."""

    parts = [kind]
    for key in ("page", "executor", "button", "note"):
        value = frame.get(key)
        if value is not None:
            parts.append(f"{key} {value}")
    if kind == "keyname" and frame.get("keyname"):
        parts.append(str(frame["keyname"]))
    return _clean(" · ".join(parts))


def describe_midi(data: bytes) -> str:
    """Describe a device write as note/velocity when it is a note-on frame."""

    if len(data) >= 3 and data[0] & 0xF0 == 0x90:
        return _clean(f"note {data[1]} · velocity {data[2]}")
    return _clean(f"{len(data)} Byte")


class ActivityTracker:
    """Thread-safe RX/TX counters and a bounded event log."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._seq = 0
        self._log: deque[LogEntry] = deque(maxlen=MAX_LOG)
        self._pending: deque[LogEntry] = deque(maxlen=MAX_PENDING)
        self._devices: dict[str, dict[str, Any]] = {}

    def record(
        self,
        direction: str,
        device: str,
        kind: str,
        summary: str,
        *,
        count: bool = True,
    ) -> None:
        if direction not in DIRECTIONS:
            raise ValueError(f"unknown direction: {direction}")
        device = device or "system"
        with self._lock:
            self._seq += 1
            ts = self._clock()
            entry = LogEntry(
                seq=self._seq,
                ts=ts,
                direction=direction,
                device=device,
                kind=kind,
                summary=_clean(summary),
            )
            self._log.append(entry)
            self._pending.append(entry)
            if not count:
                return
            state = self._devices.setdefault(
                device, {"rx": 0, "tx": 0, "last_rx": None, "last_tx": None}
            )
            state[direction] += 1
            state[f"last_{direction}"] = ts

    def record_rx(
        self, device: str, kind: str, summary: str, *, count: bool = True
    ) -> None:
        self.record("rx", device, kind, summary, count=count)

    def record_tx(
        self, device: str, kind: str, summary: str, *, count: bool = True
    ) -> None:
        self.record("tx", device, kind, summary, count=count)

    def devices(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {name: dict(state) for name, state in self._devices.items()}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "devices": {name: dict(state) for name, state in self._devices.items()},
                "log": [asdict(entry) for entry in self._log],
            }

    def take_pending(self, limit: int = MAX_FLUSH) -> list[dict[str, Any]]:
        with self._lock:
            count = min(max(limit, 0), len(self._pending))
            entries = [
                asdict(entry) for entry in list(self._pending)[:count]
            ]
            for _ in range(count):
                self._pending.popleft()
            return entries


def record_ma2_frame(tracker: ActivityTracker, kind: str, frame: dict[str, Any]) -> None:
    """Log a frame sent to onPC; polling frames are dropped entirely.

    ``ma2`` is not a configured device, so it gets no counter row; only real
    input/output devices appear in ``activity.devices``.
    """

    if kind in QUIET_FRAME_KINDS:
        return
    tracker.record_tx(
        "ma2", kind, describe_frame(kind, frame), count=False
    )
