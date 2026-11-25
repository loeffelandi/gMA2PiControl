from __future__ import annotations

import tomllib

import pytest

from ma2pi.config import ConfigError, load_config, parse_config


def test_example_config_is_valid(config):
    assert config.schema_version == 1
    assert config.ma2.host == "192.168.0.10"
    assert set(config.devices) == {"cherry", "asl"}
    assert len(config.mapping.encoders) == 4


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
        make_config(lambda data: data["devices"]["cherry"].__setitem__("profile", "missing"))


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
        data["devices"]["asl"]["vendor_id"] = 0
        data["devices"]["asl"].pop("name_contains")

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
    assert config.mapping.keys["asl_click_1"].encoder_fine == 1


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
            "screen_encoders", {"1": "screen1", "4": "screen4"}
        )
    )
    assert config.mapping.screen_encoders == {1: "screen1", 4: "screen4"}


def test_screen_encoder_slot_out_of_range(make_config):
    with pytest.raises(ConfigError, match="zwischen 1 und 4"):
        make_config(
            lambda data: data["mapping"].__setitem__("screen_encoders", {"5": "x"})
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
    assert config.devices["asl"].backend == "midi"
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


def test_unknown_backend(make_config):
    with pytest.raises(ConfigError, match="backend"):
        make_config(lambda data: data["devices"]["asl"].__setitem__("backend", "serial"))


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
