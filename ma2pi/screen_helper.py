"""UDP sender for the onPC screen-shortcut helper.

This module sends the fire-and-forget datagram ``screen <n>`` without ever
blocking the asyncio event loop on synchronous DNS resolution.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket

from .config import ScreenHelperSettings

LOGGER = logging.getLogger("ma2pi.screen_helper")


class ScreenHelper:
    """Send ``screen <n>`` datagrams to the helper on the onPC computer."""

    def __init__(self, settings: ScreenHelperSettings) -> None:
        self.settings = settings
        self._sock: socket.socket | None = None
        self._family: int | None = None
        self._resolved: tuple | None = None
        self._resolve_task: asyncio.Task[None] | None = None
        self._pending_screen: int | None = None
        self._closed = False

    def _socket(self, family: int = socket.AF_INET) -> socket.socket:
        if self._sock is not None and self._family is not None and self._family != family:
            self._sock.close()
            self._sock = None
            self._family = None
        if self._sock is None:
            self._sock = socket.socket(family, socket.SOCK_DGRAM)
            self._sock.setblocking(False)
            self._family = family
        return self._sock

    def _resolve_literal(self) -> tuple[int, tuple] | None:
        host = self.settings.host.strip().strip("[]")
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return None
        if isinstance(addr, ipaddress.IPv6Address):
            return socket.AF_INET6, (str(addr), self.settings.port, 0, 0)
        return socket.AF_INET, (str(addr), self.settings.port)

    async def _resolve_and_send(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(
                self.settings.host,
                self.settings.port,
                type=socket.SOCK_DGRAM,
            )
            if self._closed or self._pending_screen is None:
                return
            if not infos:
                raise OSError("keine Adresse aufgelöst")
            family, _, _, _, sockaddr = infos[0]
            self._resolved = (family, sockaddr)
            screen = self._pending_screen
            self._pending_screen = None
            payload = f"screen {screen}".encode("utf-8")
            self._socket(family).sendto(payload, sockaddr)
            LOGGER.info(
                "Screen-Shortcut %d an %s:%d gesendet",
                screen,
                self.settings.host,
                self.settings.port,
            )
        except asyncio.CancelledError:
            return
        except OSError as exc:
            LOGGER.error(
                "Screen-Helper %s:%d nicht erreichbar: %s",
                self.settings.host,
                self.settings.port,
                exc,
            )
        finally:
            self._resolve_task = None

    def send(self, screen: int) -> None:
        if not self.settings.enabled:
            LOGGER.warning(
                "Screen %d angefordert, aber screen_helper ist deaktiviert", screen
            )
            return
        self._closed = False
        payload = f"screen {screen}".encode("utf-8")
        target = self._resolved or self._resolve_literal()
        if target is None:
            try:
                loop = asyncio.get_running_loop()
                self._pending_screen = screen
                if self._resolve_task is None or self._resolve_task.done():
                    self._resolve_task = loop.create_task(
                        self._resolve_and_send(), name="ma2pi-screen-resolve"
                    )
                return
            except RuntimeError:
                # Synchronous fallback outside an event loop (e.g. unit tests)
                target = (socket.AF_INET, (self.settings.host, self.settings.port))
        family, sockaddr = target
        try:
            self._socket(family).sendto(payload, sockaddr)
        except OSError as exc:
            LOGGER.error(
                "Screen-Helper %s:%d nicht erreichbar: %s",
                self.settings.host,
                self.settings.port,
                exc,
            )
            return
        LOGGER.info(
            "Screen-Shortcut %d an %s:%d gesendet",
            screen,
            self.settings.host,
            self.settings.port,
        )

    def close(self) -> None:
        self._closed = True
        self._pending_screen = None
        if self._resolve_task is not None and not self._resolve_task.done():
            self._resolve_task.cancel()
        self._resolve_task = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            self._family = None
        self._resolved = None
