"""Tests for the device and logical-control API."""

from __future__ import annotations

from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from ma2pi.hid_input import DeviceInfo
from ma2pi.web import create_app
from ma2pi.web.devices import device_summary

CHERRY = DeviceInfo(
    path="/dev/input/event0",
    name="Cherry GmbH POS Keyboard",
    vendor_id=0x046A,
    product_id=0x0001,
    key_codes=frozenset({"KEY_F1"}),
    backend="evdev",
)

ASL = DeviceInfo(
    path="/dev/snd/midiC1D0",
    name="ASL MK2-E4B3",
    vendor_id=0x04D8,
    product_id=0xE817,
    backend="midi",
)


def test_device_summary_contains_controls_and_detection(config):
    devices = device_summary(config, [CHERRY, ASL])
    by_name = {entry["name"]: entry for entry in devices}

    assert set(by_name) == {"cherry", "asl"}

    cherry = by_name["cherry"]
    assert cherry["vendor_id"] == 0x046A
    assert cherry["vendor_product"] == "046a:0000"
    assert cherry["detected"]["path"] == CHERRY.path
    assert "ch_pg_plus" in cherry["controls"]["logical"]
    assert cherry["controls"]["keys"]

    asl = by_name["asl"]
    assert asl["backend"] == "midi"
    assert asl["vendor_product"] == "04d8:e817"
    assert asl["detected"]["path"] == ASL.path
    assert "asl_click_1" in asl["controls"]["logical"]
    assert [encoder["id"] for encoder in asl["controls"]["midi_encoders"]] == [
        1,
        2,
        3,
        4,
    ]


def test_device_summary_without_detection(config):
    devices = device_summary(config)
    assert all(entry["detected"] is None for entry in devices)
    assert all(entry["controls"]["logical"] for entry in devices)


async def test_devices_endpoint(config):
    provider = lambda: device_summary(config, [CHERRY, ASL])
    client = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                devices_provider=provider,
            )
        )
    )
    await client.start_server()
    try:
        response = await client.get("/api/devices")
        assert response.status == 200
        body = await response.json()
        by_name = {entry["name"]: entry for entry in body["devices"]}
        assert by_name["cherry"]["detected"]["vendor_product"] == "046a:0001"
        assert by_name["asl"]["controls"]["midi_encoders"]
    finally:
        await client.close()
