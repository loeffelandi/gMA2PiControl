"""API integration test against the mock onPC server."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import tomlkit
from aiohttp.test_utils import TestClient, TestServer

from ma2pi.__main__ import _status_snapshot
from ma2pi.config import AppConfig, load_config
from ma2pi.config_store import ConfigPaths
from ma2pi.learn import LearnManager
from ma2pi.ma2_client import Ma2Client
from ma2pi.mapping import MappingEngine
from ma2pi.runtime import ConfigStore
from ma2pi.web import create_app
from tests.mock_ma2 import MockMa2Server


async def wait_until(predicate, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


from .conftest import NullSink


def _write_config(paths: ConfigPaths, raw_config: dict, port: int) -> AppConfig:
    data = copy.deepcopy(raw_config)
    data["ma2"].update(
        {
            "host": "127.0.0.1",
            "port": port,
            "password_env": "MA2PI_TEST_PASSWORD",
            "hardkey_transport": "native",
            "keepalive_interval": 0.05,
        }
    )
    data["ma2"].pop("password_file", None)
    data["reconnect"].update(
        {
            "initial_delay": 0.01,
            "max_delay": 0.05,
            "jitter": 0.0,
            "login_failure_delay": 0.02,
        }
    )
    data["web"]["pin_enabled"] = False
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.config.write_text(tomlkit.dumps(data), encoding="utf-8")
    return load_config(paths.config)


async def test_api_read_change_apply_and_status(raw_config, tmp_path):
    server = await MockMa2Server(session_id=11).start()
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    config = _write_config(paths, raw_config, server.port)

    engine = MappingEngine(config, NullSink())
    client = Ma2Client(config)
    store = ConfigStore(config, engine, paths, client=client)
    learn = LearnManager(config)
    web = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                config_store=store,
                learn_manager=learn,
                status_provider=lambda: _status_snapshot(client, store),
            )
        )
    )
    await web.start_server()
    headers = {"X-Ma2pi-Request": "1"}
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        session = client.session

        read = await web.get("/api/config")
        assert read.status == 200
        body = await read.json()
        assert body["ma2"]["host"] == "127.0.0.1"
        assert body["ma2"]["port"] == server.port
        assert "password_file" not in body["ma2"]

        changed = await web.put(
            "/api/config",
            json={"mapping": {"keys": {"fix": {"hardkey": "Store"}}}},
            headers=headers,
        )
        assert changed.status == 200
        changed_body = await changed.json()
        assert changed_body["generation"] == 1
        assert changed_body["config"]["mapping"]["keys"]["fix"]["hardkey"] == "Store"

        # A mapping-only change must not disturb the running session.
        assert client.authenticated
        assert client.session == session
        assert server.connections == 1
        assert len(server.logins) == 1

        status = await web.get("/api/status")
        status_body = await status.json()
        assert status_body["connected"] is True
        assert status_body["generation"] == 1
        assert status_body["busy"] is False
    finally:
        await web.close()
        await client.shutdown()
        await server.stop()
