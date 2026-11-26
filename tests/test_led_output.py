"""Tests for the ASL LED output (brightness + colour index) and its configuration."""

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
    assert note_on(16, 127, 127) == ENABLE


def test_parse_color_names_and_indices():
    assert parse_color("red") == 48
    assert parse_color("GREEN") == 8
    assert parse_color("white") == 127
    assert parse_color(33) == 33
    with pytest.raises(ValueError):
        parse_color("pink")
    with pytest.raises(ValueError):
        parse_color(200)
    with pytest.raises(ValueError):
        parse_color([10, 20, 30])


def test_led_output_writes_frames(tmp_path):
    path = tmp_path / "led.mid"
    path.touch()
    led = LedOutput(path, LedSettings(note=9))
    led.open()
    led.enable()
    led.set_color(48)
    led.apply_mode(True)
    led.close()

    red = note_on(1, 9, 127) + note_on(2, 9, 48)
    green = note_on(1, 9, 127) + note_on(2, 9, 8)
    nipple_idle = note_on(1, 11, 25) + note_on(2, 11, 121)
    fine_idle = note_on(1, 10, 25) + note_on(2, 10, 123)
    # Colour updates never send the release frame; only close does.
    assert path.read_bytes() == (
        ENABLE
        + ENABLE + red
        + ENABLE + green
        + ENABLE + nipple_idle
        + ENABLE + fine_idle
        + DISABLE
    )


def test_fine_led_idle_and_pressed(tmp_path):
    path = tmp_path / "led.mid"
    path.touch()
    led = LedOutput(path, LedSettings())
    led.open()
    led.set_fine(True)
    led.set_fine(False)
    led.close()
    pressed = note_on(1, 10, 127) + note_on(2, 10, 123)
    idle = note_on(1, 10, 25) + note_on(2, 10, 123)
    assert path.read_bytes() == ENABLE + pressed + ENABLE + idle + DISABLE


def test_nipple_led_idle_and_pressed(tmp_path):
    path = tmp_path / "led.mid"
    path.touch()
    led = LedOutput(path, LedSettings())
    led.open()
    led.set_nipple(True)
    led.set_nipple(False)
    led.close()
    pressed = note_on(1, 11, 127) + note_on(2, 11, 116)
    idle = note_on(1, 11, 25) + note_on(2, 11, 121)
    assert path.read_bytes() == ENABLE + pressed + ENABLE + idle + DISABLE


def test_led_output_writes_are_optional(tmp_path):
    led = LedOutput(tmp_path / "missing.mid", LedSettings())
    # Not open: must not raise.
    led.enable()
    led.set_color(0)
    led.close()


def test_still_attached_detects_replug(tmp_path):
    path = tmp_path / "led.mid"
    path.touch()
    led = LedOutput(path, LedSettings())
    assert not led.still_attached()  # nicht geöffnet
    led.open()
    assert led.is_open and led.still_attached()

    # Replug simulieren: Knoten wird neu erzeugt (neue Inode), der alte fd bleibt.
    path.unlink()
    path.touch()
    assert led.is_open  # fd ist noch gesetzt ...
    assert not led.still_attached()  # ... gehört aber nicht mehr zum Gerät

    # Gerät ganz weg: ebenfalls nicht mehr attached.
    path.unlink()
    assert not led.still_attached()
    led.close()
    assert not led.is_open


def test_led_config_defaults(make_config):
    cfg = make_config(lambda data: data.pop("led"))
    assert cfg.led.enabled is False
    assert cfg.led.note == 9
    assert cfg.led.attribute_color == 48
    assert cfg.led.screen_color == 8
    assert cfg.led.brightness == 127
    assert (cfg.led.brightness_channel, cfg.led.color_channel) == (1, 2)


def test_led_config_parses_colors_and_channels(make_config):
    cfg = make_config(
        lambda data: data["led"].update(
            {"attribute_color": 33, "brightness": 50, "brightness_channel": 4, "color_channel": 5}
        )
    )
    assert cfg.led.attribute_color == 33
    assert cfg.led.brightness == 50
    assert cfg.led.brightness_channel == 4


def test_led_config_rejects_duplicate_channels(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError, match="verschieden"):
        make_config(
            lambda data: data["led"].update({"color_channel": 1})
        )


def test_led_config_rejects_unknown_color(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["led"].update({"screen_color": "pink"}))