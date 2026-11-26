"""Tests for the embedded configuration UI server."""

from __future__ import annotations

import asyncio
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


async def test_events_websocket_receives_initial_and_published(client):
    from ma2pi.web import BUS_KEY

    ws = await client.ws_connect("/api/events")
    initial = await ws.receive_json()
    assert initial["type"] == "status"

    client.app[BUS_KEY].publish({"type": "learn", "data": {"control": "fine"}})
    event = await ws.receive_json()
    assert event == {"type": "learn", "data": {"control": "fine"}}
    await ws.close()


async def test_events_two_clients_and_reconnect(client):
    from ma2pi.web import BUS_KEY

    bus = client.app[BUS_KEY]
    first = await client.ws_connect("/api/events")
    second = await client.ws_connect("/api/events")
    await first.receive_json()
    await second.receive_json()
    assert bus.subscriber_count == 2

    bus.publish({"type": "status", "data": {"connected": False}})
    assert (await first.receive_json())["data"] == {"connected": False}
    assert (await second.receive_json())["data"] == {"connected": False}

    await first.close()
    for _ in range(50):
        if bus.subscriber_count == 1:
            break
        await asyncio.sleep(0.01)
    assert bus.subscriber_count == 1

    bus.publish({"type": "status", "data": {"connected": True}})
    assert (await second.receive_json())["data"] == {"connected": True}
    await second.close()

    # Reconnect after a disconnect works.
    third = await client.ws_connect("/api/events")
    assert (await third.receive_json())["type"] == "status"
    await third.close()


async def test_events_slow_client_is_dropped():
    from ma2pi.web.events import EventBus

    bus = EventBus(queue_size=1)
    queue = bus.subscribe()
    bus.publish({"n": 1})
    assert bus.subscriber_count == 1
    bus.publish({"n": 2})
    assert bus.subscriber_count == 0
    assert queue.get_nowait() == {"n": 1}


def test_web_config_parsed(make_config):
    cfg = make_config(lambda data: data.update({"web": {"bind": "127.0.0.1", "port": 9000}}))
    assert cfg.web.bind == "127.0.0.1"
    assert cfg.web.port == 9000
    assert cfg.web.pin_enabled is False
    assert cfg.web.pin == ""


def test_web_config_defaults(make_config):
    cfg = make_config(lambda data: data.pop("web"))
    assert cfg.web.bind == "0.0.0.0"
    assert cfg.web.port == 8080
    assert cfg.web.pin_enabled is False
    assert cfg.web.pin == ""


def test_web_config_accepts_changed_pin(make_config):
    cfg = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "987654"})
    )
    assert cfg.web.pin_enabled is True
    assert cfg.web.pin == "987654"


@pytest.mark.parametrize("pin", ["123", "abcd", "1234567890123"])
def test_web_config_rejects_bad_pin(make_config, pin):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"pin": pin}))


def test_web_config_requires_pin_when_enabled(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"pin_enabled": True, "pin": ""}))


def test_web_config_rejects_bad_port(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"port": 70000}))


def test_web_config_rejects_unknown_key(make_config):
    from ma2pi.config import ConfigError

    with pytest.raises(ConfigError):
        make_config(lambda data: data["web"].update({"tls": True}))
