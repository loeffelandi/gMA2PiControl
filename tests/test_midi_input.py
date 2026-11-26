from __future__ import annotations

import asyncio
import dataclasses
import logging

import pytest

from ma2pi.config import ProfileConfig
from ma2pi.events import DeviceLost, InputEvent
from ma2pi.hid_input import DeviceInfo, ProfileError, RawEvent
from ma2pi.midi_input import (
    MidiManager,
    MidiStreamParser,
    select_midi_devices,
    validate_midi_profile,
)


class FakeMidiHandle:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.closed = False
        self.written: list[bytes] = []

    def write(self, data: bytes) -> bool:
        self.written.append(data)
        return True

    async def events(self):
        try:
            while True:
                item = await self.queue.get()
                if item is None:
                    return
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            await self.close()

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            await self.queue.put(None)


class FakeMidiSource:
    def __init__(self, devices: list[DeviceInfo]) -> None:
        self.devices = devices
        self.handles: dict[str, FakeMidiHandle] = {}
        self.fail_paths: dict[str, Exception] = {}
        self.opened: list[str] = []
        self.attempts = 0

    def list_devices(self) -> list[DeviceInfo]:
        return list(self.devices)

    async def open(self, info: DeviceInfo):
        self.attempts += 1
        if info.path in self.fail_paths:
            raise self.fail_paths[info.path]
        handle = FakeMidiHandle()
        self.handles[info.path] = handle
        self.opened.append(info.path)
        return handle


def midi_info(path: str = "/dev/snd/midiC3D0", readable: bool = True) -> DeviceInfo:
    return DeviceInfo(
        path=path,
        name="ASL MK2-E4B3",
        vendor_id=0x04D8,
        product_id=0xE817,
        backend="midi",
        readable=readable,
    )


def midicraft_info(path: str = "/dev/snd/midiC4D0", readable: bool = True) -> DeviceInfo:
    return DeviceInfo(
        path=path,
        name="MIDICRAFT ENC MIDI 1",
        vendor_id=0x04D8,
        product_id=0xE78C,
        backend="midi",
        readable=readable,
    )


def test_parser_note_on_and_velocity_one_release():
    parser = MidiStreamParser()
    events = parser.feed(bytes([0x90, 1, 0x7F, 0x90, 1, 0x01]))
    assert events == [
        RawEvent("note_on", "1", 0x7F),
        RawEvent("note_on", "1", 0x01),
    ]


def test_parser_keeps_zero_velocity_note_on_distinct_from_note_off():
    parser = MidiStreamParser()
    events = parser.feed(bytes([0x80, 5, 0x40, 0x90, 5, 0x00]))
    assert events == [
        RawEvent("note_off", "5", 0x40),
        RawEvent("note_on", "5", 0x00),
    ]


def test_parser_running_status_and_realtime():
    parser = MidiStreamParser()
    events = parser.feed(bytes([0x90, 1, 0x7F, 0xF8, 2, 0x7F]))
    assert events == [
        RawEvent("note_on", "1", 0x7F),
        RawEvent("note_on", "2", 0x7F),
    ]


def test_midi_device_selection(config):
    selected = select_midi_devices(config, [midi_info()])
    assert selected["asl-mk2-e4b3"].path == "/dev/snd/midiC3D0"
    assert select_midi_devices(config, []) == {}


def test_normalise_button(config):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "9", 0x7F)) == InputEvent(
        "key", "asl_bank", 1, "asl-mk2-e4b3"
    )
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "9", 0x01)) == InputEvent(
        "key", "asl_bank", 0, "asl-mk2-e4b3"
    )
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_off", "9", 0x01)) == InputEvent(
        "key", "asl_bank", 0, "asl-mk2-e4b3"
    )


def test_normalise_encoder(config):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "1", 0x7F)) == InputEvent(
        "encoder", "encoder.1", 1, "asl-mk2-e4b3"
    )
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "1", 0x01)) == InputEvent(
        "encoder", "encoder.1", -1, "asl-mk2-e4b3"
    )
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "4", 0x7F)) == InputEvent(
        "encoder", "encoder.4", 1, "asl-mk2-e4b3"
    )
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_off", "1", 0x00)) is None
    assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "1", 0x40)) is None


def test_normalise_encoder_direction_inverts(config):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    encoder = profile.midi_encoders[0]
    inverted = dataclasses.replace(
        profile,
        midi_encoders=(dataclasses.replace(encoder, direction=-1),),
    )
    assert manager._normalise(
        "asl-mk2-e4b3", inverted, RawEvent("note_on", "1", 0x7F)
    ) == InputEvent("encoder", "encoder.1", -1, "asl-mk2-e4b3")
    assert manager._normalise(
        "asl-mk2-e4b3", inverted, RawEvent("note_on", "1", 0x01)
    ) == InputEvent("encoder", "encoder.1", 1, "asl-mk2-e4b3")


def test_normalise_unknown_note_logged_once(config, caplog):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    with caplog.at_level(logging.DEBUG):
        assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "99", 0x7F)) is None
        assert manager._normalise("asl-mk2-e4b3", profile, RawEvent("note_on", "99", 0x7F)) is None
    assert caplog.text.count("Unbekannte MIDI-Note 99") == 1


def test_normalise_absolute_fader(config):
    manager = MidiManager(config)
    profile = config.profiles["midicraft-enc"]
    assert manager._normalise(
        "midicraft", profile, RawEvent("note_on", "70", 0x00)
    ) == InputEvent("value", "mc_fader_1", 0.0, "midicraft")
    assert manager._normalise(
        "midicraft", profile, RawEvent("note_on", "70", 0x40)
    ) == InputEvent("value", "mc_fader_1", 64 / 127.0, "midicraft")
    assert manager._normalise(
        "midicraft", profile, RawEvent("note_on", "70", 0x7F)
    ) == InputEvent("value", "mc_fader_1", 1.0, "midicraft")
    assert manager._normalise("midicraft", profile, RawEvent("note_off", "70", 0x00)) is None


def test_normalise_absolute_encoder(config):
    manager = MidiManager(config)
    profile = config.profiles["midicraft-enc"]
    assert manager._normalise(
        "midicraft", profile, RawEvent("note_on", "60", 0x20)
    ) == InputEvent("value", "mc_encoder_1", 32 / 127.0, "midicraft")
    assert manager._normalise("midicraft", profile, RawEvent("note_off", "60", 0x00)) is None


def test_zero_value_survives_parser_and_normalise(config):
    manager = MidiManager(config)
    profile = config.profiles["midicraft-enc"]
    events = MidiStreamParser().feed(bytes([0x90, 70, 0x00, 0x90, 60, 0x00]))
    assert [manager._normalise("midicraft", profile, event) for event in events] == [
        InputEvent("value", "mc_fader_1", 0.0, "midicraft"),
        InputEvent("value", "mc_encoder_1", 0.0, "midicraft"),
    ]


def test_normalise_unknown_note_on_midicraft_logged_once(config, caplog):
    manager = MidiManager(config)
    profile = config.profiles["midicraft-enc"]
    with caplog.at_level(logging.DEBUG):
        assert manager._normalise("midicraft", profile, RawEvent("note_on", "99", 0x7F)) is None
        assert manager._normalise("midicraft", profile, RawEvent("note_on", "99", 0x7F)) is None
    assert caplog.text.count("Unbekannte MIDI-Note 99") == 1


async def test_midi_manager_hotplug(config):
    source = FakeMidiSource([midi_info()])
    manager = MidiManager(config, source=source, poll_interval=0.01)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(manager.run(queue))
    try:
        await asyncio.sleep(0.03)
        assert "asl-mk2-e4b3" in manager.open_devices
        handle = source.handles["/dev/snd/midiC3D0"]
        await handle.queue.put(RawEvent("note_on", "9", 0x7F))
        event = await asyncio.wait_for(queue.get(), 1.0)
        assert event == InputEvent("key", "asl_bank", 1, "asl-mk2-e4b3")

        source.devices = []
        lost = await asyncio.wait_for(queue.get(), 2.0)
        assert isinstance(lost, DeviceLost)
        assert lost.device == "asl-mk2-e4b3"
        assert handle.closed

        source.devices = [midi_info()]
        await asyncio.sleep(0.05)
        assert "asl-mk2-e4b3" in manager.open_devices
        assert len(source.opened) == 2
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await manager.close()


async def test_two_midi_devices_are_independent(config):
    source = FakeMidiSource([midi_info(), midicraft_info()])
    manager = MidiManager(config, source=source, poll_interval=0.01)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(manager.run(queue))
    try:
        await asyncio.sleep(0.05)
        assert set(manager.open_devices) == {"asl-mk2-e4b3", "midicraft-enc"}
        asl = source.handles["/dev/snd/midiC3D0"]
        midicraft = source.handles["/dev/snd/midiC4D0"]
        await asl.queue.put(RawEvent("note_on", "9", 0x7F))
        await midicraft.queue.put(RawEvent("note_on", "70", 0x7F))
        first = await asyncio.wait_for(queue.get(), 1.0)
        second = await asyncio.wait_for(queue.get(), 1.0)
        by_device = {first.device: first, second.device: second}
        assert by_device["asl-mk2-e4b3"] == InputEvent("key", "asl_bank", 1, "asl-mk2-e4b3")
        assert by_device["midicraft-enc"] == InputEvent(
            "value", "mc_fader_1", 1.0, "midicraft-enc"
        )

        source.devices = [midi_info()]
        lost = await asyncio.wait_for(queue.get(), 2.0)
        while not isinstance(lost, DeviceLost):
            lost = await asyncio.wait_for(queue.get(), 2.0)
        assert lost.device == "midicraft-enc"
        assert midicraft.closed
        assert "asl-mk2-e4b3" in manager.open_devices
        assert not asl.closed

        await asl.queue.put(RawEvent("note_on", "9", 0x01))
        assert await asyncio.wait_for(queue.get(), 1.0) == InputEvent(
            "key", "asl_bank", 0, "asl-mk2-e4b3"
        )

        source.devices = [midi_info(), midicraft_info()]
        await asyncio.sleep(0.05)
        assert "midicraft-enc" in manager.open_devices
        assert source.opened.count("/dev/snd/midiC4D0") == 2
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await manager.close()


async def test_midi_permission_error_keeps_daemon_running(config, caplog):
    source = FakeMidiSource([midi_info()])
    source.fail_paths["/dev/snd/midiC3D0"] = PermissionError("denied")
    manager = MidiManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.ERROR):
        await manager.reconcile(queue)
    assert "audio" in caplog.text
    assert queue.empty()
    assert manager.open_devices == {}


async def test_missing_midi_device_warns_once(config, caplog):
    source = FakeMidiSource([])
    manager = MidiManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.WARNING):
        await manager.reconcile(queue)
        await manager.reconcile(queue)
    assert caplog.text.count("asl-mk2-e4b3 nicht gefunden") == 1
    assert caplog.text.count("midicraft-enc nicht gefunden") == 1
    assert queue.empty()


def test_midi_profile_without_notes_aborts(config):
    device = config.devices["asl-mk2-e4b3"]
    with pytest.raises(ProfileError, match="keine"):
        validate_midi_profile(
            "asl-mk2-e4b3",
            device,
            ProfileConfig(keys={"KEY_F1": "fix"}),
            midi_info(),
        )


def _banked_profile() -> ProfileConfig:
    from ma2pi.config import BankProfile, ControlProfile

    return ProfileConfig(
        controls=(
            ControlProfile("bt_fader", "fader"),
            ControlProfile("bt_button", "button"),
            ControlProfile("bt_encoder", "encoder"),
        ),
        banks=(
            BankProfile(1, 1, {70: "bt_fader", 55: "bt_button", 60: "bt_encoder"}),
            BankProfile(2, 2, {15: "bt_fader", 55: "bt_button", 10: "bt_encoder"}),
        ),
    )


def test_normalise_bank_from_channel(config):
    manager = MidiManager(config)
    profile = _banked_profile()
    assert manager._normalise(
        "banktest", profile, RawEvent("note_on", "15", 0x7F, channel=2)
    ) == InputEvent("value", "bt_fader", 1.0, "banktest", 2)


def test_normalise_same_note_on_other_channel(config):
    manager = MidiManager(config)
    profile = _banked_profile()
    down = manager._normalise(
        "banktest", profile, RawEvent("note_on", "55", 0x7F, channel=1)
    )
    two = manager._normalise(
        "banktest", profile, RawEvent("note_on", "55", 0x7F, channel=2)
    )
    assert down == InputEvent("key", "bt_button", 1, "banktest", 1)
    assert two == InputEvent("key", "bt_button", 1, "banktest", 2)


def test_normalise_unknown_channel_logged_once(config, caplog):
    manager = MidiManager(config)
    profile = _banked_profile()
    with caplog.at_level(logging.DEBUG, logger="ma2pi.midi"):
        assert manager._normalise(
            "banktest", profile, RawEvent("note_on", "55", 0x7F, channel=3)
        ) is None
        assert manager._normalise(
            "banktest", profile, RawEvent("note_on", "55", 0x7F, channel=3)
        ) is None
    assert sum("Unbekannter MIDI-Kanal" in record.message for record in caplog.records) == 1


def test_normalise_unbound_note_in_bank(config):
    manager = MidiManager(config)
    profile = _banked_profile()
    assert manager._normalise(
        "banktest", profile, RawEvent("note_on", "15", 0x7F, channel=1)
    ) is None


def test_normalise_bank_button_release(config):
    manager = MidiManager(config)
    profile = _banked_profile()
    assert manager._normalise(
        "banktest", profile, RawEvent("note_off", "55", 0x00, channel=2)
    ) == InputEvent("key", "bt_button", 0, "banktest", 2)


async def test_raw_hook_can_consume_event(config):
    source = FakeMidiSource([midi_info()])
    manager = MidiManager(config, source=source, poll_interval=0.01)
    seen: list[tuple[str, RawEvent]] = []
    manager.set_raw_hook(lambda name, raw: seen.append((name, raw)) or True)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(manager.run(queue))
    try:
        await asyncio.sleep(0.03)
        handle = source.handles["/dev/snd/midiC3D0"]
        await handle.queue.put(RawEvent("note_on", "9", 0x7F))
        await asyncio.sleep(0.03)
        assert seen and seen[0][1].code == "9"
        assert queue.empty()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await manager.close()


def test_format_input_includes_bank_and_note():
    from ma2pi.events import format_input

    line = format_input(InputEvent("value", "bt_fader", 1.0, "banktest", 2, 15))
    assert "bank=2" in line
    assert "note=15" in line


def test_learned_bank_two_example_notes(config):
    from ma2pi.config import BankProfile, ControlProfile

    manager = MidiManager(config)
    profile = ProfileConfig(
        controls=(
            ControlProfile("mc_click_1", "button"),
            ControlProfile("mc_fader_1", "fader"),
        ),
        banks=(
            BankProfile(1, 1, {55: "mc_click_1", 70: "mc_fader_1"}),
            BankProfile(2, 2, {0: "mc_click_1", 15: "mc_fader_1"}),
        ),
    )
    assert manager._normalise(
        "midicraft", profile, RawEvent("note_on", "0", 127, channel=2)
    ) == InputEvent("key", "mc_click_1", 1, "midicraft", 2)
    assert manager._normalise(
        "midicraft", profile, RawEvent("note_on", "15", 127, channel=2)
    ) == InputEvent("value", "mc_fader_1", 1.0, "midicraft", 2)


async def test_midi_reader_uses_new_config_without_restart(config, make_config):
    def mutate(data):
        data["profiles"]["asl-mk2-e4b3"]["notes"]["12"] = "asl_click_1"

    updated = make_config(mutate)
    source = FakeMidiSource([midi_info()])
    manager = MidiManager(config, source=source, poll_interval=0.01)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(manager.run(queue))
    try:
        await asyncio.sleep(0.03)
        handle = source.handles["/dev/snd/midiC3D0"]
        await handle.queue.put(RawEvent("note_on", "12", 0x7F))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), 0.05)

        manager.set_config(updated)
        await handle.queue.put(RawEvent("note_on", "12", 0x7F))
        event = await asyncio.wait_for(queue.get(), 1.0)
        assert event == InputEvent("key", "asl_click_1", 1, "asl-mk2-e4b3", note=12)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await manager.close()


def test_real_handle_write_uses_fd(monkeypatch):
    from ma2pi import midi_input

    handle = object.__new__(midi_input.RealMidiHandle)
    handle._fd = 9
    handle._closed = False
    handle._writable = True
    handle._write_warned = False
    handle._path = "/dev/snd/midiC4D0"
    written: list[tuple[int, bytes]] = []
    monkeypatch.setattr(
        midi_input.os,
        "write",
        lambda fd, data: written.append((fd, data)) or len(data),
    )

    assert handle.write(b"\x90\x41\x7f") is True
    assert written == [(9, b"\x90\x41\x7f")]


def test_real_handle_write_warns_once_on_error(monkeypatch, caplog):
    from ma2pi import midi_input

    handle = object.__new__(midi_input.RealMidiHandle)
    handle._fd = 9
    handle._closed = False
    handle._writable = True
    handle._write_warned = False
    handle._path = "/dev/snd/midiC4D0"

    def fail(fd, data):
        raise OSError("device gone")

    monkeypatch.setattr(midi_input.os, "write", fail)
    with caplog.at_level("WARNING"):
        assert handle.write(b"\x90\x41\x7f") is False
        assert handle.write(b"\x90\x41\x7f") is False
    assert caplog.text.count("MIDI-Ausgabe an /dev/snd/midiC4D0") == 1


def test_real_handle_write_is_ignored_when_closed():
    from ma2pi import midi_input

    handle = object.__new__(midi_input.RealMidiHandle)
    handle._fd = 9
    handle._closed = True
    handle._writable = True
    handle._write_warned = False
    handle._path = "/dev/snd/midiC4D0"

    assert handle.write(b"\x90\x41\x7f") is False


async def test_manager_send_uses_open_device(config):
    source = FakeMidiSource([midicraft_info()])
    manager = MidiManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    try:
        await manager.reconcile(queue)
        handle = source.handles[midicraft_info().path]
        assert manager.send("midicraft-enc", b"\x90\x41\x7f") is True
        assert handle.written == [b"\x90\x41\x7f"]
        assert manager.send("asl-mk2-e4b3", b"\x90\x41\x7f") is False
    finally:
        await manager.close()


def test_real_handle_write_is_ignored_when_read_only(monkeypatch, caplog):
    from ma2pi import midi_input

    handle = object.__new__(midi_input.RealMidiHandle)
    handle._fd = 9
    handle._closed = False
    handle._writable = False
    handle._write_warned = False
    handle._path = "/dev/snd/midiC4D0"

    def fail(fd, data):
        raise AssertionError("read-only handle must not write")

    monkeypatch.setattr(midi_input.os, "write", fail)
    with caplog.at_level("WARNING"):
        assert handle.write(b"\x90\x41\x7f") is False
        assert handle.write(b"\x90\x41\x7f") is False
    assert caplog.text.count("nur lesbar") == 1


def _real_handle(midi_input, *, writable=True, out_size=4096):
    handle = object.__new__(midi_input.RealMidiHandle)
    handle._fd = 9
    handle._closed = False
    handle._writable = writable
    handle._write_warned = False
    handle._path = "/dev/snd/midiC4D0"
    handle._out_size = out_size
    return handle


def test_real_handle_output_pending_is_buffer_minus_free(monkeypatch):
    from ma2pi import midi_input

    handle = _real_handle(midi_input)
    monkeypatch.setattr(midi_input, "rawmidi_output_free", lambda fd: 4090)
    assert handle.output_pending() == 6
    monkeypatch.setattr(midi_input, "rawmidi_output_free", lambda fd: 4096)
    assert handle.output_pending() == 0


def test_real_handle_output_pending_unknown_cases(monkeypatch):
    from ma2pi import midi_input

    monkeypatch.setattr(midi_input, "rawmidi_output_free", lambda fd: None)
    assert _real_handle(midi_input).output_pending() is None
    assert _real_handle(midi_input, writable=False).output_pending() is None
    assert _real_handle(midi_input, out_size=None).output_pending() is None
    closed = _real_handle(midi_input)
    closed._closed = True
    assert closed.output_pending() is None


def test_rawmidi_output_free_returns_none_on_error(monkeypatch):
    from ma2pi import midi_input

    def fail(fd, request, buffer, mutate):
        raise OSError("not a rawmidi device")

    monkeypatch.setattr(midi_input.fcntl, "ioctl", fail)
    assert midi_input.rawmidi_output_free(9) is None


def test_rawmidi_ioctl_numbers_match_kernel_headers():
    from ma2pi import midi_input

    # _IOWR('W', 0x20, struct snd_rawmidi_status) and _IOW('W', 0x30, int)
    assert midi_input._RAWMIDI_IOCTL_DROP == 0x40045730
    assert midi_input._RAWMIDI_IOCTL_STATUS & 0xFFFF == 0x5720
    assert midi_input._RAWMIDI_IOCTL_STATUS >> 30 == 3


async def test_real_handle_close_drops_pending_output(monkeypatch):
    from ma2pi import midi_input

    handle = _real_handle(midi_input)
    handle._loop = asyncio.get_running_loop()
    calls: list[str] = []
    monkeypatch.setattr(handle._loop, "remove_reader", lambda fd: None)
    monkeypatch.setattr(
        midi_input, "rawmidi_drop_output", lambda fd: calls.append("drop")
    )
    monkeypatch.setattr(midi_input.os, "close", lambda fd: calls.append("close"))
    await handle.close()
    assert calls == ["drop", "close"]


async def test_real_handle_close_survives_failing_drop(monkeypatch):
    from ma2pi import midi_input

    handle = _real_handle(midi_input)
    handle._loop = asyncio.get_running_loop()
    closed: list[int] = []
    monkeypatch.setattr(handle._loop, "remove_reader", lambda fd: None)

    def fail(fd):
        raise OSError("no")

    monkeypatch.setattr(midi_input, "rawmidi_drop_output", fail)
    monkeypatch.setattr(midi_input.os, "close", closed.append)
    await handle.close()
    assert closed == [9]


async def test_manager_output_pending_is_none_for_unknown_device(config):
    manager = MidiManager(config, source=FakeMidiSource([]))
    assert manager.output_pending("midicraft") is None


def test_real_handle_read_only_close_does_not_drop(monkeypatch):
    from ma2pi import midi_input

    handle = _real_handle(midi_input, writable=False)
    handle._loop = asyncio.new_event_loop()
    try:
        monkeypatch.setattr(handle._loop, "remove_reader", lambda fd: None)

        def fail(fd):
            raise AssertionError("read-only handle must not drop output")

        monkeypatch.setattr(midi_input, "rawmidi_drop_output", fail)
        monkeypatch.setattr(midi_input.os, "close", lambda fd: None)
        handle._loop.run_until_complete(handle.close())
    finally:
        handle._loop.close()


async def test_manager_stop_does_not_wait_for_a_backed_up_device(monkeypatch):
    """A device that never drains must not hold the shutdown (kernel drain 10 s)."""

    import time

    from ma2pi import midi_input

    handle = _real_handle(midi_input)
    handle._loop = asyncio.get_running_loop()
    state = {"dropped": False}
    monkeypatch.setattr(handle._loop, "remove_reader", lambda fd: None)
    monkeypatch.setattr(
        midi_input,
        "rawmidi_drop_output",
        lambda fd: state.__setitem__("dropped", True),
    )

    def close(fd):
        # Like the kernel: close() blocks while undrained output is queued.
        if not state["dropped"]:
            time.sleep(5)

    monkeypatch.setattr(midi_input.os, "close", close)

    async def idle():
        await asyncio.Event().wait()

    config = None
    manager = MidiManager.__new__(MidiManager)
    manager._stopping = False
    manager._lock = asyncio.Lock()
    manager._open = {
        "midicraft": midi_input._OpenMidi(
            midicraft_info(), handle, asyncio.create_task(idle())
        )
    }
    started = time.monotonic()
    await manager.close()
    assert time.monotonic() - started < 1.0
    assert manager._open == {}
    del config


def test_real_handle_on_readable_detaches_reader_immediately_on_oserror(monkeypatch):
    from ma2pi import midi_input

    handle = _real_handle(midi_input)
    handle._reader_removed = False
    handle._queue = asyncio.Queue()
    removed: list[int] = []

    class DummyLoop:
        def remove_reader(self, fd: int) -> None:
            removed.append(fd)

    handle._loop = DummyLoop()

    def broken_read(fd: int, size: int) -> bytes:
        raise OSError(19, "No such device")

    monkeypatch.setattr(midi_input.os, "read", broken_read)
    handle._on_readable()
    assert removed == [9]
    assert isinstance(handle._queue.get_nowait(), OSError)


def test_real_handle_refuses_partial_frame_when_buffer_nearly_full(monkeypatch):
    from ma2pi import midi_input

    handle = _real_handle(midi_input, out_size=4096)
    monkeypatch.setattr(midi_input, "rawmidi_output_free", lambda fd: 2)
    monkeypatch.setattr(
        midi_input.os,
        "write",
        lambda fd, data: (_ for _ in ()).throw(AssertionError("must not split 3-byte frame")),
    )
    assert handle.write(b"\x90\x41\x7f") is False


def test_rawmidi_output_free_falls_back_to_status64(monkeypatch):
    from ma2pi import midi_input

    monkeypatch.setattr(midi_input, "_RAWMIDI_IOCTL_STATUS", 0xC0205720)
    monkeypatch.setattr(midi_input, "_RAWMIDI_IOCTL_STATUS64", 0xC0305720)

    def fake_ioctl(fd, request, buffer, mutate):
        if request == 0xC0205720:
            raise OSError(25, "Inappropriate ioctl")
        s64 = midi_input._RawmidiStatus64.from_buffer(buffer)
        s64.avail = 3072
        return 0

    monkeypatch.setattr(midi_input.fcntl, "ioctl", fake_ioctl)
    assert midi_input.rawmidi_output_free(9) == 3072


def test_select_midi_devices_assigns_distinct_nodes(make_config):
    from ma2pi.midi_input import select_midi_devices

    def mutate(data):
        dev_name = next(k for k, v in data["devices"].items() if v["profile"] == "midicraft-enc")
        data["devices"]["midicraft_two"] = dict(data["devices"][dev_name])

    cfg = make_config(mutate)
    m1 = midicraft_info("/dev/snd/midiC3D0")
    m2 = midicraft_info("/dev/snd/midiC4D0")
    selected = select_midi_devices(cfg, [m1, m2])
    paths = sorted(info.path for info in selected.values())
    assert paths == ["/dev/snd/midiC3D0", "/dev/snd/midiC4D0"]
