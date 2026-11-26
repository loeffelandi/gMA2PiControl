"""Wired IPv4 configuration through NetworkManager.

The daemon never changes network settings directly.  ``nmcli`` is the only
interface to NetworkManager; it is called with a fixed argument vector (no
shell) and a dedicated ``LC_ALL=C`` environment so parsing is deterministic.
The service in this module owns the two-phase apply: a candidate is activated
temporarily, the UI has to confirm it, and otherwise the previous raw IPv4
settings are restored.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol

LOGGER = logging.getLogger("ma2pi.network")

NMCLI = "/usr/bin/nmcli"
PENDING_VERSION = 1
CONFIRM_TIMEOUT = 180.0
ACTIVATION_TIMEOUT = 20.0
ACTIVATION_DELAY = 0.1
POLL_INTERVAL = 0.25
FALLBACK_ADDRESS = "192.168.178.254"
FALLBACK_SUBNET_MASK = "255.255.255.0"
PHASES = frozenset(
    {"activating", "awaiting_confirmation", "confirmed", "rolling_back", "failed"}
)


class NetworkError(RuntimeError):
    """A network operation failed."""


class NetworkUnavailable(NetworkError):
    """NetworkManager, ``nmcli`` or the required permission is unavailable."""


class NetworkValidationError(NetworkError):
    """A candidate is invalid; ``field`` names the offending input."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class ApplyBusy(NetworkError):
    """Another network apply is already running."""


class PendingExists(NetworkError):
    """A change is already waiting for confirmation."""


class NoPending(NetworkError):
    """There is no open change to confirm or roll back."""


class LinkDown(NetworkError):
    """The managed interface has no carrier."""


class PendingCorrupt(NetworkError):
    """The persisted pending state cannot be read."""


# ---------------------------------------------------------------------------
# Small helpers


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def _first(text: str) -> str | None:
    for line in _lines(text):
        return line.strip()
    return None


def _split_values(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in _lines(text):
        for item in line.replace(",", " ").split():
            if item:
                values.append(item)
    return tuple(values)


def split_terse(line: str) -> list[str]:
    """Split one ``nmcli -t`` line, honouring backslash escapes."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


def mask_to_prefix(mask: str) -> int:
    """Convert a dotted IPv4 netmask to its prefix length."""
    try:
        network = ipaddress.IPv4Network(f"0.0.0.0/{mask.strip()}")
    except (ipaddress.NetmaskValueError, ValueError) as exc:
        raise NetworkValidationError("subnet_mask", "keine gültige zusammenhängende Maske") from exc
    return network.prefixlen


def prefix_to_mask(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def _parse_interface(value: str) -> tuple[str, int] | None:
    value = value.strip()
    if not value:
        return None
    try:
        interface = ipaddress.IPv4Interface(value)
    except ValueError:
        try:
            address = ipaddress.IPv4Address(value)
        except ValueError:
            return None
        return str(address), 32
    return str(interface.ip), interface.network.prefixlen


def target_url(address: str | None, port: int) -> str | None:
    if not address:
        return None
    return f"http://{address}:{port}/"


# ---------------------------------------------------------------------------
# Data model


@dataclass(frozen=True)
class InterfaceInfo:
    name: str
    type: str
    state: str
    connection: str | None = None

    @property
    def connected(self) -> bool:
        return self.state == "connected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "state": self.state,
            "connection": self.connection,
        }


@dataclass(frozen=True)
class RawIPv4:
    method: str = "auto"
    addresses: tuple[str, ...] = ()
    gateway: str = ""
    dns: tuple[str, ...] = ()
    ignore_auto_dns: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "addresses": list(self.addresses),
            "gateway": self.gateway,
            "dns": list(self.dns),
            "ignore_auto_dns": self.ignore_auto_dns,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RawIPv4":
        return cls(
            method=str(data.get("method", "auto")),
            addresses=tuple(str(item) for item in data.get("addresses", [])),
            gateway=str(data.get("gateway", "")),
            dns=tuple(str(item) for item in data.get("dns", [])),
            ignore_auto_dns=bool(data.get("ignore_auto_dns", False)),
        )


@dataclass(frozen=True)
class ProfileInfo:
    uuid: str
    name: str
    method: str
    addresses: tuple[str, ...] = ()
    gateway: str = ""
    dns: tuple[str, ...] = ()
    ignore_auto_dns: bool = False
    created: bool = False

    @property
    def mode(self) -> str:
        if self.method == "auto":
            return "dhcp"
        if self.method == "manual":
            return "static"
        return self.method

    @property
    def raw(self) -> RawIPv4:
        return RawIPv4(
            method=self.method,
            addresses=self.addresses,
            gateway=self.gateway,
            dns=self.dns,
            ignore_auto_dns=self.ignore_auto_dns,
        )


@dataclass(frozen=True)
class CurrentIPv4:
    address: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    dns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "subnet_mask": self.subnet_mask,
            "gateway": self.gateway,
            "dns": list(self.dns),
        }


@dataclass(frozen=True)
class Candidate:
    mode: str
    address: str | None = None
    subnet_mask: str | None = None
    gateway: str | None = None
    dns: tuple[str, ...] = ()

    @property
    def prefix(self) -> int:
        if not self.subnet_mask:
            raise NetworkValidationError("subnet_mask", "Subnetzmaske fehlt")
        return mask_to_prefix(self.subnet_mask)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "address": self.address,
            "subnet_mask": self.subnet_mask,
            "gateway": self.gateway,
            "dns": list(self.dns),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Candidate":
        dns = data.get("dns") or ()
        if isinstance(dns, str):
            dns = tuple(item for item in dns.replace(",", " ").split() if item)
        return cls(
            mode=str(data.get("mode", "")),
            address=str(data["address"]) if data.get("address") else None,
            subnet_mask=str(data["subnet_mask"]) if data.get("subnet_mask") else None,
            gateway=str(data["gateway"]) if data.get("gateway") else None,
            dns=tuple(str(item) for item in dns),
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Candidate":
        if not isinstance(payload, Mapping):
            raise NetworkValidationError("body", "JSON-Objekt erwartet")
        allowed = {"mode", "address", "subnet_mask", "gateway", "dns"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise NetworkValidationError("body", f"unbekannte Felder: {', '.join(unknown)}")
        mode = payload.get("mode")
        if mode not in {"dhcp", "static"}:
            raise NetworkValidationError("mode", "muss 'dhcp' oder 'static' sein")
        static_keys = ("address", "subnet_mask", "gateway", "dns")
        if mode == "dhcp":
            present = [
                key
                for key in static_keys
                if payload.get(key) not in (None, "", [])
            ]
            if present:
                raise NetworkValidationError(
                    "mode", "im DHCP-Modus sind keine statischen Felder erlaubt"
                )
            return cls(mode="dhcp")
        address = payload.get("address")
        subnet_mask = payload.get("subnet_mask")
        if not isinstance(address, str) or not address.strip():
            raise NetworkValidationError("address", "IPv4-Adresse fehlt")
        if not isinstance(subnet_mask, str) or not subnet_mask.strip():
            raise NetworkValidationError("subnet_mask", "Subnetzmaske fehlt")
        gateway = payload.get("gateway")
        if gateway is not None and not isinstance(gateway, str):
            raise NetworkValidationError("gateway", "muss eine Zeichenkette sein")
        dns = payload.get("dns")
        if dns is None:
            dns = []
        if isinstance(dns, str):
            dns = [item for item in dns.replace(",", " ").split() if item]
        if not isinstance(dns, (list, tuple)):
            raise NetworkValidationError("dns", "muss eine Liste sein")
        normalized_gateway = None
        if isinstance(gateway, str):
            normalized_gateway = gateway.strip() or None
        return cls(
            mode="static",
            address=address.strip(),
            subnet_mask=subnet_mask.strip(),
            gateway=normalized_gateway,
            dns=tuple(str(item).strip() for item in dns if str(item).strip()),
        )


@dataclass
class PendingChange:
    interface: str
    profile_uuid: str
    profile_name: str
    created_profile: bool
    previous: RawIPv4
    candidate: Candidate
    started_at: float
    phase: str = "activating"
    deadline: float | None = None
    target_url: str | None = None
    error: str | None = None
    previous_profile_uuid: str | None = None
    previous_profile_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": PENDING_VERSION,
            "interface": self.interface,
            "profile_uuid": self.profile_uuid,
            "profile_name": self.profile_name,
            "created_profile": self.created_profile,
            "previous": self.previous.to_dict(),
            "candidate": self.candidate.to_dict(),
            "started_at": self.started_at,
            "deadline": self.deadline,
            "phase": self.phase,
            "target_url": self.target_url,
            "error": self.error,
            "previous_profile_uuid": self.previous_profile_uuid,
            "previous_profile_name": self.previous_profile_name,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PendingChange":
        phase = str(data.get("phase", ""))
        if phase not in PHASES:
            raise PendingCorrupt(f"unbekannte Phase: {phase}")
        deadline = data.get("deadline")
        return cls(
            interface=str(data["interface"]),
            profile_uuid=str(data["profile_uuid"]),
            profile_name=str(data.get("profile_name", "")),
            created_profile=bool(data.get("created_profile", False)),
            previous=RawIPv4.from_dict(data["previous"]),
            candidate=Candidate.from_dict(data["candidate"]),
            started_at=float(data["started_at"]),
            phase=phase,
            deadline=float(deadline) if deadline is not None else None,
            target_url=str(data["target_url"]) if data.get("target_url") else None,
            error=str(data["error"]) if data.get("error") else None,
            previous_profile_uuid=(
                str(data["previous_profile_uuid"])
                if data.get("previous_profile_uuid")
                else None
            ),
            previous_profile_name=(
                str(data["previous_profile_name"])
                if data.get("previous_profile_name")
                else None
            ),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            **self.candidate.to_dict(),
            "phase": self.phase,
            "started_at": _iso(self.started_at),
            "deadline": _iso(self.deadline),
            "target_url": self.target_url,
            "error": self.error,
        }


@dataclass(frozen=True)
class LastResult:
    status: str
    at: float
    detail: str | None = None

    def to_api(self) -> dict[str, Any]:
        return {"status": self.status, "at": _iso(self.at), "detail": self.detail}


def fallback_candidate() -> Candidate:
    """Last-resort static address when even the previous config fails."""
    return Candidate(
        mode="static",
        address=FALLBACK_ADDRESS,
        subnet_mask=FALLBACK_SUBNET_MASK,
        gateway=None,
        dns=(),
    )


@dataclass(frozen=True)
class ValidationResult:
    candidate: Candidate
    interface: InterfaceInfo
    profile: ProfileInfo | None
    warnings: tuple[str, ...] = ()
    target_url: str | None = None


# ---------------------------------------------------------------------------
# Pending persistence


class PendingStore:
    """Atomic JSON persistence for the single open network change."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> PendingChange | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PendingCorrupt(f"Pending-Datei nicht lesbar: {exc}") from exc
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("JSON-Objekt erwartet")
            if int(data.get("version", 0)) != PENDING_VERSION:
                raise ValueError("unbekannte Schema-Version")
            return PendingChange.from_dict(data)
        except (ValueError, KeyError, TypeError) as exc:
            raise PendingCorrupt(f"Pending-Datei beschädigt: {exc}") from exc

    def save(self, pending: PendingChange) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        payload = json.dumps(pending.to_dict(), indent=2, sort_keys=True) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=".network-pending-", suffix=".tmp"
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

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()
            self._fsync_dir()

    def _fsync_dir(self) -> None:
        try:
            fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# nmcli adapter


class Runner(Protocol):
    async def run(self, *args: str, timeout: float = 10.0) -> str: ...


class SubprocessRunner:
    """Run ``nmcli`` with a fixed working environment and no shell."""

    async def run(self, *args: str, timeout: float = 10.0) -> str:
        environment = {
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "LC_ALL": "C",
            "LANG": "C",
        }
        try:
            process = await asyncio.create_subprocess_exec(
                NMCLI,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=environment,
            )
        except FileNotFoundError as exc:
            raise NetworkUnavailable("nmcli ist nicht installiert") from exc
        except OSError as exc:
            raise NetworkUnavailable(f"nmcli nicht ausführbar: {exc}") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except asyncio.TimeoutError as exc:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            with contextlib.suppress(Exception):
                await process.wait()
            raise NetworkError("nmcli-Zeitüberschreitung") from exc
        if process.returncode != 0:
            detail = stderr.decode("utf-8", "replace").strip()
            lowered = detail.lower()
            if any(
                marker in lowered
                for marker in (
                    "not authorized",
                    "not authorised",
                    "insufficient privileges",
                    "permission denied",
                    "polkit",
                )
            ):
                raise NetworkUnavailable(
                    "NetworkManager-Berechtigung fehlt; Polkit-Regel "
                    "50-ma2pi-network.rules installieren"
                )
            raise NetworkError(detail or f"nmcli endete mit Status {process.returncode}")
        return stdout.decode("utf-8", "replace")


class NetworkManagerBackend:
    """Read and write the wired IPv4 profile through ``nmcli``."""

    def __init__(self, runner: Runner | None = None, *, sleep=asyncio.sleep) -> None:
        self._runner = runner or SubprocessRunner()
        self._sleep = sleep

    async def _run(self, *args: str, timeout: float = 10.0) -> str:
        return await self._runner.run(*args, timeout=timeout)

    async def _values(self, *args: str) -> str:
        return await self._run("-g", *args)

    async def available(self) -> bool:
        try:
            await self._run("-t", "-f", "STATE", "general", timeout=5.0)
        except NetworkError:
            return False
        return True

    async def devices(self) -> list[dict[str, str]]:
        text = await self._run(
            "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"
        )
        result: list[dict[str, str]] = []
        for line in _lines(text):
            fields = split_terse(line)
            if len(fields) < 4:
                continue
            result.append(
                {
                    "device": fields[0],
                    "type": fields[1],
                    "state": fields[2],
                    "connection": fields[3],
                }
            )
        return result

    @staticmethod
    def _is_wired(device: Mapping[str, str]) -> bool:
        name = device.get("device", "")
        return (
            device.get("type") == "ethernet"
            and not name.startswith(
                ("lo", "docker", "veth", "br-", "virbr", "tun", "tap")
            )
        )

    async def _gateway(self, interface: str) -> str:
        return _first(await self._values("IP4.GATEWAY", "device", "show", interface)) or ""

    async def select_interface(self) -> InterfaceInfo | None:
        wired = [item for item in await self.devices() if self._is_wired(item)]
        if not wired:
            return None

        candidates: list[InterfaceInfo] = []
        with_gateway: list[InterfaceInfo] = []
        for item in wired:
            info = InterfaceInfo(
                name=item["device"],
                type=item["type"],
                state=item["state"],
                connection=item["connection"] or None,
            )
            candidates.append(info)
            if info.connected and await self._gateway(info.name):
                with_gateway.append(info)
        if with_gateway:
            return with_gateway[0]
        connected = [item for item in candidates if item.connected]
        return connected[0] if connected else candidates[0]

    async def _connection_rows(self, *, active: bool) -> list[list[str]]:
        args = ["-t", "-f", "NAME,UUID,TYPE,DEVICE", "connection", "show"]
        if active:
            args.append("--active")
        text = await self._run(*args)
        return [split_terse(line) for line in _lines(text)]

    async def _profile_fields(
        self, name: str, uuid: str, *, created: bool = False
    ) -> ProfileInfo:
        method = _first(
            await self._values("ipv4.method", "connection", "show", "uuid", uuid)
        ) or "auto"
        addresses = _split_values(
            await self._values("ipv4.addresses", "connection", "show", "uuid", uuid)
        )
        gateway = _first(
            await self._values("ipv4.gateway", "connection", "show", "uuid", uuid)
        ) or ""
        dns = _split_values(
            await self._values("ipv4.dns", "connection", "show", "uuid", uuid)
        )
        ignore_auto_dns = (
            _first(
                await self._values(
                    "ipv4.ignore-auto-dns", "connection", "show", "uuid", uuid
                )
            )
            == "yes"
        )
        return ProfileInfo(
            uuid=uuid,
            name=name,
            method=method,
            addresses=addresses,
            gateway=gateway,
            dns=dns,
            ignore_auto_dns=ignore_auto_dns,
            created=created,
        )

    async def profile_by_name(self, name: str) -> ProfileInfo | None:
        rows = await self._connection_rows(active=False)
        for row in rows:
            if (
                len(row) >= 4
                and row[0] == name
                and row[2] in {"802-3-ethernet", "ethernet"}
            ):
                return await self._profile_fields(row[0], row[1])
        return None

    async def read_profile(self, interface: str) -> ProfileInfo | None:
        rows = await self._connection_rows(active=True)
        chosen: list[str] | None = None
        for row in rows:
            if (
                len(row) >= 4
                and row[3] == interface
                and row[2] in {"802-3-ethernet", "ethernet"}
            ):
                chosen = row
                break
        if chosen is None:
            rows = await self._connection_rows(active=False)
            for row in rows:
                if len(row) < 4 or row[2] not in {"802-3-ethernet", "ethernet"}:
                    continue
                if row[3] == interface:
                    chosen = row
                    break
                if row[3] == "":
                    owner = _first(
                        await self._values(
                            "connection.interface-name",
                            "connection",
                            "show",
                            "uuid",
                            row[1],
                        )
                    ) or ""
                    if owner in ("", interface):
                        chosen = row
                        break
        if chosen is None:
            return None
        return await self._profile_fields(chosen[0], chosen[1])

    async def current_values(
        self, interface: str, profile: ProfileInfo | None
    ) -> CurrentIPv4:
        addresses = _split_values(
            await self._values("IP4.ADDRESS", "device", "show", interface)
        )
        gateway = _first(
            await self._values("IP4.GATEWAY", "device", "show", interface)
        )
        dns = _split_values(await self._values("IP4.DNS", "device", "show", interface))
        parsed = _parse_interface(addresses[0]) if addresses else None
        if parsed is None:
            return CurrentIPv4(gateway=gateway or None, dns=dns)
        address, prefix = parsed
        return CurrentIPv4(
            address=address,
            subnet_mask=prefix_to_mask(prefix),
            gateway=gateway or None,
            dns=dns,
        )

    async def discover(
        self, interface: str | None = None
    ) -> tuple[InterfaceInfo | None, ProfileInfo | None, CurrentIPv4]:
        info = (
            InterfaceInfo(name=interface, type="ethernet", state="unknown")
            if interface
            else await self.select_interface()
        )
        if info is None:
            return None, None, CurrentIPv4()
        profile = await self.read_profile(info.name)
        current = await self.current_values(info.name, profile)
        return info, profile, current

    async def all_addresses(self) -> dict[str, str]:
        """Map IPv4 addresses to the interface that owns them."""
        result: dict[str, str] = {}
        for device in await self.devices():
            name = device.get("device", "")
            if not name:
                continue
            for value in _split_values(
                await self._values("IP4.ADDRESS", "device", "show", name)
            ):
                parsed = _parse_interface(value)
                if parsed is not None:
                    result[parsed[0]] = name
        return result

    @staticmethod
    def _candidate_args(candidate: Candidate) -> list[str]:
        if candidate.mode == "dhcp":
            return [
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
            ]
        prefix = candidate.prefix
        return [
            "ipv4.method",
            "manual",
            "ipv4.addresses",
            f"{candidate.address}/{prefix}",
            "ipv4.gateway",
            candidate.gateway or "",
            "ipv4.dns",
            " ".join(candidate.dns),
            "ipv4.ignore-auto-dns",
            "yes",
        ]

    @staticmethod
    def _raw_args(raw: RawIPv4) -> list[str]:
        return [
            "ipv4.method",
            raw.method,
            "ipv4.addresses",
            " ".join(raw.addresses),
            "ipv4.gateway",
            raw.gateway,
            "ipv4.dns",
            " ".join(raw.dns),
            "ipv4.ignore-auto-dns",
            "yes" if raw.ignore_auto_dns else "no",
        ]

    async def create_profile(self, interface: str) -> ProfileInfo:
        name = f"ma2pi-{interface}"
        await self._run(
            "connection",
            "add",
            "type",
            "ethernet",
            "ifname",
            interface,
            "con-name",
            name,
            "autoconnect",
            "no",
            "connection.autoconnect-priority",
            "100",
            "ipv4.method",
            "auto",
        )
        profile = await self.profile_by_name(name)
        if profile is None:
            raise NetworkError("Neues Netzwerkprofil hat keine UUID")
        return ProfileInfo(
            uuid=profile.uuid,
            name=profile.name,
            method=profile.method,
            addresses=profile.addresses,
            gateway=profile.gateway,
            dns=profile.dns,
            ignore_auto_dns=profile.ignore_auto_dns,
            created=True,
        )

    async def ensure_managed_profile(self, interface: str) -> ProfileInfo:
        """Return the persistent ma2pi profile, creating it if needed.

        OS-managed profiles (netplan, distribution defaults) are never modified:
        netplan can regenerate or remove them on reload.  A dedicated profile
        with a higher autoconnect priority keeps the UI change stable.
        """
        name = f"ma2pi-{interface}"
        existing = await self.profile_by_name(name)
        if existing is not None:
            return existing
        return await self.create_profile(interface)

    async def activate_profile(self, uuid: str) -> None:
        await self._run("connection", "up", "uuid", uuid, timeout=30.0)

    async def deactivate_profile(self, uuid: str) -> None:
        try:
            await self._run("connection", "down", "uuid", uuid, timeout=15.0)
        except NetworkError:
            # Already inactive is the normal case during rollback.
            pass

    async def set_autoconnect(self, uuid: str, enabled: bool) -> None:
        await self._run(
            "connection",
            "modify",
            "uuid",
            uuid,
            "connection.autoconnect",
            "yes" if enabled else "no",
        )

    async def delete_profile(self, uuid: str) -> None:
        await self._run("connection", "delete", "uuid", uuid)

    async def stage(self, candidate: Candidate, profile: ProfileInfo) -> None:
        await self._run(
            "connection",
            "modify",
            "--temporary",
            "uuid",
            profile.uuid,
            *self._candidate_args(candidate),
        )
        await self._run("connection", "up", "uuid", profile.uuid, timeout=30.0)

    async def persist(self, candidate: Candidate, profile: ProfileInfo) -> None:
        await self._run(
            "connection",
            "modify",
            "uuid",
            profile.uuid,
            *self._candidate_args(candidate),
            "connection.autoconnect",
            "yes",
            "connection.autoconnect-priority",
            "100",
        )

    async def restore(
        self, raw: RawIPv4, profile: ProfileInfo, *, persist: bool = False
    ) -> None:
        if profile.created:
            await self._run("connection", "delete", "uuid", profile.uuid)
            return
        args = ["connection", "modify"]
        if not persist:
            args.append("--temporary")
        args.extend(["uuid", profile.uuid, *self._raw_args(raw)])
        await self._run(*args)
        await self._run("connection", "up", "uuid", profile.uuid, timeout=30.0)

    async def wait_until(
        self, candidate: Candidate, interface: str, timeout: float
    ) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            addresses = _split_values(
                await self._values("IP4.ADDRESS", "device", "show", interface)
            )
            parsed = [_parse_interface(value) for value in addresses]
            parsed = [item for item in parsed if item is not None]
            if candidate.mode == "static":
                for address, _ in parsed:
                    if address == candidate.address:
                        return address
            elif parsed:
                return parsed[0][0]
            if loop.time() >= deadline:
                raise NetworkError(
                    "Aktivierung lieferte keine passende IPv4-Adresse"
                )
            await self._sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Service and state machine


class NetworkService:
    """Own the two-phase apply and the persisted pending state."""

    def __init__(
        self,
        backend: NetworkManagerBackend,
        store: PendingStore,
        *,
        port: int = 8080,
        publish: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        confirm_timeout: float = CONFIRM_TIMEOUT,
        activation_timeout: float = ACTIVATION_TIMEOUT,
        activation_delay: float = ACTIVATION_DELAY,
    ) -> None:
        self._backend = backend
        self._store = store
        self.port = port
        self.publish = publish
        self._clock = clock or time.time
        # Use monotonic clock in production so NTP jumps cannot trigger or
        # suppress rollbacks; when tests inject ``clock`` without ``monotonic``,
        # share it so fake-clock tests stay deterministic.
        self._mono = monotonic or (clock if clock is not None else time.monotonic)
        self._sleep = sleep
        self._confirm_timeout = confirm_timeout
        self._activation_timeout = activation_timeout
        self._activation_delay = activation_delay
        self._lock = asyncio.Lock()
        self._pending: PendingChange | None = None
        self._mono_deadline: float | None = None
        self._last_result: LastResult | None = None
        self._pending_error: str | None = None
        self._timer: asyncio.Task[None] | None = None
        self._apply_task: asyncio.Task[None] | None = None
        self._apply_in_progress = False

    @property
    def pending(self) -> PendingChange | None:
        return self._pending

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def _emit(self) -> None:
        if self.publish is None:
            return
        data: dict[str, Any] = {
            "pending": self._pending.to_api() if self._pending else None,
            "last_result": self._last_result.to_api() if self._last_result else None,
        }
        self.publish({"type": "network", "data": data})

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._mono_deadline = None

    def _start_timer(self, remaining: float) -> None:
        self._cancel_timer()
        mono_deadline = self._mono() + max(0.0, remaining)
        self._mono_deadline = mono_deadline
        self._timer = asyncio.create_task(
            self._timer_loop(mono_deadline), name="ma2pi-network-rollback"
        )

    async def _timer_loop(self, mono_deadline: float) -> None:
        try:
            while True:
                remaining = mono_deadline - self._mono()
                if remaining <= 0:
                    break
                await self._sleep(remaining)
            async with self._lock:
                pending = self._pending
                if (
                    pending is not None
                    and pending.phase == "awaiting_confirmation"
                    and self._mono_deadline is not None
                    and self._mono_deadline <= self._mono()
                ):
                    await self._rollback_locked(pending, "Bestätigungsfenster abgelaufen")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Netzwerk-Rollback-Timer fehlgeschlagen: %s", exc)

    async def _read_status(
        self, *, interface: str | None = None, local_ip: str | None = None
    ) -> dict[str, Any]:
        available = await self._backend.available()
        if not available:
            return {
                "backend": "networkmanager",
                "available": False,
                "can_manage": False,
                "interface": None,
                "mode": "unknown",
                "current": CurrentIPv4().to_dict(),
                "pending": self._pending.to_api() if self._pending else None,
                "last_result": self._last_result.to_api() if self._last_result else None,
                "self_connection": False,
                "error": self._pending_error or "NetworkManager ist nicht verfügbar",
                "warnings": [],
            }
        info, profile, current = await self._backend.discover(interface)
        if info is None:
            return {
                "backend": "networkmanager",
                "available": True,
                "can_manage": False,
                "interface": None,
                "mode": "unknown",
                "current": current.to_dict(),
                "pending": self._pending.to_api() if self._pending else None,
                "last_result": self._last_result.to_api() if self._last_result else None,
                "self_connection": False,
                "error": "Keine kabelgebundene Schnittstelle gefunden",
                "warnings": [],
            }
        mode = profile.mode if profile is not None else ("dhcp" if current.address else "unknown")
        can_manage = profile is None or profile.method in {"auto", "manual"}
        self_connection = bool(local_ip and current.address == local_ip)
        return {
            "backend": "networkmanager",
            "available": True,
            "can_manage": can_manage,
            "interface": info.to_dict(),
            "mode": mode,
            "current": current.to_dict(),
            "pending": self._pending.to_api() if self._pending else None,
            "last_result": self._last_result.to_api() if self._last_result else None,
            "self_connection": self_connection,
            "error": self._pending_error,
            "warnings": [],
        }

    async def wired_ok(self) -> bool:
        """True when the managed wired interface has a usable IPv4 address."""
        try:
            status = await self._read_status()
        except NetworkError:
            return False
        interface = status.get("interface") or {}
        current = status.get("current") or {}
        return bool(
            status.get("available")
            and interface.get("state") == "connected"
            and current.get("address")
            and current.get("address") != FALLBACK_ADDRESS
            and status.get("mode") in {"dhcp", "static"}
        )

    async def status(self, *, local_ip: str | None = None) -> dict[str, Any]:
        try:
            return await self._read_status(local_ip=local_ip)
        except NetworkError as exc:
            return {
                "backend": "networkmanager",
                "available": False,
                "can_manage": False,
                "interface": None,
                "mode": "unknown",
                "current": CurrentIPv4().to_dict(),
                "pending": self._pending.to_api() if self._pending else None,
                "last_result": self._last_result.to_api() if self._last_result else None,
                "self_connection": False,
                "error": str(exc),
                "warnings": [],
            }

    async def _validate_locked(self, payload: Mapping[str, Any], *, apply: bool) -> ValidationResult:
        if self._pending is not None:
            raise PendingExists("Es wartet bereits eine Netzwerkänderung")
        candidate = Candidate.from_payload(payload)
        try:
            info, profile, current = await self._backend.discover()
        except NetworkUnavailable:
            raise
        if info is None:
            raise NetworkValidationError(
                "interface", "keine kabelgebundene Schnittstelle gefunden"
            )
        if profile is not None and profile.method not in {"auto", "manual"}:
            raise NetworkValidationError(
                "interface", f"Profilmethode '{profile.method}' wird nicht unterstützt"
            )
        warnings: list[str] = []
        if apply and not info.connected:
            raise LinkDown(f"{info.name} hat keinen Link")
        if not info.connected:
            warnings.append("Die Schnittstelle hat aktuell keinen Link.")

        if candidate.mode == "static":
            assert candidate.address is not None
            assert candidate.subnet_mask is not None
            try:
                address = ipaddress.IPv4Address(candidate.address)
            except ValueError as exc:
                raise NetworkValidationError("address", "keine gültige IPv4-Adresse") from exc
            if (
                address.is_unspecified
                or address.is_loopback
                or address.is_multicast
                or address.is_reserved
                or str(address) == "255.255.255.255"
            ):
                raise NetworkValidationError("address", "Adresse ist nicht zulässig")
            if address.is_link_local:
                warnings.append("Link-Local-Adressen sind nur für direkte Verbindungen geeignet.")
            try:
                prefix = mask_to_prefix(candidate.subnet_mask)
            except NetworkValidationError:
                raise
            if not 1 <= prefix <= 32:
                raise NetworkValidationError("subnet_mask", "Prefix muss zwischen 1 und 32 liegen")
            network = ipaddress.IPv4Network(f"{address}/{prefix}", strict=False)
            if prefix <= 30 and address in (
                network.network_address,
                network.broadcast_address,
            ):
                raise NetworkValidationError(
                    "address", "Adresse ist Netz- oder Broadcast-Adresse"
                )
            if candidate.gateway:
                try:
                    gateway = ipaddress.IPv4Address(candidate.gateway)
                except ValueError as exc:
                    raise NetworkValidationError(
                        "gateway", "keine gültige IPv4-Adresse"
                    ) from exc
                if (
                    gateway.is_unspecified
                    or gateway.is_loopback
                    or gateway.is_multicast
                    or gateway.is_reserved
                    or str(gateway) == "255.255.255.255"
                ):
                    raise NetworkValidationError(
                        "gateway", "Gateway-Adresse ist nicht zulässig"
                    )
                if gateway not in network:
                    raise NetworkValidationError(
                        "gateway", "Gateway liegt nicht im gewählten Subnetz"
                    )
                if gateway == address:
                    raise NetworkValidationError(
                        "gateway", "Gateway darf nicht die Host-Adresse sein"
                    )
                if prefix <= 30 and gateway in (
                    network.network_address,
                    network.broadcast_address,
                ):
                    raise NetworkValidationError(
                        "gateway", "Gateway ist Netz- oder Broadcast-Adresse"
                    )
                if prefix == 32:
                    raise NetworkValidationError(
                        "gateway", "Bei /32 ist kein Gateway möglich"
                    )
            else:
                warnings.append("Ohne Gateway wird keine Standardroute gesetzt.")
            if len(candidate.dns) > 3:
                raise NetworkValidationError("dns", "höchstens drei DNS-Server erlaubt")
            seen: set[str] = set()
            for value in candidate.dns:
                try:
                    resolver = ipaddress.IPv4Address(value)
                except ValueError as exc:
                    raise NetworkValidationError(
                        "dns", f"'{value}' ist keine gültige IPv4-Adresse"
                    ) from exc
                if (
                    resolver.is_multicast
                    or resolver.is_unspecified
                    or resolver.is_loopback
                    or resolver.is_reserved
                    or str(resolver) == "255.255.255.255"
                ):
                    raise NetworkValidationError("dns", "DNS-Adresse ist nicht zulässig")
                if value in seen:
                    raise NetworkValidationError("dns", "DNS-Einträge müssen eindeutig sein")
                seen.add(value)
            if not candidate.dns:
                warnings.append("Es ist kein DNS-Server konfiguriert.")
            occupied = await self._backend.all_addresses()
            owner = occupied.get(candidate.address)
            if owner is not None and owner != info.name:
                raise NetworkValidationError(
                    "address", f"Adresse ist bereits auf {owner} konfiguriert"
                )
        target = (
            target_url(candidate.address, self.port)
            if candidate.mode == "static"
            else target_url(current.address, self.port)
        )
        if candidate.mode == "dhcp" and target is None:
            warnings.append(
                "Die neue Adresse wird erst nach dem DHCP-Bezug bekannt."
            )
        return ValidationResult(
            candidate=candidate,
            interface=info,
            profile=profile,
            warnings=tuple(warnings),
            target_url=target,
        )

    async def validate(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        async with self._lock:
            result = await self._validate_locked(payload, apply=False)
        return {
            "valid": True,
            "target_url": result.target_url,
            "warnings": list(result.warnings),
        }

    async def apply(self, payload: Mapping[str, Any]) -> PendingChange:
        if self._pending is not None:
            raise PendingExists("Es wartet bereits eine Netzwerkänderung")
        if self._lock.locked() or self._apply_in_progress:
            raise ApplyBusy("Es läuft bereits ein Netzwerk-Apply")
        self._apply_in_progress = True
        try:
            async with self._lock:
                if self._pending is not None:
                    raise PendingExists("Es wartet bereits eine Netzwerkänderung")
                result = await self._validate_locked(payload, apply=True)
                active = result.profile
                target = await self._backend.ensure_managed_profile(
                    result.interface.name
                )
                same_profile = active is not None and active.uuid == target.uuid
                previous = (
                    active.raw
                    if active is not None
                    else RawIPv4()
                )
                pending = PendingChange(
                    interface=result.interface.name,
                    profile_uuid=target.uuid,
                    profile_name=target.name,
                    created_profile=target.created,
                    previous=previous,
                    candidate=result.candidate,
                    started_at=self._clock(),
                    phase="activating",
                    target_url=result.target_url,
                    previous_profile_uuid=None if same_profile else (active.uuid if active else None),
                    previous_profile_name=None if same_profile else (active.name if active else None),
                )
                try:
                    await asyncio.to_thread(self._store.save, pending)
                except OSError as exc:
                    if target.created:
                        with contextlib.suppress(Exception):
                            await self._backend.delete_profile(target.uuid)
                    raise NetworkError(f"Pending-Zustand nicht schreibbar: {exc}") from exc
                self._pending = pending
                self._pending_error = None
                LOGGER.info(
                    "Netzwerkänderung gestartet: %s %s",
                    pending.interface,
                    pending.candidate.to_dict(),
                )
                self._emit()
                self._apply_task = asyncio.create_task(
                    self._activate(pending, target), name="ma2pi-network-apply"
                )
                return pending
        finally:
            self._apply_in_progress = False

    async def _activate(self, pending: PendingChange, profile: ProfileInfo) -> None:
        await self._sleep(self._activation_delay)
        try:
            await self._backend.stage(pending.candidate, profile)
            address = await self._backend.wait_until(
                pending.candidate, pending.interface, self._activation_timeout
            )
            pending.target_url = target_url(address, self.port) or pending.target_url
        except Exception as exc:
            async with self._lock:
                if self._pending is not pending:
                    return
                await self._rollback_locked(
                    pending, f"Aktivierung fehlgeschlagen: {exc}", status="failed"
                )
            return
        async with self._lock:
            if self._pending is not pending or pending.phase != "activating":
                return
            pending.phase = "awaiting_confirmation"
            pending.deadline = self._clock() + self._confirm_timeout
            try:
                await asyncio.to_thread(self._store.save, pending)
            except OSError as exc:
                await self._rollback_locked(
                    pending, f"Pending-Zustand nicht schreibbar: {exc}"
                )
                return
            self._start_timer(self._confirm_timeout)
            LOGGER.info(
                "Netzwerkänderung aktiviert; Bestätigung bis %s",
                _iso(pending.deadline),
            )
            self._emit()

    async def confirm(self, *, local_ip: str | None = None) -> dict[str, Any]:
        async with self._lock:
            pending = self._pending
            if pending is None:
                raise NoPending("Keine offene Netzwerkänderung")
            if pending.phase != "awaiting_confirmation":
                raise PendingExists("Die Änderung ist noch nicht bestätigungsbereit")
            expired = (
                self._mono_deadline <= self._mono()
                if self._mono_deadline is not None
                else (pending.deadline is not None and pending.deadline <= self._clock())
            )
            if expired:
                await self._rollback_locked(
                    pending, "Bestätigungsfenster abgelaufen", status="failed"
                )
                raise NetworkError("Bestätigungsfenster abgelaufen")
            profile = ProfileInfo(
                uuid=pending.profile_uuid,
                name=pending.profile_name,
                method="manual" if pending.candidate.mode == "static" else "auto",
                created=pending.created_profile,
            )
            try:
                await self._backend.persist(pending.candidate, profile)
            except Exception as exc:
                await self._rollback_locked(
                    pending,
                    f"Bestätigung fehlgeschlagen: {exc}",
                    status="failed",
                    persist=True,
                )
                raise NetworkError(f"Bestätigung fehlgeschlagen: {exc}") from exc
            pending.phase = "confirmed"
            try:
                await asyncio.to_thread(self._store.save, pending)
            except OSError as exc:
                await self._rollback_locked(
                    pending,
                    f"Bestätigung nicht speicherbar: {exc}",
                    status="failed",
                    persist=True,
                )
                raise NetworkError(f"Bestätigung nicht speicherbar: {exc}") from exc
            self._cancel_timer()
            with contextlib.suppress(OSError):
                self._store.clear()
            self._pending = None
            self._last_result = LastResult("confirmed", self._clock())
            LOGGER.info("Netzwerkänderung bestätigt")
            self._emit()
        return await self.status(local_ip=local_ip)

    async def rollback(self, *, local_ip: str | None = None) -> dict[str, Any]:
        async with self._lock:
            pending = self._pending
            if pending is None:
                raise NoPending("Keine offene Netzwerkänderung")
            if pending.phase not in {"awaiting_confirmation", "failed"}:
                raise PendingExists("Die Änderung ist noch nicht bestätigungsbereit")
            await self._rollback_locked(pending, "Manueller Rollback")
        return await self.status(local_ip=local_ip)

    async def _apply_fallback_locked(
        self, pending: PendingChange, profile: ProfileInfo, detail: str
    ) -> None:
        """Apply the documented emergency address after a failed rollback."""
        candidate = fallback_candidate()
        await self._backend.stage(candidate, profile)
        temporary = False
        try:
            await self._backend.persist(candidate, profile)
        except Exception as exc:
            temporary = True
            LOGGER.error("Notfall-Adresse nur temporär aktiv: %s", exc)
        suffix = " (nur vorübergehend)" if temporary else ""
        self._cancel_timer()
        with contextlib.suppress(OSError):
            self._store.clear()
        self._pending = None
        self._last_result = LastResult(
            "fallback",
            self._clock(),
            f"{detail}; Notfall-Adresse {FALLBACK_ADDRESS}/24 aktiv{suffix}",
        )
        LOGGER.warning(
            "Notfall-Adresse %s/24 aktiv (%s)", FALLBACK_ADDRESS, detail
        )
        self._emit()

    async def _rollback_locked(
        self,
        pending: PendingChange,
        detail: str,
        *,
        status: str = "rolled_back",
        persist: bool = False,
    ) -> None:
        pending.phase = "rolling_back"
        pending.error = None
        with contextlib.suppress(OSError):
            self._store.save(pending)
        self._emit()
        target = ProfileInfo(
            uuid=pending.profile_uuid,
            name=pending.profile_name,
            method="manual" if pending.candidate.mode == "static" else "auto",
            created=pending.created_profile,
        )
        if (
            pending.previous_profile_uuid
            and pending.previous_profile_uuid != pending.profile_uuid
        ):
            try:
                await self._backend.activate_profile(pending.previous_profile_uuid)
            except Exception as exc:
                try:
                    await self._apply_fallback_locked(
                        pending, target, f"Rollback fehlgeschlagen: {exc}"
                    )
                except Exception as fallback_exc:
                    pending.phase = "failed"
                    pending.error = str(fallback_exc)
                    with contextlib.suppress(OSError):
                        self._store.save(pending)
                    self._pending = pending
                    self._last_result = LastResult(
                        "failed",
                        self._clock(),
                        f"Rollback fehlgeschlagen: {exc}; Notfall-IP fehlgeschlagen: {fallback_exc}",
                    )
                    self._emit()
                    raise NetworkError(
                        f"Rollback und Notfall-IP fehlgeschlagen: {exc}; {fallback_exc}"
                    ) from fallback_exc
                return
            try:
                await self._backend.deactivate_profile(pending.profile_uuid)
                if pending.created_profile:
                    await self._backend.delete_profile(pending.profile_uuid)
                else:
                    await self._backend.set_autoconnect(pending.profile_uuid, False)
            except Exception as exc:
                LOGGER.warning(
                    "Altes ma2pi-Profil konnte nicht entfernt werden: %s", exc
                )
            self._cancel_timer()
            with contextlib.suppress(OSError):
                self._store.clear()
            self._pending = None
            self._last_result = LastResult(status, self._clock(), detail)
            LOGGER.warning("Netzwerkänderung zurückgerollt: %s", detail)
            self._emit()
            return

        profile = ProfileInfo(
            uuid=pending.profile_uuid,
            name=pending.profile_name,
            method=pending.previous.method,
            addresses=pending.previous.addresses,
            gateway=pending.previous.gateway,
            dns=pending.previous.dns,
            ignore_auto_dns=pending.previous.ignore_auto_dns,
            created=pending.created_profile,
        )
        try:
            await self._backend.restore(pending.previous, profile, persist=persist)
        except Exception as exc:
            try:
                await self._apply_fallback_locked(
                    pending, profile, f"Rollback fehlgeschlagen: {exc}"
                )
            except Exception as fallback_exc:
                pending.phase = "failed"
                pending.error = str(fallback_exc)
                with contextlib.suppress(OSError):
                    self._store.save(pending)
                self._pending = pending
                self._last_result = LastResult(
                    "failed",
                    self._clock(),
                    f"Rollback fehlgeschlagen: {exc}; Notfall-IP fehlgeschlagen: {fallback_exc}",
                )
                self._emit()
                raise NetworkError(
                    f"Rollback und Notfall-IP fehlgeschlagen: {exc}; {fallback_exc}"
                ) from fallback_exc
            return
        self._cancel_timer()
        with contextlib.suppress(OSError):
            self._store.clear()
        self._pending = None
        self._last_result = LastResult(status, self._clock(), detail)
        LOGGER.warning("Netzwerkänderung zurückgerollt: %s", detail)
        self._emit()

    async def resume(self) -> None:
        """Recover a persisted pending change after a service start."""
        async with self._lock:
            try:
                pending = self._store.load()
            except PendingCorrupt as exc:
                self._pending_error = str(exc)
                self._last_result = LastResult("failed", self._clock(), str(exc))
                LOGGER.error("Netzwerk-Pending-Zustand beschädigt: %s", exc)
                return
            self._pending = pending
            if pending is None:
                return
            if pending.phase == "confirmed":
                with contextlib.suppress(OSError):
                    self._store.clear()
                self._pending = None
                return
            if pending.phase in {"activating", "rolling_back", "failed"}:
                try:
                    await self._rollback_locked(
                        pending, "Unterbrochene Netzwerkänderung beim Start"
                    )
                except NetworkError as exc:
                    LOGGER.error("Rollback beim Start fehlgeschlagen: %s", exc)
                return
            if pending.phase == "awaiting_confirmation":
                if pending.deadline is not None and pending.deadline <= self._clock():
                    try:
                        await self._rollback_locked(
                            pending, "Bestätigungsfenster beim Start abgelaufen"
                        )
                    except NetworkError as exc:
                        LOGGER.error("Rollback beim Start fehlgeschlagen: %s", exc)
                else:
                    remaining = (
                        min(
                            self._confirm_timeout,
                            max(0.0, pending.deadline - self._clock()),
                        )
                        if pending.deadline is not None
                        else 0.0
                    )
                    self._start_timer(remaining)
                    self._emit()

    async def close(self) -> None:
        self._cancel_timer()
        if self._apply_task is not None:
            self._apply_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._apply_task
            self._apply_task = None
