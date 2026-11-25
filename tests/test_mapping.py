from __future__ import annotations

import pytest

from ma2pi.events import InputEvent
from ma2pi.mapping import MappingEngine


class Sink:
    def __init__(self) -> None:
        self.actions: list[tuple] = []

    def press(self, hardkey_id: int, hold: bool = False) -> None:
        self.actions.append(("press", hardkey_id))

    def release(self, hardkey_id: int) -> None:
        self.actions.append(("release", hardkey_id))

    def command(self, text: str) -> None:
        self.actions.append(("command", text))

    def encoder_slot(self, slot: int, delta: float) -> None:
        self.actions.append(("slot", slot, delta))

    def encoder_attribute(self, name: str, value: float) -> None:
        self.actions.append(("attribute", name, value))

    def toggle_screen_mode(self) -> None:
        self.actions.append(("screen_mode",))

    def toggle_fine(self, slot: int) -> None:
        self.actions.append(("fine", slot))

    def screen_shortcut(self, screen: int) -> None:
        self.actions.append(("screen", screen))


@pytest.fixture
def sink() -> Sink:
    return Sink()


@pytest.fixture
def flat_config(make_config):
    return make_config(
        lambda data: data["mapping"]["encoder_acceleration"].__setitem__("curve", "none")
    )


@pytest.fixture
def engine(flat_config, sink) -> MappingEngine:
    return MappingEngine(flat_config, sink, clock=lambda: 0.0)


def key(control: str, value: int, device: str = "cherry") -> InputEvent:
    return InputEvent("key", control, value, device)


def encoder(encoder_id: int, delta: int) -> InputEvent:
    return InputEvent("encoder", f"encoder.{encoder_id}", delta, "asl")


def test_tap(engine, sink):
    engine.handle(key("fix", 1))
    engine.handle(key("fix", 0))
    assert sink.actions == [("press", "FIX"), ("release", "FIX")]


def test_hold_has_one_press_and_one_release(engine, sink):
    engine.handle(key("store_big", 1))
    engine.handle(key("store_big", 1))  # duplicate
    engine.handle(key("store_big", 0))
    engine.handle(key("store_big", 0))  # orphan
    assert sink.actions == [("press", "STORE"), ("release", "STORE")]


def test_release_without_press_is_ignored(engine, sink):
    engine.handle(key("fix", 0))
    assert sink.actions == []


def test_modifier_chord_order(engine, sink):
    engine.handle(key("ma", 1))
    engine.handle(key("fix", 1))
    engine.handle(key("fix", 0))
    engine.handle(key("ma", 0))
    assert sink.actions == [
        ("press", "MA"),
        ("press", "MA"),
        ("press", "FIX"),
        ("release", "FIX"),
        ("release", "MA"),
    ]


def test_desk_lock_acceptance(engine, sink):
    # MA held + Fix tapped is Desk Lock on the onPC.
    engine.handle(key("ma", 1))
    engine.handle(key("fix", 1))
    engine.handle(key("fix", 0))
    engine.handle(key("ma", 0))
    assert len(sink.actions) == 5
    assert sink.actions == [
        ("press", "MA"),
        ("press", "MA"),
        ("press", "FIX"),
        ("release", "FIX"),
        ("release", "MA"),
    ]


def test_cleanup_releases_in_reverse_order(engine, sink):
    engine.handle(key("ma", 1))
    engine.handle(key("store_big", 1))
    engine.handle(key("fix", 1))
    engine.cleanup()
    assert sink.actions == [
        ("press", "MA"),
        ("press", "MA"),
        ("press", "STORE"),
        ("press", "FIX"),
        ("release", "FIX"),
        ("release", "STORE"),
        ("release", "MA"),
    ]
    assert engine.held == {}


def test_cmd_key_only_sends_on_press(make_config, sink):
    config = make_config(
        lambda data: data["mapping"]["keys"].__setitem__(
            "oops", {"command": "Clear All"}
        )
    )
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    engine.handle(key("oops", 1))
    engine.handle(key("oops", 0))
    assert sink.actions == [("command", "Clear All")]


def test_cmd_key_preserves_semicolon_sequence(make_config, sink):
    config = make_config(
        lambda data: data["mapping"]["keys"].__setitem__(
            "oops", {"command": "Clear; Store"}
        )
    )
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    engine.handle(key("oops", 1))
    engine.handle(key("oops", 0))
    assert sink.actions == [("command", "Clear; Store")]


def test_screen_key_sends_shortcut_on_press_only(make_config, sink):
    config = make_config(
        lambda data: data["mapping"]["keys"].__setitem__("oops", {"screen": 2})
    )
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    engine.handle(key("oops", 1))
    engine.handle(key("oops", 0))
    assert sink.actions == [("screen", 2)]
    assert engine.held == {}


def test_unmapped_control_is_logged_once(engine, sink, caplog):
    with caplog.at_level("DEBUG"):
        engine.handle(key("unknown", 1))
        engine.handle(key("unknown", 1))
    assert sink.actions == []
    assert caplog.text.count("unmapptes Control") == 2  # debug path, no frame


def test_unmapped_control_sends_nothing(engine, sink):
    engine.handle(key("unknown", 1))
    assert sink.actions == []


def test_device_loss_releases_only_that_device(engine, sink):
    engine.handle(key("ma", 1, "cherry"))
    engine.handle(key("asl_click_1", 1, "asl"))
    engine.release_device("cherry")
    assert ("press", "MA") in sink.actions
    assert ("release", "MA") in sink.actions
    assert "ma" not in engine.held
    assert "asl_click_1" in engine.held


def test_connection_lost_clears_without_replay(engine, sink):
    engine.handle(key("ma", 1))
    engine.on_connection_lost()
    assert sink.actions == [("press", "MA"), ("press", "MA")]
    assert engine.held == {}
    engine.handle(key("ma", 0))
    assert sink.actions == [("press", "MA"), ("press", "MA")]


def test_slot_accumulates_and_flushes_once(engine, sink):
    for _ in range(10):
        engine.handle(encoder(1, 1), now=0.0)
    assert engine.pending_for(1) == 10
    engine.flush_due(0.041)
    assert sink.actions == [("slot", 1, pytest.approx(10.0))]
    assert engine.pending_for(1) == 0


def test_zero_delta_sends_nothing(engine, sink):
    engine.handle(encoder(1, 1), now=0.0)
    engine.handle(encoder(1, -1), now=0.0)
    engine.flush_due(0.1)
    assert sink.actions == []


def test_idle_flush_sends_last_detent(engine, sink):
    engine.handle(encoder(1, 1), now=0.0)
    engine.flush_due(0.01)
    assert sink.actions == []
    engine.flush_due(0.05)
    assert sink.actions == [("slot", 1, pytest.approx(1.0))]


def test_min_interval_between_flushes(engine, sink):
    engine.handle(encoder(1, 1), now=0.0)
    engine.flush_due(0.05)
    assert sink.actions == [("slot", 1, pytest.approx(1.0))]
    engine.handle(encoder(1, 1), now=0.05)
    engine.flush_due(0.06)
    assert sink.actions == [("slot", 1, pytest.approx(1.0))]
    engine.flush_due(0.091)
    assert sink.actions == [
        ("slot", 1, pytest.approx(1.0)),
        ("slot", 1, pytest.approx(1.0)),
    ]


def test_each_slot_is_separate(engine, sink):
    engine.handle(encoder(1, 1), now=0.0)
    engine.handle(encoder(4, -1), now=0.0)
    engine.flush_all(0.05)
    assert ("slot", 1, pytest.approx(1.0)) in sink.actions
    assert ("slot", 4, pytest.approx(-1.0)) in sink.actions


def test_encoder_click_toggles_fine(engine, sink):
    engine.handle(key("asl_click_1", 1))
    engine.handle(key("asl_click_1", 0))
    assert sink.actions == [("fine", 1)]


def test_screen_mode_key_toggles(engine, sink):
    engine.handle(key("asl_bank", 1))
    engine.handle(key("asl_bank", 0))
    assert sink.actions == [("screen_mode",)]


def test_acceleration_increases_delta_for_fast_rotation(config, sink):
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    engine.handle(encoder(2, 1), now=0.0)
    engine.flush_due(0.05)
    slow = sink.actions[-1][2]
    sink.actions.clear()
    for _ in range(5):
        engine.handle(encoder(2, 1), now=1.0)
    engine.flush_due(1.05)
    fast = sink.actions[-1][2]
    assert fast > slow
    assert fast > 5


def test_acceleration_keeps_sign(config, sink):
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    for _ in range(5):
        engine.handle(encoder(2, -1), now=0.0)
    engine.flush_due(0.05)
    value = sink.actions[-1][2]
    assert value < 0


def test_fixed_attribute_encoder_is_supported(make_config, sink):
    def mutate(data):
        data["mapping"]["encoders"][1] = {"id": 2, "attribute": "PAN"}
        data["mapping"]["encoder_acceleration"]["curve"] = "none"

    engine = MappingEngine(make_config(mutate), sink, clock=lambda: 0.0)
    engine.handle(encoder(2, 1), now=0.0)
    engine.flush_due(0.05)
    assert sink.actions == [("attribute", "PAN", pytest.approx(1.0))]


def test_pending_delta_is_capped(make_config, sink):
    def mutate(data):
        data["rate_limit"]["max_pending_delta"] = 5
        data["mapping"]["encoder_acceleration"]["curve"] = "none"

    engine = MappingEngine(make_config(mutate), sink, clock=lambda: 0.0)
    for _ in range(100):
        engine.handle(encoder(1, 1), now=0.0)
    assert engine.pending_for(1) == 5


def test_stress_100_detents_per_second(make_config, sink):
    def mutate(data):
        data["mapping"]["encoder_acceleration"]["curve"] = "none"
        data["rate_limit"]["max_pending_delta"] = 10_000

    engine = MappingEngine(make_config(mutate), sink, clock=lambda: 0.0)
    t = 0.0
    for step in range(10_000):  # 10 s at 1 ms resolution
        t = step / 1000.0
        if step % 10 == 0:
            engine.handle(encoder(1, 1), now=t)
        engine.flush_due(t)
    engine.flush_due(t + 1.0)
    frames = [action for action in sink.actions if action[0] == "slot"]
    ticks = sum(action[2] for action in frames)
    assert ticks == pytest.approx(1000.0)
    assert len(frames) <= 260  # roughly 25/s, never unbounded


class HoldSink:
    """Records the hold flag so tap/hold behaviour can be asserted."""

    def __init__(self) -> None:
        self.actions: list[tuple] = []

    def press(self, keyname: str, hold: bool = False) -> None:
        self.actions.append(("press", keyname, hold))

    def release(self, keyname: str) -> None:
        self.actions.append(("release", keyname))

    def command(self, text: str) -> None:
        self.actions.append(("command", text))

    def encoder_slot(self, slot: int, delta: float) -> None:
        self.actions.append(("slot", slot, delta))

    def encoder_attribute(self, name: str, value: float) -> None:
        self.actions.append(("attribute", name, value))

    def toggle_screen_mode(self) -> None:
        self.actions.append(("screen_mode",))

    def toggle_fine(self, slot: int) -> None:
        self.actions.append(("fine", slot))


def _hold_engine(make_config, sink, now):
    cfg = make_config(lambda d: d["ma2"].__setitem__("hardkey_hold_threshold", 0.3))
    return MappingEngine(cfg, sink, clock=lambda: now[0])


def test_tap_does_not_upgrade_to_hold(make_config):
    sink = HoldSink()
    now = [0.0]
    engine = _hold_engine(make_config, sink, now)
    engine.handle(key("store_big", 1))
    now[0] = 0.1
    engine.handle(key("store_big", 0))
    engine.flush_hold_upgrades(now[0])
    assert sink.actions == [("press", "STORE", False), ("release", "STORE")]


def test_hold_upgrades_after_threshold(make_config):
    sink = HoldSink()
    now = [0.0]
    engine = _hold_engine(make_config, sink, now)
    engine.handle(key("store_big", 1))
    assert sink.actions == [("press", "STORE", False)]
    now[0] = 0.2
    assert engine.flush_hold_upgrades(now[0]) == 0
    now[0] = 0.35
    assert engine.flush_hold_upgrades(now[0]) == 1
    assert sink.actions == [("press", "STORE", False), ("press", "STORE", True)]
    # Only one upgrade even if flushed again.
    now[0] = 0.5
    assert engine.flush_hold_upgrades(now[0]) == 0
    engine.handle(key("store_big", 0))
    assert sink.actions[-1] == ("release", "STORE")


def test_modifier_presses_as_held_immediately(make_config):
    sink = HoldSink()
    now = [0.0]
    engine = _hold_engine(make_config, sink, now)
    engine.handle(key("ma", 1))
    assert sink.actions == [("press", "MA", False), ("press", "MA", True)]
    engine.handle(key("ma", 0))
    assert sink.actions[-1] == ("release", "MA")


def test_native_transport_has_no_hold_upgrade(make_config):
    sink = HoldSink()
    now = [0.0]
    cfg = make_config(lambda d: d["ma2"].__setitem__("hardkey_transport", "native"))
    engine = MappingEngine(cfg, sink, clock=lambda: now[0])
    engine.handle(key("store_big", 1))
    now[0] = 1.0
    assert engine.flush_hold_upgrades(now[0]) == 0
    engine.handle(key("store_big", 0))
    assert sink.actions == [("press", "STORE", False), ("release", "STORE")]
