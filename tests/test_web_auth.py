"""Tests for the simple PIN gate on the UI/API."""

from __future__ import annotations

from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from ma2pi.web import create_app

HEADERS = {"X-Ma2pi-Request": "1"}


async def _client(config) -> TestClient:
    client = TestClient(TestServer(create_app(config, dist_dir=Path("/nonexistent"))))
    await client.start_server()
    return client


async def test_api_requires_pin(make_config):
    config = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "123456"})
    )
    client = await _client(config)
    try:
        status = await client.get("/api/status")
        assert status.status == 401
        assert (await status.json())["error"] == "pin_required"

        auth = await client.get("/api/auth/status")
        assert await auth.json() == {
            "pin_enabled": True,
            "pin_set": True,
            "authenticated": False,
        }
    finally:
        await client.close()


async def test_wrong_pin_is_rejected(make_config):
    config = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "123456"})
    )
    client = await _client(config)
    try:
        response = await client.post(
            "/api/auth/login", json={"pin": "000000"}, headers=HEADERS
        )
        assert response.status == 401
        assert (await response.json())["error"] == "pin_invalid"
    finally:
        await client.close()


async def test_correct_pin_unlocks_and_logout_locks(make_config):
    config = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "123456"})
    )
    client = await _client(config)
    try:
        response = await client.post(
            "/api/auth/login", json={"pin": "123456"}, headers=HEADERS
        )
        assert response.status == 200
        assert "ma2pi_pin" in response.cookies
        assert response.cookies["ma2pi_pin"]["httponly"] is True

        auth = await client.get("/api/auth/status")
        assert (await auth.json())["authenticated"] is True
        assert (await client.get("/api/status")).status == 200

        logout = await client.post("/api/auth/logout", json={}, headers=HEADERS)
        assert logout.status == 200
        assert (await client.get("/api/status")).status == 401
    finally:
        await client.close()


async def test_pin_disabled_keeps_api_open(make_config):
    config = make_config(lambda data: data["web"].update({"pin_enabled": False}))
    client = await _client(config)
    try:
        auth = await client.get("/api/auth/status")
        assert await auth.json() == {
            "pin_enabled": False,
            "pin_set": False,
            "authenticated": True,
        }
        assert (await client.get("/api/status")).status == 200
    finally:
        await client.close()


def test_redacted_config_hides_pin(make_config):
    from ma2pi.web.serialize import redacted_config

    config = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "123456"})
    )
    payload = redacted_config(config)
    assert "pin" not in payload["web"]
    assert payload["web"]["pin_set"] is True
