"""Tests for the writable configuration store and its one-time migration."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from ma2pi.config import DEFAULT_CONFIG_PATHS, load_config
from ma2pi.config_store import (
    CONFIG_MODE,
    PASSWORD_MODE,
    ConfigPaths,
    ensure_layout,
    migrate,
)

LEGACY_CONFIG = """\
schema_version = 1

[ma2]
host = "10.0.0.5"           # Kommentar bleibt erhalten
port = 80
path = "/?ma=1"
username = "svt"
password_file = "{password}"
hardkey_transport = "native"

[logging]
level = "INFO"

[devices.cherry]
vendor_id = 0x046a
product_id = 0x0038
name_contains = "Cherry"
profile = "cherry-g86"

[profiles.cherry-g86.keys]
KEY_F1 = "fix"

[mapping.keys]
fix = {{ hardkey = "Fix" }}
"""


def _paths(tmp_path: Path) -> ConfigPaths:
    return ConfigPaths(state_dir=tmp_path / "state", etc_dir=tmp_path / "etc")


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_state_path_is_first_default():
    assert DEFAULT_CONFIG_PATHS[0] == Path("/var/lib/ma2pi/config.toml")


def test_ensure_layout_creates_dirs_and_fixes_modes(tmp_path):
    paths = _paths(tmp_path)
    paths.state_dir.mkdir(parents=True)
    paths.config.write_text("schema_version = 1\n", encoding="utf-8")
    paths.password.write_text("", encoding="utf-8")
    os.chmod(paths.config, 0o666)
    os.chmod(paths.password, 0o666)

    ensure_layout(paths)

    assert paths.backups.is_dir()
    assert _mode(paths.state_dir) == 0o750
    assert _mode(paths.config) == CONFIG_MODE
    assert _mode(paths.password) == PASSWORD_MODE


def test_migrate_config_only(tmp_path):
    paths = _paths(tmp_path)
    paths.etc_dir.mkdir(parents=True)
    legacy = LEGACY_CONFIG.format(password="/etc/ma2pi/ma2pi.password")
    paths.legacy_config.write_text(legacy, encoding="utf-8")

    assert migrate(paths) is True
    assert paths.config.is_file()
    assert _mode(paths.config) == CONFIG_MODE
    assert list(paths.backups.glob("config-*.toml"))
    # No password file existed, so none is invented.
    assert not paths.password.exists()


def test_migrate_is_one_time(tmp_path):
    paths = _paths(tmp_path)
    paths.etc_dir.mkdir(parents=True)
    paths.legacy_config.write_text(LEGACY_CONFIG.format(password="x"), encoding="utf-8")

    assert migrate(paths) is True
    before = paths.config.read_bytes()
    paths.config.write_text("schema_version = 1\n", encoding="utf-8")
    changed = paths.config.read_bytes()

    assert migrate(paths) is False
    assert paths.config.read_bytes() == changed
    assert before != changed


def test_migrate_with_password_rewrites_path_and_keeps_comments(tmp_path):
    paths = _paths(tmp_path)
    paths.etc_dir.mkdir(parents=True)
    paths.legacy_config.write_text(
        LEGACY_CONFIG.format(password=str(paths.legacy_password)), encoding="utf-8"
    )
    paths.legacy_password.write_text("geheim", encoding="utf-8")
    os.chmod(paths.legacy_password, 0o644)

    assert migrate(paths) is True
    assert paths.password.read_text(encoding="utf-8") == "geheim"
    assert _mode(paths.password) == PASSWORD_MODE

    text = paths.config.read_text(encoding="utf-8")
    assert str(paths.password) in text
    assert "Kommentar bleibt erhalten" in text
    # The migrated file must still be schema-valid.
    config = load_config(paths.config)
    assert config.ma2.host == "10.0.0.5"
    assert config.ma2.password_file == str(paths.password)


def test_migrate_without_legacy_config_is_noop(tmp_path):
    paths = _paths(tmp_path)
    assert migrate(paths) is False
    assert not paths.config.exists()


# --- 2.2: atomic writes, merge patches and backups --------------------------


def _write_config(paths: ConfigPaths) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.config.write_text(
        LEGACY_CONFIG.format(password=str(paths.password)), encoding="utf-8"
    )


def test_merge_patch_semantics():
    from ma2pi.config_store import merge_patch

    target = {"a": 1, "b": {"c": 2, "d": 3}, "list": [1, 2]}
    merge_patch(
        target,
        {"a": None, "b": {"c": 9, "e": 4}, "list": [3], "new": "x"},
    )
    assert target == {"b": {"c": 9, "d": 3, "e": 4}, "list": [3], "new": "x"}


def test_apply_patch_preserves_comments(tmp_path):
    from ma2pi.config_store import apply_patch

    paths = _paths(tmp_path)
    _write_config(paths)

    apply_patch(paths, {"ma2": {"host": "10.9.9.9"}})

    text = paths.config.read_text(encoding="utf-8")
    assert 'host = "10.9.9.9"' in text
    assert "Kommentar bleibt erhalten" in text
    assert load_config(paths.config).ma2.host == "10.9.9.9"


def test_apply_patch_creates_backup_and_last_good(tmp_path):
    from ma2pi.config_store import LAST_GOOD, apply_patch

    paths = _paths(tmp_path)
    _write_config(paths)
    before = paths.config.read_text(encoding="utf-8")

    apply_patch(paths, {"logging": {"level": "DEBUG"}})

    backups = list(paths.backups.glob("config-*.toml"))
    assert backups
    assert backups[0].read_text(encoding="utf-8") == before
    assert (paths.backups / LAST_GOOD).read_text(encoding="utf-8") == before
    assert load_config(paths.config).logging.level == "DEBUG"


def test_apply_patch_aborts_without_partial_write(tmp_path, monkeypatch):
    import ma2pi.config_store as store

    paths = _paths(tmp_path)
    _write_config(paths)
    before = paths.config.read_bytes()

    def boom(*_args, **_kwargs):
        raise OSError("simulierter Abbruch")

    monkeypatch.setattr(store.os, "replace", boom)

    try:
        store.apply_patch(paths, {"logging": {"level": "ERROR"}})
    except OSError:
        pass
    else:  # pragma: no cover - the abort must be visible
        raise AssertionError("Abbruch wurde nicht durchgereicht")

    assert paths.config.read_bytes() == before
    assert not list(paths.state_dir.glob(".config.toml.tmp"))


def test_apply_patch_rejects_invalid_before_writing(tmp_path):
    from ma2pi.config import ConfigError, parse_config
    from ma2pi.config_store import apply_patch

    paths = _paths(tmp_path)
    _write_config(paths)
    before = paths.config.read_bytes()

    def validate(candidate):
        return parse_config(candidate, source_path="<test>")

    try:
        apply_patch(paths, {"ma2": {"port": 70000}}, validate=validate)
    except ConfigError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Validierungsfehler wurde nicht durchgereicht")

    assert paths.config.read_bytes() == before
    assert not list(paths.backups.glob("config-*.toml"))


def test_rotate_backups_keeps_newest(tmp_path):
    from ma2pi.config_store import rotate_backups

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index in range(25):
        (backup_dir / f"config-20260101-0000{index:02d}.toml").write_text("x")

    rotate_backups(backup_dir, keep=20)

    remaining = sorted(name.name for name in backup_dir.glob("config-*.toml"))
    assert len(remaining) == 20
    assert remaining[0] == "config-20260101-000005.toml"
    assert remaining[-1] == "config-20260101-000024.toml"
