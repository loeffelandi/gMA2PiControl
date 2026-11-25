from __future__ import annotations

import logging

import pytest

from ma2pi.config import ScreenHelperSettings
from ma2pi.screen_helper import ScreenHelper


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, payload: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((payload, addr))

    def close(self) -> None:
        self.closed = True


def test_disabled_sends_nothing(caplog):
    helper = ScreenHelper(ScreenHelperSettings(enabled=False))
    fake = FakeSocket()
    helper._sock = fake
    with caplog.at_level(logging.WARNING, logger="ma2pi.screen_helper"):
        helper.send(2)
    assert fake.sent == []
    assert "deaktiviert" in caplog.text


def test_enabled_sends_datagram():
    helper = ScreenHelper(
        ScreenHelperSettings(enabled=True, host="192.168.178.72", port=5005)
    )
    fake = FakeSocket()
    helper._sock = fake
    helper.send(3)
    assert fake.sent == [(b"screen 3", ("192.168.178.72", 5005))]


def test_send_error_is_logged_not_raised(caplog):
    helper = ScreenHelper(ScreenHelperSettings(enabled=True))

    class BrokenSocket(FakeSocket):
        def sendto(self, payload, addr):
            raise OSError("network down")

    helper._sock = BrokenSocket()
    with caplog.at_level(logging.ERROR, logger="ma2pi.screen_helper"):
        helper.send(1)
    assert "nicht erreichbar" in caplog.text


def test_close_releases_socket():
    helper = ScreenHelper(ScreenHelperSettings(enabled=True))
    fake = FakeSocket()
    helper._sock = fake
    helper.close()
    assert fake.closed
    assert helper._sock is None


def test_client_screen_shortcut_dry_run_logs(small_config, caplog):
    from ma2pi.ma2_client import Ma2Client

    client = Ma2Client(small_config, dry_run=True)
    with caplog.at_level(logging.INFO, logger="ma2pi.client"):
        client.screen_shortcut(4)
    assert "Screen-Shortcut 4" in caplog.text