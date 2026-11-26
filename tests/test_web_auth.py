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


async def test_pin_session_expires_and_locks_out_after_five_failures(make_config):
    config = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "123456"})
    )
    now = [1000.0]
    client = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                pin_clock=lambda: now[0],
            )
        )
    )
    await client.start_server()
    try:
        # 5 wrong attempts -> 5th triggers 15 s lockout (429 + Retry-After)
        for attempt in range(4):
            res = await client.post(
                "/api/auth/login", json={"pin": "000000"}, headers=HEADERS
            )
            assert res.status == 401, attempt
        fifth = await client.post(
            "/api/auth/login", json={"pin": "000000"}, headers=HEADERS
        )
        assert fifth.status == 429
        assert fifth.headers["Retry-After"] == "15"
        assert (await fifth.json())["error"] == "pin_locked"

        # Even right PIN is blocked during lockout, and attempts during lockout
        # do NOT double the next lockout prematurely!
        during = await client.post(
            "/api/auth/login", json={"pin": "123456"}, headers=HEADERS
        )
        assert during.status == 429

        # After 15 s, another wrong PIN doubles lockout to 30 s
        now[0] += 15.1
        sixth = await client.post(
            "/api/auth/login", json={"pin": "000000"}, headers=HEADERS
        )
        assert sixth.status == 429
        assert sixth.headers["Retry-After"] == "30"

        # After 30 s, right PIN unlocks and resets counter
        now[0] += 30.1
        ok = await client.post(
            "/api/auth/login", json={"pin": "123456"}, headers=HEADERS
        )
        assert ok.status == 200
        assert (await client.get("/api/status")).status == 200

        # Server-side 12 h TTL expires even though client still holds cookie
        now[0] += 12 * 3600.0 + 1.0
        expired = await client.get("/api/status")
        assert expired.status == 401
    finally:
        await client.close()


async def test_put_config_with_unchanged_pin_enabled_keeps_other_sessions(
    tmp_path,
):
    import shutil
    from ma2pi.config import load_config
    from ma2pi.config_store import ConfigPaths
    from ma2pi.mapping import MappingEngine
    from ma2pi.runtime import ConfigStore
    from ma2pi.web import PIN_SESSIONS_KEY, redacted_config
    from .conftest import NullSink

    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    paths.state_dir.mkdir(parents=True)
    shutil.copy(Path(__file__).resolve().parents[1] / "config.toml", paths.config)
    initial = load_config(paths.config)
    store = ConfigStore(initial, MappingEngine(initial, NullSink()), paths)
    await store.apply({"web": {"pin_enabled": True, "pin": "424242"}})
    app = create_app(store.config, dist_dir=Path("/nonexistent"), config_store=store)
    other_token = app[PIN_SESSIONS_KEY].issue()

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        await client.post("/api/auth/login", json={"pin": "424242"}, headers=HEADERS)
        payload = redacted_config(store.config)
        # UI submits full web section including unchanged pin_enabled=True without changing PIN
        saved = await client.put("/api/config", json=payload, headers=HEADERS)
        assert saved.status == 200
        assert app[PIN_SESSIONS_KEY].valid(other_token) is True
    finally:
        await client.close()
