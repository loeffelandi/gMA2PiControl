from __future__ import annotations

import asyncio
import contextlib
import dataclasses

import pytest

from ma2pi.events import InputEvent
from ma2pi.ma2_client import Ma2Client
from ma2pi.mapping import MappingEngine
from tests.mock_ma2 import MockMa2Server


def client_config(config, port: int, **changes):
    values = {
        "host": "127.0.0.1",
        "port": port,
        "password_file": None,
        "password_env": "MA2PI_TEST_PASSWORD",
        "hardkey_transport": "native",
        "keepalive_interval": 0.05,
    }
    values.update(changes)
    ma2 = dataclasses.replace(config.ma2, **values)
    reconnect = dataclasses.replace(
        config.reconnect, initial_delay=0.01, max_delay=0.05, jitter=0.0, login_failure_delay=0.02
    )
    return dataclasses.replace(config, ma2=ma2, reconnect=reconnect)


async def wait_until(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


async def test_end_to_end_input_to_recorded_frames(config):
    server = await MockMa2Server().start()
    cfg = client_config(config, server.port)
    client = Ma2Client(cfg)
    engine = MappingEngine(cfg, client)
    client.add_connection_lost_callback(engine.on_connection_lost)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)

        engine.handle(InputEvent("key", "ma", 1, "cherry"))
        engine.handle(InputEvent("key", "fix", 1, "cherry"))
        engine.handle(InputEvent("key", "fix", 0, "cherry"))
        engine.handle(InputEvent("key", "ma", 0, "cherry"))
        for _ in range(3):
            engine.handle(InputEvent("encoder", "encoder.1", 1, "asl"), now=0.0)
        engine.flush_all(0.05)

        await wait_until(lambda: len(server.frames) >= 6)
        hardkeys = [frame for frame in server.frames if frame.get("requestType") == "keyname"]
        assert [(frame["keyname"], frame["value"]) for frame in hardkeys] == [
            ("MA", 1.0),
            ("FIX", 1.0),
            ("FIX", 0.0),
            ("MA", 0.0),
        ]
        encoders = [
            frame
            for frame in server.frames
            if "gma.canbus.encoder(0," in str(frame.get("command"))
        ]
        assert encoders and _canbus_steps(encoders[-1]) > 0
    finally:
        engine.cleanup(send=False)
        await client.shutdown()
        await server.stop()


async def test_wrong_password_is_reported(config):
    server = await MockMa2Server(password="other").start()
    cfg = client_config(config, server.port)
    client = Ma2Client(cfg)
    try:
        await client.start()
        await wait_until(lambda: client.login_failures >= 1)
        assert not client.authenticated
    finally:
        await client.shutdown()
        await server.stop()


async def test_reconnect_after_server_drop(config):
    server = await MockMa2Server(drop_after=1).start()
    cfg = client_config(config, server.port, keepalive_interval=0.5)
    client = Ma2Client(cfg)
    engine = MappingEngine(cfg, client)
    client.add_connection_lost_callback(engine.on_connection_lost)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        engine.handle(InputEvent("key", "fix", 1, "cherry"))
        engine.handle(InputEvent("key", "fix", 0, "cherry"))
        await wait_until(lambda: len(server.logins) >= 2, timeout=8.0)
        await wait_until(lambda: client.authenticated, timeout=4.0)
        assert server.connections >= 2
        # No stale press is replayed after reconnect.
        replayed = [
            frame
            for frame in server.frames
            if frame.get("requestType") == "keyname" and frame.get("value") == 1.0
        ]
        assert len(replayed) == 1
    finally:
        engine.cleanup(send=False)
        await client.shutdown()
        await server.stop()


async def test_shutdown_with_held_keys_releases_then_closes(config):
    server = await MockMa2Server().start()
    cfg = client_config(config, server.port)
    client = Ma2Client(cfg)
    engine = MappingEngine(cfg, client)
    client.add_connection_lost_callback(engine.on_connection_lost)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        engine.handle(InputEvent("key", "ma", 1, "cherry"))
        engine.handle(InputEvent("key", "store_big", 1, "cherry"))
        await wait_until(
            lambda: sum(1 for f in server.frames if f.get("requestType") == "keyname") >= 2
        )
        engine.cleanup(send=client.authenticated)
        await client.shutdown()
        relevant = [
            frame
            for frame in server.frames
            if frame.get("requestType") in {"keyname", "close"}
        ]
        assert [
            (frame.get("keyname"), frame.get("value"))
            for frame in relevant
            if frame.get("requestType") == "keyname"
        ] == [("MA", 1.0), ("STORE", 1.0), ("STORE", 0.0), ("MA", 0.0)]
        assert relevant[-1].get("requestType") == "close"
    finally:
        engine.cleanup(send=False)
        await client.shutdown()
        await server.stop()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def _canbus_steps(frame) -> int:
    inner = str(frame["command"]).split("gma.canbus.encoder(", 1)[1].split(")", 1)[0]
    return int(inner.split(",")[1])


def _wheel_ticks(frames) -> float:
    total = 0.0
    for frame in frames:
        if "gma.canbus.encoder(0," in str(frame.get("command")):
            total += _canbus_steps(frame)
    return total


async def test_encoder_stress_against_mock_server(config):
    server = await MockMa2Server().start()
    base = client_config(config, server.port)
    rate = dataclasses.replace(
        base.rate_limit,
        messages_per_second=40,
        burst=10,
        max_pending_delta=1000,
    )
    acceleration = dataclasses.replace(base.mapping.acceleration, curve="none")
    mapping = dataclasses.replace(base.mapping, acceleration=acceleration)
    cfg = dataclasses.replace(base, rate_limit=rate, mapping=mapping)

    clock = FakeClock()
    client = Ma2Client(cfg, clock=clock.clock, sleep=clock.sleep)
    engine = MappingEngine(cfg, client)
    try:
        await client.connect_once()
        assert client.authenticated
        if client._keepalive_task is not None:
            client._keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await client._keepalive_task
        client._sender_task = asyncio.create_task(client._sender_loop())

        max_depth = 0
        for step in range(10_000):  # 10 s at 1 ms resolution, 100 detents/s
            t = step / 1000.0
            if step % 10 == 0:
                engine.handle(InputEvent("encoder", "encoder.1", 1, "asl"), now=t)
            engine.flush_due(t)
            max_depth = max(max_depth, client.queue.total_depth)
            await asyncio.sleep(0)
        engine.flush_all(10.0)

        await wait_until(lambda: _wheel_ticks(server.frames) >= 1000, timeout=5.0)
        wheel_frames = [
            frame
            for frame in server.frames
            if "gma.canbus.encoder(0," in str(frame.get("command"))
        ]
        assert _wheel_ticks(server.frames) == pytest.approx(1000.0)
        assert len(wheel_frames) <= 40 * 10 + 10
        assert max_depth <= 2
    finally:
        engine.cleanup(send=False)
        await client.shutdown()
        await server.stop()


async def test_playbacks_polling_round_trip(config):
    def answer(frame):
        items_type = frame["itemsType"][0]
        start = frame["startIndex"][0]
        count = frame["itemsCount"][0]
        return {
            "responseType": "playbacks",
            "iPage": 1,
            "itemGroups": [
                {
                    "itemsType": items_type,
                    "items": [
                        [
                            {
                                "iExec": start + index,
                                "isRun": index == 0,
                                "bC": "#ff0000",
                            }
                            for index in range(count)
                        ]
                    ],
                }
            ],
        }

    server = await MockMa2Server().start()
    server.playbacks = answer
    cfg = client_config(config, server.port)
    client = Ma2Client(cfg)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        client.request_playbacks("current", 100, 5, 3, 3)
        snapshot = await asyncio.wait_for(client.playback_responses.get(), timeout=2.0)
        assert snapshot["iPage"] == 1
        assert snapshot["itemGroups"][0]["itemsType"] == 3
        assert snapshot["itemGroups"][0]["items"][0][0]["iExec"] == 100
    finally:
        await client.shutdown()
        await server.stop()


class _RecordingMidi:
    def __init__(self) -> None:
        self.open_devices = {"midicraft": "/dev/snd/midiC4D0"}
        self.sent: list[bytes] = []

    def send(self, device: str, data: bytes) -> bool:
        assert device == "midicraft"
        self.sent.append(data)
        return True


async def test_feedback_polls_and_resets_on_disconnect(config):
    from ma2pi.feedback import ExecutorFeedback

    def answer(frame):
        start = frame["startIndex"][0]
        count = frame["itemsCount"][0]
        items_type = frame["itemsType"][0]
        return {
            "responseType": "playbacks",
            "iPage": 1,
            "itemGroups": [
                {
                    "itemsType": items_type,
                    "items": [
                        [
                            {
                                "iExec": start + index,
                                "isRun": index == 0,
                                "bC": "#ff0000",
                            }
                            for index in range(count)
                        ]
                    ],
                }
            ],
        }

    server = await MockMa2Server().start()
    server.playbacks = answer
    cfg = client_config(config, server.port)
    client = Ma2Client(cfg)
    midi = _RecordingMidi()
    feedback = ExecutorFeedback(cfg, client, midi)
    client.add_connection_lost_callback(feedback.reset)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        await asyncio.wait_for(feedback.step(), timeout=3.0)

        assert len(midi.sent) == 15
        assert feedback._last

        await client._handle_disconnect("test")
        assert feedback._last == {}
    finally:
        await client.shutdown()
        await server.stop()
