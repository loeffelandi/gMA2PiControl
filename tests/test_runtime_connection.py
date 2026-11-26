"""Connection test and reconnect behaviour of the configuration runtime."""

from __future__ import annotations

import asyncio
import copy

import pytest
import tomlkit

from ma2pi.config import AppConfig, load_config, parse_config
from ma2pi.config_store import ConfigPaths
from ma2pi.ma2_client import LoginError, Ma2Client, check_connection
from ma2pi.mapping import MappingEngine
from ma2pi.runtime import ConfigStore
from tests.mock_ma2 import MockMa2Server


async def wait_until(predicate, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


def _client_data(data: dict, port: int) -> None:
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
    data["rate_limit"].update({"messages_per_second": 40, "burst": 50})


def _parse(raw_config: dict, port: int) -> AppConfig:
    data = copy.deepcopy(raw_config)
    _client_data(data, port)
    return parse_config(data, source_path="<test>")


def _write_config(paths: ConfigPaths, raw_config: dict, port: int) -> AppConfig:
    data = copy.deepcopy(raw_config)
    _client_data(data, port)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.config.write_text(tomlkit.dumps(data), encoding="utf-8")
    return load_config(paths.config)


class _NullSink:
    def press(self, keyname: str, hold: bool = False) -> None:
        pass

    def release(self, keyname: str) -> None:
        pass

    def command(self, text: str) -> None:
        pass

    def encoder_slot(self, slot: int, delta: float, screen: bool = False) -> None:
        pass

    def encoder_attribute(self, name: str, value: float) -> None:
        pass

    def toggle_screen_mode(self) -> None:
        pass

    def toggle_fine(self, slot: int) -> None:
        pass

    def screen_shortcut(self, screen: int) -> None:
        pass


async def test_check_connection_success(raw_config):
    server = await MockMa2Server(session_id=31).start()
    cfg = _parse(raw_config, server.port)
    try:
        check = await check_connection(cfg)

        assert check.session == 31
        assert check.reused is False
        assert check.username == "ma2pi"
        assert [login["username"] for login in server.logins] == ["ma2pi"]
    finally:
        await server.stop()


async def test_check_connection_wrong_password(raw_config):
    server = await MockMa2Server().start()
    cfg = _parse(raw_config, server.port)
    try:
        with pytest.raises(LoginError):
            await check_connection(cfg, password="wrong")
    finally:
        await server.stop()


async def test_check_connection_unreachable_host(raw_config):
    probe = await MockMa2Server().start()
    dead_port = probe.port
    await probe.stop()
    cfg = _parse(raw_config, dead_port)

    with pytest.raises(OSError):
        await check_connection(cfg)


async def test_check_connection_reuses_active_session(raw_config):
    server = await MockMa2Server(session_id=31).start()
    cfg = _parse(raw_config, server.port)
    client = Ma2Client(cfg)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        logins_before = len(server.logins)

        check = await check_connection(cfg, active=client)

        assert check.reused is True
        assert check.session == client.session
        assert len(server.logins) == logins_before
        assert server.connections == 1
        assert client.authenticated
    finally:
        await client.shutdown()
        await server.stop()


async def test_mapping_only_apply_keeps_session(raw_config, tmp_path):
    server = await MockMa2Server(session_id=11).start()
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    cfg = _write_config(paths, raw_config, server.port)

    engine = MappingEngine(cfg, _NullSink())
    client = Ma2Client(cfg)
    store = ConfigStore(cfg, engine, paths, client=client)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        session = client.session

        await store.apply({"mapping": {"keys": {"fix": {"hardkey": "Store"}}}})

        assert store.generation == 1
        assert client.authenticated
        assert client.session == session
        assert server.connections == 1
        assert len(server.logins) == 1
        assert engine.config.mapping.keys["fix"].hardkey == "Store"
    finally:
        await client.shutdown()
        await server.stop()


async def test_changed_credentials_reconnect_to_new_target(raw_config, tmp_path):
    first = await MockMa2Server(session_id=11).start()
    second = await MockMa2Server(session_id=22).start()
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    cfg = _write_config(paths, raw_config, first.port)

    engine = MappingEngine(cfg, _NullSink())
    client = Ma2Client(cfg)
    store = ConfigStore(cfg, engine, paths, client=client)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated and client.session == 11)

        await store.apply({"ma2": {"port": second.port}})

        assert store.generation == 1
        assert store.config.ma2.port == second.port
        await wait_until(
            lambda: client.authenticated and client.session == 22, timeout=8.0
        )
        # One short-lived test session plus the reconnected daemon session.
        assert len(second.logins) >= 2
        assert first.connections == 1
    finally:
        await client.shutdown()
        await first.stop()
        await second.stop()


async def test_failed_credential_test_keeps_config_and_session(raw_config, tmp_path):
    server = await MockMa2Server(session_id=11).start()
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    cfg = _write_config(paths, raw_config, server.port)
    before = paths.config.read_bytes()

    wrong = tmp_path / "wrong.password"
    wrong.write_text("wrong", encoding="utf-8")

    engine = MappingEngine(cfg, _NullSink())
    client = Ma2Client(cfg)
    store = ConfigStore(cfg, engine, paths, client=client)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        session = client.session

        with pytest.raises(LoginError):
            await store.apply(
                {"ma2": {"password_file": str(wrong), "password_env": None}}
            )

        assert store.generation == 0
        assert paths.config.read_bytes() == before
        assert client.authenticated
        assert client.session == session
        # One active session plus the short-lived test session; the active
        # connection must not have been replaced.
        assert server.connections == 2
    finally:
        await client.shutdown()
        await server.stop()


async def test_unreachable_target_keeps_config_and_session(raw_config, tmp_path):
    server = await MockMa2Server(session_id=11).start()
    paths = ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")
    cfg = _write_config(paths, raw_config, server.port)
    before = paths.config.read_bytes()

    probe = await MockMa2Server().start()
    dead_port = probe.port
    await probe.stop()

    engine = MappingEngine(cfg, _NullSink())
    client = Ma2Client(cfg)
    store = ConfigStore(cfg, engine, paths, client=client)
    try:
        await client.start()
        await wait_until(lambda: client.authenticated)
        session = client.session

        with pytest.raises(OSError):
            await store.apply({"ma2": {"port": dead_port}})

        assert store.generation == 0
        assert paths.config.read_bytes() == before
        assert client.authenticated
        assert client.session == session
    finally:
        await client.shutdown()
        await server.stop()
