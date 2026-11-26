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
        self._resolving = False

    def _socket(self, family: int = socket.AF_INET) -> socket.socket:
        if self._sock is not None and self._family is not None and self._family != family:
            self.close()
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

    async def _resolve_and_send(self, payload: bytes, screen: int) -> None:
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(
                self.settings.host,
                self.settings.port,
                type=socket.SOCK_DGRAM,
            )
            if not infos:
                raise OSError("keine Adresse aufgelöst")
            family, _, _, _, sockaddr = infos[0]
            self._resolved = (family, sockaddr)
            self._socket(family).sendto(payload, sockaddr)
            LOGGER.info(
                "Screen-Shortcut %d an %s:%d gesendet",
                screen,
                self.settings.host,
                self.settings.port,
            )
        except OSError as exc:
            LOGGER.error(
                "Screen-Helper %s:%d nicht erreichbar: %s",
                self.settings.host,
                self.settings.port,
                exc,
            )
        finally:
            self._resolving = False

    def send(self, screen: int) -> None:
        if not self.settings.enabled:
            LOGGER.warning(
                "Screen %d angefordert, aber screen_helper ist deaktiviert", screen
            )
            return
        payload = f"screen {screen}".encode("utf-8")
        target = self._resolved or self._resolve_literal()
        if target is None:
            try:
                loop = asyncio.get_running_loop()
                if not self._resolving:
                    self._resolving = True
                    loop.create_task(self._resolve_and_send(payload, screen))
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
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            self._family = None
        self._resolved = None
