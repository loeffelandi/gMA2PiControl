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

MIDICRAFT = DeviceInfo(
    path="/dev/snd/midiC4D0",
    name="MIDICRAFT ENC MIDI 1",
    vendor_id=0x04D8,
    product_id=0xE78C,
    backend="midi",
)


def test_device_summary_contains_controls_and_detection(config):
    devices = device_summary(config, [CHERRY, ASL, MIDICRAFT])
    by_name = {entry["name"]: entry for entry in devices}

    assert {"cherry", "asl", "midicraft"} <= set(by_name)

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

    midicraft = by_name["midicraft"]
    assert midicraft["backend"] == "midi"
    assert midicraft["vendor_product"] == "04d8:e78c"
    assert midicraft["detected"]["path"] == MIDICRAFT.path
    assert "mc_fader_1" in midicraft["controls"]["logical"]
    assert midicraft["controls"]["banks"][0]["notes"]["55"] == "mc_click_1"
    assert midicraft["controls"]["banks"][0]["notes"]["70"] == "mc_fader_1"
    inventory = {entry["id"]: entry for entry in midicraft["controls"]["inventory"]}
    assert len(inventory) == 30
    assert inventory["mc_fader_1"]["kind"] == "fader"
    assert inventory["mc_encoder_1"]["kind"] == "encoder"


def test_device_summary_without_detection(config):
    devices = device_summary(config)
    assert all(entry["detected"] is None for entry in devices)
    assert all(entry["controls"]["logical"] for entry in devices)


async def test_devices_endpoint(config):
    provider = lambda: device_summary(config, [CHERRY, ASL, MIDICRAFT])
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
        assert by_name["midicraft"]["controls"]["banks"][0]["notes"]
    finally:
        await client.close()


def _bank_device_config(make_config):
    def mutate(data):
        data["led"]["enabled"] = False
        data["profiles"]["bank-test"] = {
            "controls": [
                {"id": "bt_fader", "kind": "fader", "label": "Fader"},
                {"id": "bt_button", "kind": "button"},
            ],
            "banks": [
                {"number": 1, "notes": {"70": "bt_fader"}},
                {"number": 2, "channel": 3, "notes": {"15": "bt_fader", "55": "bt_button"}},
            ],
        }
        data["devices"]["banktest"] = {
            "backend": "midi",
            "vendor_id": 0x04D8,
            "product_id": 0x1234,
            "name_contains": "Bank Test",
            "profile": "bank-test",
        }
        data["layouts"] = {
            "surface": {
                "profile": "bank-test",
                "columns": 2,
                "rows": [
                    {
                        "cells": [
                            {"label": "F", "control": "bt_fader", "color": "green"},
                            {"label": "B", "control": "bt_button"},
                        ]
                    }
                ],
            }
        }
        data["mapping"]["device_banks"] = {"banktest": {"bank_size": 7}}

    return make_config(mutate)


def test_device_summary_includes_layout_banks_and_inventory(make_config):
    config = _bank_device_config(make_config)
    entry = {item["name"]: item for item in device_summary(config, [])}["banktest"]
    assert entry["bank_size"] == 7
    assert entry["layout"]["columns"] == 2
    assert entry["layout"]["rows"][0]["cells"][0]["color"] == "green"
    assert [bank["number"] for bank in entry["controls"]["banks"]] == [1, 2]
    assert entry["controls"]["banks"][1]["channel"] == 3
    assert entry["controls"]["banks"][1]["notes"]["15"] == "bt_fader"
    assert {control["id"] for control in entry["controls"]["inventory"]} == {
        "bt_fader",
        "bt_button",
    }
    assert "bt_fader" in entry["controls"]["logical"]


def test_device_summary_without_layout_reports_null(make_config):
    config = make_config(lambda data: data["layouts"].pop("cherry"))
    entry = {item["name"]: item for item in device_summary(config, [])}["cherry"]
    assert entry["layout"] is None


def test_legacy_profile_inventory_is_derived(config):
    entry = {item["name"]: item for item in device_summary(config, [])}["asl"]
    inventory = {item["id"]: item for item in entry["controls"]["inventory"]}
    assert inventory["encoder.1"]["kind"] == "relative-encoder"
    assert inventory["asl_click_1"]["kind"] == "button"
