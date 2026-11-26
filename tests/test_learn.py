"""Tests for the key/encoder learn mode."""

from __future__ import annotations

import pytest

from ma2pi.events import InputEvent
from ma2pi.learn import LearnBusy, LearnManager
from ma2pi.mapping import MappingEngine


class Sink:
    def __init__(self) -> None:
        self.actions: list[tuple] = []

    def press(self, keyname: str, hold: bool = False) -> None:
        self.actions.append(("press", keyname))

    def release(self, keyname: str) -> None:
        self.actions.append(("release", keyname))

    def command(self, text: str) -> None:
        self.actions.append(("command", text))

    def encoder_slot(self, slot: int, delta: float, screen: bool = False) -> None:
        self.actions.append(("slot", slot, delta))

    def encoder_attribute(self, name: str, value: float) -> None:
        self.actions.append(("attribute", name, value))

    def toggle_screen_mode(self) -> None:
        self.actions.append(("screen_mode",))

    def toggle_fine(self, slot: int) -> None:
        self.actions.append(("fine", slot))

    def screen_shortcut(self, screen: int) -> None:
        self.actions.append(("screen", screen))


def key(control: str, value: int, device: str = "cherry-g86") -> InputEvent:
    return InputEvent("key", control, value, device)


def encoder(encoder_id: int, delta: int, device: str = "asl-mk2-e4b3") -> InputEvent:
    return InputEvent("encoder", f"encoder.{encoder_id}", delta, device)


def route(learner: LearnManager, engine: MappingEngine, event, now: float) -> None:
    """The production routing rule: learn owns input while a session is open."""

    if learner.active:
        learner.feed(event, now)
    else:
        engine.handle(event, now)


def test_key_capture_includes_logical_name_and_raw_code(config):
    learner = LearnManager(config)
    learner.start("key", now=0.0)

    result = learner.feed(key("fix", 1), now=0.1)

    assert result is not None
    assert result.status == "captured"
    assert result.control == "fix"
    assert result.device == "cherry-g86"
    assert result.raw == "KEY_HOME"
    assert learner.active is True  # still swallowing the matching key-up

    assert learner.feed(key("fix", 0), now=0.2) is None
    assert learner.active is False


def test_learn_suppresses_all_mapping_frames(config):
    sink = Sink()
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    learner = LearnManager(config)

    learner.start("key", now=0.0)
    route(learner, engine, key("ma", 1), 0.1)
    route(learner, engine, key("store_big", 1), 0.2)
    route(learner, engine, key("ma", 0), 0.3)
    route(learner, engine, key("store_big", 0), 0.4)

    assert sink.actions == []
    assert learner.active is False


def test_encoder_capture_collects_window(config):
    learner = LearnManager(config, encoder_window=2.0)
    learner.start("encoder", now=0.0)

    assert learner.feed(encoder(1, 1), now=0.1) is None
    assert learner.feed(encoder(1, 1), now=0.5) is None
    assert learner.active is True

    result = learner.poll(now=2.1)

    assert result is not None
    assert result.status == "captured"
    assert result.control == "encoder.1"
    assert result.raw == "note 1"
    assert result.direction == 1
    assert result.detents == 2
    assert learner.active is False


def test_encoder_direction_is_negative(config):
    learner = LearnManager(config)
    learner.start("encoder", now=0.0)
    learner.feed(encoder(2, -1), now=0.1)
    result = learner.poll(now=2.1)

    assert result is not None
    assert result.direction == -1
    assert result.detents == 1


def test_learn_times_out_without_input(config):
    learner = LearnManager(config, timeout=15.0)
    learner.start("key", now=0.0)

    result = learner.poll(now=15.0)

    assert result is not None
    assert result.status == "timeout"
    assert result.timed_out is True
    assert learner.active is False


def test_encoder_learn_times_out_without_input(config):
    learner = LearnManager(config)
    learner.start("encoder", now=0.0)
    result = learner.poll(now=15.0)

    assert result is not None
    assert result.status == "timeout"


def test_only_one_session_at_a_time(config):
    learner = LearnManager(config)
    learner.start("key", now=0.0)

    with pytest.raises(LearnBusy):
        learner.start("encoder", now=0.1)


def test_cancel_restores_normal_operation_without_result(config):
    learner = LearnManager(config)
    learner.start("key", now=0.0)

    result = learner.cancel(now=0.1)

    assert result is not None
    assert result.status == "cancelled"
    assert learner.active is False
    assert learner.poll(now=0.2) is None


def test_device_filter_ignores_other_devices(config):
    learner = LearnManager(config)
    learner.start("key", device="cherry-g86", now=0.0)

    assert learner.feed(key("asl_bank", 1, "asl-mk2-e4b3"), now=0.1) is None
    assert learner.active is True

    result = learner.feed(key("fix", 1, "cherry-g86"), now=0.2)
    assert result is not None
    assert result.control == "fix"


def test_not_learning_returns_none(config):
    learner = LearnManager(config)
    assert learner.feed(key("fix", 1), now=0.0) is None
    assert learner.poll(now=1.0) is None
