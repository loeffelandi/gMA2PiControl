"""HTTP API tests for the network configuration endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from ma2pi.network import (
    Candidate,
    CurrentIPv4,
    InterfaceInfo,
    NetworkError,
    NetworkService,
    PendingStore,
    ProfileInfo,
    RawIPv4,
)
from ma2pi.web import BUS_KEY, create_app

HEADERS = {"X-Ma2pi-Request": "1"}


class FakeBackend:
    def __init__(self) -> None:
        self.interface = InterfaceInfo("eth0", "ethernet", "connected", "Wired connection 1")
        self.profile: ProfileInfo | None = ProfileInfo("uuid-1", "Wired connection 1", "auto")
        self.current = CurrentIPv4()
        self.addresses: dict[str, str] = {}
        self.persisted: list[Candidate] = []
        self.restored: list[RawIPv4] = []
        self.fail_restore = False

    async def available(self) -> bool:
        return True

    async def discover(self, interface: str | None = None):
        return self.interface, self.profile, self.current

    async def all_addresses(self) -> dict[str, str]:
        return dict(self.addresses)

    async def create_profile(self, interface: str) -> ProfileInfo:
        self.profile = ProfileInfo("uuid-created", f"ma2pi-{interface}", "auto", created=True)
        return self.profile

    async def stage(self, candidate: Candidate, profile: ProfileInfo) -> None:
        self.current = CurrentIPv4(
            address=candidate.address if candidate.mode == "static" else "192.168.10.77",
            subnet_mask=candidate.subnet_mask if candidate.mode == "static" else "255.255.255.0",
            gateway=candidate.gateway if candidate.mode == "static" else "192.168.10.1",
            dns=candidate.dns if candidate.mode == "static" else ("192.168.10.1",),
        )

    async def wait_until(self, candidate: Candidate, interface: str, timeout: float) -> str:
        if candidate.mode == "static":
            assert candidate.address is not None
            return candidate.address
        return "192.168.10.77"

    async def persist(self, candidate: Candidate, profile: ProfileInfo) -> None:
        self.persisted.append(candidate)

    async def restore(
        self, raw: RawIPv4, profile: ProfileInfo, *, persist: bool = False
    ) -> None:
        if self.fail_restore:
            raise NetworkError("Rollback-Profil nicht verfügbar")
        self.restored.append(raw)


def _service(tmp_path: Path, backend: FakeBackend) -> NetworkService:
    return NetworkService(
        backend,  # type: ignore[arg-type]
        PendingStore(tmp_path / "network-pending.json"),
        port=8080,
        activation_delay=0,
    )


async def _client(config, service: NetworkService) -> TestClient:
    client = TestClient(
        TestServer(
            create_app(
                config,
                dist_dir=Path("/nonexistent"),
                network_service=service,
            )
        )
    )
    await client.start_server()
    return client


async def _wait_pending(service: NetworkService, timeout: float = 1.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if service.pending is not None and service.pending.phase == "awaiting_confirmation":
            return
        await asyncio.sleep(0.01)
    raise AssertionError("pending change not ready")


async def test_network_status_and_validate(config, tmp_path):
    backend = FakeBackend()
    backend.current = CurrentIPv4(
        address="192.168.10.50",
        subnet_mask="255.255.255.0",
        gateway="192.168.10.1",
        dns=("192.168.10.1",),
    )
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        status = await client.get("/api/network")
        assert status.status == 200
        body = await status.json()
        assert body["available"] is True
        assert body["interface"]["name"] == "eth0"
        assert body["current"]["address"] == "192.168.10.50"
        assert body["pending"] is None

        validated = await client.post(
            "/api/network/validate",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
                "gateway": "192.168.10.1",
            },
            headers=HEADERS,
        )
        assert validated.status == 200
        assert (await validated.json())["valid"] is True
    finally:
        await client.close()


async def test_apply_returns_202_and_confirm(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        response = await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
                "gateway": "192.168.10.1",
            },
            headers=HEADERS,
        )
        assert response.status == 202
        body = await response.json()
        assert body["pending"]["phase"] == "activating"
        assert body["target_url"] == "http://192.168.10.60:8080/"

        await _wait_pending(service)
        confirmed = await client.post("/api/network/confirm", json={}, headers=HEADERS)
        assert confirmed.status == 200
        assert (await confirmed.json())["pending"] is None
        assert backend.persisted
    finally:
        await client.close()


async def test_apply_conflicts_and_no_pending(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    payload = {
        "mode": "static",
        "address": "192.168.10.60",
        "subnet_mask": "255.255.255.0",
    }
    try:
        no_pending = await client.post("/api/network/confirm", json={}, headers=HEADERS)
        assert no_pending.status == 409
        assert (await no_pending.json())["error"] == "no_pending"

        first = await client.put("/api/network", json=payload, headers=HEADERS)
        assert first.status == 202
        second = await client.put("/api/network", json=payload, headers=HEADERS)
        assert second.status == 409
        assert (await second.json())["error"] == "pending_exists"

        invalid = await client.post(
            "/api/network/validate",
            json={"mode": "static", "address": "192.168.10.60", "subnet_mask": "255.255.0.255"},
            headers=HEADERS,
        )
        assert invalid.status == 409
        assert (await invalid.json())["error"] == "pending_exists"
    finally:
        await client.close()


async def test_apply_busy_maps_to_409(config, tmp_path):
    service = _service(tmp_path, FakeBackend())
    client = await _client(config, service)
    try:
        await service._lock.acquire()
        try:
            response = await client.put(
                "/api/network", json={"mode": "dhcp"}, headers=HEADERS
            )
        finally:
            service._lock.release()
        assert response.status == 409
        assert (await response.json())["error"] == "apply_busy"
    finally:
        await client.close()


async def test_validation_error_has_field(config, tmp_path):
    service = _service(tmp_path, FakeBackend())
    client = await _client(config, service)
    try:
        response = await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.0.255",
            },
            headers=HEADERS,
        )
        assert response.status == 422
        body = await response.json()
        assert body["error"] == "validation_error"
        assert body["field"] == "subnet_mask"
    finally:
        await client.close()


async def test_network_requires_json_and_header(config, tmp_path):
    service = _service(tmp_path, FakeBackend())
    client = await _client(config, service)
    try:
        form = await client.put("/api/network", data="mode=dhcp")
        assert form.status == 415

        no_header = await client.put(
            "/api/network",
            json={"mode": "dhcp"},
            headers={"Content-Type": "application/json"},
        )
        assert no_header.status == 403

        no_service_client = TestClient(
            TestServer(create_app(config, dist_dir=Path("/nonexistent")))
        )
        await no_service_client.start_server()
        try:
            unavailable = await no_service_client.get("/api/network")
            assert unavailable.status == 503
            assert (await unavailable.json())["error"] == "network_unavailable"
        finally:
            await no_service_client.close()
    finally:
        await client.close()


async def test_network_pin_required_for_confirm(make_config, tmp_path):
    config = make_config(
        lambda data: data["web"].update({"pin_enabled": True, "pin": "123456"})
    )
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        login = await client.post(
            "/api/auth/login", json={"pin": "123456"}, headers=HEADERS
        )
        assert login.status == 200
        applied = await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
            },
            headers=HEADERS,
        )
        assert applied.status == 202
        await _wait_pending(service)

        logout = await client.post("/api/auth/logout", json={}, headers=HEADERS)
        assert logout.status == 200
        denied = await client.post("/api/network/confirm", json={}, headers=HEADERS)
        assert denied.status == 401
        assert (await denied.json())["error"] == "pin_required"
        assert service.pending is not None and service.pending.phase == "awaiting_confirmation"

        await client.post("/api/auth/login", json={"pin": "123456"}, headers=HEADERS)
        confirmed = await client.post("/api/network/confirm", json={}, headers=HEADERS)
        assert confirmed.status == 200
    finally:
        await client.close()


async def test_network_event_is_published(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        ws = await client.ws_connect("/api/events")
        second = await client.ws_connect("/api/events")
        initial = await ws.receive_json()
        assert initial["type"] == "status"
        assert (await second.receive_json())["type"] == "status"
        response = await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
            },
            headers=HEADERS,
        )
        assert response.status == 202
        event = await ws.receive_json()
        assert event["type"] == "network"
        assert event["data"]["pending"]["phase"] in {
            "activating",
            "awaiting_confirmation",
        }
        assert (await second.receive_json())["type"] == "network"
        await _wait_pending(service)
        await ws.close()
        await second.close()
    finally:
        await client.close()


async def test_static_then_dhcp_roundtrip(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        static = await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
                "gateway": "192.168.10.1",
                "dns": ["192.168.10.1"],
            },
            headers=HEADERS,
        )
        assert static.status == 202
        await _wait_pending(service)
        assert (await client.post("/api/network/confirm", json={}, headers=HEADERS)).status == 200
        assert backend.persisted[-1].mode == "static"

        dhcp = await client.put("/api/network", json={"mode": "dhcp"}, headers=HEADERS)
        assert dhcp.status == 202
        await _wait_pending(service)
        assert (await client.post("/api/network/confirm", json={}, headers=HEADERS)).status == 200
        assert backend.persisted[-1].mode == "dhcp"

        status = await client.get("/api/network")
        body = await status.json()
        assert body["pending"] is None
        assert body["last_result"]["status"] == "confirmed"
    finally:
        await client.close()


async def test_dhcp_apply_then_rollback(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        applied = await client.put(
            "/api/network", json={"mode": "dhcp"}, headers=HEADERS
        )
        assert applied.status == 202
        await _wait_pending(service)
        rolled = await client.post("/api/network/rollback", json={}, headers=HEADERS)
        assert rolled.status == 200
        body = await rolled.json()
        assert body["pending"] is None
        assert body["last_result"]["status"] == "rolled_back"
        assert backend.restored
        assert backend.persisted == []
    finally:
        await client.close()


async def test_network_rollback_endpoint(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
            },
            headers=HEADERS,
        )
        await _wait_pending(service)
        rolled = await client.post("/api/network/rollback", json={}, headers=HEADERS)
        assert rolled.status == 200
        assert (await rolled.json())["pending"] is None
        assert backend.restored
    finally:
        await client.close()


async def test_emergency_endpoint(config, tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        response = await client.post("/api/network/emergency", json={}, headers=HEADERS)
        assert response.status == 200
        body = await response.json()
        assert body["last_result"]["status"] == "fallback"
        assert body["current"]["address"] == "192.168.178.254"
        assert body["pending"] is None
    finally:
        await client.close()


async def test_failed_rollback_uses_emergency_endpoint_result(config, tmp_path):
    backend = FakeBackend()
    backend.fail_restore = True
    service = _service(tmp_path, backend)
    client = await _client(config, service)
    try:
        applied = await client.put(
            "/api/network",
            json={
                "mode": "static",
                "address": "192.168.10.60",
                "subnet_mask": "255.255.255.0",
            },
            headers=HEADERS,
        )
        assert applied.status == 202
        await _wait_pending(service)
        rolled = await client.post("/api/network/rollback", json={}, headers=HEADERS)
        assert rolled.status == 200
        body = await rolled.json()
        assert body["last_result"]["status"] == "fallback"
        assert body["current"]["address"] == "192.168.178.254"
    finally:
        await client.close()


async def test_backend_unavailable_maps_to_503(config, tmp_path):
    from ma2pi.network import NetworkUnavailable

    class UnavailableBackend(FakeBackend):
        async def available(self) -> bool:
            return False

        async def discover(self, interface: str | None = None):
            raise NetworkUnavailable("nmcli ist nicht installiert")

    service = _service(tmp_path, UnavailableBackend())
    client = await _client(config, service)
    try:
        status = await client.get("/api/network")
        body = await status.json()
        assert status.status == 200
        assert body["available"] is False

        response = await client.post(
            "/api/network/validate", json={"mode": "dhcp"}, headers=HEADERS
        )
        assert response.status == 503
        assert (await response.json())["error"] == "network_unavailable"
    finally:
        await client.close()


async def test_backend_error_maps_to_503(config, tmp_path):
    class BrokenBackend(FakeBackend):
        async def discover(self, interface: str | None = None):
            raise NetworkError("NetworkManager antwortet nicht")

    service = _service(tmp_path, BrokenBackend())
    client = await _client(config, service)
    try:
        status = await client.get("/api/network")
        assert status.status == 200
        body = await status.json()
        assert body["available"] is False

        response = await client.post(
            "/api/network/validate", json={"mode": "dhcp"}, headers=HEADERS
        )
        assert response.status == 500
        assert (await response.json())["error"] == "apply_failed"
    finally:
        await client.close()
