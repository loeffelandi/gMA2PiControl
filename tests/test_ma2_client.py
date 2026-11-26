from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json

import pytest

from ma2pi import frames, wheel_protocol
from ma2pi.actions import (
    EncoderAttribute,
    EncoderSlot,
    Press,
    Release,
    ToggleFine,
    merge_encoder,
)
from ma2pi.events import InputEvent
from ma2pi.mapping import MappingEngine
from ma2pi.ma2_client import (
    BackpressureGuard,
    LoginError,
    Ma2Client,
    SendQueue,
    TokenBucket,
    encode_frame,
)


class MockTransport:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.uri: str | None = None
        self.connected = False
        self.closed = False
        self.buffer = 0

    async def connect(self, uri: str) -> None:
        self.uri = uri
        self.connected = True

    async def recv(self):
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True
        await self.incoming.put(None)

    def write_buffer_size(self) -> int:
        return self.buffer


def feed_handshake(transport: MockTransport, session: int = 1, result: bool = True) -> None:
    transport.incoming.put_nowait(json.dumps({"status": "server ready", "appType": "gma2"}))
    transport.incoming.put_nowait(
        json.dumps({"session": session, "forceLogin": True, "requestType": "sessionInformation"})
    )
    transport.incoming.put_nowait(
        json.dumps({"requestType": "loginResponse", "result": result, "session": session})
    )


async def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.005)


# -- frame builders -------------------------------------------------------


def test_frame_builders_exact():
    assert frames.session_request_frame() == {"session": 0}
    assert frames.keepalive_frame(4) == {"session": 4}
    assert frames.login_frame("u", "abc", 4) == {
        "requestType": "login",
        "username": "u",
        "password": "abc",
        "session": 4,
        "maxRequests": 1,
    }
    assert frames.command_frame("Clear", 4) == {
        "command": "Clear",
        "session": 4,
        "requestType": "command",
        "maxRequests": 0,
    }
    assert frames.keyname_frame("FIXTURE", True, 4, 1.0, 0.0) == {
        "requestType": "keyname",
        "keyname": "FIXTURE",
        "value": 1.0,
        "session": 4,
        "maxRequests": 0,
    }
    assert frames.keyname_frame("FIXTURE", False, 4, 1.0, 0.0)["value"] == 0.0
    assert frames.keyname_frame("STORE", True, 4)["keyname"] == "STORE"
    assert frames.encoder_attribute_frame("PAN", 0.5, 4) == {
        "requestType": "encoder",
        "name": "PAN",
        "value": 0.5,
        "session": 4,
        "maxRequests": 0,
    }
    assert frames.encoder_resolution_frame("PAN", 1, 4) == {
        "requestType": "encoder",
        "name": "PAN",
        "resolution": 1,
        "session": 4,
        "maxRequests": 0,
    }
    assert frames.preset_types_frame("full", 4) == {
        "requestType": "presetTypes",
        "type": "full",
        "session": 4,
        "maxRequests": 1,
    }
    assert frames.close_frame(4) == {"requestType": "close", "session": 4, "maxRequests": 1}


def test_frames_are_serialised_compactly():
    # onPC rejects the login request if the JSON contains spaces after ":" or
    # "," even when the credentials are correct.
    text = encode_frame(frames.login_frame("svt", "d41d8cd9", 7))
    assert text == (
        '{"requestType":"login","username":"svt","password":"d41d8cd9",'
        '"session":7,"maxRequests":1}'
    )
    assert " " not in text
    keyname = encode_frame(frames.keyname_frame("FIXTURE", True, 7))
    assert keyname == (
        '{"requestType":"keyname","keyname":"FIXTURE","value":1.0,'
        '"session":7,"maxRequests":0}'
    )


def test_frame_types():
    assert frames.frame_type(frames.command_frame("x", 1)) == "command"
    assert frames.frame_type(frames.keepalive_frame(1)) == "keepalive"
    assert frames.frame_type({"status": "server ready"}) == "status"


def test_native_wheel_requires_capture():
    with pytest.raises(wheel_protocol.NativeWheelUnavailable, match="Capture"):
        wheel_protocol.build_wheel_frame(1, 2, 1)


# -- queue ----------------------------------------------------------------


async def test_queue_control_has_priority():
    queue = SendQueue()
    queue.put(EncoderSlot(1, 3))
    queue.put(Press("FIXTURE"))
    assert await queue.get() == Press("FIXTURE")
    assert await queue.get() == EncoderSlot(1, 3)


async def test_queue_coalesces_encoder_targets():
    queue = SendQueue()
    queue.put(EncoderSlot(1, 2))
    queue.put(EncoderSlot(1, 3))
    queue.put(EncoderAttribute("Dimmer", 0.1))
    queue.put(EncoderAttribute("Dimmer", 0.2))
    assert queue.total_depth == 2
    first = await queue.get()
    second = await queue.get()
    assert first == EncoderSlot(1, 5)
    assert second == EncoderAttribute("Dimmer", pytest.approx(0.3))


async def test_queue_keeps_screen_and_attribute_targets_separate():
    queue = SendQueue()
    queue.put(EncoderSlot(1, 2))
    queue.put(EncoderSlot(1, 3, screen=True))
    assert queue.total_depth == 2
    actions = [await queue.get(), await queue.get()]
    assert EncoderSlot(1, 2) in actions
    assert EncoderSlot(1, 3, screen=True) in actions


async def test_queue_never_drops_controls():
    queue = SendQueue()
    for _ in range(200):
        queue.put(Release("FIXTURE"))
    queue.put(EncoderSlot(1, 1))
    assert queue.control_depth == 200
    assert queue.total_depth == 201


def test_merge_encoder_cancels_to_zero():
    assert merge_encoder(EncoderSlot(1, 2), EncoderSlot(1, -2)) is None
    assert merge_encoder(EncoderAttribute("A", 0.2), EncoderAttribute("A", -0.2)) is None


def test_merge_encoder_keeps_screen_flag():
    merged = merge_encoder(
        EncoderSlot(1, 2, screen=True), EncoderSlot(1, 3, screen=True)
    )
    assert merged == EncoderSlot(1, 5, screen=True)


# -- rate limiter ---------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


async def test_token_bucket_limits_200_frames_in_100ms():
    fake = FakeClock()
    bucket = TokenBucket(25, 10, clock=fake.clock, sleep=fake.sleep)
    sent = 0
    while fake.now <= 0.1:
        await bucket.acquire()
        if fake.now > 0.1:
            break
        sent += 1
    assert sent <= 14
    assert sent >= 10


async def test_token_bucket_multiplier_halves_rate():
    fake = FakeClock()
    bucket = TokenBucket(20, 1, clock=fake.clock, sleep=fake.sleep)
    bucket.multiplier = 0.5
    await bucket.acquire()
    await bucket.acquire()
    assert fake.now == pytest.approx(0.1)
    assert bucket.effective_rate == pytest.approx(10.0)


def test_backpressure_guard_engages_and_recovers():
    guard = BackpressureGuard(hold_seconds=2.0, recover_seconds=5.0)
    assert guard.observe(0.0, 101, 0) is None
    assert guard.observe(2.1, 101, 0) == "engaged"
    assert guard.observe(3.0, 0, 0) is None
    assert guard.observe(8.1, 0, 0) == "released"


def test_backpressure_guard_buffer_threshold():
    guard = BackpressureGuard(hold_seconds=1.0)
    assert guard.observe(0.0, 0, 70_000) is None
    assert guard.observe(1.1, 0, 70_000) == "engaged"


# -- client ---------------------------------------------------------------


def _client(config, transport, **kwargs) -> Ma2Client:
    return Ma2Client(config, transport=transport, jitter_source=lambda: 0.5, **kwargs)


async def test_connect_once_success(small_config):
    transport = MockTransport()
    feed_handshake(transport, session=7)
    client = _client(small_config, transport)
    await client.connect_once()
    assert client.authenticated
    assert client.session == 7
    assert transport.uri == f"ws://{small_config.ma2.host}:{small_config.ma2.port}{small_config.ma2.path}"
    assert transport.sent[0] == {"session": 0}
    login = transport.sent[1]
    assert login["requestType"] == "login"
    assert login["username"] == small_config.ma2.username
    assert login["password"] == hashlib.md5(b"secret").hexdigest()
    assert login["session"] == 7
    await client.shutdown()


async def test_login_failure_raises(small_config):
    transport = MockTransport()
    feed_handshake(transport, session=3, result=False)
    client = _client(small_config, transport)
    with pytest.raises(LoginError):
        await client.connect_once()
    assert not client.authenticated


async def test_keepalive_is_sent_on_idle(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    await asyncio.sleep(0.16)
    keepalives = [frame for frame in transport.sent if frame == {"session": 1}]
    assert len(keepalives) >= 2
    await client.shutdown()


async def test_keepalive_covers_twelve_seconds_of_idle(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    assert client._keepalive_task is not None
    client._keepalive_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await client._keepalive_task

    elapsed = 0.0

    async def fake_sleep(seconds: float) -> None:
        nonlocal elapsed
        elapsed += seconds
        if elapsed >= 12.0:
            client._shutting_down = True
        await asyncio.sleep(0)

    client._shutting_down = False
    client._sleep = fake_sleep
    await asyncio.wait_for(client._keepalive_loop(1), timeout=2.0)
    keepalives = [frame for frame in transport.sent if frame == {"session": 1}]
    assert elapsed >= 12.0
    assert len(keepalives) >= 2
    client._shutting_down = False
    await client.shutdown()


async def test_dry_run_never_connects(small_config):
    client = Ma2Client(small_config, dry_run=True)
    await client.start()
    assert client.authenticated
    client.press("FIXTURE")
    await wait_until(lambda: len(client.sent_frames) >= 1)
    assert client.sent_frames[0]["requestType"] == "keyname"
    await client.shutdown()


async def test_sender_orders_control_before_encoder(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    client._page.update(
        {
            "responseType": "presetTypes",
            "type": "full",
            "pre": [
                {
                    "i": 1,
                    "np": "Dimmer",
                    "s": True,
                    "fea": [
                        {
                            "i": 1,
                            "np": "Dimmer",
                            "s": True,
                            "att": [{"n": "DIM", "np": "Dim", "s": True}],
                        }
                    ],
                }
            ],
        }
    )
    client._sender_task = asyncio.create_task(client._sender_loop())
    client._queue.put(EncoderSlot(1, 4))
    client._queue.put(Release("FIXTURE"))
    await wait_until(
        lambda: any(f.get("requestType") == "encoder" for f in transport.sent)
    )
    names = [f.get("requestType") for f in transport.sent if f.get("requestType") in {"keyname", "encoder"}]
    assert names == ["keyname", "encoder"]
    await client.shutdown()


async def test_shutdown_drains_release_before_close(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    client._sender_task = asyncio.create_task(client._sender_loop())
    client.press("MA")
    client.release("MA")
    await client.shutdown()
    request_types = [frame.get("requestType") for frame in transport.sent]
    assert "keyname" in request_types
    assert request_types[-1] == "close"
    assert request_types.index("keyname") < len(request_types) - 1


async def test_encoder_frame_uses_attribute_name(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    client._sender_task = asyncio.create_task(client._sender_loop())
    client.encoder_attribute("PAN", 0.1)
    await wait_until(
        lambda: any(f.get("requestType") == "encoder" for f in transport.sent)
    )
    frame = [f for f in transport.sent if f.get("requestType") == "encoder"][-1]
    assert frame["name"] == "PAN"
    assert frame["value"] == pytest.approx(0.1)
    await client.shutdown()


async def test_slot_encoder_uses_console_page(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    client._page.update(
        {
            "responseType": "presetTypes",
            "type": "full",
            "pre": [
                {
                    "i": 2,
                    "np": "Position",
                    "s": True,
                    "fea": [
                        {
                            "i": 1,
                            "np": "Position",
                            "s": True,
                            "att": [
                                {"n": "PAN", "np": "Pan", "s": True},
                                {"n": "TILT", "np": "Tilt", "s": False},
                            ],
                        }
                    ],
                }
            ],
        }
    )
    client._sender_task = asyncio.create_task(client._sender_loop())
    client.encoder_slot(2, 3.0)
    await wait_until(
        lambda: any(f.get("requestType") == "encoder" for f in transport.sent)
    )
    frame = [f for f in transport.sent if f.get("requestType") == "encoder"][-1]
    assert frame["name"] == "TILT"
    assert frame["value"] == pytest.approx(3.0)
    await client.shutdown()


async def test_slot_encoder_ignored_without_page(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    client._sender_task = asyncio.create_task(client._sender_loop())
    client.encoder_slot(1, 1.0)
    await asyncio.sleep(0.05)
    assert all(frame.get("requestType") != "encoder" for frame in transport.sent)
    await client.shutdown()


async def test_fine_toggle_sends_resolution_frame(small_config):
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(small_config, transport)
    await client.connect_once()
    client._page.update(
        {
            "responseType": "presetTypes",
            "type": "full",
            "pre": [
                {
                    "i": 1,
                    "np": "Dimmer",
                    "s": True,
                    "fea": [
                        {
                            "i": 1,
                            "np": "Dimmer",
                            "s": True,
                            "att": [{"n": "DIM", "np": "Dim", "s": True}],
                        }
                    ],
                }
            ],
        }
    )
    client._sender_task = asyncio.create_task(client._sender_loop())
    client.toggle_fine(1)
    await wait_until(
        lambda: any("resolution" in f for f in transport.sent)
    )
    assert [f for f in transport.sent if f.get("resolution")][-1] == {
        "requestType": "encoder",
        "name": "DIM",
        "resolution": 1,
        "session": 1,
        "maxRequests": 0,
    }
    client.toggle_fine(1)
    await wait_until(
        lambda: [f["resolution"] for f in transport.sent if "resolution" in f][-1] == 2
    )
    assert [f for f in transport.sent if "resolution" in f][-1]["resolution"] == 2
    client.toggle_fine(1)
    await wait_until(
        lambda: [f["resolution"] for f in transport.sent if "resolution" in f][-1] == 0
    )
    assert [f for f in transport.sent if "resolution" in f][-1]["resolution"] == 0
    await client.shutdown()


async def test_fine_toggle_uses_screen_encoder_name(make_config):
    cfg = make_config(
        lambda data: data["mapping"].__setitem__(
            "screen_encoders", {"1": "screen1"}
        )
    )
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    client._screen_mode = True
    await client._dispatch(ToggleFine(1))
    assert transport.sent == [frames.encoder_resolution_frame("screen1", 1, 4)]


async def test_fine_toggle_screen_mode_without_name_warns(make_config, caplog):
    cfg = make_config(lambda data: data["mapping"].pop("screen_encoders"))
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    client._screen_mode = True
    with caplog.at_level("WARNING"):
        await client._dispatch(ToggleFine(1))
    assert transport.sent == []
    assert "screen_encoders.1" in caplog.text


async def test_slot_delta_uses_screen_encoder_name(make_config):
    cfg = make_config(
        lambda data: data["mapping"].__setitem__(
            "screen_encoders", {"2": "screen2"}
        )
    )
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    client._screen_mode = True
    await client._dispatch(EncoderSlot(2, 1.5))
    assert transport.sent == [frames.encoder_attribute_frame("screen2", 1.5, 4)]


async def test_slot_delta_can_force_screen_encoder(make_config):
    cfg = make_config(
        lambda data: data["mapping"].__setitem__(
            "screen_encoders", {"2": "screen2"}
        )
    )
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    await client._dispatch(EncoderSlot(2, 1.5, screen=True))
    assert transport.sent == [frames.encoder_attribute_frame("screen2", 1.5, 4)]


def test_backoff_login_failure_uses_long_delay(small_config):
    client = _client(small_config, MockTransport())
    assert client._backoff_delay(1, True) >= small_config.reconnect.login_failure_delay


async def test_reconnect_after_connect_failure(small_config):
    class FlakyTransport(MockTransport):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def connect(self, uri: str) -> None:
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("onPC nicht erreichbar")
            await super().connect(uri)
            feed_handshake(self)

    transport = FlakyTransport()
    client = _client(small_config, transport)
    await client.start()
    await wait_until(lambda: client.authenticated)
    assert transport.attempts >= 2
    assert client.reconnects >= 1
    await client.shutdown()


async def test_backpressure_loop_engages_and_recovers(small_config, caplog):
    client = _client(small_config, MockTransport())
    client._guard = BackpressureGuard(depth_threshold=0, hold_seconds=0.0, recover_seconds=0.0)
    client._queue.put(Release(1))
    task = asyncio.create_task(client._backpressure_loop())
    try:
        with caplog.at_level("WARNING"):
            await asyncio.sleep(0.3)
        assert client._limiter.multiplier == 0.5
        assert "Backpressure aktiv" in caplog.text
        client._queue.clear()
        await asyncio.sleep(0.3)
        assert client._limiter.multiplier == 1.0
    finally:
        client._stop_sender = True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_lua_hardkey_frame_exact():
    # Tap press: hold=false.
    assert frames.lua_hardkey_frame(59, True, 4) == {
        "command": "LUA 'gma.canbus.hardkey(59, true, false)'",
        "session": 4,
        "requestType": "command",
        "maxRequests": 0,
    }
    # Held press: hold=true.
    assert frames.lua_hardkey_frame(59, True, 4, hold=True)["command"] == (
        "LUA 'gma.canbus.hardkey(59, true, true)'"
    )
    # Release always hold=false.
    assert frames.lua_hardkey_frame(59, False, 4)["command"] == (
        "LUA 'gma.canbus.hardkey(59, false, false)'"
    )


def _lua_config(make_config, verified=True):
    def mutate(data):
        data["ma2"]["host"] = "127.0.0.1"
        data["ma2"]["port"] = 9
        data["ma2"]["password_file"] = None
        data["ma2"]["password_env"] = "MA2PI_TEST_PASSWORD"
        data["ma2"]["hardkey_transport"] = "lua"
        data["ma2"]["keepalive_interval"] = 0.05
        data["reconnect"]["initial_delay"] = 0.01
        data["reconnect"]["max_delay"] = 0.05
        data["reconnect"]["jitter"] = 0.0
        data["reconnect"]["login_failure_delay"] = 0.02
        data["rate_limit"]["messages_per_second"] = 40
        data["rate_limit"]["burst"] = 50
        for entry in data["hardkeys"].values():
            entry["verified"] = verified

    return make_config(mutate)


async def test_lua_dispatch_press_and_release(make_config):
    cfg = _lua_config(make_config)
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    await client._dispatch(Press("STORE"))
    await client._dispatch(Release("STORE"))
    assert transport.sent == [
        frames.lua_hardkey_frame(59, True, 4),
        frames.lua_hardkey_frame(59, False, 4),
    ]


async def test_native_dispatch_uses_keyname(make_config):
    cfg = _lua_config(make_config)
    cfg = dataclasses.replace(cfg, ma2=dataclasses.replace(cfg.ma2, hardkey_transport="native"))
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    await client._dispatch(Press("STORE"))
    assert transport.sent[0]["requestType"] == "keyname"
    assert transport.sent[0]["keyname"] == "STORE"


async def test_unverified_hardkey_is_not_sent(make_config, caplog):
    cfg = _lua_config(make_config, verified=False)
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    with caplog.at_level("WARNING"):
        await client._dispatch(Press("STORE"))
    assert transport.sent == []
    assert "nicht verifiziert" in caplog.text


async def test_unverified_hardkeys_warn_at_start(make_config, caplog):
    cfg = _lua_config(make_config, verified=False)
    client = Ma2Client(cfg, transport=MockTransport())
    with caplog.at_level("WARNING"):
        client.warn_unverified_hardkeys()
    assert "STORE" in caplog.text


async def test_lua_device_loss_sends_exactly_one_release(make_config):
    cfg = _lua_config(make_config)
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(cfg, transport)
    await client.connect_once()
    engine = MappingEngine(cfg, client)
    client._sender_task = asyncio.create_task(client._sender_loop())
    engine.handle(InputEvent("key", "store_big", 1, "cherry"))
    engine.release_device("cherry")
    await wait_until(
        lambda: len([f for f in transport.sent if f.get("requestType") == "command"]) >= 2
    )
    commands = [f["command"] for f in transport.sent if f.get("requestType") == "command"]
    assert commands == [
        "LUA 'gma.canbus.hardkey(59, true, false)'",
        "LUA 'gma.canbus.hardkey(59, false, false)'",
    ]
    engine.cleanup(send=False)
    await client.shutdown()


async def test_lua_connection_loss_does_not_resend_release(make_config):
    cfg = _lua_config(make_config)
    transport = MockTransport()
    feed_handshake(transport)
    client = _client(cfg, transport)
    await client.connect_once()
    engine = MappingEngine(cfg, client)
    engine.handle(InputEvent("key", "store_big", 1, "cherry"))
    engine.on_connection_lost()
    engine.cleanup()
    assert engine.held == {}
    assert [f for f in transport.sent if f.get("requestType") == "command"] == []
    await client.shutdown()


async def test_unknown_hardkey_in_lua_path_is_dropped(make_config, caplog):
    cfg = _lua_config(make_config)
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    with caplog.at_level("ERROR"):
        await client._dispatch(Press("NOT_A_KEY"))
    assert transport.sent == []
    assert "Kein Keycode" in caplog.text


async def test_native_canbus_only_key_is_dropped(make_config, caplog):
    cfg = _lua_config(make_config)
    cfg = dataclasses.replace(cfg, ma2=dataclasses.replace(cfg.ma2, hardkey_transport="native"))
    transport = MockTransport()
    client = Ma2Client(cfg, transport=transport)
    client._session = 4
    client._authenticated = True
    with caplog.at_level("ERROR"):
        await client._dispatch(Press("CHANNEL"))
    assert transport.sent == []
    assert "keinen Web-Remote-Keyname" in caplog.text
