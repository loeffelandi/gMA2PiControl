"""UDP sender for the onPC screen-shortcut helper.

The grandMA2 onPC has no Web Remote request and no canbus hardkey for its
screen buttons; they are reached with PC keyboard shortcuts (Insert toggles
the shortcut mode, then ``Ctrl+Alt+F1..F6`` selects a screen).  A small helper
on the onPC computer listens for UDP packets and injects those keystrokes.

This module only sends the fire-and-forget datagram ``screen <n>``; it is
independent of the MA2 WebSocket session.
"""

from __future__ import annotations

import logging
import socket

from .config import ScreenHelperSettings

LOGGER = logging.getLogger("ma2pi.screen_helper")


class ScreenHelper:
    """Send ``screen <n>`` datagrams to the helper on the onPC computer."""

    def __init__(self, settings: ScreenHelperSettings) -> None:
        self.settings = settings
        self._sock: socket.socket | None = None

    def _socket(self) -> socket.socket:
        if self._sock is None:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return self._sock

    def send(self, screen: int) -> None:
        if not self.settings.enabled:
            LOGGER.warning(
                "Screen %d angefordert, aber screen_helper ist deaktiviert", screen
            )
            return
        payload = f"screen {screen}".encode("utf-8")
        try:
            self._socket().sendto(payload, (self.settings.host, self.settings.port))
        except OSError as exc:
            LOGGER.error("Screen-Helper %s:%d nicht erreichbar: %s",
                         self.settings.host, self.settings.port, exc)
            return
        LOGGER.info("Screen-Shortcut %d an %s:%d gesendet",
                    screen, self.settings.host, self.settings.port)

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None