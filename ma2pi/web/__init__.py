"""Embedded configuration UI: HTTP server, JSON API and static SPA.

The server runs inside the daemon's asyncio loop.  It serves the built Svelte
bundle from ``web/dist`` and the JSON API under ``/api``.  No external asset is
loaded at runtime.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import hmac
import ipaddress
import logging
import math
import os
import secrets
import socket
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from aiohttp import web

from .. import __version__
from ..config import AppConfig, ConfigError
from ..config_store import BackupError, ConfigWriteError
from ..device_learn import DeviceLearnError
from ..learn import LearnBusy, LearnManager
from ..ma2_client import ConnectionClosed, HandshakeError, LoginError
from ..network import (
    ApplyBusy as NetworkApplyBusy,
    LinkDown as NetworkLinkDown,
    NetworkError,
    NetworkService,
    NetworkUnavailable,
    NetworkValidationError,
    NoPending as NetworkNoPending,
    PendingExists as NetworkPendingExists,
)
from ..power import (
    PowerDisabled,
    PowerError,
    PowerService,
    PowerUnavailable,
    ShutdownPending,
)
from ..recovery import RecoveryError, RecoveryService, RecoveryValidationError
from ..runtime import ApplyBusy, ConfigStore, StaleConfig
from .devices import detect_devices
from .events import EventBus, events_handler
from .serialize import redacted_config

LOGGER = logging.getLogger("ma2pi.web")

API_VERSION = "1"

#: Header every write request must carry.  A simple HTML form POST cannot set
#: it, so it blocks trivial CSRF attempts without being an authentication.
REQUEST_HEADER = "X-Ma2pi-Request"

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Default location of the built SPA, relative to the repository root.
DEFAULT_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def _resolve_default_dist() -> Path:
    """Locate ``web/dist`` across repo checkouts and installed wheel layouts."""

    env = os.environ.get("MA2PI_WEB_DIST")
    candidates = [
        Path(env) if env else None,
        DEFAULT_DIST,
        Path.cwd() / "web" / "dist",
        Path("/opt/ma2pi/app/web/dist"),
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "index.html").is_file():
            return candidate
    return DEFAULT_DIST


SESSION_TTL = 12 * 3600.0
MAX_FREE_FAILURES = 5
INITIAL_LOCKOUT = 15.0
MAX_LOCKOUT = 300.0


class PinSessions:
    """Server-side PIN sessions with fixed 12 h TTL and exponential lockout."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._tokens: dict[str, float] = {}
        self._failures = 0
        self._locked_until = 0.0
        self._last_lockout = 0.0

    def _prune(self, now: float) -> None:
        expired = [tok for tok, exp in self._tokens.items() if exp <= now]
        for tok in expired:
            self._tokens.pop(tok, None)

    def issue(self) -> str:
        now = self._clock()
        self._prune(now)
        token = secrets.token_urlsafe(32)
        self._tokens[token] = now + SESSION_TTL
        return token

    def valid(self, token: str | None) -> bool:
        if not token:
            return False
        now = self._clock()
        self._prune(now)
        return token in self._tokens

    def revoke(self, token: str | None) -> None:
        if token:
            self._tokens.pop(token, None)

    def clear(self) -> None:
        self._tokens.clear()
        self._failures = 0
        self._locked_until = 0.0
        self._last_lockout = 0.0

    async def authenticate(
        self, supplied: str, expected: str
    ) -> tuple[str | None, int | None]:
        """Verify ``supplied`` against ``expected`` under a single lock.

        Returns ``(token, None)`` on success, ``(None, None)`` on ordinary
        mismatch, or ``(None, retry_after_seconds)`` when locked out.
        Attempts during an active lockout do not advance the failure counter.
        """

        async with self._lock:
            now = self._clock()
            self._prune(now)
            if now < self._locked_until:
                return None, max(1, math.ceil(self._locked_until - now))

            supplied_digest = hashlib.sha256(supplied.encode("utf-8")).digest()
            expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
            if hmac.compare_digest(supplied_digest, expected_digest):
                self._failures = 0
                self._locked_until = 0.0
                self._last_lockout = 0.0
                token = secrets.token_urlsafe(32)
                self._tokens[token] = now + SESSION_TTL
                return token, None

            self._failures += 1
            if self._failures >= MAX_FREE_FAILURES:
                duration = (
                    INITIAL_LOCKOUT
                    if self._last_lockout == 0.0
                    else min(MAX_LOCKOUT, self._last_lockout * 2.0)
                )
                self._last_lockout = duration
                self._locked_until = now + duration
                return None, max(1, math.ceil(duration))
            return None, None


CONFIG_KEY: web.AppKey[AppConfig] = web.AppKey("config", AppConfig)
CONFIG_STORE_KEY: web.AppKey[ConfigStore] = web.AppKey("config_store", ConfigStore)
LEARN_KEY: web.AppKey[LearnManager] = web.AppKey("learn", LearnManager)
DEVICE_LEARN_KEY: web.AppKey[Any] = web.AppKey("device_learn", Any)
NETWORK_KEY: web.AppKey[NetworkService] = web.AppKey("network", NetworkService)
RECOVERY_KEY: web.AppKey[RecoveryService] = web.AppKey("recovery", RecoveryService)
POWER_KEY: web.AppKey[PowerService] = web.AppKey("power", PowerService)
DIST_KEY: web.AppKey[Path] = web.AppKey("dist_dir", Path)
BUS_KEY: web.AppKey[EventBus] = web.AppKey("bus", EventBus)
PIN_SESSIONS_KEY: web.AppKey[PinSessions] = web.AppKey("pin_sessions", PinSessions)

PIN_COOKIE = "ma2pi_pin"
PUBLIC_API_PATHS = frozenset(
    {"/api/health", "/api/version", "/api/auth/status", "/api/auth/login"}
)


def _current_config(app: web.Application) -> AppConfig:
    store = app.get(CONFIG_STORE_KEY)
    return store.config if store is not None else app[CONFIG_KEY]


def _extract_host(raw_host: str) -> str:
    value = raw_host.strip()
    if not value:
        return ""
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end > 0 else value
    if ":" in value:
        host_part, _, _ = value.rpartition(":")
        return host_part
    return value


def _is_allowed_host(raw_host: str) -> bool:
    host = _extract_host(raw_host).rstrip(".").lower()
    if not host or host in {"localhost", "testserver"}:
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host.endswith(".local"):
        return True
    try:
        local_name = socket.gethostname().rstrip(".").lower()
    except Exception:
        local_name = ""
    if local_name:
        short_name = local_name.split(".", 1)[0]
        if host in {local_name, short_name}:
            return True
    return False


def _origin_matches_host(origin: str, request_host: str) -> bool:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    origin_netloc = parsed.netloc.lower()
    req_netloc = request_host.strip().lower()
    if origin_netloc == req_netloc:
        return True
    # Allow default-port omission (e.g. Origin http://10.0.0.1 vs Host 10.0.0.1:80).
    default_port = 80 if parsed.scheme == "http" else 443
    if parsed.port is None and f"{origin_netloc}:{default_port}" == req_netloc:
        return True
    return False


@web.middleware
async def host_origin_guard(
    request: web.Request, handler: Callable[[web.Request], Any]
) -> web.StreamResponse:
    """Reject external DNS-rebinding Host headers and foreign Origins."""

    raw_host = request.headers.get("Host", "")
    if raw_host and not _is_allowed_host(raw_host):
        return _json_error(403, "forbidden_host", "Unzulässiger Host-Header")
    origin = request.headers.get("Origin")
    if origin and (
        request.method in WRITE_METHODS or request.path == "/api/events"
    ):
        if not _origin_matches_host(origin, raw_host or request.host):
            return _json_error(403, "forbidden_origin", "Unzulässiger Origin-Header")
    return await handler(request)


@web.middleware
async def pin_guard(
    request: web.Request, handler: Callable[[web.Request], Any]
) -> web.StreamResponse:
    """Require a PIN session for every non-public API path when enabled."""

    config = _current_config(request.app)
    if not config.web.pin_enabled:
        return await handler(request)
    if not request.path.startswith("/api/") or request.path in PUBLIC_API_PATHS:
        return await handler(request)
    token = request.cookies.get(PIN_COOKIE)
    if request.app[PIN_SESSIONS_KEY].valid(token):
        return await handler(request)
    return _json_error(401, "pin_required", "PIN erforderlich")


def learn_event(result) -> dict[str, Any]:
    """Convert a learn result into the WebSocket event payload."""

    from dataclasses import asdict

    return {"type": "learn", "data": asdict(result)}


def _etag(generation: int) -> str:
    return f'"{generation}"'


def _parse_etag(value: str) -> int | None:
    """Parse an ``If-Match`` value such as ``"3"`` into a generation."""

    text = value.strip()
    if text.startswith("W/"):
        text = text[2:]
    text = text.strip('"')
    return int(text) if text.isdigit() else None


def _json_error(status: int, error: str, detail: str = "") -> web.Response:
    payload: dict[str, Any] = {"error": error}
    if detail:
        payload["detail"] = detail
    return web.json_response(payload, status=status)


def _network_error(exc: BaseException) -> web.Response:
    """Map network failures to the documented API errors."""
    if isinstance(exc, NetworkValidationError):
        return web.json_response(
            {
                "error": "validation_error",
                "field": exc.field,
                "detail": exc.message,
            },
            status=422,
        )
    if isinstance(exc, NetworkUnavailable):
        return _json_error(503, "network_unavailable", str(exc))
    if isinstance(exc, NetworkApplyBusy):
        return _json_error(409, "apply_busy", str(exc))
    if isinstance(exc, NetworkPendingExists):
        return _json_error(409, "pending_exists", str(exc))
    if isinstance(exc, NetworkNoPending):
        return _json_error(409, "no_pending", str(exc))
    if isinstance(exc, NetworkLinkDown):
        return _json_error(409, "link_down", str(exc))
    if isinstance(exc, (ValueError, TypeError)):
        return _json_error(422, "invalid_request", str(exc))
    if isinstance(exc, NetworkError):
        return _json_error(500, "apply_failed", str(exc))
    return _json_error(500, "apply_failed", str(exc))


def _local_ip(request: web.Request) -> str | None:
    transport = request.transport
    if transport is None:
        return None
    sockname = transport.get_extra_info("sockname")
    if isinstance(sockname, tuple) and sockname:
        return str(sockname[0])
    return None


def _apply_error(exc: BaseException) -> web.Response:
    """Map configuration/connection failures to JSON without leaking secrets."""

    if isinstance(exc, ConfigError):
        payload: dict[str, Any] = {"error": "validation_error", "detail": str(exc)}
        if exc.path:
            payload["field"] = exc.path
        return web.json_response(payload, status=422)
    if isinstance(exc, (LoginError, HandshakeError, ConnectionClosed, asyncio.TimeoutError)):
        return _json_error(422, "connection_failed", str(exc))
    if isinstance(exc, OSError):
        return _json_error(502, "unreachable", str(exc))
    if isinstance(exc, (ValueError, TypeError)):
        return _json_error(422, "invalid_request", str(exc))
    return _json_error(500, "config_failed", str(exc))


async def _json_body(request: web.Request) -> dict[str, Any] | None:
    try:
        value = await request.json()
    except Exception:
        return None
    return value if isinstance(value, dict) else None


@web.middleware
async def request_guard(
    request: web.Request, handler: Callable[[web.Request], Any]
) -> web.StreamResponse:
    """Enforce JSON writes and the custom request header.

    The guard only applies to ``/api`` write endpoints.  Reads stay open, as
    documented in ADR-0013 (LAN access model without login).
    """
    if request.method in WRITE_METHODS and request.path.startswith("/api/"):
        content_type = request.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            return _json_error(415, "unsupported_media_type", "JSON erwartet")
        if request.headers.get(REQUEST_HEADER) != "1":
            return _json_error(403, "missing_request_header", f"{REQUEST_HEADER}: 1 fehlt")
    return await handler(request)


@web.middleware
async def no_cors(
    request: web.Request, handler: Callable[[web.Request], Any]
) -> web.StreamResponse:
    """Serve same-origin only; never advertise CORS headers."""
    response = await handler(request)
    response.headers.pop("Access-Control-Allow-Origin", None)
    return response


def _ui_build(dist: Path) -> str:
    """Return a build stamp derived from the bundle, or ``"missing"``."""
    index = dist / "index.html"
    try:
        stat = index.stat()
    except OSError:
        return "missing"
    return f"{int(stat.st_mtime)}-{stat.st_size}"


def create_app(
    config: AppConfig,
    *,
    dist_dir: Path | str | None = None,
    status_provider: Callable[[], dict[str, Any]] | None = None,
    config_store: ConfigStore | None = None,
    devices_provider: Callable[[], list[dict[str, Any]]] | None = None,
    learn_manager: LearnManager | None = None,
    device_learn_manager: Any | None = None,
    network_service: NetworkService | None = None,
    recovery_service: RecoveryService | None = None,
    power_service: PowerService | None = None,
    pin_clock: Callable[[], float] = time.monotonic,
    event_queue_size: int | None = None,
) -> web.Application:
    """Build the aiohttp application for the configuration UI."""
    dist = Path(dist_dir) if dist_dir is not None else _resolve_default_dist()

    app = web.Application(
        middlewares=[no_cors, host_origin_guard, pin_guard, request_guard]
    )
    bus = EventBus(queue_size=event_queue_size) if event_queue_size else EventBus()
    app[CONFIG_KEY] = config
    app[DIST_KEY] = dist
    app[BUS_KEY] = bus
    app[PIN_SESSIONS_KEY] = PinSessions(clock=pin_clock)
    if config_store is not None:
        app[CONFIG_STORE_KEY] = config_store
    if learn_manager is not None:
        app[LEARN_KEY] = learn_manager
    if device_learn_manager is not None:
        app[DEVICE_LEARN_KEY] = device_learn_manager
    if network_service is not None:
        app[NETWORK_KEY] = network_service
        if network_service.publish is None:
            network_service.publish = bus.publish
    if recovery_service is not None:
        app[RECOVERY_KEY] = recovery_service
        if recovery_service.publish is None:
            recovery_service.publish = bus.publish
    if power_service is not None:
        app[POWER_KEY] = power_service

    async def auth_status(request: web.Request) -> web.Response:
        current = _current_config(request.app)
        token = request.cookies.get(PIN_COOKIE)
        authenticated = (
            not current.web.pin_enabled
            or request.app[PIN_SESSIONS_KEY].valid(token)
        )
        return web.json_response(
            {
                "pin_enabled": current.web.pin_enabled,
                "pin_set": bool(current.web.pin),
                "authenticated": authenticated,
            }
        )

    async def auth_login(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        current = _current_config(request.app)
        if not current.web.pin_enabled:
            return web.json_response({"ok": True})
        raw_pin = body.get("pin", "")
        if not isinstance(raw_pin, (str, int)) or isinstance(raw_pin, bool):
            return _json_error(400, "invalid_json", "PIN muss eine Zeichenkette sein")
        supplied = str(raw_pin)
        token, retry_after = await request.app[PIN_SESSIONS_KEY].authenticate(
            supplied, current.web.pin
        )
        if retry_after is not None:
            return web.json_response(
                {
                    "error": "pin_locked",
                    "detail": f"Zu viele Fehlversuche – bitte {retry_after} s warten",
                    "retry_after": retry_after,
                },
                status=429,
                headers={"Retry-After": str(retry_after)},
            )
        if token is None:
            await asyncio.sleep(0.05)
            return _json_error(401, "pin_invalid", "PIN falsch")
        response = web.json_response({"ok": True})
        response.set_cookie(
            PIN_COOKIE,
            token,
            httponly=True,
            samesite="Strict",
            path="/",
            max_age=int(SESSION_TTL),
        )
        return response

    async def auth_logout(request: web.Request) -> web.Response:
        token = request.cookies.get(PIN_COOKIE)
        request.app[PIN_SESSIONS_KEY].revoke(token)
        if _current_config(request.app).web.pin_enabled:
            bus.close_all()
        response = web.json_response({"ok": True})
        response.del_cookie(PIN_COOKIE, path="/")
        return response

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def version(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "api": API_VERSION,
                "package": __version__,
                "ui": _ui_build(dist),
            }
        )

    async def status(_: web.Request) -> web.Response:
        if status_provider is None:
            return web.json_response({"api": API_VERSION, "runtime": "unavailable"})
        return web.json_response(status_provider())

    async def events(request: web.Request) -> web.WebSocketResponse:
        initial = {"type": "status", "data": status_provider() if status_provider else None}
        return await events_handler(request, bus, initial=initial)

    async def get_config(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        response = web.json_response(redacted_config(store.config))
        response.headers["ETag"] = _etag(store.generation)
        return response

    def _sanitize_web_config_patch(body: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(body)
        ma2 = cleaned.get("ma2")
        if isinstance(ma2, dict):
            ma2 = dict(ma2)
            ma2.pop("password_file", None)
            ma2.pop("password_env", None)
            cleaned["ma2"] = ma2
        return cleaned

    async def put_config(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        ma2 = body.get("ma2")
        password = ma2.get("password") if isinstance(ma2, dict) else None
        if password is not None and not isinstance(password, str):
            return _json_error(422, "invalid_request", "password muss eine Zeichenkette sein")
        prev_pin = (store.config.web.pin_enabled, store.config.web.pin)
        sanitized = _sanitize_web_config_patch(body)
        apply_kwargs: dict[str, Any] = {"password": password}
        if_match = request.headers.get("If-Match")
        if if_match is not None:
            expected = _parse_etag(if_match)
            if expected is None:
                return _json_error(400, "invalid_if_match", "If-Match muss eine Generation sein")
            apply_kwargs["expected_generation"] = expected
        try:
            config = await store.apply(sanitized, **apply_kwargs)
        except ApplyBusy as exc:
            return _json_error(409, "apply_busy", str(exc))
        except StaleConfig as exc:
            return web.json_response(
                {
                    "error": "stale_config",
                    "detail": str(exc),
                    "generation": exc.current,
                },
                status=412,
            )
        except Exception as exc:
            return _apply_error(exc)
        bus.publish(
            {"type": "config", "data": {"generation": store.generation}}
        )
        response = web.json_response(
            {"generation": store.generation, "config": redacted_config(config)}
        )
        response.headers["ETag"] = _etag(store.generation)
        if (config.web.pin_enabled, config.web.pin) != prev_pin:
            sessions = request.app[PIN_SESSIONS_KEY]
            sessions.clear()
            bus.close_all()
            if config.web.pin_enabled:
                token = sessions.issue()
                response.set_cookie(
                    PIN_COOKIE,
                    token,
                    httponly=True,
                    samesite="Strict",
                    path="/",
                    max_age=int(SESSION_TTL),
                )
        return response

    async def validate_config(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        ma2 = body.get("ma2")
        password = ma2.get("password") if isinstance(ma2, dict) else None
        try:
            store.validate(_sanitize_web_config_patch(body), password=password)
        except Exception as exc:
            return _apply_error(exc)
        return web.json_response({"valid": True})

    async def test_connection(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        try:
            check = await store.test_connection(body)
        except Exception as exc:
            return _apply_error(exc)
        return web.json_response(dataclasses.asdict(check))

    async def devices(request: web.Request) -> web.Response:
        if devices_provider is not None:
            return web.json_response({"devices": devices_provider()})
        config = _current_config(request.app)
        summary = await asyncio.to_thread(detect_devices, config)
        return web.json_response({"devices": summary})

    async def learn_start(request: web.Request) -> web.Response:
        learn = request.app.get(LEARN_KEY)
        if learn is None:
            return _json_error(503, "learn_unavailable", "Learn-Modus nicht aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        try:
            result = learn.start(body.get("kind"), device=body.get("device"))
        except LearnBusy as exc:
            return _json_error(409, "learn_busy", str(exc))
        except (ValueError, TypeError) as exc:
            return _json_error(422, "invalid_learn_request", str(exc))
        event = learn_event(result)
        bus.publish(event)
        return web.json_response(event["data"])

    async def learn_cancel(request: web.Request) -> web.Response:
        learn = request.app.get(LEARN_KEY)
        if learn is None:
            return _json_error(503, "learn_unavailable", "Learn-Modus nicht aktiv")
        result = learn.cancel()
        if result is not None:
            bus.publish(learn_event(result))
        return web.json_response(
            {
                "cancelled": result is not None,
                "learn": learn_event(result)["data"] if result is not None else None,
            }
        )

    async def device_learn_state(request: web.Request) -> web.Response:
        manager = request.app.get(DEVICE_LEARN_KEY)
        if manager is None:
            return _json_error(503, "device_learn_unavailable", "Learn-Modus nicht aktiv")
        try:
            return web.json_response(manager.status())
        except DeviceLearnError:
            return web.json_response({"active": False})

    async def device_learn_start(request: web.Request) -> web.Response:
        manager = request.app.get(DEVICE_LEARN_KEY)
        if manager is None:
            return _json_error(503, "device_learn_unavailable", "Learn-Modus nicht aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Körper erwartet")
        try:
            bank = int(body.get("bank"))
            control = body.get("control")
            result = manager.start(
                str(body.get("device")),
                bank,
                str(control) if control is not None else None,
            )
        except DeviceLearnError as exc:
            message = str(exc)
            status = 409 if "bereits" in message else 422
            return _json_error(status, "device_learn_failed", message)
        except (TypeError, ValueError):
            return _json_error(422, "invalid_learn_request", "bank muss eine Zahl sein")
        bus.publish({"type": "device_learn", "data": result})
        return web.json_response(result)

    async def device_learn_skip(request: web.Request) -> web.Response:
        manager = request.app.get(DEVICE_LEARN_KEY)
        if manager is None:
            return _json_error(503, "device_learn_unavailable", "Learn-Modus nicht aktiv")
        try:
            result = manager.skip()
        except DeviceLearnError as exc:
            return _json_error(409, "device_learn_inactive", str(exc))
        bus.publish({"type": "device_learn", "data": result})
        return web.json_response(result)

    async def device_learn_cancel(request: web.Request) -> web.Response:
        manager = request.app.get(DEVICE_LEARN_KEY)
        if manager is None:
            return _json_error(503, "device_learn_unavailable", "Learn-Modus nicht aktiv")
        result = manager.cancel()
        if result is not None:
            bus.publish({"type": "device_learn", "data": {"active": False, "cancelled": True}})
        return web.json_response({"cancelled": result is not None, "learn": result})

    device_learn_lock = asyncio.Lock()

    async def device_learn_finish(request: web.Request) -> web.Response:
        manager = request.app.get(DEVICE_LEARN_KEY)
        if manager is None:
            return _json_error(503, "device_learn_unavailable", "Learn-Modus nicht aktiv")
        async with device_learn_lock:
            try:
                device, bank, captured = manager.peek()
            except DeviceLearnError as exc:
                return _json_error(409, "device_learn_inactive", str(exc))
            if not captured:
                manager.clear()
                bus.publish({"type": "device_learn", "data": {"active": False}})
                return web.json_response({"saved": False, "device": device, "bank": bank})
            store = request.app.get(CONFIG_STORE_KEY)
            if store is None:
                return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
            config = store.config
            try:
                profile_name = config.devices[device].profile
                profile = config.profiles[profile_name]
            except KeyError:
                manager.clear()
                return _json_error(
                    409, "device_learn_stale", f"Gerät {device!r} ist nicht mehr konfiguriert"
                )
            bank_profile = profile.bank(bank)
            if bank_profile is not None:
                for note, control in captured.items():
                    for entry in profile.banks:
                        if entry.channel != bank_profile.channel:
                            continue
                        existing = entry.notes.get(note)
                        if existing is not None and existing != control:
                            return _json_error(
                                409,
                                "device_learn_conflict",
                                f"Note {note} ist inzwischen {existing} zugeordnet",
                            )
            banks = []
            for entry in profile.banks:
                notes = {str(note): control for note, control in entry.notes.items()}
                if entry.number == bank:
                    relearned = set(captured.values())
                    notes = {
                        note: control
                        for note, control in notes.items()
                        if control not in relearned
                    }
                    notes.update({str(note): control for note, control in captured.items()})
                banks.append({"number": entry.number, "channel": entry.channel, "notes": notes})
            patch = {"profiles": {profile_name: {"banks": banks}}}
            try:
                updated = await store.apply(patch)
            except ApplyBusy as exc:
                return _json_error(409, "apply_busy", str(exc))
            except Exception as exc:
                return _apply_error(exc)
            manager.set_config(updated)
            manager.clear()
            bus.publish({"type": "device_learn", "data": {"active": False, "saved": True}})
            bus.publish({"type": "config", "data": {"generation": store.generation}})
            return web.json_response(
                {
                    "saved": True,
                    "device": device,
                    "bank": bank,
                    "generation": store.generation,
                    "notes": [
                        {"note": note, "control": control}
                        for note, control in sorted(captured.items())
                    ],
                }
            )

    async def backups(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        return web.json_response({"backups": store.backups()})

    async def create_backup(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        try:
            entry = store.create_backup()
        except (ConfigWriteError, OSError) as exc:
            return _json_error(500, "backup_failed", str(exc))
        bus.publish({"type": "backup", "data": entry})
        return web.json_response(entry, status=201)

    async def restore_backup(request: web.Request) -> web.Response:
        store = request.app.get(CONFIG_STORE_KEY)
        if store is None:
            return _json_error(503, "config_store_unavailable", "Kein Config-Store aktiv")
        backup_id = request.match_info["backup_id"]
        old_pin = (store.config.web.pin_enabled, store.config.web.pin)
        try:
            restored = await store.restore(backup_id)
        except ApplyBusy as exc:
            return _json_error(409, "apply_busy", str(exc))
        except (BackupError, ConfigError) as exc:
            return _json_error(422, "invalid_backup", str(exc))
        except (ConfigWriteError, OSError) as exc:
            return _json_error(500, "restore_failed", str(exc))
        if (restored.web.pin_enabled, restored.web.pin) != old_pin:
            request.app[PIN_SESSIONS_KEY].clear()
            bus.close_all()
        bus.publish(
            {
                "type": "backup_restored",
                "data": {"id": backup_id, "generation": store.generation},
            }
        )
        return web.json_response(
            {
                "ok": True,
                "id": backup_id,
                "generation": store.generation,
                "ma2": {
                    "host": restored.ma2.host,
                    "port": restored.ma2.port,
                    "path": restored.ma2.path,
                    "username": restored.ma2.username,
                },
            }
        )

    async def get_network(request: web.Request) -> web.Response:
        service = request.app.get(NETWORK_KEY)
        if service is None:
            return _json_error(503, "network_unavailable", "Netzwerkverwaltung nicht aktiv")
        return web.json_response(await service.status(local_ip=_local_ip(request)))

    async def validate_network(request: web.Request) -> web.Response:
        service = request.app.get(NETWORK_KEY)
        if service is None:
            return _json_error(503, "network_unavailable", "Netzwerkverwaltung nicht aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        try:
            return web.json_response(await service.validate(body))
        except Exception as exc:
            return _network_error(exc)

    async def apply_network(request: web.Request) -> web.Response:
        service = request.app.get(NETWORK_KEY)
        if service is None:
            return _json_error(503, "network_unavailable", "Netzwerkverwaltung nicht aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        try:
            pending = await service.apply(body)
        except Exception as exc:
            return _network_error(exc)
        return web.json_response(
            {"pending": pending.to_api(), "target_url": pending.target_url}, status=202
        )

    async def confirm_network(request: web.Request) -> web.Response:
        service = request.app.get(NETWORK_KEY)
        if service is None:
            return _json_error(503, "network_unavailable", "Netzwerkverwaltung nicht aktiv")
        try:
            return web.json_response(await service.confirm(local_ip=_local_ip(request)))
        except Exception as exc:
            return _network_error(exc)

    async def rollback_network(request: web.Request) -> web.Response:
        service = request.app.get(NETWORK_KEY)
        if service is None:
            return _json_error(503, "network_unavailable", "Netzwerkverwaltung nicht aktiv")
        try:
            return web.json_response(await service.rollback(local_ip=_local_ip(request)))
        except Exception as exc:
            return _network_error(exc)

    async def get_recovery(request: web.Request) -> web.Response:
        service = request.app.get(RECOVERY_KEY)
        if service is None:
            return _json_error(503, "recovery_unavailable", "Rettungs-WLAN nicht aktiv")
        return web.json_response(await service.status())

    async def put_recovery(request: web.Request) -> web.Response:
        service = request.app.get(RECOVERY_KEY)
        if service is None:
            return _json_error(503, "recovery_unavailable", "Rettungs-WLAN nicht aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        try:
            return web.json_response(await service.save(body))
        except RecoveryValidationError as exc:
            return web.json_response(
                {"error": "validation_error", "field": exc.field, "detail": exc.message},
                status=422,
            )
        except Exception as exc:
            return _json_error(500, "recovery_failed", str(exc))

    async def get_power(request: web.Request) -> web.Response:
        service = request.app.get(POWER_KEY)
        if service is None:
            return _json_error(503, "power_unavailable", "Ausschalten nicht aktiv")
        return web.json_response(service.status())

    async def power_shutdown(request: web.Request) -> web.Response:
        service = request.app.get(POWER_KEY)
        if service is None:
            return _json_error(503, "power_unavailable", "Ausschalten nicht aktiv")
        body = await _json_body(request)
        if body is None:
            return _json_error(400, "invalid_json", "JSON-Objekt erwartet")
        if body.get("confirm") is not True:
            return _json_error(
                422, "confirmation_required", "confirm: true erforderlich"
            )
        try:
            await service.shutdown("Web-Oberfläche")
        except PowerDisabled as exc:
            return _json_error(403, "power_disabled", str(exc))
        except PowerUnavailable as exc:
            return _json_error(503, "power_unavailable", str(exc))
        except ShutdownPending as exc:
            return _json_error(409, "shutdown_pending", str(exc))
        except PowerError as exc:
            return _json_error(500, "shutdown_failed", str(exc))
        return web.json_response(service.status(), status=202)

    app.router.add_get("/api/health", health)
    app.router.add_get("/api/version", version)
    app.router.add_get("/api/auth/status", auth_status)
    app.router.add_post("/api/auth/login", auth_login)
    app.router.add_post("/api/auth/logout", auth_logout)
    app.router.add_get("/api/status", status)
    app.router.add_get("/api/events", events)
    app.router.add_get("/api/config", get_config)
    app.router.add_put("/api/config", put_config)
    app.router.add_post("/api/config/validate", validate_config)
    app.router.add_post("/api/test-connection", test_connection)
    app.router.add_get("/api/devices", devices)
    app.router.add_post("/api/learn/start", learn_start)
    app.router.add_post("/api/learn/cancel", learn_cancel)
    app.router.add_get("/api/device-learn", device_learn_state)
    app.router.add_post("/api/device-learn/start", device_learn_start)
    app.router.add_post("/api/device-learn/skip", device_learn_skip)
    app.router.add_post("/api/device-learn/cancel", device_learn_cancel)
    app.router.add_post("/api/device-learn/finish", device_learn_finish)
    app.router.add_get("/api/backups", backups)
    app.router.add_post("/api/backups", create_backup)
    app.router.add_post("/api/backups/{backup_id}/restore", restore_backup)
    app.router.add_get("/api/network", get_network)
    app.router.add_post("/api/network/validate", validate_network)
    app.router.add_put("/api/network", apply_network)
    app.router.add_post("/api/network/confirm", confirm_network)
    app.router.add_post("/api/network/rollback", rollback_network)
    app.router.add_get("/api/recovery", get_recovery)
    app.router.add_put("/api/recovery", put_recovery)
    app.router.add_get("/api/power", get_power)
    app.router.add_post("/api/power/shutdown", power_shutdown)

    _mount_static(app, dist)
    return app


def _mount_static(app: web.Application, dist: Path) -> None:
    """Serve the SPA, falling back to ``index.html`` for client-side routes."""
    index = dist / "index.html"
    root = dist.resolve()

    async def spa(request: web.Request) -> web.StreamResponse:
        if not index.is_file():
            return _json_error(
                503,
                "ui_not_built",
                "web/dist fehlt; 'npm ci && npm run build' im Ordner web/ ausführen",
            )
        requested = (root / request.path.lstrip("/")).resolve()
        if requested.is_file() and requested.is_relative_to(root):
            return web.FileResponse(requested)
        return web.FileResponse(index)

    assets = dist / "assets"
    if assets.is_dir():
        app.router.add_static("/assets/", assets, name="assets")

    app.router.add_get("/", spa)
    app.router.add_get("/{tail:.*}", spa)
