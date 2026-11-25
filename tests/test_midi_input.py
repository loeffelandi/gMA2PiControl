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


def test_parser_note_on_and_velocity_one_release():
    parser = MidiStreamParser()
    events = parser.feed(bytes([0x90, 1, 0x7F, 0x90, 1, 0x01]))
    assert events == [
        RawEvent("note_on", "1", 0x7F),
        RawEvent("note_on", "1", 0x01),
    ]


def test_parser_note_off_and_velocity_zero():
    parser = MidiStreamParser()
    events = parser.feed(bytes([0x80, 5, 0x40, 0x90, 5, 0x00]))
    assert events == [
        RawEvent("note_off", "5", 0x40),
        RawEvent("note_off", "5", 0x00),
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
    assert selected["asl"].path == "/dev/snd/midiC3D0"
    assert select_midi_devices(config, []) == {}


def test_normalise_button(config):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    assert manager._normalise("asl", profile, RawEvent("note_on", "9", 0x7F)) == InputEvent(
        "key", "asl_bank", 1, "asl"
    )
    assert manager._normalise("asl", profile, RawEvent("note_on", "9", 0x01)) == InputEvent(
        "key", "asl_bank", 0, "asl"
    )
    assert manager._normalise("asl", profile, RawEvent("note_off", "9", 0x01)) == InputEvent(
        "key", "asl_bank", 0, "asl"
    )


def test_normalise_encoder(config):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    assert manager._normalise("asl", profile, RawEvent("note_on", "1", 0x7F)) == InputEvent(
        "encoder", "encoder.1", 1, "asl"
    )
    assert manager._normalise("asl", profile, RawEvent("note_on", "1", 0x01)) == InputEvent(
        "encoder", "encoder.1", -1, "asl"
    )
    assert manager._normalise("asl", profile, RawEvent("note_on", "4", 0x7F)) == InputEvent(
        "encoder", "encoder.4", 1, "asl"
    )
    assert manager._normalise("asl", profile, RawEvent("note_off", "1", 0x00)) is None
    assert manager._normalise("asl", profile, RawEvent("note_on", "1", 0x40)) is None


def test_normalise_encoder_direction_inverts(config):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    encoder = profile.midi_encoders[0]
    inverted = dataclasses.replace(
        profile,
        midi_encoders=(dataclasses.replace(encoder, direction=-1),),
    )
    assert manager._normalise(
        "asl", inverted, RawEvent("note_on", "1", 0x7F)
    ) == InputEvent("encoder", "encoder.1", -1, "asl")
    assert manager._normalise(
        "asl", inverted, RawEvent("note_on", "1", 0x01)
    ) == InputEvent("encoder", "encoder.1", 1, "asl")


def test_normalise_unknown_note_logged_once(config, caplog):
    manager = MidiManager(config)
    profile = config.profiles["asl-mk2-e4b3"]
    with caplog.at_level(logging.DEBUG):
        assert manager._normalise("asl", profile, RawEvent("note_on", "99", 0x7F)) is None
        assert manager._normalise("asl", profile, RawEvent("note_on", "99", 0x7F)) is None
    assert caplog.text.count("Unbekannte MIDI-Note 99") == 1


async def test_midi_manager_hotplug(config):
    source = FakeMidiSource([midi_info()])
    manager = MidiManager(config, source=source, poll_interval=0.01)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(manager.run(queue))
    try:
        await asyncio.sleep(0.03)
        assert "asl" in manager.open_devices
        handle = source.handles["/dev/snd/midiC3D0"]
        await handle.queue.put(RawEvent("note_on", "9", 0x7F))
        event = await asyncio.wait_for(queue.get(), 1.0)
        assert event == InputEvent("key", "asl_bank", 1, "asl")

        source.devices = []
        lost = await asyncio.wait_for(queue.get(), 2.0)
        assert isinstance(lost, DeviceLost)
        assert lost.device == "asl"
        assert handle.closed

        source.devices = [midi_info()]
        await asyncio.sleep(0.05)
        assert "asl" in manager.open_devices
        assert len(source.opened) == 2
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
    assert caplog.text.count("nicht gefunden") == 1
    assert queue.empty()


def test_midi_profile_without_notes_aborts(config):
    device = config.devices["asl"]
    with pytest.raises(ProfileError, match="keine"):
        validate_midi_profile(
            "asl",
            device,
            ProfileConfig(keys={"KEY_F1": "fix"}),
            midi_info(),
        )
