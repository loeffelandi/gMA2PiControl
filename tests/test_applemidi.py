from __future__ import annotations

import asyncio
import socket
import struct

import pytest

from ma2pi import applemidi
from ma2pi.applemidi import AppleMidiSession, rtp_midi_packet


class FakeResponder:
    """rtpMIDI stand-in on two consecutive localhost UDP ports."""

    def __init__(self, mode: str = "accept") -> None:
        self.mode = mode
        self.invites: list[str] = []
        self.byes = 0
        self.midi: list[bytes] = []
        self.clock_syncs = 0
        self.control: asyncio.DatagramTransport | None = None
        self.data: asyncio.DatagramTransport | None = None
        self.peer_control: tuple | None = None
        self.port = 0

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        for _ in range(50):
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            try:
                self.control, _ = await loop.create_datagram_endpoint(
                    lambda: _Proto(self, "control"), local_addr=("127.0.0.1", port)
                )
                self.data, _ = await loop.create_datagram_endpoint(
                    lambda: _Proto(self, "data"), local_addr=("127.0.0.1", port + 1)
                )
            except OSError:
                if self.control is not None:
                    self.control.close()
                    self.control = None
                continue
            self.port = port
            return
        raise RuntimeError("no free port pair")

    def close(self) -> None:
        for transport in (self.control, self.data):
            if transport is not None:
                transport.close()

    def bye(self) -> None:
        packet = b"\xff\xffBY" + struct.pack(">III", 2, 0, 0x11111111)
        self.control.sendto(packet, self.peer_control)

    def handle(self, kind: str, data: bytes, addr) -> None:
        transport = self.control if kind == "control" else self.data
        if data[:4] == b"\xff\xffIN":
            self.invites.append(kind)
            if kind == "control":
                self.peer_control = addr
            if self.mode == "silent":
                return
            token = data[8:12]
            answer = b"NO" if self.mode == "reject" else b"OK"
            transport.sendto(
                b"\xff\xff" + answer + struct.pack(">I", 2) + token
                + struct.pack(">I", 0x11111111) + b"Fake\0",
                addr,
            )
        elif data[:4] == b"\xff\xffBY":
            self.byes += 1
        elif data[:4] == b"\xff\xffCK":
            ssrc, count, t1, _, _ = struct.unpack(">IB3xQQQ", data[4:36])
            if count == 0:
                self.clock_syncs += 1
                if self.mode == "stop-syncing" and self.clock_syncs > 1:
                    return
                reply = b"\xff\xffCK" + struct.pack(">IB3xQQQ", 0x11111111, 1, t1, 4242, 0)
                transport.sendto(reply, addr)
        elif data[:2] == b"\x80\x61":
            self.midi.append(data[13 : 13 + (data[12] & 0x0F)])


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, owner: FakeResponder, kind: str) -> None:
        self.owner, self.kind = owner, kind

    def datagram_received(self, data, addr) -> None:
        self.owner.handle(self.kind, data, addr)


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(applemidi, "INVITE_TIMEOUT", 0.1)
    monkeypatch.setattr(applemidi, "SYNC_INTERVAL", 0.05)
    monkeypatch.setattr(applemidi, "MAX_BACKOFF", 0.05)


async def _wait_for(predicate, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.01)


def test_rtp_midi_packet_bytes():
    packet = rtp_midi_packet(0x1234, 0x01020304, 0xA1B2C3D4, bytes.fromhex("9F057F"))
    assert packet.hex() == "8061123401020304a1b2c3d4039f057f"


def test_rtp_midi_packet_rejects_long_messages():
    with pytest.raises(ValueError):
        rtp_midi_packet(0, 0, 0, bytes(16))


async def test_session_connects_sends_and_says_goodbye(fast):
    responder = FakeResponder()
    await responder.start()
    states: list[str] = []
    session = AppleMidiSession(
        "127.0.0.1", responder.port, on_state=lambda state, _: states.append(state)
    )
    session.start()
    try:
        await _wait_for(lambda: session.connected)
        assert responder.invites[:2] == ["control", "data"]
        assert session.latency_ms is not None
        assert session.send(bytes.fromhex("9F057F"))
        assert session.send(bytes.fromhex("8F0500"))
        await _wait_for(lambda: len(responder.midi) == 2)
        assert responder.midi == [bytes.fromhex("9F057F"), bytes.fromhex("8F0500")]
        await session.close()
        await _wait_for(lambda: responder.byes == 1)
    finally:
        await session.close()
        responder.close()
    assert states[:2] == ["connecting", "connected"]
    assert states[-1] == "disconnected"


async def test_rejected_invitation_stays_disconnected_and_retries(fast):
    responder = FakeResponder("reject")
    await responder.start()
    session = AppleMidiSession("127.0.0.1", responder.port)
    session.start()
    try:
        await _wait_for(lambda: responder.invites.count("control") >= 2)
        assert not session.connected
        assert session.detail == "Einladung abgelehnt"
        assert session.send(b"\x9f\x05\x7f") is False
    finally:
        await session.close()
        responder.close()


async def test_silent_peer_times_out(fast):
    responder = FakeResponder("silent")
    await responder.start()
    session = AppleMidiSession("127.0.0.1", responder.port)
    session.start()
    try:
        await _wait_for(lambda: "keine Antwort" in session.detail)
        assert session.state == "disconnected"
    finally:
        await session.close()
        responder.close()


async def test_peer_bye_triggers_reconnect(fast):
    responder = FakeResponder()
    await responder.start()
    session = AppleMidiSession("127.0.0.1", responder.port)
    session.start()
    try:
        await _wait_for(lambda: session.connected)
        responder.bye()
        await _wait_for(lambda: not session.connected)
        await _wait_for(lambda: session.connected)
        assert responder.invites.count("control") == 2
    finally:
        await session.close()
        responder.close()


async def test_missing_clock_sync_answers_drop_the_session(fast):
    responder = FakeResponder("stop-syncing")
    await responder.start()
    session = AppleMidiSession("127.0.0.1", responder.port)
    session.start()
    try:
        await _wait_for(lambda: session.connected)
        await _wait_for(lambda: session.detail == "keine Antwort auf Clock-Sync", timeout=3.0)
        assert not session.connected
    finally:
        await session.close()
        responder.close()


async def test_peer_clock_sync_is_answered(fast):
    responder = FakeResponder()
    await responder.start()
    session = AppleMidiSession("127.0.0.1", responder.port)
    received: list[bytes] = []
    session.start()
    try:
        await _wait_for(lambda: session.connected)
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        class Probe(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                received.append(data)
                if not future.done():
                    future.set_result(data)

        # The session's data socket is control + 1; ask it from a fresh socket.
        data_port = session._data.transport.get_extra_info("sockname")[1]
        transport, _ = await loop.create_datagram_endpoint(Probe, local_addr=("127.0.0.1", 0))
        transport.sendto(
            b"\xff\xffCK" + struct.pack(">IB3xQQQ", 0x22222222, 0, 777, 0, 0),
            ("127.0.0.1", data_port),
        )
        await asyncio.wait_for(future, 1.0)
        transport.close()
    finally:
        await session.close()
        responder.close()
    assert received, "no CK1 answer"
    _, count, t1, _, _ = struct.unpack(">IB3xQQQ", received[0][4:36])
    assert (count, t1) == (1, 777)
