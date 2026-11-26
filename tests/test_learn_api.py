"""Tests for learn endpoints, WebSocket events and input routing."""

from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from ma2pi.__main__ import _learn_loop, _process_input
from ma2pi.events import InputEvent
from ma2pi.learn import LearnManager
from ma2pi.mapping import MappingEngine
from ma2pi.web import create_app
from ma2pi.web.events import EventBus


class Sink:
    def __init__(self) -> None:
        self.actions: list[tuple] = []

    def press(self, keyname: str, hold: bool = False) -> None:
        self.actions.append(("press", keyname))

    def release(self, keyname: str) -> None:
        self.actions.append(("release", keyname))

    def command(self, text: str) -> None:
        self.actions.append(("command", text))

    def encoder_slot(self, slot: int, delta: float, screen: bool = False) -> None:
        self.actions.append(("slot", slot, delta))

    def encoder_attribute(self, name: str, value: float) -> None:
        self.actions.append(("attribute", name, value))

    def toggle_screen_mode(self) -> None:
        self.actions.append(("screen_mode",))

    def toggle_fine(self, slot: int) -> None:
        self.actions.append(("fine", slot))

    def screen_shortcut(self, screen: int) -> None:
        self.actions.append(("screen", screen))


def key(control: str, value: int, device: str = "cherry-g86") -> InputEvent:
    return InputEvent("key", control, value, device)


async def wait_until(predicate, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


async def test_learn_api_start_and_cancel_publish_events(config):
    learn = LearnManager(config)
    client = TestClient(
        TestServer(
            create_app(
                config, dist_dir=Path("/nonexistent"), learn_manager=learn
            )
        )
    )
    await client.start_server()
    headers = {"X-Ma2pi-Request": "1"}
    try:
        ws = await client.ws_connect("/api/events")
        await ws.receive_json()  # initial status

        started = await client.post(
            "/api/learn/start", json={"kind": "key"}, headers=headers
        )
        assert started.status == 200
        assert (await started.json())["status"] == "active"
        event = await ws.receive_json()
        assert event["type"] == "learn"
        assert event["data"]["kind"] == "key"
        assert event["data"]["status"] == "active"

        busy = await client.post(
            "/api/learn/start", json={"kind": "encoder"}, headers=headers
        )
        assert busy.status == 409

        cancelled = await client.post("/api/learn/cancel", json={}, headers=headers)
        assert cancelled.status == 200
        body = await cancelled.json()
        assert body["cancelled"] is True
        assert body["learn"]["status"] == "cancelled"
        event = await ws.receive_json()
        assert event["data"]["status"] == "cancelled"
        assert learn.active is False
        await ws.close()
    finally:
        await client.close()


async def test_learn_api_rejects_unknown_kind(config):
    learn = LearnManager(config)
    client = TestClient(
        TestServer(
            create_app(
                config, dist_dir=Path("/nonexistent"), learn_manager=learn
            )
        )
    )
    await client.start_server()
    try:
        response = await client.post(
            "/api/learn/start",
            json={"kind": "wheel"},
            headers={"X-Ma2pi-Request": "1"},
        )
        assert response.status == 422
    finally:
        await client.close()


async def test_input_routing_suppresses_frames_and_resumes(config):
    sink = Sink()
    engine = MappingEngine(config, sink)
    learn = LearnManager(config)
    bus = EventBus()
    queue: asyncio.Queue = asyncio.Queue()
    events: asyncio.Queue = bus.subscribe()

    input_task = asyncio.create_task(_process_input(queue, engine, learn, bus))
    learn_task = asyncio.create_task(_learn_loop(learn, bus))
    try:
        learn.start("key")
        await queue.put(key("fix", 1))
        await queue.put(key("fix", 0))
        await wait_until(lambda: not learn.active)

        captured = await asyncio.wait_for(events.get(), timeout=2.0)
        assert captured["type"] == "learn"
        assert captured["data"]["status"] == "captured"
        assert captured["data"]["control"] == "fix"
        assert captured["data"]["raw"] == "KEY_HOME"
        assert sink.actions == []

        # Normal operation resumes after the session ended.
        await queue.put(key("fix", 1))
        await wait_until(lambda: sink.actions == [("press", "FIX")])
    finally:
        input_task.cancel()
        learn_task.cancel()
        for task in (input_task, learn_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        bus.unsubscribe(events)


async def test_learn_timeout_returns_to_normal_operation(config):
    sink = Sink()
    engine = MappingEngine(config, sink)
    learn = LearnManager(config, timeout=0.2)
    bus = EventBus()
    queue: asyncio.Queue = asyncio.Queue()
    events: asyncio.Queue = bus.subscribe()

    input_task = asyncio.create_task(_process_input(queue, engine, learn, bus))
    learn_task = asyncio.create_task(_learn_loop(learn, bus))
    try:
        learn.start("key")
        timed_out = await asyncio.wait_for(events.get(), timeout=3.0)
        assert timed_out["data"]["status"] == "timeout"
        assert learn.active is False

        await queue.put(key("fix", 1))
        await wait_until(lambda: sink.actions == [("press", "FIX")])
    finally:
        input_task.cancel()
        learn_task.cancel()
        for task in (input_task, learn_task):
            try:
                await task
            except asyncio.CancelledError:
                pass
        bus.unsubscribe(events)


class _FakeStore:
    def __init__(self, config):
        self.config = config
        self.generation = 0
        self.patches: list[dict] = []

    async def apply(self, patch, *, password=None):
        self.patches.append(patch)
        self.generation += 1
        return self.config


def _banked_config(make_config):
    def mutate(data):
        data["led"]["enabled"] = False
        data["profiles"]["bank-test"] = {
            "controls": [
                {"id": "bt_fader", "kind": "fader"},
                {"id": "bt_button", "kind": "button"},
            ],
            "banks": [
                {"number": 1, "notes": {"70": "bt_fader", "55": "bt_button"}},
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
                "columns": 2,
                "rows": [
                    {
                        "cells": [
                            {"label": "F", "control": "bt_fader"},
                            {"label": "B", "control": "bt_button"},
                        ]
                    }
                ],
            }
        }

    return make_config(mutate)


async def test_device_learn_api_start_skip_finish(make_config):
    from ma2pi.device_learn import DeviceLearnManager
    from ma2pi.hid_input import RawEvent

    config = _banked_config(make_config)
    store = _FakeStore(config)
    manager = DeviceLearnManager(config)
    client = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                config_store=store,
                device_learn_manager=manager,
            )
        )
    )
    await client.start_server()
    headers = {"X-Ma2pi-Request": "1"}
    try:
        started = await client.post(
            "/api/device-learn/start",
            json={"device": "banktest", "bank": 2},
            headers=headers,
        )
        assert started.status == 200
        status = await started.json()
        assert status["current"] == "bt_fader"

        busy = await client.post(
            "/api/device-learn/start",
            json={"device": "banktest", "bank": 2},
            headers=headers,
        )
        assert busy.status == 409

        manager.handle_raw("banktest", RawEvent("note_on", "15", 127, channel=2))
        skipped = await client.post("/api/device-learn/skip", json={}, headers=headers)
        assert skipped.status == 200

        manager.handle_raw("banktest", RawEvent("note_on", "0", 127, channel=2))
        finished = await client.post("/api/device-learn/finish", json={}, headers=headers)
        assert finished.status == 200
        body = await finished.json()
        assert body["saved"] is True
        assert store.patches
        banks = store.patches[-1]["profiles"]["bank-test"]["banks"]
        assert banks[1]["notes"] == {"15": "bt_fader"}
    finally:
        await client.close()


async def test_device_learn_api_relearns_bound_control(make_config):
    from ma2pi.device_learn import DeviceLearnManager
    from ma2pi.hid_input import RawEvent

    config = _banked_config(make_config)
    store = _FakeStore(config)
    manager = DeviceLearnManager(config)
    client = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                config_store=store,
                device_learn_manager=manager,
            )
        )
    )
    await client.start_server()
    headers = {"X-Ma2pi-Request": "1"}
    try:
        started = await client.post(
            "/api/device-learn/start",
            json={"device": "banktest", "bank": 1, "control": "bt_fader"},
            headers=headers,
        )
        assert started.status == 200
        status = await started.json()
        assert status["current"] == "bt_fader"
        assert status["total"] == 1

        manager.handle_raw("banktest", RawEvent("note_on", "72", 127, channel=1))
        finished = await client.post("/api/device-learn/finish", json={}, headers=headers)
        assert finished.status == 200
        banks = store.patches[-1]["profiles"]["bank-test"]["banks"]
        assert banks[0]["notes"] == {"55": "bt_button", "72": "bt_fader"}
    finally:
        await client.close()
