"""AppleMIDI (RTP-MIDI) session initiator.

``ma2pi`` invites the rtpMIDI driver on the onPC computer and sends MIDI to it.
Only the parts the MA path needs are implemented: invitation on the control
and data port, clock sync in both directions, ``BY`` and RTP-MIDI packets
without recovery journal (measured: rtpMIDI accepts them, see the
``add-midi-remote-executors`` verification).
"""

from __future__ import annotations

import asyncio
import logging
import random
import socket
import struct
import time
from typing import Callable

LOGGER = logging.getLogger("ma2pi.applemidi")

SIGNATURE = b"\xff\xff"
VERSION = 2
RTP_MIDI_PAYLOAD_TYPE = 0x61

INVITE_TIMEOUT = 1.0
INVITE_ATTEMPTS = 3
SYNC_INTERVAL = 10.0
SYNC_MISSES_BEFORE_RECONNECT = 3
MAX_BACKOFF = 10.0


def _command(name: bytes, token: int, ssrc: int, session_name: bytes = b"") -> bytes:
    body = SIGNATURE + name + struct.pack(">III", VERSION, token, ssrc)
    return body + session_name


def _clock_sync(ssrc: int, count: int, t1: int, t2: int, t3: int) -> bytes:
    return SIGNATURE + b"CK" + struct.pack(">IB3xQQQ", ssrc, count, t1, t2, t3)


def rtp_midi_packet(sequence: int, timestamp: int, ssrc: int, midi: bytes) -> bytes:
    """RTP header plus a short MIDI command section (no journal, no delta time)."""

    if len(midi) > 15:
        raise ValueError("Kurzform des MIDI-Abschnitts trägt höchstens 15 Byte")
    header = struct.pack(
        ">BBHII",
        0x80,
        RTP_MIDI_PAYLOAD_TYPE,
        sequence & 0xFFFF,
        timestamp & 0xFFFFFFFF,
        ssrc,
    )
    return header + bytes([len(midi)]) + midi


class _Endpoint(asyncio.DatagramProtocol):
    def __init__(self, on_packet: Callable[[bytes, tuple], None]) -> None:
        self._on_packet = on_packet
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:
        self._on_packet(data, addr)

    def error_received(self, exc: Exception) -> None:
        LOGGER.debug("RTP-MIDI UDP-Fehler: %s", exc)


class AppleMidiSession:
    """Keep one RTP-MIDI session to ``host:port`` and send MIDI messages."""

    def __init__(
        self,
        host: str,
        port: int = 5004,
        *,
        name: str = "ma2pi",
        on_state: Callable[[str, str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.state = "disconnected"
        self.detail = ""
        self.latency_ms: float | None = None
        self._on_state = on_state
        self._clock = clock
        self._t0 = clock()
        self._ssrc = random.getrandbits(32)
        self._token = 0
        self._sequence = random.getrandbits(16)
        self._address: tuple | None = None
        self._control: _Endpoint | None = None
        self._data: _Endpoint | None = None
        self._waiters: dict[tuple[str, bytes], asyncio.Future] = {}
        self._clock_reply: asyncio.Future | None = None
        self._peer_bye = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # -- public -------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.state == "connected"

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="applemidi")

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._say_goodbye()
        self._close_endpoints()
        if self.state == "connected":
            LOGGER.info("RTP-MIDI-Sitzung abgemeldet")
        self.state, self.detail = "disconnected", "beendet"
        if self._on_state is not None:
            self._on_state(self.state, self.detail)

    def send(self, midi: bytes) -> bool:
        if not self.connected or self._data is None or self._address is None:
            return False
        self._sequence = (self._sequence + 1) & 0xFFFF
        packet = rtp_midi_packet(self._sequence, self._timestamp(), self._ssrc, midi)
        self._data.transport.sendto(packet, self._data_address())
        return True

    # -- session loop -------------------------------------------------------

    async def _run(self) -> None:
        backoff = 1.0
        while True:
            try:
                await self._connect()
                backoff = 1.0
                await self._hold()
            except asyncio.CancelledError:
                raise
            except (OSError, ConnectionError, asyncio.TimeoutError) as exc:
                self._set_state("disconnected", str(exc) or type(exc).__name__)
            self._say_goodbye()
            self._close_endpoints()
            await asyncio.sleep(backoff)
            backoff = min(MAX_BACKOFF, backoff * 2)

    async def _connect(self) -> None:
        self._set_state("connecting", f"{self.host}:{self.port}")
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(self.host, self.port, type=socket.SOCK_DGRAM)
        family, _, _, _, sockaddr = infos[0]
        self._address = sockaddr
        self._control, self._data = await self._open_endpoints(family)
        self._token = random.getrandbits(32)
        self._peer_bye.clear()
        name = self.name.encode("utf-8") + b"\0"
        await self._invite(self._control, self._control_address(), name)
        await self._invite(self._data, self._data_address(), name)
        await self._sync()
        self._set_state("connected", f"{self.host}:{self.port}")

    async def _hold(self) -> None:
        misses = 0
        while True:
            try:
                await asyncio.wait_for(self._peer_bye.wait(), SYNC_INTERVAL)
                raise ConnectionError("Gegenstelle hat die Sitzung beendet")
            except asyncio.TimeoutError:
                pass
            try:
                await self._sync()
                misses = 0
            except asyncio.TimeoutError:
                misses += 1
                if misses >= SYNC_MISSES_BEFORE_RECONNECT:
                    raise ConnectionError("keine Antwort auf Clock-Sync")

    async def _open_endpoints(self, family: int) -> tuple[_Endpoint, _Endpoint]:
        loop = asyncio.get_running_loop()
        bind = "::" if family == socket.AF_INET6 else "0.0.0.0"
        for _ in range(20):
            control_transport, control = await loop.create_datagram_endpoint(
                lambda: _Endpoint(self._on_control), local_addr=(bind, 0), family=family
            )
            control_port = control_transport.get_extra_info("sockname")[1]
            try:
                _, data = await loop.create_datagram_endpoint(
                    lambda: _Endpoint(self._on_data),
                    local_addr=(bind, control_port + 1),
                    family=family,
                )
            except OSError:
                control_transport.close()
                continue
            return control, data
        raise OSError("keine zwei aufeinanderfolgenden UDP-Ports frei")

    def _close_endpoints(self) -> None:
        for endpoint in (self._control, self._data):
            if endpoint is not None and endpoint.transport is not None:
                endpoint.transport.close()
        self._control = self._data = None
        for future in self._waiters.values():
            if not future.done():
                future.cancel()
        self._waiters.clear()

    async def _invite(self, endpoint: _Endpoint, address: tuple, name: bytes) -> None:
        loop = asyncio.get_running_loop()
        port_kind = "control" if endpoint is self._control else "data"
        for _ in range(INVITE_ATTEMPTS):
            future = loop.create_future()
            self._waiters[(port_kind, b"invite")] = future
            endpoint.transport.sendto(
                _command(b"IN", self._token, self._ssrc, name), address
            )
            try:
                answer = await asyncio.wait_for(future, INVITE_TIMEOUT)
            except asyncio.TimeoutError:
                continue
            if answer == b"NO":
                raise ConnectionError("Einladung abgelehnt")
            return
        raise asyncio.TimeoutError(f"keine Antwort auf {address[0]}:{address[1]}")

    async def _sync(self) -> None:
        loop = asyncio.get_running_loop()
        self._clock_reply = loop.create_future()
        t1 = self._timestamp64()
        self._data.transport.sendto(_clock_sync(self._ssrc, 0, t1, 0, 0), self._data_address())
        t2 = await asyncio.wait_for(self._clock_reply, INVITE_TIMEOUT)
        t3 = self._timestamp64()
        self._data.transport.sendto(_clock_sync(self._ssrc, 2, t1, t2, t3), self._data_address())
        self.latency_ms = (t3 - t1) / 10.0

    # -- packets --------------------------------------------------------------

    def _on_control(self, data: bytes, addr) -> None:
        self._on_command("control", data)

    def _on_data(self, data: bytes, addr) -> None:
        if data[:4] == SIGNATURE + b"CK" and len(data) >= 36:
            ssrc, count, t1, t2, _ = struct.unpack(">IB3xQQQ", data[4:36])
            if count == 0:
                reply = _clock_sync(self._ssrc, 1, t1, self._timestamp64(), 0)
                self._data.transport.sendto(reply, addr)
            elif count == 1 and self._clock_reply is not None and not self._clock_reply.done():
                self._clock_reply.set_result(t2)
            return
        self._on_command("data", data)

    def _on_command(self, port_kind: str, data: bytes) -> None:
        if data[:2] != SIGNATURE or len(data) < 4:
            return
        command = data[2:4]
        if command in (b"OK", b"NO"):
            future = self._waiters.pop((port_kind, b"invite"), None)
            if future is not None and not future.done():
                future.set_result(command)
        elif command == b"BY":
            self._peer_bye.set()

    # -- helpers --------------------------------------------------------------

    def _control_address(self) -> tuple:
        return (self._address[0], self.port, *self._address[2:])

    def _data_address(self) -> tuple:
        return (self._address[0], self.port + 1, *self._address[2:])

    def _timestamp64(self) -> int:
        return int((self._clock() - self._t0) * 10000)

    def _timestamp(self) -> int:
        return self._timestamp64() & 0xFFFFFFFF

    def _say_goodbye(self) -> None:
        if self.state != "connected" or self._control is None or self._address is None:
            return
        self._control.transport.sendto(
            _command(b"BY", self._token, self._ssrc), self._control_address()
        )

    def _set_state(self, state: str, detail: str) -> None:
        if (state, detail) == (self.state, self.detail):
            return
        previous = self.state
        self.state, self.detail = state, detail
        if state == "connected":
            LOGGER.info("RTP-MIDI-Sitzung zu %s steht", detail)
        elif previous == "connected":
            LOGGER.warning("RTP-MIDI-Sitzung getrennt: %s", detail)
        else:
            LOGGER.debug("RTP-MIDI %s: %s", state, detail)
        if self._on_state is not None:
            self._on_state(state, detail)
