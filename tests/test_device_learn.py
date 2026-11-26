from __future__ import annotations

import pytest

from ma2pi.device_learn import DeviceLearnError, DeviceLearnManager
from ma2pi.hid_input import RawEvent


def _bank_config(data):
    data["led"]["enabled"] = False
    data["profiles"]["bank-test"] = {
        "controls": [
            {"id": "bt_fader", "kind": "fader"},
            {"id": "bt_button", "kind": "button"},
            {"id": "bt_encoder", "kind": "encoder"},
        ],
        "banks": [
            {
                "number": 1,
                "notes": {"70": "bt_fader", "55": "bt_button", "60": "bt_encoder"},
            },
            {"number": 2, "notes": {}},
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
            "columns": 3,
            "rows": [
                {
                    "cells": [
                        {"label": "F", "control": "bt_fader"},
                        {"label": "B", "control": "bt_button"},
                        {"label": "E", "control": "bt_encoder"},
                    ]
                }
            ],
        }
    }


@pytest.fixture
def bank_config(make_config):
    return make_config(_bank_config)


def test_start_walks_layout_order(bank_config):
    manager = DeviceLearnManager(bank_config, clock=lambda: 10.0)
    status = manager.start("banktest", 2)
    assert status["current"] == "bt_fader"
    assert status["total"] == 3
    assert status["channel"] == 2


def test_start_rejects_running_session(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    with pytest.raises(DeviceLearnError, match="bereits"):
        manager.start("banktest", 2)


def test_start_rejects_unknown_bank(bank_config):
    manager = DeviceLearnManager(bank_config)
    with pytest.raises(DeviceLearnError, match="nicht definiert"):
        manager.start("banktest", 5)


def test_capture_advances_and_sets_note(bank_config):
    manager = DeviceLearnManager(bank_config, clock=lambda: 5.0)
    manager.start("banktest", 2)
    assert manager.handle_raw(
        "banktest", RawEvent("note_on", "15", 127, channel=2)
    )
    status = manager.status()
    assert status["current"] == "bt_button"
    assert status["captured"] == [{"note": 15, "control": "bt_fader"}]


def test_wrong_channel_is_reported(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=3))
    status = manager.status()
    assert "Kanal 3" in status["error"]
    assert status["current"] == "bt_fader"
    assert status["captured"] == []


def test_duplicate_note_is_rejected(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=2))
    manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=2))
    status = manager.status()
    assert "bereits" in status["error"]
    assert status["current"] == "bt_button"


def test_skip_moves_on_without_capture(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    status = manager.skip()
    assert status["current"] == "bt_button"
    assert status["captured"] == []


def test_cancel_discards_captures(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=2))
    manager.cancel()
    assert not manager.active


def test_finish_returns_bank_and_captures(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=2))
    manager.handle_raw("banktest", RawEvent("note_on", "0", 127, channel=2))
    device, bank, captured = manager.finish()
    assert device == "banktest"
    assert bank == 2
    assert captured == {15: "bt_fader", 0: "bt_button"}
    assert not manager.active


def test_device_loss_pauses(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.device_lost("banktest")
    status = manager.status()
    assert status["paused"] is True
    assert "getrennt" in status["error"]


def test_timeout_pauses(bank_config):
    now = [0.0]
    manager = DeviceLearnManager(bank_config, clock=lambda: now[0], timeout=10.0)
    manager.start("banktest", 2)
    now[0] = 11.0
    manager.poll()
    status = manager.status()
    assert status["paused"] is True
    assert "Zeit" in status["error"]


def test_paused_session_resumes_on_next_note(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.device_lost("banktest")
    assert manager.status()["paused"] is True
    manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=2))
    status = manager.status()
    assert status["paused"] is False
    assert status["captured"] == [{"note": 15, "control": "bt_fader"}]


def test_skip_resumes_paused_session(bank_config):
    manager = DeviceLearnManager(bank_config)
    manager.start("banktest", 2)
    manager.device_lost("banktest")
    status = manager.skip()
    assert status["paused"] is False
    assert status["current"] == "bt_button"


def test_start_with_explicit_bound_control(bank_config):
    manager = DeviceLearnManager(bank_config)
    status = manager.start("banktest", 1, control="bt_fader")
    assert status["total"] == 1
    assert status["current"] == "bt_fader"
    assert manager.handle_raw(
        "banktest", RawEvent("note_on", "72", 127, channel=1)
    )
    assert manager.status()["captured"] == [{"note": 72, "control": "bt_fader"}]
