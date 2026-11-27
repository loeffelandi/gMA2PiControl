from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from pathlib import Path

import pytest

from ma2pi import ma2_telnet
from ma2pi.ma2_telnet import (
    CommandError,
    Ma2Telnet,
    MidiRemoteEntry,
    MidiRemoteTable,
    TelnetError,
    clean,
    parse_midi_remote_list,
)

FIXTURES = Path(__file__).parent / "fixtures" / "telnet"


def load_fixture(name: str) -> tuple[bytes, dict[str, deque[bytes]]]:
    """Split a recording into the banner and the answers per command."""

    banner = b""
    answers: dict[str, deque[bytes]] = defaultdict(deque)
    current: str | None = None
    chunks: list[bytes] = []

    def flush() -> None:
        nonlocal banner
        body = b"".join(chunks)
        if body.endswith(b"\n"):
            body = body[:-1]
        if current == "":
            banner = body
        elif current is not None:
            answers[current].append(body)

    for line in (FIXTURES / name).read_bytes().splitlines(keepends=True):
        if line.startswith(b"### banner"):
            flush()
            current, chunks = "", []
        elif line.startswith(b"### >> "):
            flush()
            current, chunks = line[7:].rstrip(b"\n").decode(), []
        else:
            chunks.append(line)
    flush()
    return banner, answers


class FakeMa:
    def __init__(self, fixture: str = "session.txt") -> None:
        self.banner, self.answers = load_fixture(fixture)
        self.received: list[str] = []
        self.server: asyncio.base_events.Server | None = None
        self.port = 0
        self.mute_after: int | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def _client(self, reader, writer) -> None:
        # The banner arrives in two pieces like on the console: prompt, then
        # "Please login !" and a second prompt.
        split = self.banner.index(b">\x1b[K") + 4
        writer.write(self.banner[:split])
        await writer.drain()
        await asyncio.sleep(0.01)
        writer.write(self.banner[split:])
        await writer.drain()
        try:
            while line := await reader.readline():
                command = line.decode().rstrip("\r\n")
                self.received.append(command)
                if self.mute_after is not None and len(self.received) > self.mute_after:
                    continue
                queue = self.answers.get(command)
                if queue:
                    answer = queue.popleft() if len(queue) > 1 else queue[0]
                else:
                    answer = b"\n\r\rRemoteTypes/MidiRemotes 2 >\x1b[K"
                writer.write(answer)
                await writer.drain()
        finally:
            writer.close()


@pytest.fixture
async def fake_ma():
    server = FakeMa()
    await server.start()
    yield server
    await server.stop()


def _lines(command: str) -> list[str]:
    _, answers = load_fixture("session.txt")
    return clean(answers[command][0].decode())


def test_list_parses_all_entries_and_columns():
    entries = parse_midi_remote_list(_lines("list"))
    assert len(entries) == 85
    assert entries[0] == MidiRemoteEntry(1, 1, 1, "Exec", 3, 162, "Button 1")
    assert entries[30] == MidiRemoteEntry(31, 33, 2, "Exec", 3, 39, "Fader")
    assert {entry.channel for entry in entries} == {1, 2, 3}


def test_list_parses_multi_word_page():
    entries = parse_midi_remote_list(_lines("list 86"))
    assert entries == [MidiRemoteEntry(86, 100, 16, "Exec", "current", 101, "Button 1")]


def test_empty_list_parses_to_nothing():
    _, answers = load_fixture("session.txt")
    assert parse_midi_remote_list(clean(answers["list 86"][-1].decode())) == []


def test_unreadable_row_is_an_error():
    header = "              Name        Note  Channel  Type  Page  Executor  Button    Keycode  CMD  Info"
    row = "RemoteMidi  1 MIDI Input  x     1        Exec  3     162       Button 1  None"
    with pytest.raises(TelnetError):
        parse_midi_remote_list([header, row])


async def test_login_and_midi_remote_commands(fake_ma):
    telnet = Ma2Telnet("127.0.0.1", fake_ma.port, username="svt")
    await telnet.connect()
    table = MidiRemoteTable(telnet)
    await table.enter()
    assert telnet.prompt == "RemoteTypes/MidiRemotes 2"
    assert len(await table.list()) == 85
    await table.store(86)
    await table.assign_exec(86, note=100, channel=16, page="current", executor=101, button=1)
    assert (await table.list(86))[0].page == "current"
    await table.delete(86)
    await telnet.close()
    assert fake_ma.received == [
        'login "svt" ""',
        "cd /",
        "cd 36",
        "cd 2",
        "list",
        "store 86",
        'assign 86 /note=100 /channel=16 /type="Exec" /page=0 /executor=101 /button="Button 1"',
        "list 86",
        "delete 86 /noconfirm",
    ]


async def test_command_errors_carry_code_and_message(fake_ma):
    telnet = Ma2Telnet("127.0.0.1", fake_ma.port, username="svt")
    await telnet.connect()
    with pytest.raises(CommandError) as error:
        await telnet.command("assign 86 /channel=17")
    assert (error.value.code, error.value.message) == (9, "NUMBER TOO LARGE  (max=16)")
    # Silent on the MA, so no error here: the sync reads back instead.
    assert await telnet.command('assign 86 /button="Button 9"') == [
        'Executing : Assign 86 /button="Button 9"'
    ]
    await telnet.close()


async def test_rejected_login_is_reported():
    server = FakeMa("badlogin.txt")
    await server.start()
    telnet = Ma2Telnet("127.0.0.1", server.port, username="nobody", password="x")
    try:
        with pytest.raises(TelnetError, match="abgelehnt"):
            await telnet.connect()
        assert not telnet.connected
    finally:
        await server.stop()


async def test_missing_prompt_times_out_and_disconnects(fake_ma):
    fake_ma.mute_after = 1
    telnet = Ma2Telnet("127.0.0.1", fake_ma.port, username="svt", timeout=0.2)
    await telnet.connect()
    with pytest.raises(TelnetError, match="abgebrochen"):
        await telnet.command("list")
    assert not telnet.connected


async def test_unreachable_host_is_a_telnet_error():
    telnet = Ma2Telnet("127.0.0.1", 1, username="svt", timeout=0.5)
    with pytest.raises(TelnetError, match="nicht erreichbar"):
        await telnet.connect()


def test_quotes_and_newlines_are_refused():
    with pytest.raises(ValueError):
        ma2_telnet.quote('a"b')
    telnet = Ma2Telnet("127.0.0.1", 1, username="svt")
    with pytest.raises(ValueError):
        asyncio.run(telnet.command("list\r\ndelete 1"))
