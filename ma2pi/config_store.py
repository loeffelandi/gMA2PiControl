"""Configuration storage: paths, permissions and one-time migration.

The active configuration lives in ``/var/lib/ma2pi`` because the daemon needs a
writable location for hot reload and backups, while the systemd unit keeps
``ProtectSystem=strict``.  ``/etc/ma2pi`` is only the legacy/initial location and
is migrated once.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

LOGGER = logging.getLogger("ma2pi.config_store")

DEFAULT_STATE_DIR = Path("/var/lib/ma2pi")
DEFAULT_ETC_DIR = Path("/etc/ma2pi")

CONFIG_MODE = 0o640
PASSWORD_MODE = 0o600
DIR_MODE = 0o750


@dataclass(frozen=True, slots=True)
class ConfigPaths:
    """All paths the daemon reads or writes for its configuration."""

    state_dir: Path = DEFAULT_STATE_DIR
    etc_dir: Path = DEFAULT_ETC_DIR

    @property
    def config(self) -> Path:
        return self.state_dir / "config.toml"

    @property
    def password(self) -> Path:
        return self.state_dir / "ma2pi.password"

    @property
    def backups(self) -> Path:
        return self.state_dir / "backups"

    @property
    def legacy_config(self) -> Path:
        return self.etc_dir / "config.toml"

    @property
    def legacy_password(self) -> Path:
        return self.etc_dir / "ma2pi.password"


def _owner_ids(user: str | None) -> tuple[int, int] | None:
    """Resolve ``user`` to (uid, gid); ``None`` when unavailable or not root."""
    if not user or os.geteuid() != 0:
        return None
    try:
        import grp
        import pwd

        entry = pwd.getpwnam(user)
        group = grp.getgrnam(user)
    except KeyError:
        return None
    return entry.pw_uid, group.gr_gid


def _apply(path: Path, mode: int, owner: str | None) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:  # pragma: no cover - depends on filesystem
        LOGGER.warning("chmod %s fehlgeschlagen: %s", path, exc)
    ids = _owner_ids(owner)
    if ids is not None:
        try:
            os.chown(path, *ids)
        except OSError as exc:  # pragma: no cover - depends on filesystem
            LOGGER.warning("chown %s fehlgeschlagen: %s", path, exc)


def ensure_layout(paths: ConfigPaths, *, owner: str | None = "ma2pi") -> None:
    """Create the state and backup directories and fix existing file modes."""

    for directory in (paths.state_dir, paths.backups):
        directory.mkdir(parents=True, exist_ok=True)
        _apply(directory, DIR_MODE, owner)
    for file, mode in ((paths.config, CONFIG_MODE), (paths.password, PASSWORD_MODE)):
        if file.is_file():
            _apply(file, mode, owner)


def _backup(path: Path, destination_dir: Path) -> Path | None:
    if not path.is_file():
        return None
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = destination_dir / f"{path.stem}-{stamp}{path.suffix}"
    suffix = 0
    while target.exists():
        suffix += 1
        target = destination_dir / f"{path.stem}-{stamp}-{suffix}{path.suffix}"
    shutil.copy2(path, target)
    return target


def _rewrite_password_path(
    config: Path, password: Path, owner: str | None = None
) -> bool:
    """Point ``ma2.password_file`` at ``password`` while keeping comments."""
    try:
        import tomlkit
    except ImportError:  # pragma: no cover - tomlkit is a runtime dependency
        return False
    try:
        document = tomlkit.parse(config.read_text(encoding="utf-8"))
    except Exception as exc:  # invalid TOML/search: keep the byte copy
        LOGGER.warning("Passwortpfad nicht angepasst (%s): %s", config, exc)
        return False
    ma2 = document.get("ma2")
    if ma2 is None or "password_file" not in ma2:
        return False
    ma2["password_file"] = str(password)
    _atomic_write(config, tomlkit.dumps(document), CONFIG_MODE, owner)
    return True


def migrate(
    paths: ConfigPaths,
    *,
    owner: str | None = "ma2pi",
    now: datetime | None = None,
) -> bool:
    """Copy a legacy ``/etc/ma2pi`` configuration into the state dir once.

    Returns ``True`` when a migration happened.  Running it again is a no-op,
    which keeps ``install.sh`` idempotent.  The legacy files stay in place; a
    timestamped copy is written to ``backups/`` first.
    """

    if paths.config.exists():
        return False
    if not paths.legacy_config.is_file():
        return False

    paths.backups.mkdir(parents=True, exist_ok=True)
    _apply(paths.backups, DIR_MODE, owner)

    stamped = now or datetime.now()
    backup = _backup(paths.legacy_config, paths.backups)
    if backup is not None:
        LOGGER.info("Altkonfiguration gesichert: %s", backup)

    shutil.copy2(paths.legacy_config, paths.config)
    _apply(paths.config, CONFIG_MODE, owner)

    if paths.legacy_password.is_file():
        _backup(paths.legacy_password, paths.backups)
        shutil.copy2(paths.legacy_password, paths.password)
        _apply(paths.password, PASSWORD_MODE, owner)
        _rewrite_password_path(paths.config, paths.password, owner)

    LOGGER.info("Konfiguration von %s nach %s migriert", paths.etc_dir, paths.state_dir)
    return True


#: How many timestamped backups are kept; ``last-good.toml`` is separate.
MAX_BACKUPS = 20
LAST_GOOD = "last-good.toml"


class ConfigWriteError(RuntimeError):
    """A configuration could not be written safely."""


def merge_patch(target: dict, patch: Mapping[str, Any]) -> dict:
    """Apply an RFC 7386 JSON merge patch to ``target`` in place."""

    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            existing = target.get(key)
            if not isinstance(existing, dict):
                existing = {}
                target[key] = existing
            merge_patch(existing, value)
        else:
            target[key] = value
    return target


def _apply_patch_to_table(table: Any, patch: Mapping[str, Any]) -> None:
    """Apply a merge patch to a tomlkit container, preserving comments."""

    import tomlkit

    for key, value in patch.items():
        if value is None:
            if key in table:
                del table[key]
        elif isinstance(value, dict):
            child = table.get(key)
            if child is None or isinstance(child, (list, tuple)) or not hasattr(
                child, "__setitem__"
            ):
                table[key] = tomlkit.table()
                child = table[key]
            _apply_patch_to_table(child, value)
        else:
            table[key] = value


def _atomic_write(path: Path, text: str, mode: int, owner: str | None) -> None:
    """Write ``text`` via a synced temporary file and an atomic rename."""

    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _apply(tmp, mode, owner)
        try:
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    # Make the rename durable as well.
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def rotate_backups(backup_dir: Path, keep: int = MAX_BACKUPS) -> None:
    """Keep the newest ``keep`` timestamped backups, delete the rest."""

    files = sorted(backup_dir.glob("config-*.toml"))
    if keep <= 0:
        return
    for old in files[:-keep]:
        old.unlink(missing_ok=True)


def apply_patch(
    paths: ConfigPaths,
    patch: Mapping[str, Any],
    *,
    owner: str | None = "ma2pi",
    validate: Callable[[dict[str, Any]], Any] | None = None,
) -> Any:
    """Merge ``patch`` into the active config and write it atomically.

    ``validate`` receives the merged plain dict and must raise on invalid
    content; it runs *before* anything is written.  On success the previous
    file is kept in ``backups/`` and as ``last-good.toml``.
    """

    import copy
    import tomlkit

    ensure_layout(paths, owner=owner)
    if not paths.config.is_file():
        raise ConfigWriteError(f"Konfiguration {paths.config} fehlt")

    document = tomlkit.parse(paths.config.read_text(encoding="utf-8"))
    candidate = merge_patch(copy.deepcopy(dict(document.unwrap())), patch)

    result = validate(candidate) if validate is not None else candidate

    _apply_patch_to_table(document, patch)
    text = tomlkit.dumps(document)

    _backup(paths.config, paths.backups)
    paths.backups.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths.config, paths.backups / LAST_GOOD)
    rotate_backups(paths.backups)

    _atomic_write(paths.config, text, CONFIG_MODE, owner)
    LOGGER.info("Konfiguration atomar geschrieben: %s", paths.config)
    return result
