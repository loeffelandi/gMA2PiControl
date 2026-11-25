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


def _rewrite_password_path(config: Path, password: Path) -> bool:
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
    config.write_text(tomlkit.dumps(document), encoding="utf-8")
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
        _rewrite_password_path(paths.config, paths.password)

    LOGGER.info("Konfiguration von %s nach %s migriert", paths.etc_dir, paths.state_dir)
    return True
