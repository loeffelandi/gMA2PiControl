from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from ma2pi import midi_remote_service
from ma2pi.ma2_telnet import TelnetError
from ma2pi.midi_remote_service import MidiRemoteService
from ma2pi.midi_remote_sync import SyncResult
from ma2pi.web import create_app


class FakeSession:
    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.connected = True
        self.state = "connected"
        self.detail = f"{host}:{port}"
        self.latency_ms = 1.5
        self.sent: list[bytes] = []
        self.started = self.closed = False

    def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    def send(self, midi: bytes) -> bool:
        self.sent.append(midi)
        return True


class FakeSync:
    """Confirms every desired target unless told to fail; can be held open."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail: str | None = None
        self.gate: asyncio.Event | None = None
        self.result: SyncResult | None = None

    async def __call__(self, config, desired):
        self.calls.append(dict(desired))
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise TelnetError(self.fail)
        if self.result is not None:
            return self.result
        return SyncResult(config.midi_remote.sync, frozenset(desired), len(desired), created=len(desired))


def _config(make_config, playbacks, **midi):
    def mutate(data):
        data["mapping"]["playbacks"] = playbacks
        data["midi_remote"] = {"enabled": True, **midi}

    return make_config(mutate)


A = {"mc_click_1": {"page": 1, "executor": 5, "kind": "button"}}
AB = {**A, "mc_click_2": {"page": 1, "executor": 6, "kind": "button"}}


async def _settle():
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(midi_remote_service, "SYNC_RETRY_MIN", 0.01)
    monkeypatch.setattr(midi_remote_service, "SYNC_RETRY_MAX", 0.02)


async def test_connect_syncs_then_sends(make_config):
    sync = FakeSync()
    sessions: list[FakeSession] = []
    service = MidiRemoteService(
        _config(make_config, A),
        sync_runner=sync,
        session_factory=lambda host, port: sessions.append(FakeSession(host, port)) or sessions[-1],
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    assert not service.press((1, 5, 1), True)  # not synced yet
    await _settle()
    assert len(sync.calls) == 1
    assert service.press((1, 5, 1), True)
    assert sessions[0].sent == [bytes.fromhex("9F 00 7F")]
    assert sessions[0].started
    await service.close()
    assert sessions[0].closed


async def test_config_swap_keeps_unchanged_targets_and_waits_for_new_ones(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()
    sync.gate = asyncio.Event()
    service.set_config(_config(make_config, AB))
    await _settle()
    # (1, 5, 1) keeps note 0, so it stays usable during the sync; (1, 6, 1) waits.
    assert service.is_synced((1, 5, 1))
    assert not service.is_synced((1, 6, 1))
    assert service.status()["sync"]["running"] is True
    sync.gate.set()
    await _settle()
    assert service.is_synced((1, 6, 1))
    assert sync.calls[-1].keys() == {(1, 5, 1), (1, 6, 1)}
    await service.close()


async def test_moved_address_is_unsynced_until_the_sync(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, {"mc_click_1": {"page": 1, "executor": 9, "kind": "button"}}),
        sync_runner=sync,
        session_factory=FakeSession,
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()
    sync.gate = asyncio.Event()
    # Exec 5 sorts before 9, so (1, 9, 1) moves from note 0 to note 1.
    service.set_config(
        _config(make_config, {**A, "mc_click_2": {"page": 1, "executor": 9, "kind": "button"}})
    )
    assert not service.is_synced((1, 9, 1))
    sync.gate.set()
    await _settle()
    assert service.is_synced((1, 9, 1))
    await service.close()


async def test_start_alone_does_not_sync(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    await _settle()
    assert sync.calls == []
    assert not service.press((1, 5, 1), True)
    await service.close()


async def test_successful_sync_is_not_repeated(make_config, fast):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await asyncio.sleep(0.1)
    assert len(sync.calls) == 1
    await service.close()


async def test_incomplete_sync_is_not_retried_on_its_own(make_config, fast):
    sync = FakeSync()
    sync.result = SyncResult("auto", frozenset(), 1, failed=1)
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await asyncio.sleep(0.05)
    status = service.status()["sync"]
    assert (status["synced"], status["failed"]) == (0, 1)
    assert status["error"] is None
    assert len(sync.calls) == 1
    sync.result = None
    service.request_sync()  # next connect, or the status button
    await asyncio.sleep(0.05)
    assert len(sync.calls) == 2
    assert service.status()["sync"]["failed"] == 0
    assert service.is_synced((1, 5, 1))
    await service.close()


async def test_check_mode_reports_deviations_once(make_config, fast):
    sync = FakeSync()
    sync.result = SyncResult("check", frozenset(), 1, failed=1, deviations=1)
    service = MidiRemoteService(
        _config(make_config, A, sync="check"),
        sync_runner=sync,
        session_factory=FakeSession,
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await asyncio.sleep(0.05)
    assert len(sync.calls) == 1
    await service.close()


async def test_retrigger_keeps_already_synced_targets(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()
    assert service.is_synced((1, 5, 1))
    sync.gate = asyncio.Event()
    service.request_sync()
    await _settle()
    assert service.is_synced((1, 5, 1))
    assert service.press((1, 5, 1), True)
    sync.gate.set()
    await _settle()
    await service.close()


async def test_failed_sync_reports_and_retries(make_config, fast):
    sync = FakeSync()
    sync.fail = "Telnet 10.0.0.1:30000 nicht erreichbar: refused"
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await asyncio.sleep(0.05)
    status = service.status()["sync"]
    assert status["error"] == sync.fail
    assert (status["targets"], status["synced"], status["failed"]) == (1, 0, 1)
    assert len(sync.calls) >= 2
    sync.fail = None
    await asyncio.sleep(0.05)
    assert service.status()["sync"]["error"] is None
    assert service.is_synced((1, 5, 1))
    await service.close()


async def test_request_sync_runs_again(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()
    service.request_sync()
    await _settle()
    assert len(sync.calls) == 2
    await service.close()


async def test_sync_off_sends_without_telnet(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A, sync="off"), sync_runner=sync, session_factory=FakeSession
    )
    service.start()
    service.request_sync()
    await _settle()
    assert sync.calls == []
    assert service.press((1, 5, 1), True)
    await service.close()


async def test_dry_run_neither_opens_rtp_nor_telnet(make_config):
    sync = FakeSync()
    service = MidiRemoteService(
        _config(make_config, A),
        dry_run=True,
        sync_runner=sync,
        session_factory=lambda *_: pytest.fail("no session in dry-run"),
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()
    assert sync.calls == []
    assert service.press((1, 5, 1), True)
    assert service.status()["session"]["state"] == "dry-run"
    await service.close()


async def test_disabling_closes_the_session(make_config):
    sessions: list[FakeSession] = []
    service = MidiRemoteService(
        _config(make_config, A),
        sync_runner=FakeSync(),
        session_factory=lambda host, port: sessions.append(FakeSession(host, port)) or sessions[-1],
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()

    def off(data):
        data["mapping"]["playbacks"] = A

    service.set_config(make_config(off))
    await _settle()
    assert sessions[0].closed
    assert service.status() == {"enabled": False}
    assert not service.press((1, 5, 1), True)
    await service.close()


async def test_status_reports_session_and_counts(make_config):
    service = MidiRemoteService(
        _config(make_config, AB, host="10.0.0.9"),
        sync_runner=FakeSync(),
        session_factory=FakeSession,
    )
    service.start()
    service.request_sync()  # the Web Remote connect
    await _settle()
    status = service.status()
    assert status["session"] == {
        "state": "connected",
        "detail": "10.0.0.9:5004",
        "host": "10.0.0.9",
        "port": 5004,
        "latency_ms": 1.5,
    }
    assert {key: status["sync"][key] for key in ("mode", "targets", "synced", "created")} == {
        "mode": "auto",
        "targets": 2,
        "synced": 2,
        "created": 2,
    }
    await service.close()


HEADERS = {"X-Ma2pi-Request": "1"}


class StubRemote:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.syncs = 0

    def status(self) -> dict:
        return self.payload

    def request_sync(self) -> None:
        self.syncs += 1
        self.payload = {
            **self.payload,
            "sync": {**self.payload["sync"], "running": True},
        }


def _enabled_status(**sync) -> dict:
    return {
        "enabled": True,
        "session": {
            "state": "connected",
            "detail": "",
            "host": "10.0.0.1",
            "port": 5004,
            "latency_ms": 1.0,
        },
        "sync": {
            "mode": "auto",
            "running": False,
            "targets": 2,
            "synced": 2,
            "created": 0,
            "changed": 0,
            "removed": 0,
            "failed": 0,
            "deviations": 0,
            "error": None,
            "at": 1.0,
            **sync,
        },
    }


async def test_post_midi_remote_sync_retriggers(config):
    remote = StubRemote(_enabled_status())
    client = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                midi_remote_service=remote,
            )
        )
    )
    await client.start_server()
    try:
        response = await client.post("/api/midi-remote/sync", json={}, headers=HEADERS)
        assert response.status == 202
        body = await response.json()
        assert body["sync"]["running"] is True
        assert remote.syncs == 1
    finally:
        await client.close()


async def test_post_midi_remote_sync_disabled(config):
    remote = SimpleNamespace(
        status=lambda: {"enabled": False},
        request_sync=lambda: pytest.fail("must not sync when disabled"),
    )
    client = TestClient(
        TestServer(
            create_app(
                config, dist_dir=Path("/nonexistent"), midi_remote_service=remote
            )
        )
    )
    await client.start_server()
    try:
        response = await client.post("/api/midi-remote/sync", json={}, headers=HEADERS)
        assert response.status == 409
        assert (await response.json())["error"] == "midi_remote_disabled"
    finally:
        await client.close()


async def test_post_midi_remote_sync_off(config):
    remote = StubRemote(_enabled_status(mode="off"))
    client = TestClient(
        TestServer(
            create_app(
                config, dist_dir=Path("/nonexistent"), midi_remote_service=remote
            )
        )
    )
    await client.start_server()
    try:
        response = await client.post("/api/midi-remote/sync", json={}, headers=HEADERS)
        assert response.status == 409
        assert (await response.json())["error"] == "midi_remote_sync_off"
        assert remote.syncs == 0
    finally:
        await client.close()


async def test_post_midi_remote_sync_without_service(config):
    client = TestClient(TestServer(create_app(config, dist_dir=Path("/nonexistent"))))
    await client.start_server()
    try:
        response = await client.post("/api/midi-remote/sync", json={}, headers=HEADERS)
        assert response.status == 503
        assert (await response.json())["error"] == "midi_remote_unavailable"
    finally:
        await client.close()
