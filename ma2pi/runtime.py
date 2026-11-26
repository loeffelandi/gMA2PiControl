"""Validated hot reload of the active configuration.

The store owns the ``AppConfig`` instance the daemon is currently running with
and applies JSON merge patches atomically.  A patch is validated with the same
rules as daemon start and written through :mod:`ma2pi.config_store`; changed
credentials are tested before they are persisted.  Held keys are released in
reverse press order and open encoder deltas are dropped while the engine is
frozen, so no frame from the old configuration leaks into the new generation.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import tomllib
from typing import Any, Awaitable, Callable, Mapping

from .config import AppConfig, Ma2Settings, parse_config
from .config_store import (
    ConfigPaths,
    PreparedConfig,
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


class ApplyBusy(RuntimeError):
    """Another configuration apply is already running."""


def _secret(ma2: Ma2Settings) -> str | None:
    try:
        return ma2.read_password()
    except Exception:
        return None


def credentials_changed(current: AppConfig, candidate: AppConfig) -> bool:
    """True when applying ``candidate`` needs a reconnect.

    Host, port, path, user and the actual password count; a what-if password
    written by the UI is compared by reading the candidate's source.  Invalid
    or missing password sources do not raise here; the connection test reports
    them instead.
    """

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
        owner: str | None = "ma2pi",
        validate: Callable[[dict[str, Any]], Any] | None = None,
        tester: Callable[[AppConfig, str | None], Awaitable[Any]] | None = None,
    ) -> None:
        self._config = config
        self._engine = engine
        self._paths = paths
        self._client = client
        self._owner = owner
        self._tester = tester
        self._validate = validate or (
            lambda raw: parse_config(raw, source_path=str(paths.config))
        )
        self._lock = asyncio.Lock()
        self._generation = 0

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
        if password is not None:
            ma2 = {} if ma2 is None else ma2
            ma2["password_file"] = str(self._paths.password)
            ma2["password_env"] = None
            cleaned["ma2"] = ma2
        if isinstance(ma2, dict):
            ma2.pop("password", None)
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
        path, text = read_backup(self._paths, backup_id)
        candidate = parse_config(
            tomllib.loads(text), source_path=str(self._paths.config)
        )
        return PreparedConfig(candidate=candidate, text=text)

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
            # Test before anything is written; a failed test leaves the old
            # configuration and session in place.
            await self._test_credentials(candidate, password)

        if password is not None:
            write_password(self._paths, password, owner=self._owner)
        commit_prepared(self._paths, prepared, owner=self._owner)

        # Release against the old configuration, then switch.  The engine is
        # frozen, so the encoder loop cannot flush an old delta between these
        # steps.
        self._engine.cleanup()
        self._engine.swap_config(candidate)
        self._config = candidate
        self._generation += 1
        if self._client is not None:
            self._client.apply_config(candidate)
        LOGGER.info("Konfiguration angewendet, Generation %d", self._generation)

        if changed and self._client is not None:
            await self._client.reconnect()
        return self._config

    async def _run(self, action: Callable[[], Any]) -> Any:
        if self._lock.locked():
            raise ApplyBusy("Ein anderes Apply läuft bereits")
        async with self._lock:
            self._engine.freeze()
            try:
                return await action()
            finally:
                self._engine.unfreeze()

    async def apply(
        self, patch: Mapping[str, Any], *, password: str | None = None
    ) -> AppConfig:
        """Validate, persist and activate ``patch`` as a new generation.

        ``password`` is the write-only MA2 password from the UI; it is tested
        with the candidate credentials and written to the state directory, but
        never added to the TOML patch or returned.

        Raises :class:`ApplyBusy` when another apply is still running,
        :class:`ma2pi.config.ConfigError` for an invalid configuration and the
        client's connection errors when new credentials do not work.  In all
        failure cases the active configuration and session stay untouched.
        """

        async def run() -> AppConfig:
            prepared = prepare_patch(
                self._paths,
                self._clean_patch(patch, password),
                owner=self._owner,
                validate=self._validate,
            )
            return await self._activate(prepared, test=True, password=password)

        return await self._run(run)

    async def restore(self, backup_id: str) -> AppConfig:
        """Validate and activate a backup, then reconnect if needed.

        An invalid backup leaves the active configuration untouched.  A
        restored credential set is applied even when the onPC is currently
        unreachable; the regular reconnect then keeps retrying in the
        background.
        """

        async def run() -> AppConfig:
            prepared = self._prepare_restore(backup_id)
            return await self._activate(prepared, test=False)

        return await self._run(run)
