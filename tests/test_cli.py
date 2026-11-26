from __future__ import annotations

import pytest

from ma2pi import PRODUCT_NAME
from ma2pi.__main__ import main


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert PRODUCT_NAME in capsys.readouterr().out


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


async def test_run_daemon_shutdown_leaves_no_ma2pi_tasks(monkeypatch, make_config):
    import asyncio
    from ma2pi import __main__ as main_mod

    cfg = make_config(lambda d: d["led"].update({"enabled": False}))
    monkeypatch.setattr(main_mod, "_start_web", lambda *a, **kw: asyncio.sleep(0))
    monkeypatch.setattr("ma2pi.hid_input.EvdevSource.list_devices", lambda self: [])
    monkeypatch.setattr("ma2pi.midi_input.list_midi_devices", lambda: [])

    stop_holder: list[asyncio.Event] = []
    orig_event = main_mod.asyncio.Event

    class CapturingEvent(asyncio.Event):
        def __init__(self) -> None:
            super().__init__()
            stop_holder.append(self)

    monkeypatch.setattr(main_mod.asyncio, "Event", CapturingEvent)
    daemon_task = asyncio.create_task(main_mod.run_daemon(cfg, dry_run=True))
    await asyncio.sleep(0.05)
    for ev in stop_holder:
        ev.set()
    rc = await asyncio.wait_for(daemon_task, timeout=3.0)
    assert rc == 0
    leaked = [
        t.get_name()
        for t in asyncio.all_tasks()
        if t is not asyncio.current_task() and t.get_name().startswith("ma2pi-") and not t.done()
    ]
    assert leaked == []
