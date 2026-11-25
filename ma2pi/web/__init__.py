"""Embedded configuration UI: HTTP server, JSON API and static SPA.

The server runs inside the daemon's asyncio loop.  It serves the built Svelte
bundle from ``web/dist`` and the JSON API under ``/api``.  No external asset is
loaded at runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from .. import __version__
from ..config import AppConfig

LOGGER = logging.getLogger("ma2pi.web")

API_VERSION = "1"

#: Header every write request must carry.  A simple HTML form POST cannot set
#: it, so it blocks trivial CSRF attempts without being an authentication.
REQUEST_HEADER = "X-Ma2pi-Request"

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Default location of the built SPA, relative to the repository root.
DEFAULT_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

CONFIG_KEY: web.AppKey[AppConfig] = web.AppKey("config", AppConfig)
DIST_KEY: web.AppKey[Path] = web.AppKey("dist_dir", Path)


def _json_error(status: int, error: str, detail: str = "") -> web.Response:
    payload: dict[str, Any] = {"error": error}
    if detail:
        payload["detail"] = detail
    return web.json_response(payload, status=status)


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
) -> web.Application:
    """Build the aiohttp application for the configuration UI."""
    dist = Path(dist_dir) if dist_dir is not None else DEFAULT_DIST

    app = web.Application(middlewares=[no_cors, request_guard])
    app[CONFIG_KEY] = config
    app[DIST_KEY] = dist

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

    app.router.add_get("/api/health", health)
    app.router.add_get("/api/version", version)
    app.router.add_get("/api/status", status)

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
