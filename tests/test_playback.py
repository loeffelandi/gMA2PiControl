from __future__ import annotations

import asyncio
import dataclasses

import pytest

from ma2pi.__main__ import _process_input
from ma2pi.events import InputEvent
from ma2pi.mapping import MappingEngine
from ma2pi.playback import PlaybackRouter


class FakeClient:
    def __init__(self) -> None:
        self.buttons: list[tuple[int, int, int, bool]] = []
        self.faders: list[tuple[int, int, float]] = []

    def playback_button(
        self, page: int, executor: int, button: int, pressed: bool
    ) -> None:
        self.buttons.append((page, executor, button, pressed))

    def playback_fader(self, page: int, executor: int, value: float) -> None:
        self.faders.append((page, executor, value))

    def press(self, keyname: str, hold: bool = False) -> None:
        pass

    def release(self, keyname: str) -> None:
        pass


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _accelerated_router(make_config, *, accelerated: bool = True):
    config = _config(
        make_config,
        {
            "mc_encoder_1": {
                "page": 1,
                "executor": 1,
                "kind": "fader",
                "accelerated": accelerated,
            }
        },
    )
    client = FakeClient()
    engine = MappingEngine(config, client)
    clock = FakeClock()
    return PlaybackRouter(engine, client, clock=clock), engine, client, clock


def _config(make_config, entries):
    def mutate(data):
        data["mapping"]["playbacks"] = entries

    return make_config(mutate)


def test_router_button_target(make_config):
    config = _config(
        make_config,
        {"mc_click_1": {"page": 2, "executor": 7, "kind": "button", "button": 2}},
    )
    client = FakeClient()
    router = PlaybackRouter(MappingEngine(config, client), client)

    assert router.handle(InputEvent("key", "mc_click_1", 1, "midicraft")) is True
    assert router.handle(InputEvent("key", "mc_click_1", 0, "midicraft")) is True
    assert client.buttons == [(2, 7, 2, True), (2, 7, 2, False)]
    assert client.faders == []


def test_router_fader_target_deduplicates(make_config):
    config = _config(
        make_config,
        {"mc_fader_1": {"page": 1, "executor": 3, "kind": "fader"}},
    )
    client = FakeClient()
    router = PlaybackRouter(MappingEngine(config, client), client)

    assert router.handle(InputEvent("value", "mc_fader_1", 0.5, "midicraft")) is True
    assert router.handle(InputEvent("value", "mc_fader_1", 0.5, "midicraft")) is True
    assert router.handle(InputEvent("value", "mc_fader_1", 0.25, "midicraft")) is True
    assert client.faders == [(1, 3, 0.5), (1, 3, 0.25)]


def test_router_clamps_and_passes_through_unknown_controls(make_config):
    config = _config(
        make_config,
        {"mc_fader_1": {"page": 1, "executor": 3, "kind": "fader"}},
    )
    client = FakeClient()
    router = PlaybackRouter(MappingEngine(config, client), client)

    assert router.handle(InputEvent("value", "mc_fader_1", 2.0, "midicraft")) is True
    assert client.faders == [(1, 3, 1.0)]
    assert router.handle(InputEvent("key", "asl_bank", 1, "asl")) is False


def test_router_rejects_mismatched_event_kind(make_config, caplog):
    config = _config(
        make_config,
        {"mc_click_1": {"page": 1, "executor": 1, "kind": "button"}},
    )
    client = FakeClient()
    router = PlaybackRouter(MappingEngine(config, client), client)

    assert router.handle(InputEvent("value", "mc_click_1", 0.5, "midicraft")) is True
    assert router.handle(InputEvent("value", "mc_click_1", 0.6, "midicraft")) is True
    assert client.buttons == []
    assert caplog.text.count("erwartet einen Tastenwert") == 1


def test_router_slow_encoder_movement_stays_one_to_one(make_config):
    router, _, client, clock = _accelerated_router(make_config)
    assert router.handle(InputEvent("value", "mc_encoder_1", 0.0, "midicraft")) is True
    clock.now += 0.5
    assert router.handle(InputEvent("value", "mc_encoder_1", 1 / 127, "midicraft")) is True
    clock.now += 0.5
    assert router.handle(InputEvent("value", "mc_encoder_1", 2 / 127, "midicraft")) is True
    assert [value for _, _, value in client.faders] == pytest.approx(
        [0.0, 1 / 127, 2 / 127]
    )


def test_router_fast_encoder_movement_is_amplified(make_config):
    router, _, client, clock = _accelerated_router(make_config)
    router.handle(InputEvent("value", "mc_encoder_1", 0.0, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 1 / 127, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 2 / 127, "midicraft"))

    assert client.faders[-1][2] > 2 / 127
    assert client.faders[-1][2] == pytest.approx(2.875 / 127)


def test_router_encoder_without_opt_in_stays_raw(make_config):
    router, _, client, clock = _accelerated_router(make_config, accelerated=False)
    router.handle(InputEvent("value", "mc_encoder_1", 0.0, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 1 / 127, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 2 / 127, "midicraft"))

    assert client.faders[-1][2] == pytest.approx(2 / 127)


def test_router_acceleration_is_per_control(make_config):
    config = _config(
        make_config,
        {
            "mc_encoder_1": {
                "page": 1,
                "executor": 1,
                "kind": "fader",
                "accelerated": True,
            },
            "mc_encoder_2": {
                "page": 1,
                "executor": 2,
                "kind": "fader",
                "accelerated": True,
            },
        },
    )
    client = FakeClient()
    clock = FakeClock()
    router = PlaybackRouter(MappingEngine(config, client), client, clock=clock)

    router.handle(InputEvent("value", "mc_encoder_1", 0.0, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 1 / 127, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 2 / 127, "midicraft"))

    router.handle(InputEvent("value", "mc_encoder_2", 0.0, "midicraft"))
    clock.now += 0.5
    router.handle(InputEvent("value", "mc_encoder_2", 1 / 127, "midicraft"))

    fast = [value for _, executor, value in client.faders if executor == 1][-1]
    slow = [value for _, executor, value in client.faders if executor == 2][-1]
    assert fast > slow


def test_router_resets_acceleration_on_config_change(make_config):
    router, engine, client, clock = _accelerated_router(make_config)
    config = engine.config
    router.handle(InputEvent("value", "mc_encoder_1", 0.0, "midicraft"))
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 1 / 127, "midicraft"))

    mapping = dataclasses.replace(
        config.mapping, playbacks=dict(config.mapping.playbacks)
    )
    engine.config = dataclasses.replace(config, mapping=mapping)
    clock.now += 0.01
    router.handle(InputEvent("value", "mc_encoder_1", 0.7, "midicraft"))

    assert client.faders[-1][2] == pytest.approx(0.7)


def test_router_accelerated_encoder_reaches_both_ends(make_config):
    router, _, client, clock = _accelerated_router(make_config)
    for step in range(128):
        clock.now = step * 0.01
        router.handle(InputEvent("value", "mc_encoder_1", step / 127, "midicraft"))
    assert client.faders[-1][2] == pytest.approx(1.0)

    for step in range(126, -1, -1):
        clock.now += 0.01
        router.handle(InputEvent("value", "mc_encoder_1", step / 127, "midicraft"))
    assert client.faders[-1][2] == pytest.approx(0.0)


async def test_process_input_gives_playback_precedence(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {
            "mc_click_1": {"page": 1, "executor": 1, "kind": "button"}
        }
        data["mapping"]["keys"]["mc_click_1"] = {"hardkey": "STORE"}

    config = make_config(mutate)
    client = FakeClient()

    class StubEngine:
        def __init__(self):
            self.config = config
            self.handled = []

        def handle(self, item):
            self.handled.append(item)

        def release_device(self, device):
            pass

    class StubLearn:
        active = False

    engine = StubEngine()
    router = PlaybackRouter(engine, client)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_process_input(queue, engine, StubLearn(), None, router))
    try:
        await queue.put(InputEvent("key", "mc_click_1", 1, "midicraft"))
        while not client.buttons:
            await asyncio.sleep(0.005)
        assert client.buttons == [(1, 1, 1, True)]
        assert engine.handled == []

        await queue.put(InputEvent("key", "asl_bank", 1, "asl"))
        while not engine.handled:
            await asyncio.sleep(0.005)
        assert engine.handled == [InputEvent("key", "asl_bank", 1, "asl")]
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class BankingClient(FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.commands: list[str] = []

    def command(self, text: str) -> None:
        self.commands.append(text)


def _bank_playback_config(make_config, layer=None):
    def mutate(data):
        data["led"]["enabled"] = False
        data["profiles"]["bank-test"] = {
            "controls": [
                {"id": "bt_fader", "kind": "fader"},
                {"id": "bt_button", "kind": "button"},
                {"id": "bt_encoder", "kind": "encoder"},
            ],
            "banks": [
                {"number": 1, "notes": {"70": "bt_fader", "55": "bt_button", "60": "bt_encoder"}},
                {"number": 2, "notes": {"15": "bt_fader", "55": "bt_button", "10": "bt_encoder"}},
            ],
        }
        data["devices"]["banktest"] = {
            "backend": "midi",
            "vendor_id": 0x04D8,
            "product_id": 0x1234,
            "name_contains": "Bank Test",
            "profile": "bank-test",
        }
        data["mapping"]["playbacks"] = {
            "bt_fader": {"page": 1, "executor": 1, "kind": "fader"},
            "bt_button": {"page": 1, "executor": 10, "kind": "button", "button": 2},
        }
        data["mapping"]["device_banks"] = {
            "banktest": {"bank_size": 5, "2": layer or {}}
        }

    return make_config(mutate)


def _router(make_config, layer=None):
    config = _bank_playback_config(make_config, layer)
    client = BankingClient()
    engine = MappingEngine(config, client)
    return PlaybackRouter(engine, client), client, engine


def test_bank_offset_applies_to_inherited_executor(make_config):
    router, client, _ = _router(make_config)
    assert router.handle(InputEvent("value", "bt_fader", 0.5, "banktest", 2))
    assert client.faders == [(1, 6, 0.5)]


def test_bank_override_wins_without_offset(make_config):
    router, client, _ = _router(
        make_config, {"playbacks": {"bt_fader": {"executor": 20}}}
    )
    assert router.handle(InputEvent("value", "bt_fader", 0.5, "banktest", 2))
    assert client.faders == [(1, 20, 0.5)]


def test_button_number_stays_with_offset(make_config):
    router, client, _ = _router(make_config)
    assert router.handle(InputEvent("key", "bt_button", 1, "banktest", 2))
    assert client.buttons == [(1, 15, 2, True)]


def test_ma_page_binding_disables_offset_and_sends_once(make_config):
    router, client, _ = _router(make_config, {"ma_page": 4})
    assert router.handle(InputEvent("value", "bt_fader", 0.5, "banktest", 2))
    assert client.faders == [(1, 1, 0.5)]
    assert client.commands == ["Page 4"]
    assert router.handle(InputEvent("value", "bt_fader", 0.6, "banktest", 2))
    assert client.commands == ["Page 4"]


def test_partial_bank_override_still_receives_offset(make_config):
    router, client, _ = _router(
        make_config, {"playbacks": {"bt_fader": {"kind": "fader"}}}
    )
    assert router.handle(InputEvent("value", "bt_fader", 0.5, "banktest", 2))
    assert client.faders == [(1, 6, 0.5)]


def test_bank_key_override_takes_precedence_over_global_playback(make_config):
    router, client, _ = _router(
        make_config, {"keys": {"bt_button": {"hardkey": "BLACKOUT"}}}
    )
    assert not router.handle(InputEvent("key", "bt_button", 1, "banktest", 2))
    assert client.buttons == []


def test_playback_button_release_after_bank_switch_and_device_lost(make_config):
    router, client, engine = _router(
        make_config, {"keys": {"bt_button": {"hardkey": "BLACKOUT"}}}
    )
    # Press on Bank 1 (Exec 2) -> switch to Bank 2 -> release still hits Exec 2!
    assert router.handle(InputEvent("key", "bt_button", 1, "banktest", 1)) is True
    assert router.handle(InputEvent("key", "bt_button", 0, "banktest", 2)) is True
    assert client.buttons == [(1, 10, 2, True), (1, 10, 2, False)]

    # Press on Bank 2 (Hardkey BLACKOUT in engine) -> switch to Bank 1 -> release
    # must pass through PlaybackRouter so engine releases BLACKOUT!
    ev_press = InputEvent("key", "bt_button", 1, "banktest", 2)
    assert router.handle(ev_press) is False
    engine.handle(ev_press)
    assert ("banktest", "bt_button") in engine.held
    ev_rel = InputEvent("key", "bt_button", 0, "banktest", 1)
    assert router.handle(ev_rel) is False
    engine.handle(ev_rel)
    assert engine.held == {}

    # DeviceLost releases held playback button
    client.buttons.clear()
    router.handle(InputEvent("key", "bt_button", 1, "banktest", 1))
    router.release_device("banktest")
    assert client.buttons == [(1, 10, 2, True), (1, 10, 2, False)]


def test_acceleration_separates_banks_and_emits_no_info_log(make_config, caplog):
    router, _, client, clock = _accelerated_router(make_config)
    with caplog.at_level("INFO", logger="ma2pi.playback"):
        router.handle(InputEvent("value", "mc_encoder_1", 1.0, "midicraft", bank=1))
        clock.now += 0.01
        router.handle(InputEvent("value", "mc_encoder_1", 0.2, "midicraft", bank=2))
    # Bank 2 starts cleanly at 0.2 instead of amplifying -0.8 against Bank 1!
    assert client.faders[-1][2] == pytest.approx(0.2)
    assert caplog.records == []


def test_unpaired_key_up_after_connection_loss_sends_no_orphan_release(make_config):
    router, client, _ = _router(make_config, {"ma_page": 4})
    router.handle(InputEvent("key", "bt_button", 1, "banktest", 1))
    assert len(client.buttons) == 1
    router.on_connection_lost()
    client.buttons.clear()
    client.commands.clear()

    assert router.handle(InputEvent("key", "bt_button", 0, "banktest", 2)) is True
    assert client.buttons == []
    assert client.commands == []
