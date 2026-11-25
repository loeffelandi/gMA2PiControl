from __future__ import annotations

import pytest

from ma2pi.__main__ import main


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "ma2pi" in capsys.readouterr().out


def test_check_config_exit_zero(config, capsys):
    assert main(["--config", str(config.source_path), "--check-config"]) == 0
    assert "gültig" in capsys.readouterr().out


def test_check_config_error(tmp_path, capsys):
    path = tmp_path / "bad.toml"
    path.write_text("schema_version = 2\n", encoding="utf-8")
    assert main(["--config", str(path), "--check-config"]) == 2
    assert "Konfigurationsfehler" in capsys.readouterr().err


def test_list_devices(monkeypatch, config, capsys):
    from ma2pi.hid_input import DeviceInfo

    monkeypatch.setattr(
        "ma2pi.__main__.list_devices",
        lambda: [DeviceInfo("/dev/input/event1", "Cherry", 0x046A, 0x0001, frozenset({"KEY_F1"}))],
    )
    assert main(["--config", str(config.source_path), "--list-devices"]) == 0
    out = capsys.readouterr().out
    assert "event1" in out
    assert "0x046a" in out


def test_dump_input_delegates(monkeypatch, config):
    async def fake(config):
        return 0

    monkeypatch.setattr("ma2pi.__main__.run_dump_input", fake)
    assert main(["--config", str(config.source_path), "--dump-input"]) == 0
