"""Tests for the embedded configuration UI server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from ma2pi.web import API_VERSION, create_app


async def _client(config, **kwargs) -> TestClient:
    client = TestClient(TestServer(create_app(config, **kwargs)))
    await client.start_server()
    return client


@pytest.fixture
async def client(config):
    client = await _client(config, dist_dir=Path("/nonexistent"))
    yield client
    await client.close()


async def test_health_endpoint(client):
    response = await client.get("/api/health")
    assert response.status == 200
    assert await response.json() == {"status": "ok"}


async def test_version_endpoint(client):
    response = await client.get("/api/version")
    assert response.status == 200
    body = await response.json()
    assert body["api"] == API_VERSION
    assert body["package"]
    assert body["ui"] == "missing"


async def test_status_without_provider(client):
    response = await client.get("/api/status")
    assert response.status == 200
    assert (await response.json())["runtime"] == "unavailable"


async def test_status_with_provider(config):
    client = await _client(
        config,
        dist_dir=Path("/nonexistent"),
        status_provider=lambda: {"connected": True, "session": 7},
    )
    try:
        response = await client.get("/api/status")
        assert await response.json() == {"connected": True, "session": 7}
    finally:
        await client.close()


async def test_write_requires_json(client):
    response = await client.post("/api/config", data="host=evil")
    assert response.status == 415
    assert (await response.json())["error"] == "unsupported_media_type"


async def test_write_requires_request_header(client):
    response = await client.post(
        "/api/config", json={"ma2": {"host": "x"}}, headers={"Content-Type": "application/json"}
    )
    assert response.status == 403
    assert (await response.json())["error"] == "missing_request_header"


async def test_write_passes_guard_when_header_present(client):
    # No handler is registered yet; the guard must let the request through so
    # the router answers instead of 403.
    response = await client.post(
        "/api/config",
        json={"ma2": {"host": "x"}},
        headers={"X-Ma2pi-Request": "1"},
    )
    assert response.status in (404, 405)


async def test_read_has_no_cors_header(client):
    response = await client.get("/api/health")
    assert "Access-Control-Allow-Origin" not in response.headers


async def test_spa_reports_missing_build(client):
    response = await client.get("/")
    assert response.status == 503
    assert (await response.json())["error"] == "ui_not_built"


async def test_spa_serves_index_and_assets(config, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>ui</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    client = await _client(config, dist_dir=dist)
    try:
        root = await client.get("/")
        assert root.status == 200
        assert "ui" in await root.text()

        asset = await client.get("/assets/app.js")
        assert asset.status == 200
        assert "console.log" in await asset.text()

        # Client-side route falls back to index.html.
        deep = await client.get("/mapping/encoders")
        assert deep.status == 200
        assert "ui" in await deep.text()

        version = await client.get("/api/version")
        assert (await version.json())["ui"] != "missing"
    finally:
        await client.close()


async def test_spa_does_not_escape_dist(config, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>ui</html>", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    client = await _client(config, dist_dir=dist)
    try:
        response = await client.get("/../secret.txt")
        assert "top secret" not in await response.text()
    finally:
        await client.close()


def test_web_config_parsed(make_config):
    cfg = make_config(lambda data: data.update({"web": {"bind": "127.0.0.1", "port": 9000}}))
    assert cfg.web.bind == "127.0.0.1"
    assert cfg.web.port == 9000
    assert cfg.web.pin_enabled is False


def test_web_config_defaults(make_config):
    cfg = make_config(lambda data: data.pop("web"))
    assert cfg.web.bind == "0.0.0.0"
    assert cfg.web.port == 8080


def test_web_config_rejects_pin(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"pin_enabled": True}))


def test_web_config_rejects_bad_port(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"port": 70000}))


def test_web_config_rejects_unknown_key(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"tls": True}))
