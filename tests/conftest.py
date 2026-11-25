from __future__ import annotations

import copy
import dataclasses
import tomllib
from pathlib import Path

import pytest

from ma2pi.config import AppConfig, load_config, parse_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.toml"


@pytest.fixture
def config() -> AppConfig:
    return load_config(CONFIG_PATH)


@pytest.fixture
def raw_config() -> dict:
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


@pytest.fixture
def make_config(raw_config):
    def _make(mutator=None) -> AppConfig:
        data = copy.deepcopy(raw_config)
        if mutator is not None:
            mutator(data)
        return parse_config(data, source_path="<test>")

    return _make


@pytest.fixture
def small_config(make_config) -> AppConfig:
    """A fast client config with a fake password source."""

    def mutate(data):
        data["ma2"]["host"] = "127.0.0.1"
        data["ma2"]["port"] = 9
        data["ma2"]["password_file"] = None
        data["ma2"]["password_env"] = "MA2PI_TEST_PASSWORD"
        data["ma2"]["keepalive_interval"] = 0.05
        data["reconnect"]["initial_delay"] = 0.01
        data["reconnect"]["max_delay"] = 0.05
        data["reconnect"]["jitter"] = 0.0
        data["reconnect"]["login_failure_delay"] = 0.02
        data["rate_limit"]["messages_per_second"] = 40
        data["rate_limit"]["burst"] = 50

    return make_config(mutate)


@pytest.fixture(autouse=True)
def test_password(monkeypatch):
    monkeypatch.setenv("MA2PI_TEST_PASSWORD", "secret")
