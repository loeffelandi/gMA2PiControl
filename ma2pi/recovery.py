"""Recovery hotspot on the WiFi interface.

The hotspot is a NetworkManager AP profile with an internal DHCP server.  It is
deliberately separate from the normal WiFi connection and can be enabled from
the configuration UI or automatically when the wired management network is
missing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .network import (
    NetworkError,
    NetworkUnavailable,
    Runner,
    SubprocessRunner,
    split_terse,
)

LOGGER = logging.getLogger("ma2pi.recovery")

DEFAULT_SSID = "ma2pi-recovery"
DEFAULT_PASSWORD = "ma2pi-recovery"
DEFAULT_ADDRESS = "192.168.50.1"
DEFAULT_PREFIX = 24
PROFILE_NAME = "ma2pi-recovery"
SETTINGS_VERSION = 1
AUTO_DOWN_GRACE = 60.0
AUTO_UP_GRACE = 60.0
MONITOR_INTERVAL = 10.0


class RecoveryError(RuntimeError):
    """Recovery hotspot operation failed."""


class RecoveryValidationError(RecoveryError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


@dataclass
class RecoverySettings:
    enabled: bool = False
    ssid: str = DEFAULT_SSID
    password: str = DEFAULT_PASSWORD
    auto: bool = True
    auto_triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SETTINGS_VERSION,
            "enabled": self.enabled,
            "ssid": self.ssid,
            "password": self.password,
            "auto": self.auto,
            "auto_triggered": self.auto_triggered,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RecoverySettings":
        return cls(
            enabled=bool(data.get("enabled", False)),
            ssid=str(data.get("ssid", DEFAULT_SSID)),
            password=str(data.get("password", DEFAULT_PASSWORD)),
            auto=bool(data.get("auto", True)),
            auto_triggered=bool(data.get("auto_triggered", False)),
        )


class RecoveryStore:
    """Atomic JSON persistence for the recovery settings."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> RecoverySettings:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return RecoverySettings()
        except OSError as exc:
            raise RecoveryError(f"Rettungs-Einstellungen nicht lesbar: {exc}") from exc
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("JSON-Objekt erwartet")
            return RecoverySettings.from_dict(data)
        except (ValueError, TypeError) as exc:
            raise RecoveryError(f"Rettungs-Einstellungen beschädigt: {exc}") from exc

    def save(self, settings: RecoverySettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        payload = json.dumps(settings.to_dict(), indent=2, sort_keys=True) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=".recovery-", suffix=".tmp"
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            self._fsync_dir()
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise

    def _fsync_dir(self) -> None:
        try:
            fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class RecoveryBackend:
    """Create and activate the NetworkManager AP profile."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    async def _run(self, *args: str, timeout: float = 15.0) -> str:
        return await self._runner.run(*args, timeout=timeout)

    async def _values(self, *args: str) -> str:
        return await self._run("-g", *args)

    async def wifi_device(self) -> str | None:
        text = await self._run(
            "-t", "-f", "DEVICE,TYPE,STATE", "device", "status", timeout=5.0
        )
        for line in text.splitlines():
            fields = split_terse(line)
            if len(fields) >= 3 and fields[1] == "wifi" and not fields[0].startswith("p2p-"):
                return fields[0]
        return None

    async def available(self) -> bool:
        try:
            await self._run("-t", "-f", "STATE", "general", timeout=5.0)
            return await self.wifi_device() is not None
        except NetworkError:
            return False

    async def profile_uuid(self) -> str | None:
        text = await self._run(
            "-t", "-f", "NAME,UUID,TYPE", "connection", "show", timeout=5.0
        )
        for line in text.splitlines():
            fields = split_terse(line)
            if len(fields) >= 3 and fields[0] == PROFILE_NAME:
                return fields[1]
        return None

    @staticmethod
    def _properties(settings: RecoverySettings) -> list[str]:
        return [
            "wifi.ssid",
            settings.ssid,
            "wifi.mode",
            "ap",
            "wifi.band",
            "bg",
            "wifi.channel",
            "6",
            "wifi-sec.key-mgmt",
            "wpa-psk",
            "wifi-sec.psk",
            settings.password,
            "ipv4.method",
            "shared",
            "ipv4.addresses",
            f"{DEFAULT_ADDRESS}/{DEFAULT_PREFIX}",
            "ipv6.method",
            "ignore",
            "connection.autoconnect",
            "no",
        ]

    async def apply(self, settings: RecoverySettings) -> str:
        interface = await self.wifi_device()
        if interface is None:
            raise NetworkUnavailable("Keine WLAN-Schnittstelle gefunden")
        uuid = await self.profile_uuid()
        if uuid is None:
            await self._run(
                "connection",
                "add",
                "type",
                "wifi",
                "ifname",
                interface,
                "con-name",
                PROFILE_NAME,
                *self._properties(settings),
                timeout=20.0,
            )
            uuid = await self.profile_uuid()
            if uuid is None:
                raise RecoveryError("Rettungsprofil konnte nicht angelegt werden")
        else:
            await self._run(
                "connection",
                "modify",
                "uuid",
                uuid,
                *self._properties(settings),
                timeout=20.0,
            )
        await self._run("connection", "up", "uuid", uuid, timeout=30.0)
        return uuid

    async def disable(self) -> None:
        uuid = await self.profile_uuid()
        if uuid is None:
            return
        try:
            await self._run("connection", "down", "uuid", uuid, timeout=15.0)
        except NetworkError:
            pass

    async def active(self) -> bool:
        text = await self._run(
            "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status", timeout=5.0
        )
        for line in text.splitlines():
            fields = split_terse(line)
            if len(fields) >= 4 and fields[1] == "wifi":
                return fields[3] == PROFILE_NAME and fields[2] == "connected"
        return False

    async def address(self) -> str | None:
        interface = await self.wifi_device()
        if interface is None:
            return None
        value = await self._values("IP4.ADDRESS", "device", "show", interface)
        for line in value.splitlines():
            if line.strip():
                return line.strip().split("/", 1)[0]
        return None


class RecoveryService:
    """Toggle the hotspot and decide when automatic recovery is allowed."""

    def __init__(
        self,
        backend: RecoveryBackend,
        store: RecoveryStore,
        *,
        port: int = 8080,
        publish: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] | None = None,
        down_grace: float = AUTO_DOWN_GRACE,
        up_grace: float = AUTO_UP_GRACE,
    ) -> None:
        import time

        self._backend = backend
        self._store = store
        self.port = port
        self.publish = publish
        self._clock = clock or time.time
        self._down_grace = down_grace
        self._up_grace = up_grace
        self._lock = asyncio.Lock()
        self._settings = RecoverySettings()
        self._last_wired_ok: bool | None = None
        self._wired_since: float | None = None

    @property
    def settings(self) -> RecoverySettings:
        return self._settings

    def _emit(self) -> None:
        if self.publish is not None:
            self.publish(
                {
                    "type": "recovery",
                    "data": {
                        "enabled": self._settings.enabled,
                        "ssid": self._settings.ssid,
                        "active": self._settings.enabled,
                    },
                }
            )

    async def resume(self) -> None:
        async with self._lock:
            try:
                self._settings = self._store.load()
            except RecoveryError as exc:
                LOGGER.error("Rettungs-Einstellungen nicht lesbar: %s", exc)
                return
            if self._settings.enabled:
                try:
                    await self._backend.apply(self._settings)
                    LOGGER.info("Rettungs-WLAN nach Start aktiviert")
                except Exception as exc:
                    LOGGER.error("Rettungs-WLAN konnte nicht aktiviert werden: %s", exc)

    async def status(self) -> dict[str, Any]:
        try:
            available = await self._backend.available()
        except NetworkError:
            available = False
        active = False
        address = None
        error = None
        if available:
            try:
                active = await self._backend.active()
                address = await self._backend.address() if active else None
            except NetworkError as exc:
                error = str(exc)
        return {
            "available": available,
            "enabled": self._settings.enabled,
            "active": active,
            "ssid": self._settings.ssid,
            "password": self._settings.password,
            "auto": self._settings.auto,
            "auto_triggered": self._settings.auto_triggered,
            "address": address or (DEFAULT_ADDRESS if active else None),
            "url": f"http://{address or DEFAULT_ADDRESS}:{self.port}/",
            "error": error,
        }

    async def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise RecoveryValidationError("body", "JSON-Objekt erwartet")
        allowed = {"enabled", "ssid", "password", "auto"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise RecoveryValidationError("body", f"unbekannte Felder: {', '.join(unknown)}")
        async with self._lock:
            ssid = str(payload.get("ssid", self._settings.ssid)).strip()
            password = str(payload.get("password", self._settings.password))
            enabled = bool(payload.get("enabled", self._settings.enabled))
            auto = bool(payload.get("auto", self._settings.auto))
            if not 1 <= len(ssid) <= 32:
                raise RecoveryValidationError("ssid", "muss 1 bis 32 Zeichen lang sein")
            if not 8 <= len(password) <= 63:
                raise RecoveryValidationError("password", "muss 8 bis 63 Zeichen lang sein")
            self._settings = RecoverySettings(
                enabled=enabled,
                ssid=ssid,
                password=password,
                auto=auto,
                auto_triggered=self._settings.auto_triggered if enabled else False,
            )
            try:
                self._store.save(self._settings)
            except OSError as exc:
                raise RecoveryError(f"Rettungs-Einstellungen nicht schreibbar: {exc}") from exc
            try:
                if enabled:
                    await self._backend.apply(self._settings)
                else:
                    await self._backend.disable()
            except Exception as exc:
                self._settings.enabled = False
                with contextlib.suppress(OSError):
                    self._store.save(self._settings)
                raise RecoveryError(f"Rettungs-WLAN nicht anwendbar: {exc}") from exc
            self._emit()
        return await self.status()

    async def set_enabled(self, enabled: bool) -> dict[str, Any]:
        return await self.save({"enabled": enabled})

    async def auto_cycle(self, wired_ok: bool) -> None:
        """Enable the hotspot after a wired outage, disable after recovery.

        Only a sustained outage or recovery changes the state.  A single lost
        packet or a short reconnect does not toggle the WiFi.
        """
        if not self._settings.auto:
            return
        now = self._clock()
        if self._last_wired_ok is None or self._last_wired_ok != wired_ok:
            self._last_wired_ok = wired_ok
            self._wired_since = now
            return
        if wired_ok:
            if self._settings.auto_triggered and self._wired_since is not None:
                if now - self._wired_since >= self._up_grace:
                    try:
                        await self.set_enabled(False)
                        self._settings.auto_triggered = False
                        self._store.save(self._settings)
                        LOGGER.info("Rettungs-WLAN automatisch deaktiviert")
                    except Exception as exc:
                        LOGGER.error("Rettungs-WLAN konnte nicht deaktiviert werden: %s", exc)
            return
        if not self._settings.enabled and self._wired_since is not None:
            if now - self._wired_since >= self._down_grace:
                try:
                    self._settings.auto_triggered = True
                    await self.save({"enabled": True})
                    LOGGER.warning("Rettungs-WLAN automatisch aktiviert (LAN fehlt)")
                except Exception as exc:
                    LOGGER.error("Rettungs-WLAN konnte nicht aktiviert werden: %s", exc)
