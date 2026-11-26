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


def test_led_step_routes_through_midi_manager_and_hot_reloads(make_config):
    from ma2pi.__main__ import _find_led_target, _led_step
    from ma2pi.hid_input import DeviceInfo
    from ma2pi.ma2_client import Ma2Client

    class FakeMidi:
        def __init__(self) -> None:
            self.open_devices = {"asl-mk2-e4b3": "/dev/snd/midiC3D0"}
            self.open_generations = {"asl-mk2-e4b3": 1}
            self.sent: list[tuple[str, bytes]] = []

        def send(self, device: str, data: bytes) -> bool:
            self.sent.append((device, data))
            return True

    cfg_off = make_config(lambda d: d["led"].update({"enabled": False, "device": "asl-mk2-e4b3"}))
    cfg_on = make_config(lambda d: d["led"].update({"enabled": True, "device": "asl-mk2-e4b3"}))
    cfg_color = make_config(
        lambda d: d["led"].update({"enabled": True, "device": "asl-mk2-e4b3", "attribute_color": 127})
    )

    client = Ma2Client(cfg_off, dry_run=True)
    midi = FakeMidi()
    holder: dict = {}

    # Idle when disabled
    _led_step(cfg_off, client, midi, holder)
    assert holder == {}
    assert midi.sent == []

    # Enable at runtime -> sends enable + mode/button frames via midi.send
    _led_step(cfg_on, client, midi, holder)
    assert holder["led"].is_open
    assert client._led is holder["led"]
    count_after_enable = len(midi.sent)
    assert count_after_enable >= 4

    # Re-running with unchanged generation & settings is a no-op
    _led_step(cfg_on, client, midi, holder)
    assert len(midi.sent) == count_after_enable

    # Replug on same path bumps generation -> re-initialises
    midi.open_generations["asl-mk2-e4b3"] = 2
    _led_step(cfg_on, client, midi, holder)
    assert holder["generation"] == 2
    assert len(midi.sent) > count_after_enable

    # Changing [led] colour hot-reloads
    _led_step(cfg_color, client, midi, holder)
    assert holder["settings"] == cfg_color.led

    # Disable at runtime -> sends DISABLE and clears client._led
    _led_step(cfg_off, client, midi, holder)
    assert holder == {}
    assert client._led is None
    assert midi.sent[-1] == ("asl-mk2-e4b3", DISABLE)


def test_find_led_target_never_falls_back_to_unrelated_midi_device(monkeypatch, make_config):
    from ma2pi import __main__ as main_mod
    from ma2pi.hid_input import DeviceInfo

    def mutate(d):
        d["devices"] = {"asl-mk2-e4b3": d["devices"]["asl-mk2-e4b3"]}
        d["mapping"].pop("device_banks", None)
        d["led"].update({"enabled": True, "device": None})

    cfg = make_config(mutate)
    unrelated = DeviceInfo(
        path="/dev/snd/midiC9D0",
        name="Unrelated Synth",
        vendor_id=0x9999,
        product_id=0x9999,
        backend="midi",
    )
    monkeypatch.setattr(main_mod, "list_midi_devices", lambda: [unrelated])
    assert main_mod._find_led_target(cfg) is None

def test_led_step_reports_every_release_of_the_buttons(make_config):
    from ma2pi.__main__ import _led_step
    from ma2pi.ma2_client import Ma2Client

    class FakeMidi:
        def __init__(self) -> None:
            self.open_devices = {"asl-mk2-e4b3": "/dev/snd/midiC3D0"}
            self.open_generations = {"asl-mk2-e4b3": 1}
            self.sent: list[tuple[str, bytes]] = []

        def send(self, device: str, data: bytes) -> bool:
            self.sent.append((device, data))
            return True

    cfg_on = make_config(lambda d: d["led"].update({"enabled": True, "device": "asl-mk2-e4b3"}))
    cfg_color = make_config(
        lambda d: d["led"].update(
            {"enabled": True, "device": "asl-mk2-e4b3", "attribute_color": 127}
        )
    )
    cfg_off = make_config(lambda d: d["led"].update({"enabled": False, "device": "asl-mk2-e4b3"}))
    client = Ma2Client(cfg_on, dry_run=True)
    midi = FakeMidi()
    holder: dict = {}
    released: list[str] = []

    _led_step(cfg_on, client, midi, holder, released.append)
    assert released == []  # first start: nothing was released

    _led_step(cfg_on, client, midi, holder, released.append)
    assert released == []  # unchanged: no-op

    _led_step(cfg_color, client, midi, holder, released.append)
    assert released == ["asl-mk2-e4b3"]  # re-init sent DISABLE first

    _led_step(cfg_off, client, midi, holder, released.append)
    assert released == ["asl-mk2-e4b3", "asl-mk2-e4b3"]


def test_resend_device_sends_the_full_state_again(make_config):
    from ma2pi.feedback import ExecutorFeedback, RequestBlock, parse_playbacks

    class Midi:
        open_devices = {"midicraft-enc": "/dev/snd/midiC4D0"}

        def __init__(self) -> None:
            self.sent: list[bytes] = []

        def send(self, device: str, data: bytes) -> bool:
            self.sent.append(data)
            return True

    def enable(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["enabled"] = True

    midi = Midi()
    feedback = ExecutorFeedback(make_config(enable), None, midi)
    snapshot = parse_playbacks(
        {
            "iPage": 0,  # "current" is answered with the placeholder 0
            "itemGroups": [
                {"itemsType": 2, "items": [[{"iExec": 0, "isRun": True, "bC": "#ff0000"}]]}
            ],
        }
    )
    block = RequestBlock("current", 0, 5, 2, 2)
    feedback._apply(snapshot, block)
    feedback.pump()
    first = list(midi.sent)
    feedback._apply(snapshot, block)
    feedback.pump()
    assert midi.sent == first  # unchanged state is not repeated

    feedback.resend_device("midicraft-enc")
    feedback._apply(snapshot, block)
    feedback.pump()
    assert midi.sent[len(first):][:1] == first[:1]


def test_fixed_leds_and_feedback_share_one_asl_device(make_config):
    from ma2pi.__main__ import _led_step
    from ma2pi.feedback import ExecutorFeedback, RequestBlock, parse_playbacks
    from ma2pi.ma2_client import Ma2Client

    class FakeMidi:
        def __init__(self) -> None:
            self.open_devices = {"asl-mk2-e4b3": "/dev/snd/midiC3D0"}
            self.open_generations = {"asl-mk2-e4b3": 1}
            self.sent: list[bytes] = []

        def send(self, device: str, data: bytes) -> bool:
            assert device == "asl-mk2-e4b3"
            self.sent.append(data)
            return True

    def mutate(data):
        # [led] keeps the mode LED on note 9; the Fine button (note 10) goes
        # to executor feedback instead.
        data["led"].update(
            {"enabled": True, "device": "asl-mk2-e4b3", "fine_note": 12, "nipple_note": 13}
        )
        data["profiles"]["asl-mk2-e4b3"]["led_feedback"] = {
            "protocol": "asl-mk2",
            "led_notes": [10],
        }
        data["mapping"]["playbacks"]["asl_button_2"] = {
            "page": "current",
            "executor": 1,
            "kind": "button",
        }

    cfg = make_config(mutate)
    midi = FakeMidi()
    client = Ma2Client(cfg, dry_run=True)
    holder: dict = {}
    feedback = ExecutorFeedback(cfg, client, midi)
    _led_step(cfg, client, midi, holder, feedback.resend_device)

    snapshot = parse_playbacks(
        {
            "iPage": 0,  # "current" is answered with the placeholder 0
            "itemGroups": [
                {"itemsType": 2, "items": [[{"iExec": 0, "isRun": True, "bC": "#ff0000"}]]}
            ],
        }
    )
    feedback._apply(snapshot, RequestBlock("current", 0, 5, 2, 2))
    feedback.pump()
    assert midi.sent[-1].endswith(bytes((0x90, 10, 127, 0x91, 10, 48)))

    # A mode change only touches the mode LED (note 9).
    before = len(midi.sent)
    holder["led"].set_mode_color(True)
    mode_frames = midi.sent[before:]
    assert mode_frames
    assert all(bytes((0x90, 10)) not in frame and bytes((0x91, 10)) not in frame
               for frame in mode_frames)

    # Switching feedback off writes nothing, so the fixed LEDs stay as they are.
    before = len(midi.sent)
    feedback.set_config(
        make_config(lambda d: (mutate(d), d["feedback"].__setitem__("enabled", False)))
    )
    feedback.pump()
    assert len(midi.sent) == before
