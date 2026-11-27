"""Command line access to grandMA2 over Telnet, used for the MIDI remote table.

The MA echoes ``Executing : <cmd>``, prints its output and ends with a prompt
(``<path> >`` followed by ``ESC[K``).  Errors show up as ``Error #<n>: ...``.
Many invalid commands pass silently, so callers read back what they wrote.
Syntax and output are recorded in ``tests/fixtures/telnet/``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

LOGGER = logging.getLogger("ma2pi.ma2_telnet")

PROMPT_END = b">\x1b[K"
SETTLE = 0.05
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_ERROR = re.compile(r"^Error #(\d+):\s*(.*)$")
_LIST_COLUMNS = (
    "Name", "Note", "Channel", "Type", "Page", "Executor", "Button", "Keycode", "CMD", "Info",
)


class TelnetError(Exception):
    pass


class CommandError(TelnetError):
    def __init__(self, command: str, code: int, message: str) -> None:
        super().__init__(f"{command}: Error #{code}: {message}")
        self.command = command
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class MidiRemoteEntry:
    number: int
    note: int
    channel: int | None  # None = All
    type: str  # Exec, CMD, None
    page: int | str  # "current" = Current Page on Master
    executor: int
    button: str  # "Button 1".."Button 3", "Fader"
    cmd: str = ""


def clean(text: str) -> list[str]:
    """Output lines without colour codes, carriage returns and blank lines."""

    text = _ANSI.sub("", text)
    return [line.rstrip() for line in re.split(r"[\r\n]+", text) if line.strip()]


def errors(lines: list[str]) -> list[tuple[int, str]]:
    found = []
    for line in lines:
        match = _ERROR.match(line.strip())
        if match:
            found.append((int(match.group(1)), match.group(2).strip()))
    return found


def parse_midi_remote_list(lines: list[str]) -> list[MidiRemoteEntry]:
    """Parse the ``list`` table of ``RemoteTypes/MidiRemotes``.

    Fields may contain spaces (``Current Page on Master``), so the columns are
    cut at the positions of the header names.
    """

    entries: list[MidiRemoteEntry] = []
    starts: list[int] | None = None
    for line in lines:
        if starts is None or line.lstrip().startswith("Name"):
            header = _header_positions(line)
            if header is not None:
                starts = header
            continue
        if not line.startswith("RemoteMidi"):
            continue
        number_part = line[: starts[0]].split()
        fields = [
            line[start:end].strip()
            for start, end in zip(starts, [*starts[1:], len(line) + 1])
        ]
        values = dict(zip(_LIST_COLUMNS, fields))
        try:
            entries.append(
                MidiRemoteEntry(
                    number=int(number_part[-1]),
                    note=int(values["Note"]),
                    channel=None if values["Channel"] == "All" else int(values["Channel"]),
                    type=values["Type"],
                    page=(
                        "current"
                        if values["Page"].startswith("Current")
                        else int(values["Page"])
                    ),
                    executor=int(values["Executor"]),
                    button=values["Button"],
                    cmd=values.get("CMD", ""),
                )
            )
        except (ValueError, IndexError) as exc:
            raise TelnetError(f"MIDI-Remote-Zeile nicht lesbar: {line!r}") from exc
    return entries


def _header_positions(line: str) -> list[int] | None:
    positions: list[int] = []
    cursor = 0
    for name in _LIST_COLUMNS:
        index = line.find(name, cursor)
        if index < 0:
            return None
        positions.append(index)
        cursor = index + len(name)
    return positions


def quote(value: str) -> str:
    if '"' in value:
        raise ValueError(f"Anführungszeichen sind in MA-Befehlen nicht möglich: {value!r}")
    return f'"{value}"'


class Ma2Telnet:
    """One Telnet session to the MA command line."""

    def __init__(
        self,
        host: str,
        port: int = 30000,
        *,
        username: str,
        password: str = "",
        timeout: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.prompt = ""
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        await self.close()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
            await self._read_until_prompt()
            await self.command(f"login {quote(self.username)} {quote(self.password)}")
        except (OSError, asyncio.TimeoutError, TelnetError) as exc:
            await self.close()
            if isinstance(exc, CommandError):
                raise TelnetError(f"Telnet-Anmeldung als {self.username!r} abgelehnt") from exc
            if isinstance(exc, TelnetError):
                raise
            raise TelnetError(
                f"Telnet {self.host}:{self.port} nicht erreichbar: {exc or type(exc).__name__}"
            ) from exc

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    async def command(self, command: str) -> list[str]:
        """Send one command; return its output lines, raise on ``Error #``."""

        if "\r" in command or "\n" in command:
            raise ValueError("Ein Telnet-Befehl darf keinen Zeilenumbruch enthalten")
        async with self._lock:
            if self._writer is None:
                raise TelnetError("Telnet nicht verbunden")
            LOGGER.debug("Telnet >> %s", command)
            try:
                self._writer.write(command.encode("utf-8") + b"\r\n")
                await self._writer.drain()
                raw = await self._read_until_prompt()
            except (OSError, asyncio.TimeoutError) as exc:
                await self.close()
                raise TelnetError(f"Telnet abgebrochen bei {command!r}: {exc}") from exc
        lines = clean(raw)
        if lines and lines[-1].endswith(">"):
            self.prompt = lines.pop()[:-1].strip()
        found = errors(lines)
        if found:
            code, message = found[0]
            raise CommandError(command, code, message)
        return lines

    async def _read_until_prompt(self) -> str:
        buffer = bytearray()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        while True:
            # After a prompt, wait briefly: the banner prints a second prompt.
            wait = SETTLE if buffer.endswith(PROMPT_END) else deadline - loop.time()
            if wait <= 0:
                raise asyncio.TimeoutError("kein Prompt der MA")
            try:
                chunk = await asyncio.wait_for(self._reader.read(65536), wait)
            except asyncio.TimeoutError:
                if buffer.endswith(PROMPT_END):
                    return buffer.decode("utf-8", "replace")
                raise
            if not chunk:
                raise ConnectionError("MA hat die Telnet-Verbindung geschlossen")
            buffer += chunk


class MidiRemoteTable:
    """``RemoteTypes/MidiRemotes`` of the running show."""

    def __init__(self, telnet: Ma2Telnet) -> None:
        self._telnet = telnet

    async def enter(self) -> None:
        # Absolute paths (``cd /36``) are rejected; a fresh session starts at the root.
        await self._telnet.command("cd /")
        await self._telnet.command("cd 36")
        await self._telnet.command("cd 2")
        if "MidiRemotes" not in self._telnet.prompt:
            raise TelnetError(
                f"MidiRemotes nicht gefunden (Prompt {self._telnet.prompt!r})"
            )

    async def list(self, number: int | None = None) -> list[MidiRemoteEntry]:
        command = "list" if number is None else f"list {number}"
        return parse_midi_remote_list(await self._telnet.command(command))

    async def store(self, number: int) -> None:
        await self._telnet.command(f"store {number}")

    async def assign_exec(
        self, number: int, *, note: int, channel: int, page: int | str, executor: int, button: int
    ) -> None:
        ma_page = 0 if page == "current" else page
        await self._telnet.command(
            f"assign {number} /note={note} /channel={channel} /type={quote('Exec')} "
            f"/page={ma_page} /executor={executor} /button={quote(f'Button {button}')}"
        )

    async def delete(self, number: int) -> None:
        await self._telnet.command(f"delete {number} /noconfirm")
