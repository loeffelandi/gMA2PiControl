from __future__ import annotations

import asyncio
import contextlib
import os
from types import SimpleNamespace

from ma2pi.activity import (
    MAX_FLUSH,
    MAX_LOG,
    MAX_PENDING,
    ActivityTracker,
    describe_frame,
    describe_input,
    describe_midi,
    record_ma2_frame,
)
from ma2pi.__main__ import _activity_event, _process_input, _status_snapshot
from ma2pi.events import InputEvent
from ma2pi.led_output import LedOutput
from ma2pi.ma2_client import Ma2Client
from ma2pi.midi_input import MidiManager


class Clock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        self.now += 0.5
        return self.now


def test_counters_and_timestamps_per_device() -> None:
    clock = Clock()
    tracker = ActivityTracker(clock=clock)

    tracker.record_rx("cherry", "key", "ch_pg_plus")
    tracker.record_rx("cherry", "key", "ch_pg_minus")
    tracker.record_tx("midicraft", "midi", "note 70")

    devices = tracker.devices()
    assert devices["cherry"]["rx"] == 2
    assert devices["cherry"]["tx"] == 0
    assert devices["cherry"]["last_rx"] == 1001.0
    assert devices["cherry"]["last_tx"] is None
    assert devices["midicraft"]["tx"] == 1
    assert devices["midicraft"]["last_tx"] == 1001.5


def test_log_is_bounded_and_sequences_are_monotonic() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    for index in range(MAX_LOG + 25):
        tracker.record_rx("cherry", "key", f"event {index}")

    log = tracker.snapshot()["log"]
    assert len(log) == MAX_LOG
    sequences = [entry["seq"] for entry in log]
    assert sequences == sorted(sequences)
    assert sequences[-1] == MAX_LOG + 25
    assert log[-1]["summary"] == f"event {MAX_LOG + 24}"


def test_pending_is_bounded_and_drained() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    for index in range(MAX_PENDING + 10):
        tracker.record_tx("ma2", "playbacksRequest", "playbacksRequest")

    first = tracker.take_pending()
    assert len(first) == MAX_FLUSH
    rest: list[dict] = []
    while True:
        chunk = tracker.take_pending()
        if not chunk:
            break
        assert len(chunk) <= MAX_FLUSH
        rest.extend(chunk)
    assert len(first) + len(rest) == MAX_PENDING
    assert tracker.take_pending() == []

    tracker.record_tx("ma2", "x", "x")
    tracker.record_tx("ma2", "y", "y")
    assert len(tracker.take_pending(limit=1)) == 1


def test_snapshot_is_detached_from_internal_state() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    tracker.record_rx("cherry", "key", "x")

    snapshot = tracker.snapshot()
    snapshot["devices"]["cherry"]["rx"] = 99
    snapshot["log"].clear()

    assert tracker.devices()["cherry"]["rx"] == 1
    assert len(tracker.snapshot()["log"]) == 1


def test_device_falls_back_to_system() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    tracker.record_rx("", "lost", "device lost")
    assert "system" in tracker.devices()


def test_summaries_stay_short_and_single_line() -> None:
    event = InputEvent(
        kind="key",
        control="ch_pg_plus",
        value=1,
        device="cherry",
        bank=2,
        note=42,
    )
    summary = describe_input(event)
    assert summary == "ch_pg_plus · value 1 · note 42 · bank 2"

    frame = {"type": "playbacksRequest", "page": 3, "executor": 201, "command": "Go"}
    frame_summary = describe_frame("playbacksRequest", frame)
    assert frame_summary == "playbacksRequest · page 3 · executor 201"
    assert "Go" not in frame_summary

    assert describe_midi(bytes((0x90, 70, 127))) == "note 70 · velocity 127"
    assert describe_midi(b"\x9f\x01") == "2 Byte"

    long = describe_input(
        InputEvent(kind="key", control="x" * 400, value=1, device="cherry")
    )
    assert len(long) <= 120
    assert "\n" not in long


def test_unknown_direction_is_rejected() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    try:
        tracker.record("sideways", "cherry", "key", "x")
    except ValueError:
        pass
    else:  # pragma: no cover - the assert documents the contract
        raise AssertionError("expected ValueError")


def test_midi_send_hook_reports_success() -> None:
    manager = MidiManager(SimpleNamespace(), source=SimpleNamespace())
    written: list[bytes] = []
    handle = SimpleNamespace(write=lambda data: written.append(data) or True)
    manager._open["midicraft"] = SimpleNamespace(handle=handle)
    calls: list[tuple[str, bytes]] = []
    manager.set_send_hook(lambda device, data: calls.append((device, data)))

    assert manager.send("midicraft", b"\x90\x01\x02") is True
    assert written == [b"\x90\x01\x02"]
    assert calls == [("midicraft", b"\x90\x01\x02")]
    assert manager.send("missing", b"\x90\x01\x02") is False


def test_activity_event_bundles_and_drains() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    assert _activity_event(tracker) is None

    for index in range(MAX_FLUSH + 5):
        tracker.record_rx("cherry", "key", f"event {index}")

    event = _activity_event(tracker)
    assert event is not None
    assert event["type"] == "activity"
    assert len(event["data"]["entries"]) == MAX_FLUSH
    assert len(tracker.take_pending()) == 5


def test_ma2_frames_are_logged_but_not_counted_as_device() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)

    record_ma2_frame(tracker, "playbacksRequest", {"type": "playbacksRequest"})
    assert tracker.snapshot()["log"] == []

    record_ma2_frame(
        tracker, "keyname", {"type": "keyname", "keyname": "GO", "value": 1}
    )
    log = tracker.snapshot()["log"]
    assert len(log) == 1
    assert log[0]["device"] == "ma2"
    assert log[0]["summary"] == "keyname · GO"
    assert tracker.devices() == {}

    record_ma2_frame(
        tracker,
        "playbackButton",
        {"pageIndex": -1, "execIndex": 2, "buttonId": 0, "pressed": True},
    )
    record_ma2_frame(
        tracker,
        "hardkeyPress",
        {"type": "remoteCommand", "keyname": "GO"},
    )
    summaries = [entry["summary"] for entry in tracker.snapshot()["log"]]
    assert "playbackButton · page current · executor 3 · button 1" in summaries
    assert "hardkeyPress · GO" in summaries


async def test_ma2_client_frame_hook(make_config) -> None:
    client = Ma2Client(make_config(), dry_run=True)
    tracker = ActivityTracker(clock=lambda: 1.0)
    client.on_frame = lambda kind, frame: record_ma2_frame(tracker, kind, frame)

    await client._send_raw({"type": "playbacksRequest"}, "playbacksRequest")
    await client._send_raw(
        {"type": "keyname", "keyname": "GO", "value": 1}, "keyname"
    )

    log = tracker.snapshot()["log"]
    assert [entry["kind"] for entry in log] == ["keyname"]
    assert log[0]["summary"] == "keyname · GO"


async def test_frame_hook_failure_does_not_break_sending(make_config) -> None:
    client = Ma2Client(make_config(), dry_run=True)

    def broken(kind, frame):
        raise RuntimeError("hook failed")

    client.on_frame = broken
    await client._send_raw({"type": "keyname", "keyname": "GO", "value": 1}, "keyname")
    assert client.frames_sent == 1


def test_led_write_hook_reports_labels(tmp_path) -> None:
    path = tmp_path / "led"
    path.write_bytes(b"")
    led = LedOutput(path, SimpleNamespace(device="asl"))
    led._fd = os.open(path, os.O_WRONLY)
    labels: list[str] = []
    led.on_write = labels.append
    try:
        led._write(b"\x90\x01\x02", "color")
    finally:
        os.close(led._fd)
        led._fd = None

    assert labels == ["color"]
    assert led.device_name == "asl"


def test_status_snapshot_contains_activity() -> None:
    tracker = ActivityTracker(clock=lambda: 5.0)
    tracker.record_tx("midicraft", "midi", "note 70")
    client = SimpleNamespace(
        connected=True,
        authenticated=True,
        session=1,
        queue=[],
        limiter=SimpleNamespace(effective_rate=25.0),
        screen_mode=False,
        frames_sent=1,
        last_frame_types=["playbacksRequest"],
        reconnects=0,
        last_error=None,
    )

    snapshot = _status_snapshot(client, None, tracker)

    assert snapshot["activity"]["devices"]["midicraft"]["tx"] == 1
    assert snapshot["activity"]["log"][0]["summary"] == "note 70"
    assert snapshot["midi_remote"] == {"enabled": False}

    remote = SimpleNamespace(status=lambda: {"enabled": True, "session": {"state": "connected"}})
    snapshot = _status_snapshot(client, None, tracker, midi_remote=remote)
    assert snapshot["midi_remote"]["session"]["state"] == "connected"


class _Engine:
    def __init__(self) -> None:
        self.handled: list[InputEvent] = []

    def handle(self, item: InputEvent) -> None:
        self.handled.append(item)

    def release_device(self, device: str) -> None:
        pass


class _Learn:
    active = False


async def test_process_input_records_rx() -> None:
    tracker = ActivityTracker(clock=lambda: 1.0)
    queue: asyncio.Queue[InputEvent] = asyncio.Queue()
    event = InputEvent(
        kind="key", control="ch_pg_plus", value=1, device="cherry", note=42
    )
    await queue.put(event)
    engine = _Engine()

    task = asyncio.create_task(
        _process_input(queue, engine, _Learn(), None, None, None, tracker)
    )
    try:
        for _ in range(50):
            if tracker.devices():
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert engine.handled == [event]
    assert tracker.devices()["cherry"]["rx"] == 1
    entry = tracker.snapshot()["log"][-1]
    assert entry["direction"] == "rx"
    assert entry["device"] == "cherry"
    assert entry["summary"] == "ch_pg_plus · value 1 · note 42 · bank 1"


def test_describe_midi_formats_asl_compound_and_control_frames() -> None:
    assert describe_midi(b"\x9f\x7f\x7f") == "led enable"
    assert describe_midi(b"\x9f\x7f\x7e") == "led disable"
    assert (
        describe_midi(b"\x9f\x7f\x7f\x90\x09\x7f\x91\x09\x04")
        == "note 9 · brightness 127 · color 4"
    )
    assert describe_midi(b"\x90\x09\x19\x91\x09\x3c") == "note 9 · brightness 25 · color 60"
    assert describe_midi(b"\x90\x41\x25") == "note 65 · velocity 37"
