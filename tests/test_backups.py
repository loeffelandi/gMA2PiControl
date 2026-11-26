"""Tests for configuration backups and their HTTP API."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from ma2pi.config import ConfigError, load_config
from ma2pi.config_store import BackupError, ConfigPaths, LAST_GOOD
from ma2pi.mapping import MappingEngine
from ma2pi.runtime import ConfigStore
from ma2pi.web import create_app

ROOT = Path(__file__).resolve().parents[1]


from .conftest import NullSink


def _setup(tmp_path: Path) -> tuple[ConfigPaths, ConfigStore]:
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    paths.state_dir.mkdir(parents=True)
    shutil.copy(ROOT / "config.toml", paths.config)
    _disable_pin(paths.config)
    config = load_config(paths.config)
    engine = MappingEngine(config, NullSink())
    return paths, ConfigStore(config, engine, paths)


def _disable_pin(path: Path) -> None:
    import tomlkit

    document = tomlkit.parse(path.read_text(encoding="utf-8"))
    document["web"]["pin_enabled"] = False
    path.write_text(tomlkit.dumps(document), encoding="utf-8")


async def test_create_list_and_restore_backup(tmp_path):
    paths, store = _setup(tmp_path)

    entry = store.create_backup()
    assert entry["id"].startswith("config-")
    assert entry["last_good"] is False
    assert any(item["id"] == entry["id"] for item in store.backups())

    await store.apply({"logging": {"level": "DEBUG"}})
    assert load_config(paths.config).logging.level == "DEBUG"

    await store.restore(entry["id"])

    assert load_config(paths.config).logging.level == "INFO"
    assert store.generation == 2
    assert (paths.backups / LAST_GOOD).is_file()


async def test_invalid_backup_keeps_active_config(tmp_path):
    paths, store = _setup(tmp_path)
    before = paths.config.read_bytes()
    broken = paths.backups / "config-broken.toml"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("schema_version = 1\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        await store.restore(broken.name)

    assert paths.config.read_bytes() == before
    assert store.generation == 0


async def test_restore_rejects_path_traversal(tmp_path):
    _, store = _setup(tmp_path)

    with pytest.raises(BackupError):
        await store.restore("../config.toml")
    with pytest.raises(BackupError):
        await store.restore("missing.toml")


async def test_backup_api(tmp_path):
    _, store = _setup(tmp_path)
    client = TestClient(TestServer(create_app(store.config, dist_dir=Path("/nonexistent"), config_store=store)))
    await client.start_server()
    headers = {"X-Ma2pi-Request": "1"}
    try:
        created = await client.post("/api/backups", json={}, headers=headers)
        assert created.status == 201
        entry = await created.json()
        assert entry["id"].startswith("config-")

        listed = await client.get("/api/backups")
        assert listed.status == 200
        assert [item["id"] for item in (await listed.json())["backups"]] == [entry["id"]]

        restored = await client.post(
            f"/api/backups/{entry['id']}/restore", json={}, headers=headers
        )
        assert restored.status == 200
        body = await restored.json()
        assert body["ok"] is True
        assert body["generation"] == 1
        assert "password" not in body["ma2"]
        assert "password_file" not in body["ma2"]
    finally:
        await client.close()


async def test_backup_restore_unknown_id_is_422(tmp_path):
    _, store = _setup(tmp_path)
    client = TestClient(TestServer(create_app(store.config, dist_dir=Path("/nonexistent"), config_store=store)))
    await client.start_server()
    try:
        response = await client.post(
            "/api/backups/missing.toml/restore",
            json={},
            headers={"X-Ma2pi-Request": "1"},
        )
        assert response.status == 422
        assert (await response.json())["error"] == "invalid_backup"
    finally:
        await client.close()


async def test_backup_api_without_store_is_503(config):
    client = TestClient(TestServer(create_app(config, dist_dir=Path("/nonexistent"))))
    await client.start_server()
    try:
        response = await client.get("/api/backups")
        assert response.status == 503
        assert (await response.json())["error"] == "config_store_unavailable"
    finally:
        await client.close()
