from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from ma2pi.config import load_config
from ma2pi.events import DeviceLost, InputEvent
from ma2pi.hid_input import (
    DeviceInfo,
    EncoderDecoder,
    HidManager,
    RawEvent,
    device_matches,
    format_devices,
    select_devices,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeHandle:
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


class FakeSource:
    def __init__(self, devices: list[DeviceInfo]) -> None:
        self.devices = devices
        self.handles: dict[str, FakeHandle] = {}
        self.fail_paths: dict[str, Exception] = {}
        self.opened: list[str] = []
        self.attempts = 0

    def list_devices(self) -> list[DeviceInfo]:
        return list(self.devices)

    async def open(self, info: DeviceInfo):
        self.attempts += 1
        if info.path in self.fail_paths:
            raise self.fail_paths[info.path]
        handle = FakeHandle()
        self.handles[info.path] = handle
        self.opened.append(info.path)
        return handle


# The fake Cherry device advertises exactly the keys the shipped profile maps,
# so profile/device mismatches show up as a real error instead of test noise.
CHERRY_KEYS = tuple(
    load_config(ROOT / "config.toml").profiles["cherry-g86"].keys
)

ASL_KEYS = ("BTN_0", "BTN_1")
ASL_ABS = ("ABS_X", "ABS_Y", "ABS_Z", "ABS_RX")


def info(
    path: str,
    name: str = "Cherry",
    vendor: int = 0x046A,
    product: int = 0x0001,
    keys: tuple[str, ...] = CHERRY_KEYS,
    abs_codes: tuple[str, ...] = (),
) -> DeviceInfo:
    return DeviceInfo(
        path=path,
        name=name,
        vendor_id=vendor,
        product_id=product,
        key_codes=frozenset(keys),
        abs_codes=frozenset(abs_codes),
        abs_ranges={code: (0, 23) for code in abs_codes},
    )


def cherry() -> DeviceInfo:
    return info("/dev/input/event1")


def asl() -> DeviceInfo:
    return info(
        "/dev/input/event2",
        name="ASL MK2 E4B3",
        vendor=0x1234,
        product=0x5678,
        keys=ASL_KEYS,
        abs_codes=ASL_ABS,
    )


def test_device_matches(config):
    device = config.devices["cherry-g86"]
    assert device_matches(device, cherry())
    assert not device_matches(device, info("/dev/input/event9", vendor=0x1111))
    assert not device_matches(device, info("/dev/input/event9", name="Other"))
    unreadable = DeviceInfo("/dev/input/event9", "Cherry", 0x046A, 1, readable=False)
    assert not device_matches(device, unreadable)


def test_select_prefers_keyboard_interface(config):
    weak = info("/dev/input/event1", keys=("KEY_F1",))
    strong = info("/dev/input/event2", keys=("KEY_F1", "KEY_F2", "KEY_F3"))
    selected = select_devices(config, [weak, strong])
    assert selected["cherry-g86"].path == "/dev/input/event2"


def test_select_ignores_unknown(config):
    selected = select_devices(config, [info("/dev/input/event9", name="Maus", vendor=0x2222)])
    assert selected == {}


def test_normalise_key_and_autorepeat(config):
    manager = HidManager(config, source=FakeSource([]))
    profile = config.profiles["cherry-g86"]
    device = cherry()
    assert manager._normalise("cherry-g86", device, profile, RawEvent("key", "KEY_E", 1)) == InputEvent(
        "key", "pause_big", 1, "cherry-g86"
    )
    assert manager._normalise("cherry-g86", device, profile, RawEvent("key", "KEY_E", 0)) == InputEvent(
        "key", "pause_big", 0, "cherry-g86"
    )
    assert manager._normalise("cherry-g86", device, profile, RawEvent("key", "KEY_E", 2)) is None
    assert manager._normalise("cherry-g86", device, profile, RawEvent("key", "KEY_MICMUTE", 1)) is None


def test_encoder_absolute_three_and_minus_two():
    from ma2pi.config import EncoderProfile

    decoder = EncoderDecoder(EncoderProfile(1, "ABS_X", 24, 1))
    assert decoder.feed(RawEvent("abs", "ABS_X", 0, 0, 23)) == 0
    assert decoder.feed(RawEvent("abs", "ABS_X", 3, 0, 23)) == 3
    assert decoder.feed(RawEvent("abs", "ABS_X", 1, 0, 23)) == -2


def test_encoder_absolute_wrap_around():
    from ma2pi.config import EncoderProfile

    decoder = EncoderDecoder(EncoderProfile(1, "ABS_X", 24, 1))
    assert decoder.feed(RawEvent("abs", "ABS_X", 22, 0, 23)) == 0
    assert decoder.feed(RawEvent("abs", "ABS_X", 1, 0, 23)) == 3


def test_encoder_relative_and_direction():
    from ma2pi.config import EncoderProfile

    decoder = EncoderDecoder(EncoderProfile(1, "ABS_X", 24, -1))
    assert decoder.feed(RawEvent("rel", "ABS_X", 3)) == -3
    assert decoder.feed(RawEvent("rel", "ABS_X", -2)) == 2


def test_encoder_threshold_discards_noise():
    from ma2pi.config import EncoderProfile

    decoder = EncoderDecoder(EncoderProfile(1, "ABS_X", 24, 1, threshold=2))
    assert decoder.feed(RawEvent("abs", "ABS_X", 0, 0, 23)) == 0
    assert decoder.feed(RawEvent("abs", "ABS_X", 1, 0, 23)) == 0
    assert decoder.feed(RawEvent("abs", "ABS_X", 4, 0, 23)) == 3


def test_normalise_encoder_event(config):
    from ma2pi.config import EncoderProfile, ProfileConfig

    manager = HidManager(config, source=FakeSource([]))
    profile = ProfileConfig(encoders=(EncoderProfile(1, "ABS_X", 24, 1),))
    device = info(
        "/dev/input/event2",
        name="Test-Encoder",
        vendor=0x1234,
        product=0x5678,
        keys=(),
        abs_codes=("ABS_X",),
    )
    assert manager._normalise("asl-mk2-e4b3", device, profile, RawEvent("abs", "ABS_X", 0, 0, 23)) is None
    event = manager._normalise("asl-mk2-e4b3", device, profile, RawEvent("abs", "ABS_X", 3, 0, 23))
    assert event == InputEvent("encoder", "encoder.1", 3, "asl-mk2-e4b3")


async def test_hid_manager_hotplug(config):
    source = FakeSource([cherry()])
    manager = HidManager(config, source=source, poll_interval=0.01)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(manager.run(queue))
    try:
        await asyncio.sleep(0.03)
        assert "cherry-g86" in manager.open_devices
        handle = source.handles["/dev/input/event1"]
        await handle.queue.put(RawEvent("key", "KEY_E", 1))
        event = await asyncio.wait_for(queue.get(), 1.0)
        assert event == InputEvent("key", "pause_big", 1, "cherry-g86")

        source.devices = []
        lost = await asyncio.wait_for(queue.get(), 2.0)
        assert isinstance(lost, DeviceLost)
        assert lost.device == "cherry-g86"
        assert handle.closed

        source.devices = [cherry()]
        await asyncio.sleep(0.05)
        assert "cherry-g86" in manager.open_devices
        assert len(source.opened) == 2
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await manager.close()


async def test_permission_error_keeps_daemon_running(config, caplog):
    source = FakeSource([cherry()])
    source.fail_paths["/dev/input/event1"] = PermissionError("denied")
    manager = HidManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.ERROR):
        await manager.reconcile(queue)
    assert "udev" in caplog.text
    assert queue.empty()
    assert manager.open_devices == {}


async def test_missing_device_at_start_only_warns_once(config, caplog):
    source = FakeSource([])
    manager = HidManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.WARNING):
        await manager.reconcile(queue)
        await manager.reconcile(queue)
    assert caplog.text.count("nicht gefunden") == 1  # ASL is a MIDI device now
    assert queue.empty()


def test_format_devices():
    text = format_devices([cherry()])
    assert "event1" in text
    assert "0x046a" in text
    assert "KEY_F1" not in text  # only count is printed


async def test_profile_with_missing_control_aborts(config):
    from ma2pi.hid_input import ProfileError

    source = FakeSource([info("/dev/input/event1", keys=("KEY_F1",))])
    manager = HidManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with pytest.raises(ProfileError, match="KEY_F2"):
        await manager.reconcile(queue)
    assert source.attempts == 0
    assert manager.open_devices == {}


async def test_open_failure_uses_backoff(config, caplog):
    source = FakeSource([cherry()])
    source.fail_paths["/dev/input/event1"] = PermissionError("denied")
    now = [0.0]
    manager = HidManager(config, source=source, clock=lambda: now[0])
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.ERROR):
        await manager.reconcile(queue)
        await manager.reconcile(queue)
    assert source.attempts == 1
    assert caplog.text.count("nächster Versuch") == 1
    now[0] = 1.1
    await manager.reconcile(queue)
    assert source.attempts == 2


async def test_unknown_device_is_logged_once(config, caplog):
    source = FakeSource(
        [info("/dev/input/event9", name="Maus", vendor=0x2222, product=0x0001)]
    )
    manager = HidManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.DEBUG):
        await manager.reconcile(queue)
        await manager.reconcile(queue)
    assert caplog.text.count("Unbekanntes Gerät ignoriert") == 1


async def test_vendor_match_without_profile_warns(config, caplog):
    source = FakeSource(
        [info("/dev/input/event9", name="Anderes Gerät", vendor=0x046A, product=0x0001)]
    )
    manager = HidManager(config, source=source)
    queue: asyncio.Queue = asyncio.Queue()
    with caplog.at_level(logging.WARNING):
        await manager.reconcile(queue)
        await manager.reconcile(queue)
    assert caplog.text.count("passt zur Vendor-ID") == 1
    assert manager.open_devices == {}
