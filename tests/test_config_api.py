"""Tests for the configuration read/write and connection-test API."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from ma2pi.config import load_config
from ma2pi.config_store import ConfigPaths
from ma2pi.ma2_client import ConnectionCheck
from ma2pi.mapping import MappingEngine
from ma2pi.runtime import ConfigStore
from ma2pi.web import create_app
from ma2pi.web.serialize import redacted_config

ROOT = Path(__file__).resolve().parents[1]


from .conftest import NullSink


def _setup(tmp_path: Path, *, tester=None) -> tuple[ConfigPaths, ConfigStore]:
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    paths.state_dir.mkdir(parents=True)
    shutil.copy(ROOT / "config.toml", paths.config)
    _disable_pin(paths.config)
    config = load_config(paths.config)
    engine = MappingEngine(config, NullSink())
    return paths, ConfigStore(config, engine, paths, tester=tester)


def _disable_pin(path: Path) -> None:
    import tomlkit

    document = tomlkit.parse(path.read_text(encoding="utf-8"))
    document["web"]["pin_enabled"] = False
    path.write_text(tomlkit.dumps(document), encoding="utf-8")


async def _app(store: ConfigStore) -> TestClient:
    client = TestClient(
        TestServer(
            create_app(
                store.config,
                dist_dir=Path("/nonexistent"),
                config_store=store,
            )
        )
    )
    await client.start_server()
    return client


def test_redacted_config_contains_no_password_material(config):
    payload = redacted_config(config)
    ma2 = payload["ma2"]

    assert "password_file" not in ma2
    assert "password_env" not in ma2
    assert "password" not in ma2
    assert ma2["password_set"] is True
    assert "source_path" not in payload


async def test_get_config_never_returns_password(tmp_path):
    _, store = _setup(tmp_path)
    client = await _app(store)
    try:
        response = await client.get("/api/config")
        assert response.status == 200
        text = await response.text()
        body = json.loads(text)
        assert "password" not in body["ma2"]
        assert body["ma2"]["password_set"] is True
        assert "ma2.password" not in text
    finally:
        await client.close()


async def test_put_password_is_write_only(tmp_path):
    seen: dict[str, str | None] = {}

    async def tester(candidate, password):
        seen["password"] = password
        return ConnectionCheck(
            session=3,
            username=candidate.ma2.username,
            target="ws://test",
            reused=False,
        )

    paths, store = _setup(tmp_path, tester=tester)
    client = await _app(store)
    headers = {"X-Ma2pi-Request": "1"}
    try:
        response = await client.put(
            "/api/config",
            json={"ma2": {"password": "s3cret"}},
            headers=headers,
        )
        assert response.status == 200
        text = await response.text()
        assert "s3cret" not in text
        assert paths.password.read_text(encoding="utf-8").strip() == "s3cret"
        assert seen["password"] == "s3cret"

        loaded = load_config(paths.config)
        assert loaded.ma2.password_file == str(paths.password)

        body = await (await client.get("/api/config")).json()
        assert "s3cret" not in json.dumps(body)
        assert body["ma2"]["password_set"] is True
        assert "password_file" not in body["ma2"]
    finally:
        await client.close()


async def test_put_rejects_invalid_config_without_writing(tmp_path):
    paths, store = _setup(tmp_path)
    before = paths.config.read_bytes()
    client = await _app(store)
    try:
        response = await client.put(
            "/api/config",
            json={"ma2": {"port": 70000}},
            headers={"X-Ma2pi-Request": "1"},
        )
        assert response.status == 422
        body = await response.json()
        assert body["error"] == "validation_error"
        assert "ma2.port" in body["detail"]
        assert paths.config.read_bytes() == before
    finally:
        await client.close()


async def test_put_sets_and_removes_screen_encoders(tmp_path):
    _, store = _setup(tmp_path)
    client = await _app(store)
    headers = {"X-Ma2pi-Request": "1"}
    try:
        response = await client.put(
            "/api/config",
            json={
                "mapping": {
                    "screen_encoders": {
                        "1": 5,
                        "2": 6,
                        "3": None,
                        "4": None,
                    }
                }
            },
            headers=headers,
        )
        assert response.status == 200
        assert store.config.mapping.screen_encoders == {
            1: 5,
            2: 6,
        }

        response = await client.put(
            "/api/config",
            json={"mapping": {"screen_encoders": {"2": None}}},
            headers=headers,
        )
        assert response.status == 200
        assert store.config.mapping.screen_encoders == {1: 5}
        body = await (await client.get("/api/config")).json()
        assert body["mapping"]["screen_encoders"] == {"1": 5}
    finally:
        await client.close()


async def test_validate_does_not_write(tmp_path):
    paths, store = _setup(tmp_path)
    before = paths.config.read_bytes()
    client = await _app(store)
    headers = {"X-Ma2pi-Request": "1"}
    try:
        valid = await client.post(
            "/api/config/validate",
            json={"logging": {"level": "DEBUG"}},
            headers=headers,
        )
        assert valid.status == 200
        assert await valid.json() == {"valid": True}
        assert paths.config.read_bytes() == before

        invalid = await client.post(
            "/api/config/validate",
            json={"ma2": {"port": 70000}},
            headers=headers,
        )
        assert invalid.status == 422
    finally:
        await client.close()


async def test_connection_test_returns_no_password(tmp_path):
    seen: dict[str, str | None] = {}

    async def tester(candidate, password):
        seen["password"] = password
        seen["host"] = candidate.ma2.host
        return ConnectionCheck(
            session=9,
            username=candidate.ma2.username,
            target="ws://test",
            reused=False,
        )

    _, store = _setup(tmp_path, tester=tester)
    client = await _app(store)
    try:
        response = await client.post(
            "/api/test-connection",
            json={
                "host": "10.0.0.9",
                "port": 80,
                "username": "svt",
                "password": "s3cret",
            },
            headers={"X-Ma2pi-Request": "1"},
        )
        assert response.status == 200
        text = await response.text()
        assert "s3cret" not in text
        body = json.loads(text)
        assert body["session"] == 9
        assert body["username"] == "svt"
        assert seen["password"] == "s3cret"
        assert seen["host"] == "10.0.0.9"
    finally:
        await client.close()


def test_redacted_config_contains_layouts_profiles_and_bank_layers(make_config):
    def mutate(data):
        data["led"]["enabled"] = False
        data["profiles"]["bank-test"] = {
            "controls": [{"id": "bt_fader", "kind": "fader"}],
            "banks": [{"number": 1, "notes": {"70": "bt_fader"}}],
        }
        data["devices"]["banktest"] = {
            "backend": "midi",
            "vendor_id": 0x04D8,
            "product_id": 0x1234,
            "profile": "bank-test",
        }
        data["layouts"] = {
            "surface": {
                "profile": "bank-test",
                "columns": 1,
                "rows": [{"cells": [{"label": "F", "control": "bt_fader"}]}],
            }
        }
        data["mapping"]["device_banks"] = {
            "banktest": {"bank_size": 5, "1": {"ma_page": 2}}
        }

    config = make_config(mutate)
    data = redacted_config(config)
    assert data["layouts"]["surface"]["columns"] == 1
    assert data["layouts"]["surface"]["profile"] == "bank-test"
    assert data["profiles"]["bank-test"]["banks"][0]["notes"] == {"70": "bt_fader"}
    assert data["mapping"]["device_banks"]["banktest"]["bank_size"] == 5
    assert data["mapping"]["device_banks"]["banktest"]["1"]["ma_page"] == 2
    assert "banks" not in data["mapping"]["device_banks"]["banktest"]
    assert "password_file" not in data["ma2"]
    assert "pin" not in data["web"]


async def test_redacted_config_roundtrips_cleanly_through_prepare_patch(tmp_path):
    from ma2pi.config_store import prepare_patch

    paths, store = _setup(tmp_path)
    payload = redacted_config(store.config)
    cleaned = store._clean_patch(payload, None)
    prepared = prepare_patch(
        paths,
        cleaned,
        validate=lambda raw: load_config(paths.config).__class__
        if False
        else store._validate(raw),
    )
    assert prepared.candidate.mapping.encoders == store.config.mapping.encoders
    assert prepared.candidate.mapping.device_banks == store.config.mapping.device_banks


async def test_put_config_strips_password_file_and_list_nones(tmp_path):
    paths, store = _setup(tmp_path)
    secret_probe = tmp_path / "probe.txt"
    secret_probe.write_text("do-not-read", encoding="utf-8")
    client = await _app(store)
    headers = {"X-Ma2pi-Request": "1"}
    try:
        response = await client.put(
            "/api/config",
            json={
                "ma2": {
                    "password_file": str(secret_probe),
                    "password_env": "EVIL_ENV",
                },
                "mapping": {
                    "encoders": [
                        {"id": 1, "slot": 1, "attribute": None},
                        {"id": 2, "slot": 2, "attribute": None},
                        {"id": 3, "slot": 3, "attribute": None},
                        {"id": 4, "slot": 4, "attribute": None},
                    ]
                },
            },
            headers=headers,
        )
        assert response.status == 200
        loaded = load_config(paths.config)
        assert loaded.ma2.password_file != str(secret_probe)
        assert loaded.ma2.password_env is None
    finally:
        await client.close()


async def test_store_roundtrips_led_feedback_fields_and_keeps_others(tmp_path):
    paths, store = _setup(tmp_path)

    updated = await store.apply(
        {
            "profiles": {
                "midicraft-enc": {
                    "led_feedback": {"enabled": False, "frame_interval_ms": 50}
                }
            }
        }
    )

    feedback = updated.profiles["midicraft-enc"].led_feedback
    assert feedback.enabled is False
    assert feedback.frame_interval_ms == 50
    # Keys that the patch does not mention survive the merge.
    assert feedback.protocol == "midicraft-v2"
    assert feedback.notes is not None and 65 in feedback.notes

    # An unrelated edit keeps the new fields in the file on disk.
    await store.apply({"logging": {"level": "DEBUG"}})
    reloaded = load_config(paths.config)
    again = reloaded.profiles["midicraft-enc"].led_feedback
    assert again.enabled is False
    assert again.frame_interval_ms == 50
