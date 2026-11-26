"""Unit tests for the NetworkManager adapter and network state machine."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
from pathlib import Path

import pytest

from ma2pi.network import (
    ApplyBusy,
    Candidate,
    CurrentIPv4,
    InterfaceInfo,
    LinkDown,
    NetworkError,
    NetworkManagerBackend,
    NetworkService,
    NetworkUnavailable,
    NetworkValidationError,
    PendingChange,
    PendingCorrupt,
    PendingExists,
    PendingStore,
    ProfileInfo,
    RawIPv4,
    mask_to_prefix,
    prefix_to_mask,
    split_terse,
    target_url,
)


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, ...], str | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, ...]] = []

    async def run(self, *args: str, timeout: float = 10.0) -> str:
        self.calls.append(args)
        value = self.responses.get(tuple(args))
        if value is None:
            for key, candidate in self.responses.items():
                if tuple(args)[: len(key)] == key:
                    value = candidate
                    break
        if value is None:
            raise AssertionError(f"unerwarteter nmcli-Aufruf: {args}")
        if isinstance(value, Exception):
            raise value
        return value


def _adapter(responses: dict[tuple[str, ...], str | Exception]) -> NetworkManagerBackend:
    return NetworkManagerBackend(FakeRunner(responses))


def _status_rows(*rows: str) -> str:
    return "\n".join(rows) + "\n"


def test_terse_parser_and_mask_conversion():
    assert split_terse(r"eth0:ethernet:connected:Wired\: LAN") == [
        "eth0",
        "ethernet",
        "connected",
        "Wired: LAN",
    ]
    assert mask_to_prefix("255.255.255.0") == 24
    assert prefix_to_mask(24) == "255.255.255.0"
    with pytest.raises(NetworkValidationError):
        mask_to_prefix("255.255.0.255")


def test_candidate_roundtrip_and_target_url():
    candidate = Candidate(
        mode="static",
        address="192.168.10.50",
        subnet_mask="255.255.255.0",
        gateway="192.168.10.1",
        dns=("192.168.10.1", "1.1.1.1"),
    )
    assert Candidate.from_dict(candidate.to_dict()) == candidate
    assert target_url("192.168.10.50", 8080) == "http://192.168.10.50:8080/"


async def test_select_interface_prefers_gateway_and_ignores_wifi():
    responses = {
        ("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"): _status_rows(
            "eth0:ethernet:connected:Wired connection 1",
            "eth1:ethernet:disconnected:Wired connection 2",
            "wlan0:wifi:connected:WLAN",
            "docker0:bridge:connected:docker0",
        ),
        ("-g", "IP4.GATEWAY", "device", "show", "eth0"): "192.168.10.1\n",
        ("-g", "IP4.GATEWAY", "device", "show", "eth1"): "\n",
    }
    backend = _adapter(responses)
    info = await backend.select_interface()
    assert info is not None
    assert info.name == "eth0"
    assert info.connected


async def test_select_interface_without_wired_returns_none():
    backend = _adapter(
        {
            ("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"): _status_rows(
                "lo:loopback:unmanaged:lo",
                "wlan0:wifi:connected:WLAN",
            )
        }
    )
    assert await backend.select_interface() is None


async def test_read_static_profile_and_current_values():
    responses = {
        ("-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active"): _status_rows(
            "Wired connection 1:uuid-1:802-3-ethernet:eth0"
        ),
        ("-g", "ipv4.method", "connection", "show", "uuid", "uuid-1"): "manual\n",
        ("-g", "ipv4.addresses", "connection", "show", "uuid", "uuid-1"): "192.168.10.50/24\n",
        ("-g", "ipv4.gateway", "connection", "show", "uuid", "uuid-1"): "192.168.10.1\n",
        ("-g", "ipv4.dns", "connection", "show", "uuid", "uuid-1"): "192.168.10.1 1.1.1.1\n",
        ("-g", "ipv4.ignore-auto-dns", "connection", "show", "uuid", "uuid-1"): "yes\n",
        ("-g", "IP4.ADDRESS", "device", "show", "eth0"): "192.168.10.50/24\n",
        ("-g", "IP4.GATEWAY", "device", "show", "eth0"): "192.168.10.1\n",
        ("-g", "IP4.DNS", "device", "show", "eth0"): "192.168.10.1 1.1.1.1\n",
    }
    backend = _adapter(responses)
    profile = await backend.read_profile("eth0")
    assert profile is not None
    assert profile.mode == "static"
    assert profile.raw.addresses == ("192.168.10.50/24",)
    current = await backend.current_values("eth0", profile)
    assert current.address == "192.168.10.50"
    assert current.subnet_mask == "255.255.255.0"
    assert current.gateway == "192.168.10.1"
    assert current.dns == ("192.168.10.1", "1.1.1.1")


async def test_read_inactive_profile_matches_interface_name():
    responses = {
        ("-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active"): "",
        ("-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show"): _status_rows(
            "Wired 1:uuid-1:802-3-ethernet:",
            "Wired 2:uuid-2:802-3-ethernet:",
        ),
        ("-g", "connection.interface-name", "connection", "show", "uuid", "uuid-1"): "eth1\n",
        ("-g", "connection.interface-name", "connection", "show", "uuid", "uuid-2"): "eth0\n",
        ("-g", "ipv4.method", "connection", "show", "uuid", "uuid-2"): "auto\n",
        ("-g", "ipv4.addresses", "connection", "show", "uuid", "uuid-2"): "",
        ("-g", "ipv4.gateway", "connection", "show", "uuid", "uuid-2"): "",
        ("-g", "ipv4.dns", "connection", "show", "uuid", "uuid-2"): "",
        ("-g", "ipv4.ignore-auto-dns", "connection", "show", "uuid", "uuid-2"): "no\n",
    }
    backend = _adapter(responses)
    profile = await backend.read_profile("eth0")
    assert profile is not None
    assert profile.uuid == "uuid-2"


async def test_read_dhcp_profile():
    responses = {
        ("-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show", "--active"): _status_rows(
            "Wired connection 1:uuid-1:802-3-ethernet:eth0"
        ),
        ("-g", "ipv4.method", "connection", "show", "uuid", "uuid-1"): "auto\n",
        ("-g", "ipv4.addresses", "connection", "show", "uuid", "uuid-1"): "",
        ("-g", "ipv4.gateway", "connection", "show", "uuid", "uuid-1"): "",
        ("-g", "ipv4.dns", "connection", "show", "uuid", "uuid-1"): "",
        ("-g", "ipv4.ignore-auto-dns", "connection", "show", "uuid", "uuid-1"): "no\n",
    }
    backend = _adapter(responses)
    profile = await backend.read_profile("eth0")
    assert profile is not None
    assert profile.mode == "dhcp"


async def test_stage_uses_temporary_ipv4_only_arguments():
    runner = FakeRunner(
        {
            (
                "connection",
                "modify",
                "--temporary",
                "uuid",
                "uuid-1",
            ): "",
            ("connection", "up", "uuid", "uuid-1"): "",
        }
    )
    backend = NetworkManagerBackend(runner)
    candidate = Candidate(
        mode="static",
        address="192.168.10.50",
        subnet_mask="255.255.255.0",
        gateway="192.168.10.1",
        dns=("192.168.10.1", "1.1.1.1"),
    )
    profile = ProfileInfo("uuid-1", "Wired connection 1", "auto")
    await backend.stage(candidate, profile)
    modify = runner.calls[0]
    assert modify[:5] == ("connection", "modify", "--temporary", "uuid", "uuid-1")
    assert "ipv4.method" in modify
    assert "manual" in modify
    assert "192.168.10.50/24" in modify
    assert "192.168.10.1 1.1.1.1" in modify
    assert "connection.id" not in modify
    assert runner.calls[1] == ("connection", "up", "uuid", "uuid-1")


async def test_persist_and_dhcp_arguments_are_deterministic():
    runner = FakeRunner(
        {
            ("connection", "modify", "uuid", "uuid-1"): "",
        }
    )
    backend = NetworkManagerBackend(runner)
    profile = ProfileInfo("uuid-1", "Wired connection 1", "manual")
    await backend.persist(Candidate(mode="dhcp"), profile)
    assert runner.calls[0] == (
        "connection",
        "modify",
        "uuid",
        "uuid-1",
        "ipv4.method",
        "auto",
        "ipv4.addresses",
        "",
        "ipv4.gateway",
        "",
        "ipv4.dns",
        "",
        "ipv4.ignore-auto-dns",
        "no",
    )


async def test_restore_uses_raw_values_and_created_profile_is_deleted():
    runner = FakeRunner(
        {
            (
                "connection",
                "modify",
                "--temporary",
                "uuid",
                "uuid-1",
            ): "",
            ("connection", "up", "uuid", "uuid-1"): "",
            ("connection", "delete", "uuid", "uuid-created"): "",
        }
    )
    backend = NetworkManagerBackend(runner)
    raw = RawIPv4(
        method="manual",
        addresses=("192.168.10.40/24",),
        gateway="192.168.10.1",
        dns=("192.168.10.1",),
        ignore_auto_dns=True,
    )
    await backend.restore(raw, ProfileInfo("uuid-1", "Wired connection 1", "manual"))
    assert "192.168.10.40/24" in runner.calls[0]
    assert "yes" in runner.calls[0]
    await backend.restore(raw, ProfileInfo("uuid-created", "ma2pi-eth0", "auto", created=True))
    assert runner.calls[-1] == ("connection", "delete", "uuid", "uuid-created")


async def test_create_profile_returns_created_flag():
    runner = FakeRunner(
        {
            (
                "connection",
                "add",
                "type",
                "ethernet",
                "ifname",
                "eth0",
                "con-name",
                "ma2pi-eth0",
                "autoconnect",
                "no",
                "ipv4.method",
                "auto",
            ): "",
            ("-g", "UUID", "connection", "show", "id", "ma2pi-eth0"): "uuid-new\n",
        }
    )
    backend = NetworkManagerBackend(runner)
    profile = await backend.create_profile("eth0")
    assert profile.uuid == "uuid-new"
    assert profile.created is True


async def test_backend_unavailable_when_nmcli_fails():
    backend = _adapter(
        {
            ("-t", "-f", "STATE", "general"): NetworkUnavailable("nmcli fehlt"),
            (
                "-t",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
            ): NetworkUnavailable("nmcli fehlt"),
        }
    )
    assert await backend.available() is False
    with pytest.raises(NetworkUnavailable):
        await backend.devices()


def test_pending_store_roundtrip_and_permissions(tmp_path):
    store = PendingStore(tmp_path / "network-pending.json")
    pending = PendingChange(
        interface="eth0",
        profile_uuid="uuid-1",
        profile_name="Wired connection 1",
        created_profile=False,
        previous=RawIPv4(method="auto", gateway="", dns=(), ignore_auto_dns=False),
        candidate=Candidate(
            mode="static",
            address="192.168.10.50",
            subnet_mask="255.255.255.0",
            gateway="192.168.10.1",
            dns=("192.168.10.1",),
        ),
        started_at=1000.0,
        phase="awaiting_confirmation",
        deadline=1180.0,
        target_url="http://192.168.10.50:8080/",
    )
    store.save(pending)
    assert store.path.stat().st_mode & 0o777 == 0o600
    loaded = store.load()
    assert loaded is not None
    assert loaded.candidate == pending.candidate
    assert loaded.previous == pending.previous
    assert loaded.deadline == 1180.0
    store.clear()
    assert not store.path.exists()


def test_pending_store_keeps_old_file_when_replace_fails(tmp_path, monkeypatch):
    store = PendingStore(tmp_path / "network-pending.json")
    old = PendingChange(
        interface="eth0",
        profile_uuid="uuid-1",
        profile_name="Wired connection 1",
        created_profile=False,
        previous=RawIPv4(),
        candidate=Candidate(
            mode="static", address="192.168.10.50", subnet_mask="255.255.255.0"
        ),
        started_at=1000.0,
        phase="awaiting_confirmation",
        deadline=1180.0,
    )
    store.save(old)

    def fail_replace(source, destination):
        raise OSError("simulierter Abbruch")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        store.save(
            dataclasses.replace(
                old,
                candidate=Candidate(
                    mode="static",
                    address="192.168.10.60",
                    subnet_mask="255.255.255.0",
                ),
            )
        )
    assert store.load() == old
    assert not list(tmp_path.glob(".network-pending-*"))


def test_pending_store_rejects_corrupt_file(tmp_path):
    path = tmp_path / "network-pending.json"
    path.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(PendingCorrupt):
        PendingStore(path).load()


def test_pending_store_rejects_unknown_version(tmp_path):
    path = tmp_path / "network-pending.json"
    path.write_text(json.dumps({"version": 99}), encoding="utf-8")
    with pytest.raises(PendingCorrupt):
        PendingStore(path).load()


class FakeBackend:
    def __init__(self) -> None:
        self.interface = InterfaceInfo("eth0", "ethernet", "connected", "Wired connection 1")
        self.profile: ProfileInfo | None = ProfileInfo(
            "uuid-1", "Wired connection 1", "auto"
        )
        self.current = CurrentIPv4()
        self.addresses: dict[str, str] = {}
        self.staged: list[Candidate] = []
        self.persisted: list[Candidate] = []
        self.restored: list[RawIPv4] = []
        self.fail_stage = False
        self.fail_restore = False
        self.assign_on_stage = True

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
        if self.fail_stage:
            raise NetworkError("Aktivierung fehlgeschlagen")
        self.staged.append(candidate)
        if not self.assign_on_stage:
            return
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
        self.profile = dataclasses.replace(
            profile,
            method="manual" if candidate.mode == "static" else "auto",
            addresses=(f"{candidate.address}/{candidate.prefix}",) if candidate.mode == "static" else (),
            gateway=candidate.gateway or "",
            dns=candidate.dns,
        )

    async def restore(
        self, raw: RawIPv4, profile: ProfileInfo, *, persist: bool = False
    ) -> None:
        if self.fail_restore:
            raise NetworkError("Rollback-Profil nicht verfügbar")
        self.restored.append(raw)


def _service(tmp_path: Path, backend: FakeBackend, **kwargs) -> NetworkService:
    return NetworkService(
        backend,  # type: ignore[arg-type]
        PendingStore(tmp_path / "network-pending.json"),
        port=8080,
        activation_delay=0,
        **kwargs,
    )


async def _wait_phase(service: NetworkService, phase: str, timeout: float = 1.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if service.pending is not None and service.pending.phase == phase:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Phase {phase} nicht erreicht")


async def test_validate_static_candidate_and_warnings(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    result = await service.validate(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.10.1",
            "dns": ["192.168.10.1"],
        }
    )
    assert result["valid"] is True
    assert result["target_url"] == "http://192.168.10.50:8080/"
    assert result["warnings"] == []


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"mode": "static", "address": "192.168.10.50", "subnet_mask": "255.255.0.255"}, "subnet_mask"),
        ({"mode": "static", "address": "192.168.10.50", "subnet_mask": "255.255.255.0", "gateway": "192.168.20.1"}, "gateway"),
        ({"mode": "static", "address": "192.168.10.50", "subnet_mask": "255.255.255.0", "dns": ["kaputt"]}, "dns"),
        ({"mode": "dhcp", "address": "192.168.10.50"}, "mode"),
        ({"mode": "static", "address": "192.168.10.50"}, "subnet_mask"),
    ],
)
async def test_validate_rejects_invalid_candidates(tmp_path, payload, field):
    service = _service(tmp_path, FakeBackend())
    with pytest.raises(NetworkValidationError) as exc:
        await service.validate(payload)
    assert exc.value.field == field


async def test_validate_rejects_address_used_on_another_interface(tmp_path):
    backend = FakeBackend()
    backend.addresses = {"192.168.10.50": "eth1"}
    service = _service(tmp_path, backend)
    with pytest.raises(NetworkValidationError) as exc:
        await service.validate(
            {
                "mode": "static",
                "address": "192.168.10.50",
                "subnet_mask": "255.255.255.0",
            }
        )
    assert exc.value.field == "address"


async def test_validate_allows_gateway_and_dns_empty(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    result = await service.validate(
        {"mode": "static", "address": "192.168.10.50", "subnet_mask": "255.255.255.0"}
    )
    assert result["valid"] is True
    assert any("Gateway" in warning for warning in result["warnings"])
    assert any("DNS" in warning for warning in result["warnings"])


async def test_apply_confirm_persists_and_clears_pending(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    pending = await service.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.10.1",
            "dns": ["192.168.10.1"],
        }
    )
    assert pending.phase == "activating"
    await _wait_phase(service, "awaiting_confirmation")
    assert backend.staged[0].address == "192.168.10.50"
    status = await service.confirm()
    assert backend.persisted[0].address == "192.168.10.50"
    assert status["pending"] is None
    assert service.pending is None
    assert status["last_result"]["status"] == "confirmed"


async def test_apply_lock_reports_busy(tmp_path):
    service = _service(tmp_path, FakeBackend())
    await service._lock.acquire()
    try:
        with pytest.raises(ApplyBusy):
            await service.apply({"mode": "dhcp"})
    finally:
        service._lock.release()


async def test_second_apply_is_rejected(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    payload = {
        "mode": "static",
        "address": "192.168.10.50",
        "subnet_mask": "255.255.255.0",
    }
    await service.apply(payload)
    with pytest.raises(PendingExists):
        await service.apply(payload)
    await _wait_phase(service, "awaiting_confirmation")


async def test_timeout_rolls_back(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend, confirm_timeout=0.05)
    await service.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.10.1",
        }
    )
    await _wait_phase(service, "awaiting_confirmation")
    for _ in range(100):
        if service.pending is None:
            break
        await asyncio.sleep(0.01)
    assert service.pending is None
    assert backend.restored
    status = await service.status()
    assert status["last_result"]["status"] == "rolled_back"


async def test_activation_failure_rolls_back_with_failed_result(tmp_path):
    backend = FakeBackend()
    backend.fail_stage = True
    service = _service(tmp_path, backend)
    await service.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
        }
    )
    for _ in range(100):
        if service.pending is None:
            break
        await asyncio.sleep(0.01)
    assert service.pending is None
    assert backend.restored
    status = await service.status()
    assert status["last_result"]["status"] == "failed"
    assert "Aktivierung" in status["last_result"]["detail"]


async def test_late_confirm_rolls_back(tmp_path):
    clock = [1000.0]
    backend = FakeBackend()
    service = NetworkService(
        backend,
        PendingStore(tmp_path / "network-pending.json"),
        port=8080,
        activation_delay=0,
        clock=lambda: clock[0],
    )
    await service.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
        }
    )
    await _wait_phase(service, "awaiting_confirmation")
    clock[0] = 2000.0
    with pytest.raises(NetworkError):
        await service.confirm()
    assert service.pending is None
    assert backend.restored


async def test_failed_rollback_falls_back_to_emergency_address(tmp_path):
    backend = FakeBackend()
    backend.fail_restore = True
    service = _service(tmp_path, backend)
    await service.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
        }
    )
    await _wait_phase(service, "awaiting_confirmation")
    status = await service.rollback()
    assert status["pending"] is None
    assert status["last_result"]["status"] == "fallback"
    assert backend.staged[-1].address == "192.168.178.254"
    assert backend.staged[-1].subnet_mask == "255.255.255.0"
    assert backend.persisted[-1].address == "192.168.178.254"


async def test_manual_emergency_address(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    status = await service.emergency()
    assert status["pending"] is None
    assert status["last_result"]["status"] == "fallback"
    assert status["current"]["address"] == "192.168.178.254"
    assert backend.persisted[-1].address == "192.168.178.254"


async def test_manual_rollback(tmp_path):
    backend = FakeBackend()
    service = _service(tmp_path, backend)
    await service.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
        }
    )
    await _wait_phase(service, "awaiting_confirmation")
    status = await service.rollback()
    assert status["pending"] is None
    assert backend.restored


async def test_resume_expired_pending_rolls_back(tmp_path):
    backend = FakeBackend()
    store = PendingStore(tmp_path / "network-pending.json")
    pending = PendingChange(
        interface="eth0",
        profile_uuid="uuid-1",
        profile_name="Wired connection 1",
        created_profile=False,
        previous=RawIPv4(method="auto"),
        candidate=Candidate(
            mode="static",
            address="192.168.10.50",
            subnet_mask="255.255.255.0",
        ),
        started_at=1000.0,
        phase="awaiting_confirmation",
        deadline=1001.0,
    )
    store.save(pending)
    service = NetworkService(
        backend, store, port=8080, clock=lambda: 2000.0, activation_delay=0
    )
    await service.resume()
    assert service.pending is None
    assert backend.restored
    assert not store.path.exists()


async def test_resume_active_window_continues_timer(tmp_path):
    backend = FakeBackend()
    store = PendingStore(tmp_path / "network-pending.json")
    first = NetworkService(
        backend, store, port=8080, activation_delay=0, confirm_timeout=0.08
    )
    await first.apply(
        {
            "mode": "static",
            "address": "192.168.10.50",
            "subnet_mask": "255.255.255.0",
        }
    )
    await _wait_phase(first, "awaiting_confirmation")
    await first.close()

    restarted = NetworkService(
        backend, store, port=8080, activation_delay=0, confirm_timeout=0.08
    )
    await restarted.resume()
    assert restarted.pending is not None
    for _ in range(100):
        if restarted.pending is None:
            break
        await asyncio.sleep(0.01)
    assert restarted.pending is None
    assert backend.restored
    assert not store.path.exists()


async def test_resume_confirmed_pending_is_cleared(tmp_path):
    backend = FakeBackend()
    store = PendingStore(tmp_path / "network-pending.json")
    pending = PendingChange(
        interface="eth0",
        profile_uuid="uuid-1",
        profile_name="Wired connection 1",
        created_profile=False,
        previous=RawIPv4(method="auto"),
        candidate=Candidate(
            mode="static",
            address="192.168.10.50",
            subnet_mask="255.255.255.0",
        ),
        started_at=1000.0,
        phase="confirmed",
    )
    store.save(pending)
    service = NetworkService(backend, store, port=8080, activation_delay=0)
    await service.resume()
    assert service.pending is None
    assert not store.path.exists()
    assert not backend.restored


@pytest.mark.parametrize("phase", ["activating", "rolling_back", "failed"])
async def test_resume_interrupted_phases_roll_back(tmp_path, phase):
    backend = FakeBackend()
    store = PendingStore(tmp_path / "network-pending.json")
    pending = PendingChange(
        interface="eth0",
        profile_uuid="uuid-1",
        profile_name="Wired connection 1",
        created_profile=False,
        previous=RawIPv4(method="auto"),
        candidate=Candidate(
            mode="static",
            address="192.168.10.50",
            subnet_mask="255.255.255.0",
        ),
        started_at=1000.0,
        phase=phase,
    )
    store.save(pending)
    service = NetworkService(backend, store, port=8080, activation_delay=0)
    await service.resume()
    assert service.pending is None
    assert backend.restored
    assert not store.path.exists()


async def test_resume_corrupt_pending_does_not_change_network(tmp_path):
    backend = FakeBackend()
    path = tmp_path / "network-pending.json"
    path.write_text("{kaputt", encoding="utf-8")
    service = NetworkService(
        backend, PendingStore(path), port=8080, activation_delay=0
    )
    await service.resume()
    assert service.pending is None
    assert not backend.restored
    status = await service.status()
    assert status["last_result"]["status"] == "failed"


async def test_link_down_blocks_apply(tmp_path):
    backend = FakeBackend()
    backend.interface = dataclasses.replace(backend.interface, state="disconnected")
    service = _service(tmp_path, backend)
    with pytest.raises(LinkDown):
        await service.apply(
            {
                "mode": "static",
                "address": "192.168.10.50",
                "subnet_mask": "255.255.255.0",
            }
        )
