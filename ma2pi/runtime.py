"""Validated hot reload of the active configuration.

The store owns the ``AppConfig`` instance the daemon is currently running with
and applies JSON merge patches atomically.  A patch is validated with the same
rules as daemon start and written through :mod:`ma2pi.config_store`; changed
credentials are tested before live inputs are frozen or anything is persisted.
Held keys and playback buttons are released in reverse press order and open
encoder deltas are dropped while frozen, so no frame from the old configuration
leaks into the new generation.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import tomllib
from typing import Any, Awaitable, Callable, Mapping

from .config import AppConfig, Ma2Settings, parse_config
from .config_store import (
    PASSWORD_MODE,
    ConfigPaths,
    PreparedConfig,
    _atomic_write,
    commit_prepared,
    create_backup,
    list_backups,
    prepare_patch,
    read_backup,
    write_password,
)
from .ma2_client import ConnectionCheck, Ma2Client, check_connection
from .mapping import MappingEngine

LOGGER = logging.getLogger("ma2pi.runtime")

_RELEASE_DRAIN_SECONDS = 0.5


class ApplyBusy(RuntimeError):
    """Another configuration apply is already running."""


class StaleConfig(RuntimeError):
    """The caller edited an older configuration generation than the active one."""

    def __init__(self, expected: int, current: int) -> None:
        self.expected = expected
        self.current = current
        super().__init__(
            f"Konfiguration wurde inzwischen geändert (Generation {current}, "
            f"Entwurf basiert auf {expected})"
        )


def _secret(ma2: Ma2Settings) -> str | None:
    try:
        return ma2.read_password()
    except Exception:
        return None


def credentials_changed(current: AppConfig, candidate: AppConfig) -> bool:
    """True when applying ``candidate`` needs a reconnect."""

    old = current.ma2
    new = candidate.ma2
    if (old.host, old.port, old.path, old.username) != (
        new.host,
        new.port,
        new.path,
        new.username,
    ):
        return True
    return _secret(old) != _secret(new)


class ConfigStore:
    """Hold the active configuration and apply validated patches in place."""

    def __init__(
        self,
        config: AppConfig,
        engine: MappingEngine,
        paths: ConfigPaths,
        *,
        client: Ma2Client | None = None,
        playback: Any = None,
        owner: str | None = "ma2pi",
        validate: Callable[[dict[str, Any]], Any] | None = None,
        tester: Callable[[AppConfig, str | None], Awaitable[Any]] | None = None,
    ) -> None:
        self._config = config
        self._engine = engine
        self._paths = paths
        self._client = client
        self._playback = playback
        self._owner = owner
        self._tester = tester
        self._validate = validate or (
            lambda raw: parse_config(raw, source_path=str(paths.config))
        )
        self._lock = asyncio.Lock()
        self._generation = 0
        self._activate_hooks: list[Callable[[AppConfig], None]] = []

    def set_playback(self, playback: Any) -> None:
        """Attach the playback router so held buttons release on apply."""

        self._playback = playback

    def add_activate_hook(self, hook: Callable[[AppConfig], None]) -> None:
        """Register a callback that receives every successfully applied config."""

        self._activate_hooks.append(hook)

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def generation(self) -> int:
        """Monotonic counter, incremented once per successful apply."""

        return self._generation

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def _test_credentials(
        self, candidate: AppConfig, password: str | None = None
    ) -> Any:
        if self._client is not None and self._client.dry_run:
            return None
        if self._tester is not None:
            return await self._tester(candidate, password)
        return await check_connection(
            candidate, password=password, active=self._client
        )

    async def test_connection(self, body: Mapping[str, Any]) -> ConnectionCheck:
        """Test credentials from the UI without writing any configuration."""

        fields = copy.deepcopy(dict(body))
        nested = fields.get("ma2")
        if isinstance(nested, dict):
            fields = copy.deepcopy(dict(nested))
        allowed = {"host", "port", "path", "username", "password"}
        unknown = sorted(set(fields) - allowed)
        if unknown:
            raise ValueError(f"unbekannte Felder: {', '.join(unknown)}")
        password = fields.pop("password", None)
        if password is not None and not isinstance(password, str):
            raise ValueError("password muss eine Zeichenkette sein")

        prepared = prepare_patch(
            self._paths,
            {"ma2": fields},
            owner=self._owner,
            validate=self._validate,
        )
        return await self._test_credentials(prepared.candidate, password)

    def _clean_patch(
        self, patch: Mapping[str, Any], password: str | None
    ) -> dict[str, Any]:
        cleaned = copy.deepcopy(dict(patch))
        ma2 = cleaned.get("ma2")
        if ma2 is not None and not isinstance(ma2, dict):
            raise ValueError("ma2 muss eine Tabelle sein")
        if isinstance(ma2, dict):
            ma2.pop("password", None)
            ma2.pop("password_set", None)
        if password is not None:
            ma2 = {} if ma2 is None else ma2
            ma2["password_file"] = str(self._paths.password)
            ma2["password_env"] = None
            cleaned["ma2"] = ma2
        web = cleaned.get("web")
        if isinstance(web, dict):
            web.pop("pin_set", None)
        return cleaned

    def validate(
        self, patch: Mapping[str, Any], *, password: str | None = None
    ) -> AppConfig:
        """Validate a merge patch in memory without writing anything."""

        prepared = prepare_patch(
            self._paths,
            self._clean_patch(patch, password),
            owner=self._owner,
            validate=self._validate,
        )
        return prepared.candidate

    def backups(self) -> list[dict[str, Any]]:
        return list_backups(self._paths)

    def create_backup(self) -> dict[str, Any]:
        return create_backup(self._paths, owner=self._owner)

    def _prepare_restore(self, backup_id: str) -> PreparedConfig:
        _, text = read_backup(self._paths, backup_id)
        candidate = parse_config(
            tomllib.loads(text), source_path=str(self._paths.config)
        )
        return PreparedConfig(candidate=candidate, text=text)

    async def _drain_releases(self) -> None:
        """Best-effort wait so queued release frames leave under the old config."""

        client = self._client
        if client is None or client.dry_run or not client.authenticated:
            return
        deadline = time.monotonic() + _RELEASE_DRAIN_SECONDS
        while len(client.queue) and time.monotonic() < deadline:
            if not client.authenticated:
                break
            await asyncio.sleep(0.005)

    async def _activate(
        self,
        prepared: PreparedConfig,
        *,
        test: bool,
        password: str | None = None,
    ) -> AppConfig:
        candidate = prepared.candidate
        changed = credentials_changed(self._config, candidate)
        if password is not None:
            changed = changed or _secret(self._config.ma2) != password
        if test and changed:
            # Test before freezing or writing; a slow or failed check leaves
            # live inputs and the current session completely uninterrupted.
            await self._test_credentials(candidate, password)

        had_password = self._paths.password.is_file()
        old_password_text = (
            self._paths.password.read_text(encoding="utf-8")
            if had_password
            else None
        )
        if password is not None:
            write_password(self._paths, password, owner=self._owner)
        try:
            commit_prepared(self._paths, prepared, owner=self._owner)
        except BaseException:
            if password is not None:
                try:
                    if had_password and old_password_text is not None:
                        _atomic_write(
                            self._paths.password,
                            old_password_text,
                            PASSWORD_MODE,
                            self._owner,
                        )
                    else:
                        self._paths.password.unlink(missing_ok=True)
                except OSError:
                    LOGGER.warning("Passwort-Rollback fehlgeschlagen", exc_info=True)
            raise

        self._engine.freeze()
        try:
            send_releases = self._client is None or self._client.authenticated or self._client.dry_run
            if self._playback is not None and hasattr(self._playback, "cleanup"):
                self._playback.cleanup(send=send_releases)
            self._engine.cleanup(send=send_releases)
            await self._drain_releases()
            self._engine.swap_config(candidate)
            self._config = candidate
            self._generation += 1
            for hook in self._activate_hooks:
                hook(candidate)
            if self._client is not None:
                self._client.apply_config(candidate)
            LOGGER.info("Konfiguration angewendet, Generation %d", self._generation)
        finally:
            self._engine.unfreeze()

        if changed and self._client is not None:
            await self._client.reconnect()
        return self._config

    async def _run(self, action: Callable[[], Awaitable[AppConfig]]) -> AppConfig:
        if self._lock.locked():
            raise ApplyBusy("Ein anderes Apply läuft bereits")
        async with self._lock:
            return await action()

    async def apply(
        self,
        patch: Mapping[str, Any],
        *,
        password: str | None = None,
        expected_generation: int | None = None,
    ) -> AppConfig:
        """Validate, test, persist and activate ``patch`` as a new generation.

        ``expected_generation`` rejects the write with :class:`StaleConfig` when
        the active configuration moved on since the caller read it.
        """

        async def run() -> AppConfig:
            if expected_generation is not None and expected_generation != self._generation:
                raise StaleConfig(expected_generation, self._generation)
            prepared = prepare_patch(
                self._paths,
                self._clean_patch(patch, password),
                owner=self._owner,
                validate=self._validate,
            )
            return await self._activate(prepared, test=True, password=password)

        return await self._run(run)

    async def restore(self, backup_id: str) -> AppConfig:
        """Validate and activate a backup, then reconnect if needed."""

        async def run() -> AppConfig:
            prepared = self._prepare_restore(backup_id)
            return await self._activate(prepared, test=False)

        return await self._run(run)
