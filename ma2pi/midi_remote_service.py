"""Run the MIDI remote path: RTP-MIDI session, note output and table sync.

The router asks :meth:`MidiRemoteService.press` for every executor button with
``transport = "midi"``.  A target is only sent while the session is up and the
sync has confirmed its remote in the MA; otherwise ``press`` returns False and
the router drops the event.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .applemidi import AppleMidiSession
from .config import AppConfig, ConfigError
from .ma2_telnet import Ma2Telnet, MidiRemoteTable, TelnetError
from .midi_remote import MidiAddress, MidiRemoteOutput, TargetKey, assign_addresses
from .midi_remote_sync import SyncResult, failed_result, sync_table
from .playback_targets import midi_button_targets

LOGGER = logging.getLogger("ma2pi.midi_remote")

SYNC_RETRY_MIN = 1.0
SYNC_RETRY_MAX = 10.0

SyncRunner = Callable[[AppConfig, dict[TargetKey, MidiAddress]], Awaitable[SyncResult]]


class _DryRunSender:
    connected = True
    state = "dry-run"
    detail = ""
    latency_ms = None

    def send(self, midi: bytes) -> bool:
        LOGGER.info("dry-run: MIDI %s", midi.hex(" ").upper())
        return True


class _NoSender:
    connected = False

    def send(self, midi: bytes) -> bool:
        return False


async def telnet_sync(config: AppConfig, desired: dict[TargetKey, MidiAddress]) -> SyncResult:
    settings = config.midi_remote
    telnet = Ma2Telnet(
        config.ma2.host,
        settings.telnet_port,
        username=config.ma2.username,
        password=config.ma2.read_password(),
    )
    await telnet.connect()
    try:
        return await sync_table(
            MidiRemoteTable(telnet), desired, settings.channels, settings.sync
        )
    finally:
        await telnet.close()


class MidiRemoteService:
    def __init__(
        self,
        config: AppConfig,
        *,
        dry_run: bool = False,
        sync_runner: SyncRunner = telnet_sync,
        session_factory: Callable[[str, int], Any] = AppleMidiSession,
    ) -> None:
        self._config = config
        self._dry_run = dry_run
        self._sync_runner = sync_runner
        self._session_factory = session_factory
        self._session: Any = None
        self._session_key: tuple[str, int] | None = None
        self._output = MidiRemoteOutput(_NoSender())
        self._addresses: dict[TargetKey, MidiAddress] = {}
        self._result: SyncResult | None = None
        self._syncing = False
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._started = False

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        self._started = True
        self.set_config(self._config)

    async def close(self) -> None:
        self._started = False
        self._output.close()
        await self._stop_sync()
        await self._stop_session()

    def set_config(self, config: AppConfig) -> None:
        """Take a newly activated config; changed targets wait for the sync."""

        self._config = config
        if not self._started:
            return
        settings = config.midi_remote
        if not settings.enabled:
            self._addresses = {}
            self._output.set_table({}, ())
            self._result = None
            asyncio.ensure_future(self._stop_sync())
            asyncio.ensure_future(self._stop_session())
            return

        addresses = assign_addresses(midi_button_targets(config), settings.channels)
        unchanged = [
            target
            for target, address in addresses.items()
            if self._addresses.get(target) == address and self._output.is_synced(target)
        ]
        self._addresses = addresses
        self._ensure_session(config)
        if self._dry_run or settings.sync == "off":
            # No table to compare against: send to every target.
            self._output.set_table(addresses, addresses)
            self._result = SyncResult(settings.sync, frozenset(addresses), len(addresses))
            asyncio.ensure_future(self._stop_sync())
            return
        self._output.set_table(addresses, unchanged)
        self.request_sync()

    def request_sync(self) -> None:
        """Sync again, e.g. after the MA session was lost and may have a new show."""

        settings = self._config.midi_remote
        if not self._started or not settings.enabled or settings.sync == "off" or self._dry_run:
            return
        self._wake.set()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._sync_loop(), name="ma2pi-midi-sync")

    # -- router interface -----------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._output.connected

    def is_synced(self, target: TargetKey) -> bool:
        return self._output.is_synced(target)

    def press(self, target: TargetKey, pressed: bool) -> bool:
        return self._output.press(target, pressed)

    # -- status ---------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        settings = self._config.midi_remote
        if not settings.enabled:
            return {"enabled": False}
        sender = self._output.sender
        result = self._result
        return {
            "enabled": True,
            "session": {
                "state": getattr(sender, "state", "disconnected"),
                "detail": getattr(sender, "detail", ""),
                "host": self._session_key[0] if self._session_key else None,
                "port": settings.port,
                "latency_ms": getattr(sender, "latency_ms", None),
            },
            "sync": {
                "mode": settings.sync,
                "running": self._syncing,
                "targets": len(self._addresses),
                "synced": sum(1 for target in self._addresses if self._output.is_synced(target)),
                "created": result.created if result else 0,
                "changed": result.changed if result else 0,
                "removed": result.removed if result else 0,
                "failed": result.failed if result else 0,
                "deviations": result.deviations if result else 0,
                "error": result.error if result else None,
                "at": result.at if result else None,
            },
        }

    # -- internals ------------------------------------------------------------

    def _ensure_session(self, config: AppConfig) -> None:
        if self._dry_run:
            if not isinstance(self._output.sender, _DryRunSender):
                self._output.sender = _DryRunSender()
            return
        key = (config.midi_remote.host or config.ma2.host, config.midi_remote.port)
        if self._session is not None and key == self._session_key:
            return
        old = self._session
        self._session = self._session_factory(*key)
        self._session_key = key
        self._output.sender = self._session
        self._session.start()
        if old is not None:
            asyncio.ensure_future(old.close())

    async def _stop_session(self) -> None:
        session, self._session, self._session_key = self._session, None, None
        self._output.sender = _NoSender()
        if session is not None:
            await session.close()

    async def _stop_sync(self) -> None:
        task, self._task = self._task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _sync_loop(self) -> None:
        delay = SYNC_RETRY_MIN
        while True:
            await self._wake.wait()
            self._wake.clear()
            config = self._config
            desired = dict(self._addresses)
            self._syncing = True
            try:
                result = await self._sync_runner(config, desired)
            except (TelnetError, ConfigError, OSError) as exc:
                message = str(exc)
                if self._result is None or self._result.error != message:
                    LOGGER.error("MIDI-Remote-Abgleich fehlgeschlagen: %s", message)
                result = failed_result(config.midi_remote.sync, len(desired), message)
            finally:
                self._syncing = False
            if config is not self._config or self._wake.is_set():
                # A newer config arrived meanwhile; its sync runs next.
                continue
            self._result = result
            self._output.set_table(self._addresses, result.synced)
            if result.error is None:
                delay = SYNC_RETRY_MIN
                continue
            try:
                await asyncio.wait_for(self._wake.wait(), delay)
            except asyncio.TimeoutError:
                self._wake.set()
            delay = min(SYNC_RETRY_MAX, delay * 2)
