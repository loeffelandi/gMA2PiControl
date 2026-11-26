"""Tests for validated hot reload and generation tracking."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ma2pi.config import ConfigError, load_config, parse_config
from ma2pi.config_store import ConfigPaths
from ma2pi.events import InputEvent
from ma2pi.mapping import MappingEngine
from ma2pi.runtime import ApplyBusy, ConfigStore

ROOT = Path(__file__).resolve().parents[1]


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


def _setup(
    tmp_path: Path, *, validate=None
) -> tuple[ConfigPaths, ConfigStore, MappingEngine, Sink]:
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    paths.state_dir.mkdir(parents=True)
    shutil.copy(ROOT / "config.toml", paths.config)
    config = load_config(paths.config)
    sink = Sink()
    engine = MappingEngine(config, sink, clock=lambda: 0.0)
    store = ConfigStore(config, engine, paths, validate=validate)
    return paths, store, engine, sink


def _key(control: str, value: int) -> InputEvent:
    return InputEvent("key", control, value, "cherry")


def _encoder(encoder_id: int, delta: int) -> InputEvent:
    return InputEvent("encoder", f"encoder.{encoder_id}", delta, "asl")


async def test_apply_releases_held_keys_reverse_and_bumps_generation(tmp_path):
    paths, store, engine, sink = _setup(tmp_path)
    assert store.generation == 0

    engine.handle(_key("ma", 1))
    engine.handle(_key("store_big", 1))

    await store.apply({"logging": {"level": "DEBUG"}})

    releases = [action for action in sink.actions if action[0] == "release"]
    assert releases == [("release", "STORE"), ("release", "MA")]
    assert engine.held == {}
    assert store.generation == 1
    assert store.config.logging.level == "DEBUG"
    assert engine.config is store.config
    assert load_config(paths.config).logging.level == "DEBUG"


async def test_apply_discards_open_encoder_delta(tmp_path):
    _, store, engine, sink = _setup(tmp_path)

    engine.handle(_encoder(1, 5), now=0.0)
    assert engine.pending_for(1) == 5

    await store.apply({"logging": {"level": "DEBUG"}})

    assert engine.pending_for(1) == 0
    assert not [action for action in sink.actions if action[0] in ("slot", "attribute")]


async def test_apply_rejects_invalid_patch_without_changing_anything(tmp_path):
    paths, store, engine, sink = _setup(tmp_path)
    before = paths.config.read_bytes()
    active = engine.config

    with pytest.raises(ConfigError):
        await store.apply({"ma2": {"port": 70000}})

    assert paths.config.read_bytes() == before
    assert store.generation == 0
    assert engine.config is active
    assert not engine.frozen
    assert sink.actions == []


async def test_apply_validates_with_daemon_rules(tmp_path):
    seen: dict[str, bool] = {}

    def validate(raw):
        # The lock is held for the whole apply, so a second caller can be
        # rejected instead of racing the file and the mapping swap.
        seen["busy"] = store.busy
        return parse_config(raw, source_path="<test>")

    _, store, _, _ = _setup(tmp_path, validate=validate)
    await store.apply({"logging": {"level": "INFO"}})

    assert seen["busy"] is True


async def test_apply_rejects_second_call_while_busy(tmp_path):
    _, store, _, _ = _setup(tmp_path)

    async with store._lock:
        with pytest.raises(ApplyBusy):
            await store.apply({"logging": {"level": "DEBUG"}})

    assert store.generation == 0


async def test_engine_frozen_discards_input_and_flushes(tmp_path):
    _, _, engine, sink = _setup(tmp_path)

    engine.freeze()
    engine.handle(_key("fix", 1))
    engine.handle(_encoder(1, 1), now=0.0)
    engine.flush_due(10.0)
    engine.flush_all(10.0)

    assert engine.frozen is True
    assert engine.held == {}
    assert engine.pending_for(1) == 0
    assert sink.actions == []

    engine.unfreeze()
    engine.handle(_key("fix", 1))
    assert sink.actions == [("press", "FIX")]
