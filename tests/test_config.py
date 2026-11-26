from __future__ import annotations

import tomllib

import pytest

from ma2pi.config import ConfigError, load_config, parse_config


def test_example_config_is_valid(config):
    assert config.schema_version == 1
    assert config.ma2.host == "192.168.0.10"
    assert set(config.devices) == {
        "cherry-g86",
        "asl-mk2-e4b3",
        "midicraft-enc",
        "midicraft-push",
        "midicraft-fade",
        "midicraft-turn",
        "midicraft-mix",
        "midicraft-spot",
    }
    assert len(config.mapping.encoders) == 4
    assert config.mapping.playbacks["mc_fader_1"].page == "current"
    assert config.mapping.playbacks["mc_encoder_1"].accelerated is True
    assert config.mapping.value_acceleration.max_multiplier == 8.0


def test_example_has_required_key_coverage(config):
    controls = set(config.mapping.keys) | set(config.mapping.modifiers)
    required = {
        "ma",
        "fix",
        "store_big",
        "clear",
        "at",
        "thru",
        "please_big",
        "go_plus",
        "go_minus",
        "pause",
        *(f"num_{digit}" for digit in range(10)),
    }
    assert required <= controls


def test_unknown_top_level_key(make_config):
    with pytest.raises(ConfigError, match="unbekannte Schlüssel: extra"):
        make_config(lambda data: data.__setitem__("extra", 1))


def test_unknown_nested_key(make_config):
    with pytest.raises(ConfigError, match="ma2"):
        make_config(lambda data: data["ma2"].__setitem__("nope", True))


def test_schema_version(make_config):
    with pytest.raises(ConfigError, match="Version 1"):
        make_config(lambda data: data.__setitem__("schema_version", 2))


def test_two_password_sources(make_config):
    def mutate(data):
        data["ma2"]["password_env"] = "MA2PI_TEST_PASSWORD"

    with pytest.raises(ConfigError, match="genau eine Passwortquelle"):
        make_config(mutate)


def test_no_password_source(make_config):
    with pytest.raises(ConfigError, match="genau eine Passwortquelle"):
        make_config(lambda data: data["ma2"].pop("password_file"))


def test_keepalive_must_be_below_ten(make_config):
    with pytest.raises(ConfigError, match="keepalive_interval"):
        make_config(lambda data: data["ma2"].__setitem__("keepalive_interval", 10.0))


def test_rate_limit_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 5 und 40"):
        make_config(lambda data: data["rate_limit"].__setitem__("messages_per_second", 100))


def test_slot_out_of_range(make_config):
    def mutate(data):
        data["mapping"]["encoders"][0]["slot"] = 9

    with pytest.raises(ConfigError, match="zwischen 1 und 8"):
        make_config(mutate)


def test_wheel_and_attribute_are_exclusive(make_config):
    def mutate(data):
        data["mapping"]["encoders"][0]["attribute"] = "Dimmer"

    with pytest.raises(ConfigError, match="genau eines"):
        make_config(mutate)


def test_duplicate_encoder_id(make_config):
    def mutate(data):
        data["mapping"]["encoders"][1]["id"] = data["mapping"]["encoders"][0]["id"]

    with pytest.raises(ConfigError, match="doppelte Encoder-ID"):
        make_config(mutate)


def test_unknown_profile_reference(make_config):
    with pytest.raises(ConfigError, match="unbekanntes Profil"):
        make_config(lambda data: data["devices"]["cherry-g86"].__setitem__("profile", "missing"))


def test_unknown_control_reference(make_config):
    with pytest.raises(ConfigError, match="kommt in keinem Profil vor"):
        make_config(lambda data: data["mapping"]["keys"].__setitem__("ghost", {"hardkey": "Fix"}))


def test_unknown_hardkey(make_config):
    def mutate(data):
        data["mapping"]["keys"]["fix"] = {"hardkey": "NoSuchKey"}

    with pytest.raises(ConfigError, match="unbekannter Hardkey"):
        make_config(mutate)


def test_numeric_hardkey_is_rejected(make_config):
    with pytest.raises(ConfigError, match="muss ein Hardkey-Name sein"):
        make_config(lambda data: data["mapping"]["keys"].__setitem__("fix", {"hardkey": 42}))


def test_hardkey_resolves_to_keyname(make_config):
    config = make_config()
    assert config.mapping.keys["fix"].hardkey == "Fix"
    assert config.logical_to_hardkey("fix") == "FIX"
    assert config.logical_to_hardkey("please_big") == "ENTER"


def test_vendor_zero_requires_name(make_config):
    def mutate(data):
        data["devices"]["asl-mk2-e4b3"]["vendor_id"] = 0
        data["devices"]["asl-mk2-e4b3"].pop("name_contains")

    with pytest.raises(ConfigError, match="name_contains"):
        make_config(mutate)


def test_resolution_modifier_must_be_defined(make_config):
    def mutate(data):
        data["mapping"]["encoder_resolution"]["modifiers"] = {"fine": "nope"}

    with pytest.raises(ConfigError, match="ist nicht definiert"):
        make_config(mutate)


def test_screen_mode_key(make_config):
    config = make_config()
    assert config.mapping.keys["asl_bank"].screen_mode is True
    assert config.mapping.keys["asl_click_1"].encoder_press == 1


def test_screen_mode_rejects_non_bool(make_config):
    with pytest.raises(ConfigError, match="muss true oder false sein"):
        make_config(
            lambda data: data["mapping"]["keys"]["asl_bank"].__setitem__(
                "screen_mode", "yes"
            )
        )


def test_screen_encoders_parsed(make_config):
    config = make_config(
        lambda data: data["mapping"].__setitem__(
            "screen_encoders", {"1": 5, "4": "8"}
        )
    )
    assert config.mapping.screen_encoders == {1: 5, 4: 8}


def test_screen_encoders_default_order(make_config):
    config = make_config()
    assert config.mapping.screen_encoders == {1: 8, 2: 7, 3: 6, 4: 5}


def test_rightmost_asl_button_is_nipple(make_config):
    config = make_config()
    assert config.mapping.keys["asl_button_3"].hardkey == "NIPPLE"
    assert "asl_button_3" not in config.mapping.modifiers


def test_screen_encoder_slot_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 1 und 4"):
        make_config(
            lambda data: data["mapping"].__setitem__("screen_encoders", {"5": 5})
        )


def test_screen_encoder_number_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 5 und 10"):
        make_config(
            lambda data: data["mapping"].__setitem__("screen_encoders", {"1": 11})
        )


def test_nipple_led_defaults(make_config):
    led = make_config().led
    assert (led.nipple_note, led.nipple_idle_color, led.nipple_idle_brightness) == (11, 121, 25)
    assert (led.nipple_pressed_color, led.nipple_pressed_brightness) == (116, 127)
    assert (led.fine_note, led.fine_color) == (10, 123)
    assert (led.fine_idle_brightness, led.fine_pressed_brightness) == (25, 127)


def test_screen_shortcut_key(make_config):
    config = make_config()
    assert config.mapping.keys["screen2"].screen == 2
    assert config.mapping.keys["screen6"].screen == 6


def test_screen_shortcut_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 1 und 6"):
        make_config(
            lambda data: data["mapping"]["keys"]["screen2"].__setitem__("screen", 7)
        )


def test_screen_helper_defaults(make_config):
    config = make_config(lambda data: data.pop("screen_helper", None))
    assert config.screen_helper.enabled is False
    assert config.screen_helper.port == 5005


def test_screen_helper_parsed(make_config):
    config = make_config(
        lambda data: data.__setitem__(
            "screen_helper", {"enabled": True, "host": "192.168.178.72", "port": 5005}
        )
    )
    assert config.screen_helper.enabled is True
    assert config.screen_helper.host == "192.168.178.72"
    assert config.screen_helper.port == 5005


def test_screen_helper_port_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 1 und 65535"):
        make_config(
            lambda data: data.__setitem__("screen_helper", {"port": 0})
        )


def test_key_mapping_requires_exactly_one_kind(make_config):
    with pytest.raises(ConfigError, match="genau eines"):
        make_config(
            lambda data: data["mapping"]["keys"]["asl_bank"].__setitem__(
                "hardkey", "MA"
            )
        )


def test_exponential_curve_accepts_german_spelling(make_config):
    config = make_config(
        lambda data: data["mapping"]["encoder_acceleration"].__setitem__(
            "curve", "exponentiell"
        )
    )
    assert config.mapping.acceleration.curve == "exponentiell"


def test_encoder_id_must_be_unique_across_profiles(make_config):
    def mutate(data):
        data["profiles"]["cherry-g86"]["encoders"] = [
            {"id": 1, "control": "ABS_X", "detents_per_revolution": 24, "direction": 1}
        ]

    with pytest.raises(ConfigError, match="anderen Profil"):
        make_config(mutate)


def test_missing_config_file(tmp_path):
    with pytest.raises(ConfigError, match="nicht gefunden"):
        load_config(tmp_path / "nope.toml")


def test_invalid_toml(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text("not = [", encoding="utf-8")
    with pytest.raises(ConfigError, match="ungültiges TOML"):
        load_config(path)


def test_password_read_file(tmp_path, make_config):
    secret = tmp_path / "pw"
    secret.write_text("hunter2\n", encoding="utf-8")
    config = make_config(
        lambda data: (
            data["ma2"].pop("password_env", None),
            data["ma2"].__setitem__("password_file", str(secret)),
        )
    )
    assert config.ma2.read_password() == "hunter2"


def test_password_read_env(make_config, monkeypatch):
    monkeypatch.setenv("PW_ENV", "from-env")
    config = make_config(
        lambda data: (
            data["ma2"].pop("password_file", None),
            data["ma2"].__setitem__("password_env", "PW_ENV"),
        )
    )
    assert config.ma2.read_password() == "from-env"


def test_midi_backend_and_notes(make_config):
    config = make_config()
    assert config.devices["asl-mk2-e4b3"].backend == "midi"
    profile = config.profiles["asl-mk2-e4b3"]
    assert profile.notes[9] == "asl_bank"
    assert profile.notes[5] == "asl_click_1"
    assert {encoder.id for encoder in profile.midi_encoders} == {1, 2, 3, 4}
    assert [encoder.note for encoder in profile.midi_encoders] == [1, 2, 3, 4]
    assert profile.midi_encoders[0].cw_velocity == 127
    assert profile.midi_encoders[0].ccw_velocity == 1


def test_midi_note_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 0 und 127"):
        make_config(
            lambda data: data["profiles"]["asl-mk2-e4b3"]["notes"].__setitem__(
                "128", "too_high"
            )
        )


def test_midi_encoder_velocities_must_differ(make_config):
    def mutate(data):
        data["profiles"]["asl-mk2-e4b3"]["midi_encoders"][0]["cw_velocity"] = 1

    with pytest.raises(ConfigError, match="verschieden"):
        make_config(mutate)


def test_midi_encoder_velocity_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 1 und 127"):
        make_config(
            lambda data: data["profiles"]["asl-mk2-e4b3"]["midi_encoders"][0].__setitem__(
                "cw_velocity", 0
            )
        )


def test_midi_note_cannot_be_button_and_encoder(make_config):
    with pytest.raises(ConfigError, match="bereits von einer Taste"):
        make_config(
            lambda data: data["profiles"]["asl-mk2-e4b3"]["notes"].__setitem__(
                "1", "conflict"
            )
        )


def test_midi_encoder_id_is_global(make_config):
    def mutate(data):
        data["profiles"]["cherry-g86"]["encoders"] = [
            {"id": 1, "control": "ABS_X", "detents_per_revolution": 24, "direction": 1}
        ]

    with pytest.raises(ConfigError, match="anderen Profil"):
        make_config(mutate)


def test_midicraft_profile_layout(make_config):
    config = make_config()
    device = config.devices["midicraft-enc"]
    assert device.backend == "midi"
    assert device.product_id == 0xE78C
    profile = config.profiles["midicraft-enc"]
    assert profile.banks[0].notes[55] == "mc_click_1"
    assert profile.banks[0].notes[84] == "mc_row3_5"
    assert profile.banks[0].notes[70] == "mc_fader_1"
    assert profile.banks[0].notes[60] == "mc_encoder_1"
    assert profile.control_kinds["mc_fader_1"] == "fader"
    assert profile.control_kinds["mc_encoder_1"] == "encoder"
    assert profile.banks[1].channel == 2
    assert len(profile.banks) == 16


def test_midi_value_note_cannot_be_button(make_config):
    def mutate(data):
        data["profiles"]["asl-mk2-e4b3"]["midi_values"] = [
            {"control": "asl_click_1", "note": 5, "kind": "fader"}
        ]

    with pytest.raises(ConfigError, match="bereits von einer Taste"):
        make_config(mutate)


def test_midi_value_kind_invalid(make_config):
    def mutate(data):
        data["profiles"]["asl-mk2-e4b3"]["midi_values"] = [
            {"control": "extra", "note": 20, "kind": "cc"}
        ]

    with pytest.raises(ConfigError, match="kind"):
        make_config(mutate)


def test_playback_mapping_parses(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {
            "mc_fader_1": {"page": 2, "executor": 7, "kind": "fader"},
            "mc_click_1": {"page": 1, "executor": 3, "kind": "button", "button": 2},
        }

    config = make_config(mutate)
    fader = config.mapping.playbacks["mc_fader_1"]
    assert (fader.page, fader.executor, fader.kind, fader.button) == (2, 7, "fader", 1)
    button = config.mapping.playbacks["mc_click_1"]
    assert (button.page, button.executor, button.kind, button.button) == (1, 3, "button", 2)


def test_playback_current_page(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {
            "mc_fader_1": {"page": "current", "executor": 7, "kind": "fader"},
            "mc_click_1": {"page": "current", "executor": 3, "kind": "button", "button": 2},
        }

    config = make_config(mutate)
    assert config.mapping.playbacks["mc_fader_1"].page == "current"
    assert config.mapping.playbacks["mc_click_1"].page == "current"


def test_playback_page_rejects_unknown_string(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {
            "mc_fader_1": {"page": "next", "executor": 1, "kind": "fader"}
        }

    with pytest.raises(ConfigError, match="page"):
        make_config(mutate)


def test_playback_fader_rejects_button(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {
            "mc_fader_1": {"page": 1, "executor": 1, "kind": "fader", "button": 1}
        }

    with pytest.raises(ConfigError, match="button ist nur"):
        make_config(mutate)


def test_playback_page_must_be_positive(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {"mc_fader_1": {"page": 0, "executor": 1}}

    with pytest.raises(ConfigError, match="mindestens 1"):
        make_config(mutate)


def test_playback_control_must_exist(make_config):
    def mutate(data):
        data["mapping"]["playbacks"] = {"nope": {"page": 1, "executor": 1}}

    with pytest.raises(ConfigError, match="kommt in keinem Profil vor"):
        make_config(mutate)


def test_playback_encoder_accepts_acceleration(make_config):
    def mutate(data):
        data["mapping"]["playbacks"]["mc_encoder_1"]["accelerated"] = True

    config = make_config(mutate)
    assert config.mapping.playbacks["mc_encoder_1"].accelerated is True


def test_playback_physical_fader_rejects_acceleration(make_config):
    def mutate(data):
        data["mapping"]["playbacks"]["mc_fader_1"]["accelerated"] = True

    with pytest.raises(ConfigError, match="nur für absolute Encoder"):
        make_config(mutate)


def test_playback_button_rejects_acceleration(make_config):
    def mutate(data):
        data["mapping"]["playbacks"]["mc_click_1"]["accelerated"] = True

    with pytest.raises(ConfigError, match='nur bei kind = "fader"'):
        make_config(mutate)


def test_playback_key_control_rejects_acceleration(make_config):
    def mutate(data):
        data["mapping"]["playbacks"]["asl_click_1"] = {
            "page": 1,
            "executor": 1,
            "kind": "fader",
            "accelerated": True,
        }

    with pytest.raises(ConfigError, match="nur für absolute Encoder"):
        make_config(mutate)


def test_value_acceleration_defaults(make_config):
    def mutate(data):
        data["mapping"].pop("value_acceleration", None)

    settings = make_config(mutate).mapping.value_acceleration
    assert (
        settings.curve,
        settings.window,
        settings.slow_rate,
        settings.fast_rate,
        settings.max_multiplier,
    ) == ("linear", 0.12, 2, 10, 8.0)


def test_value_acceleration_partial_section_keeps_defaults(make_config):
    def mutate(data):
        data["mapping"]["value_acceleration"] = {"max_multiplier": 4}

    settings = make_config(mutate).mapping.value_acceleration
    assert settings.curve == "linear"
    assert settings.window == 0.12
    assert settings.slow_rate == 2
    assert settings.fast_rate == 10
    assert settings.max_multiplier == 4


def test_value_acceleration_parses_custom_values(make_config):
    def mutate(data):
        data["mapping"]["value_acceleration"] = {
            "curve": "exponentiell",
            "window": 0.2,
            "slow_rate": 3,
            "fast_rate": 12,
            "max_multiplier": 6,
        }

    settings = make_config(mutate).mapping.value_acceleration
    assert settings.curve == "exponential"
    assert settings.window == 0.2
    assert settings.slow_rate == 3
    assert settings.fast_rate == 12
    assert settings.max_multiplier == 6


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("window", 0, "window"),
        ("max_multiplier", 0.5, "max_multiplier"),
        ("slow_rate", 0, "slow_rate"),
        ("fast_rate", 2, "fast_rate"),
    ],
)
def test_value_acceleration_rejects_invalid_values(make_config, key, value, message):
    def mutate(data):
        data["mapping"]["value_acceleration"][key] = value

    with pytest.raises(ConfigError, match=message):
        make_config(mutate)


def test_multiple_midi_devices_require_led_device(make_config):
    with pytest.raises(ConfigError, match="mehreren MIDI-Geräten"):
        make_config(lambda data: data["led"].pop("device"))


def test_led_device_must_exist(make_config):
    with pytest.raises(ConfigError, match="unbekanntes Gerät"):
        make_config(lambda data: data["led"].__setitem__("device", "nope"))


def test_unknown_backend(make_config):
    with pytest.raises(ConfigError, match="backend"):
        make_config(lambda data: data["devices"]["asl-mk2-e4b3"].__setitem__("backend", "serial"))


def test_default_hardkey_transport_is_lua(make_config):
    config = make_config(lambda data: data["ma2"].pop("hardkey_transport"))
    assert config.ma2.hardkey_transport == "lua"


def test_invalid_hardkey_transport(make_config):
    with pytest.raises(ConfigError, match="hardkey_transport"):
        make_config(lambda data: data["ma2"].__setitem__("hardkey_transport", "osc"))


def test_missing_hardkey_code_names_the_key(make_config):
    with pytest.raises(ConfigError, match="STORE"):
        make_config(lambda data: data["hardkeys"].pop("STORE"))


def test_hardkey_code_range(make_config):
    with pytest.raises(ConfigError, match="CLEAR"):
        make_config(lambda data: data["hardkeys"]["CLEAR"].__setitem__("code", 0))
    with pytest.raises(ConfigError, match="CLEAR"):
        make_config(lambda data: data["hardkeys"]["CLEAR"].__setitem__("code", 300))


def test_hardkey_verified_is_required(make_config):
    with pytest.raises(ConfigError, match="CLEAR.*verified"):
        make_config(lambda data: data["hardkeys"]["CLEAR"].pop("verified"))


def test_hardkey_alias_is_rejected_as_table_key(make_config):
    def mutate(data):
        data["hardkeys"]["Store"] = data["hardkeys"].pop("STORE")

    with pytest.raises(ConfigError, match="kanonischen Namen"):
        make_config(mutate)


def test_native_transport_does_not_require_codes(make_config):
    def mutate(data):
        data["ma2"]["hardkey_transport"] = "native"
        data.pop("hardkeys")

    config = make_config(mutate)
    assert config.ma2.hardkey_transport == "native"
    assert config.hardkeys == {}


def test_default_hardkey_hold_threshold(make_config):
    config = make_config(lambda data: data["ma2"].pop("hardkey_hold_threshold", None))
    assert config.ma2.hardkey_hold_threshold == 0.5


def test_invalid_hardkey_hold_threshold(make_config):
    with pytest.raises(ConfigError, match="hardkey_hold_threshold"):
        make_config(lambda data: data["ma2"].__setitem__("hardkey_hold_threshold", 0))


# --- layouts, control inventory and banks ---------------------------------


def _with_bank_profile(data):
    data["led"]["enabled"] = False
    data["profiles"]["bank-test"] = {
        "controls": [
            {"id": "bt_fader", "kind": "fader"},
            {"id": "bt_button", "kind": "button"},
            {"id": "bt_encoder", "kind": "encoder"},
        ],
        "banks": [
            {"number": 1, "notes": {"70": "bt_fader", "55": "bt_button", "60": "bt_encoder"}},
            {"number": 2, "notes": {"15": "bt_fader", "0": "bt_button", "10": "bt_encoder"}},
        ],
    }
    data["devices"]["banktest"] = {
        "backend": "midi",
        "vendor_id": 0x04D8,
        "product_id": 0x1234,
        "name_contains": "Bank Test",
        "profile": "bank-test",
    }
    data["mapping"]["device_banks"] = {
        "banktest": {
            "bank_size": 5,
            "2": {"ma_page": 4, "playbacks": {"bt_fader": {"page": "current", "executor": 6}}},
        }
    }


def test_layout_parsing(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["layouts"] = {
            "surface": {
                "profile": "bank-test",
                "columns": 3,
                "rows": [
                    {
                        "cells": [
                            {"label": "F1", "control": "bt_fader", "col_span": 2, "color": "green"},
                            {"label": "", "col_span": 1},
                        ]
                    }
                ],
            }
        }

    config = make_config(mutate)
    layout = config.layouts["bank-test"]
    assert layout.columns == 3
    assert layout.rows[0].cells[0].control == "bt_fader"
    assert layout.rows[0].cells[0].col_span == 2
    assert layout.rows[0].cells[0].color == "green"
    assert config.layout_for_device("banktest") is layout


def test_layout_unknown_profile(make_config):
    def mutate(data):
        data["layouts"] = {"x": {"profile": "missing", "columns": 1}}

    with pytest.raises(ConfigError, match="unbekanntes Profil"):
        make_config(mutate)


def test_layout_unknown_control(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["layouts"] = {
            "x": {"profile": "bank-test", "columns": 1, "rows": [{"cells": [{"label": "X", "control": "ghost"}]}]}
        }

    with pytest.raises(ConfigError, match="kommt im Profil"):
        make_config(mutate)


def test_layout_duplicate_control(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["layouts"] = {
            "x": {
                "profile": "bank-test",
                "columns": 2,
                "rows": [
                    {
                        "cells": [
                            {"label": "A", "control": "bt_fader"},
                            {"label": "B", "control": "bt_fader"},
                        ]
                    }
                ],
            }
        }

    with pytest.raises(ConfigError, match="doppelt im Layout"):
        make_config(mutate)


def test_layout_invalid_span(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["layouts"] = {
            "x": {
                "profile": "bank-test",
                "columns": 2,
                "rows": [{"cells": [{"label": "A", "control": "bt_fader", "col_span": 0}]}],
            }
        }

    with pytest.raises(ConfigError, match="mindestens 1"):
        make_config(mutate)


def test_control_inventory_without_notes_is_valid(make_config):
    def mutate(data):
        _with_bank_profile(data)
        for bank in data["profiles"]["bank-test"]["banks"]:
            bank["notes"] = {}

    config = make_config(mutate)
    profile = config.profiles["bank-test"]
    assert {control.id for control in profile.controls} == {
        "bt_fader",
        "bt_button",
        "bt_encoder",
    }
    assert profile.control_kinds["bt_encoder"] == "encoder"


def test_legacy_profile_derives_control_inventory(make_config):
    config = make_config(lambda data: None)
    profile = config.profiles["asl-mk2-e4b3"]
    assert profile.control_kinds["asl_click_1"] == "button"
    assert profile.control_kinds["encoder.1"] == "relative-encoder"


def test_bank_number_out_of_range(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["profiles"]["bank-test"]["banks"][0]["number"] = 17

    with pytest.raises(ConfigError, match="zwischen 1 und 16"):
        make_config(mutate)


def test_duplicate_bank_channel(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["profiles"]["bank-test"]["banks"][1]["channel"] = 1

    with pytest.raises(ConfigError, match="bereits von einer anderen Bank"):
        make_config(mutate)


def test_bank_channel_defaults_to_number(make_config):
    config = make_config(lambda data: _with_bank_profile(data))
    banks = config.profiles["bank-test"].banks
    assert banks[0].channel == 1
    assert banks[1].channel == 2


def test_same_note_on_different_channels_is_valid(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["profiles"]["bank-test"]["banks"][1]["notes"] = {"55": "bt_button"}

    config = make_config(mutate)
    assert config.profiles["bank-test"].banks[1].notes[55] == "bt_button"


def test_bank_requires_control_inventory(make_config):
    def mutate(data):
        data["profiles"]["bank-test"] = {"banks": [{"number": 1, "notes": {"55": "x"}}]}

    with pytest.raises(ConfigError, match="Control-Inventar"):
        make_config(mutate)


def test_bank_note_requires_inventory_control(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["profiles"]["bank-test"]["banks"][0]["notes"]["55"] = "ghost"

    with pytest.raises(ConfigError, match="fehlt im Control-Inventar"):
        make_config(mutate)


def test_device_banks_parsing(make_config):
    config = make_config(lambda data: _with_bank_profile(data))
    settings = config.mapping.device_banks["banktest"]
    assert settings.bank_size == 5
    layer = settings.banks[2]
    assert layer.ma_page == 4
    assert layer.playbacks["bt_fader"].executor == 6


def test_device_banks_unknown_bank(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["mapping"]["device_banks"]["banktest"]["3"] = {"ma_page": 3}

    with pytest.raises(ConfigError, match="nicht definiert"):
        make_config(mutate)


def test_device_banks_unknown_control(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["mapping"]["device_banks"]["banktest"]["2"]["keys"] = {"ghost": {"hardkey": "Fix"}}

    with pytest.raises(ConfigError, match="kommt in keinem Profil vor"):
        make_config(mutate)


def test_device_banks_bank_size_zero(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["mapping"]["device_banks"]["banktest"]["bank_size"] = 0

    with pytest.raises(ConfigError, match="mindestens 1"):
        make_config(mutate)


def test_device_banks_invalid_ma_page(make_config):
    def mutate(data):
        _with_bank_profile(data)
        data["mapping"]["device_banks"]["banktest"]["2"]["ma_page"] = 0

    with pytest.raises(ConfigError, match="mindestens 1"):
        make_config(mutate)


def test_global_control_names_must_be_unique(make_config):
    def mutate(data):
        data["profiles"]["duplicate"] = {
            "controls": [{"id": "mc_fader_1", "kind": "fader"}],
        }

    with pytest.raises(ConfigError, match="bereits in Profil"):
        make_config(mutate)


def test_feedback_defaults_to_disabled(make_config):
    cfg = make_config(lambda data: data.pop("feedback"))
    assert cfg.feedback.enabled is False
    assert cfg.feedback.interval_ms == 250
    assert cfg.feedback.off_state == "dark"
    assert cfg.feedback.fallback_color == "white"


def test_feedback_interval_bounds(make_config):
    with pytest.raises(ConfigError, match="interval_ms"):
        make_config(lambda data: data["feedback"].__setitem__("interval_ms", 50))
    with pytest.raises(ConfigError, match="interval_ms"):
        make_config(lambda data: data["feedback"].__setitem__("interval_ms", 2001))


def test_feedback_unknown_key(make_config):
    with pytest.raises(ConfigError, match="feedback"):
        make_config(lambda data: data["feedback"].__setitem__("extra", True))


def test_feedback_off_state_and_colour(make_config):
    with pytest.raises(ConfigError, match="off_state"):
        make_config(lambda data: data["feedback"].__setitem__("off_state", "dim"))
    with pytest.raises(ConfigError, match="fallback_color"):
        make_config(
            lambda data: data["feedback"].__setitem__("fallback_color", "chartreuse")
        )


def test_profile_led_feedback_parsed(config):
    profile = config.profiles["midicraft-enc"]
    assert profile.led_feedback is not None
    assert profile.led_feedback.protocol == "midicraft-v2"
    assert profile.led_feedback.notes is not None
    assert 65 in profile.led_feedback.notes
    assert 55 not in profile.led_feedback.notes


def test_profile_led_feedback_requires_known_protocol(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["protocol"] = "foo"

    with pytest.raises(ConfigError, match="protocol"):
        make_config(mutate)


def test_profile_led_feedback_rejects_duplicate_note(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["led_notes"] = [65, 65]

    with pytest.raises(ConfigError, match="doppelt"):
        make_config(mutate)


def test_profile_led_feedback_rejects_bad_note(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["led_notes"] = [128]

    with pytest.raises(ConfigError, match="zwischen 0 und 127"):
        make_config(mutate)


def test_profile_led_feedback_rejects_note_not_in_profile(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["led_notes"] = [65, 85]

    with pytest.raises(ConfigError, match="gehört nicht zum Profil"):
        make_config(mutate)


def test_profile_led_feedback_defaults(config):
    feedback = config.profiles["midicraft-enc"].led_feedback
    assert feedback is not None
    assert feedback.frame_interval_ms == 20


def test_profile_led_feedback_enabled_defaults_to_true(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"].pop("enabled", None)

    cfg = make_config(mutate)
    assert cfg.profiles["midicraft-enc"].led_feedback.enabled is True


def test_profile_led_feedback_can_be_disabled(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["enabled"] = False

    cfg = make_config(mutate)
    assert cfg.profiles["midicraft-enc"].led_feedback.enabled is False


def test_profile_led_feedback_enabled_must_be_boolean(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["enabled"] = "yes"

    with pytest.raises(ConfigError, match="enabled"):
        make_config(mutate)


@pytest.mark.parametrize("value", [0, 501])
def test_profile_led_feedback_frame_interval_range(make_config, value):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["frame_interval_ms"] = value

    with pytest.raises(ConfigError, match="frame_interval_ms"):
        make_config(mutate)


def test_profile_led_feedback_frame_interval_is_read(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["frame_interval_ms"] = 50

    cfg = make_config(mutate)
    assert cfg.profiles["midicraft-enc"].led_feedback.frame_interval_ms == 50


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_config_rejects_non_finite_floats(make_config, bad):
    def mutate(data):
        data["ma2"]["keepalive_interval"] = bad

    with pytest.raises(ConfigError, match="endliche Zahl"):
        make_config(mutate)


def test_lua_hardkey_codes_required_for_device_bank_keys(make_config):
    def mutate(data):
        dev_name = next(
            name
            for name, dev in data["devices"].items()
            if dev["profile"] == "midicraft-enc"
        )
        ctrl_id = next(
            c["id"]
            for c in data["profiles"]["midicraft-enc"]["controls"]
            if c.get("kind", "button") == "button"
        )
        data["ma2"]["hardkey_transport"] = "lua"
        data["hardkeys"].pop("MACRO", None)
        banks = data["mapping"].setdefault("device_banks", {})
        banks.setdefault(dev_name, {})["2"] = {
            "keys": {ctrl_id: {"hardkey": "Macro"}}
        }

    with pytest.raises(ConfigError, match="hardkeys.MACRO"):
        make_config(mutate)


def test_banked_auto_encoder_ids_skip_later_explicit_profile_ids(raw_config):
    import copy

    data = copy.deepcopy(raw_config)
    # Place a banked profile with auto-ID relative-encoder BEFORE asl-mk2-e4b3 (id=1..3)
    reordered: dict = {
        "banked-wheel": {
            "controls": [{"id": "wheel_a", "kind": "relative-encoder"}],
            "banks": [{"number": 1, "channel": 1, "notes": {"40": "wheel_a"}}],
        }
    }
    reordered.update(data["profiles"])
    data["profiles"] = reordered
    cfg = parse_config(data, source_path="<test>")
    wheel = cfg.profiles["banked-wheel"].controls[0]
    assert wheel.encoder_id not in {1, 2, 3, 4}
    assert wheel.encoder_id == 5
