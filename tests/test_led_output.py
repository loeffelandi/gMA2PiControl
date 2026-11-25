"""Tests for the ASL RGB LED output and its configuration."""

from __future__ import annotations

import pytest

from ma2pi.led_output import (
    DISABLE,
    ENABLE,
    LedOutput,
    LedSettings,
    note_on,
    parse_color,
)


def test_note_on_bytes():
    assert note_on(1, 9, 127) == bytes([0x90, 9, 127])
    assert note_on(2, 10, 0x30) == bytes([0x91, 10, 48])
    assert note_on(3, 11, 0x08) == bytes([0x92, 11, 8])
    assert note_on(16, 127, 127) == ENABLE


def test_parse_color_names_and_triples():
    assert parse_color("red") == (127, 0, 0)
    assert parse_color("GREEN") == (0, 127, 0)
    assert parse_color([10, 20, 30]) == (10, 20, 30)
    with pytest.raises(ValueError):
        parse_color("pink")
    with pytest.raises(ValueError):
        parse_color([0, 0, 200])


def test_led_output_writes_frames(tmp_path):
    path = tmp_path / "led.mid"
    path.touch()
    led = LedOutput(path, LedSettings(note=9))
    led.open()
    led.enable()
    led.set_color((127, 0, 0))
    led.apply_mode(True)
    led.close()

    data = path.read_bytes()
    assert data.startswith(ENABLE)
    assert note_on(1, 9, 127) + note_on(2, 9, 0) + note_on(3, 9, 0) in data
    assert note_on(1, 9, 0) + note_on(2, 9, 127) + note_on(3, 9, 0) in data
    assert data.endswith(DISABLE)


def test_led_output_writes_are_optional(tmp_path):
    led = LedOutput(tmp_path / "missing.mid", LedSettings())
    # Not open: must not raise.
    led.enable()
    led.set_color((0, 0, 0))
    led.close()


def test_led_config_defaults(make_config):
    cfg = make_config(lambda data: data.pop("led"))
    assert cfg.led.enabled is False
    assert cfg.led.note == 9
    assert cfg.led.attribute_color == (127, 0, 0)
    assert cfg.led.screen_color == (0, 127, 0)
    assert (cfg.led.red_channel, cfg.led.green_channel, cfg.led.blue_channel) == (1, 2, 3)


def test_led_config_parses_colors_and_channels(make_config):
    cfg = make_config(
        lambda data: data["led"].update(
            {"attribute_color": [10, 20, 30], "red_channel": 4, "green_channel": 5, "blue_channel": 6}
        )
    )
    assert cfg.led.attribute_color == (10, 20, 30)
    assert cfg.led.red_channel == 4


def test_led_config_rejects_duplicate_channels(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError, match="verschieden"):
        make_config(
            lambda data: data["led"].update({"green_channel": 1})
        )


def test_led_config_rejects_unknown_color(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["led"].update({"screen_color": "pink"}))
