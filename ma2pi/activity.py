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
    if "pageIndex" in frame and isinstance(frame["pageIndex"], int):
        idx = frame["pageIndex"]
        parts.append("page current" if idx < 0 else f"page {idx + 1}")
    elif frame.get("page") is not None:
        parts.append(f"page {frame['page']}")

    if "execIndex" in frame and isinstance(frame["execIndex"], int):
        parts.append(f"executor {frame['execIndex'] + 1}")
    elif frame.get("executor") is not None:
        parts.append(f"executor {frame['executor']}")

    if "buttonId" in frame and isinstance(frame["buttonId"], int):
        parts.append(f"button {frame['buttonId'] + 1}")
    elif frame.get("button") is not None:
        parts.append(f"button {frame['button']}")

    if frame.get("faderValue") is not None:
        try:
            parts.append(f"fader {float(frame['faderValue']):.2f}")
        except (TypeError, ValueError):
            pass

    if frame.get("name"):
        parts.append(str(frame["name"]))

    if frame.get("note") is not None:
        parts.append(f"note {frame['note']}")

    if kind in {"keyname", "hardkeyPress", "hardkeyRelease"} and frame.get("keyname"):
        parts.append(str(frame["keyname"]))
    return _clean(" · ".join(parts))


def describe_midi(data: bytes) -> str:
    """Describe a device write as note/velocity or ASL LED frame."""

    if data == b"\x9f\x7f\x7f":
        return "led enable"
    if data == b"\x9f\x7f\x7e":
        return "led disable"
    if (
        len(data) >= 9
        and data[:3] == b"\x9f\x7f\x7f"
        and (data[3] & 0xF0) == 0x90
        and (data[6] & 0xF0) == 0x90
        and data[4] == data[7]
    ):
        return _clean(f"note {data[4]} · brightness {data[5]} · color {data[8]}")
    if (
        len(data) == 6
        and (data[0] & 0xF0) == 0x90
        and (data[3] & 0xF0) == 0x90
        and data[1] == data[4]
    ):
        return _clean(f"note {data[1]} · brightness {data[2]} · color {data[5]}")
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
