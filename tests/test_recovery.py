"""Tests for the recovery hotspot settings and automatic switch."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from ma2pi.recovery import (
    DEFAULT_ADDRESS,
    RecoveryService,
    RecoverySettings,
    RecoveryStore,
    RecoveryValidationError,
)
from ma2pi.web import create_app

HEADERS = {"X-Ma2pi-Request": "1"}


class FakeRecoveryBackend:
    def __init__(self) -> None:
        self.applied: list[RecoverySettings] = []
        self.disabled = 0
        self.is_active = False
        self.current_address: str | None = None
        self.is_available = True

    async def available(self) -> bool:
        return self.is_available

    async def apply(self, settings: RecoverySettings) -> str:
        self.applied.append(settings)
        self.is_active = True
        self.current_address = DEFAULT_ADDRESS
        return "uuid-recovery"

    async def disable(self) -> None:
        self.disabled += 1
        self.is_active = False
        self.current_address = None

    async def active(self) -> bool:
        return self.is_active

    async def address(self) -> str | None:
        return self.current_address


def _service(tmp_path: Path, backend: FakeRecoveryBackend, **kwargs) -> RecoveryService:
    return RecoveryService(
        backend,  # type: ignore[arg-type]
        RecoveryStore(tmp_path / "recovery.json"),
        port=8080,
        **kwargs,
    )


def test_recovery_store_roundtrip(tmp_path):
    store = RecoveryStore(tmp_path / "recovery.json")
    settings = RecoverySettings(
        enabled=True,
        ssid="test-recovery",
        password="ein-langes-passwort",
        auto=False,
        auto_triggered=True,
    )
    store.save(settings)
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.load() == settings


async def test_recovery_save_enables_and_disables(tmp_path):
    backend = FakeRecoveryBackend()
    service = _service(tmp_path, backend)
    status = await service.save(
        {
            "enabled": True,
            "ssid": "test-recovery",
            "password": "ein-langes-passwort",
            "auto": False,
        }
    )
    assert status["enabled"] is True
    assert status["active"] is True
    assert status["ssid"] == "test-recovery"
    assert status["address"] == DEFAULT_ADDRESS
    assert backend.applied[-1].password == "ein-langes-passwort"

    off = await service.save({"enabled": False})
    assert off["enabled"] is False
    assert off["active"] is False
    assert backend.disabled == 1


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"ssid": ""}, "ssid"),
        ({"ssid": "x" * 33}, "ssid"),
        ({"password": "kurz"}, "password"),
        ({"password": "x" * 64}, "password"),
        ({"mail": "x"}, "body"),
    ],
)
async def test_recovery_validation(tmp_path, payload, field):
    service = _service(tmp_path, FakeRecoveryBackend())
    with pytest.raises(RecoveryValidationError) as exc:
        await service.save(payload)
    assert exc.value.field == field


async def test_auto_cycle_enables_after_down_grace_and_disables_after_up_grace(tmp_path):
    clock = [1000.0]
    backend = FakeRecoveryBackend()
    service = _service(
        tmp_path,
        backend,
        clock=lambda: clock[0],
        down_grace=10.0,
        up_grace=20.0,
    )
    await service.auto_cycle(False)
    clock[0] = 1009.0
    await service.auto_cycle(False)
    assert service.settings.enabled is False
    clock[0] = 1011.0
    await service.auto_cycle(False)
    assert service.settings.enabled is True
    assert service.settings.auto_triggered is True
    assert backend.applied

    await service.auto_cycle(True)
    clock[0] = 1029.0
    await service.auto_cycle(True)
    assert service.settings.enabled is True
    clock[0] = 1032.0
    await service.auto_cycle(True)
    assert service.settings.enabled is False
    assert backend.disabled == 1


async def test_recovery_api_roundtrip(make_config, tmp_path):
    backend = FakeRecoveryBackend()
    service = _service(tmp_path, backend)
    client = TestClient(
        TestServer(
            create_app(
                make_config(),
                dist_dir=Path("/nonexistent"),
                recovery_service=service,
            )
        )
    )
    await client.start_server()
    try:
        read = await client.get("/api/recovery")
        assert read.status == 200
        assert (await read.json())["ssid"] == "ma2pi-recovery"

        saved = await client.put(
            "/api/recovery",
            json={
                "enabled": True,
                "ssid": "test-recovery",
                "password": "ein-langes-passwort",
                "auto": True,
            },
            headers=HEADERS,
        )
        assert saved.status == 200
        body = await saved.json()
        assert body["active"] is True
        assert body["address"] == "192.168.50.1"

        invalid = await client.put(
            "/api/recovery", json={"password": "kurz"}, headers=HEADERS
        )
        assert invalid.status == 422
        assert (await invalid.json())["field"] == "password"
    finally:
        await client.close()
