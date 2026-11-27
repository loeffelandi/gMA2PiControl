"""Shutdown chord, power service, API and the input path."""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from ma2pi.__main__ import _process_input, _status_snapshot
from ma2pi.config import ConfigError, PowerSettings
from ma2pi.events import DeviceLost, InputEvent
from ma2pi.power import (
    PASS,
    PowerDisabled,
    PowerService,
    PowerUnavailable,
    ShutdownCombo,
    ShutdownPending,
)
from ma2pi.web import create_app


def key(control: str, value: int, device: str = "cherry") -> InputEvent:
    return InputEvent("key", control, value, device)


def press(control: str, device: str = "cherry") -> InputEvent:
    return key(control, 1, device)


def release(control: str, device: str = "cherry") -> InputEvent:
    return key(control, 0, device)


class Harness:
    """A chord plus the events it reports."""

    def __init__(self, **overrides) -> None:
        self.events: list[tuple[str, dict]] = []
        self.settings = dataclasses.replace(PowerSettings(), **overrides)
        self.combo = ShutdownCombo(
            self.settings,
            listener=lambda name, info: self.events.append((name, info)),
        )

    def names(self) -> list[str]:
        return [name for name, _ in self.events]

    def hold(self) -> InputEvent:
        """Hold MA + Off; returns the withheld Off press."""

        assert self.combo.feed(press("ma")) == PASS
        withheld = press("off")
        assert self.combo.feed(withheld).swallow
        assert self.combo.phase == ShutdownCombo.HOLDING
        return withheld


# -- chord state machine ------------------------------------------------------


def test_unrelated_keys_pass_untouched():
    h = Harness()
    for event in (press("fix"), release("fix"), press("please_big"), release("please_big")):
        result = h.combo.feed(event)
        assert not result.swallow and result.forward == ()
    assert h.combo.phase == ShutdownCombo.IDLE
    assert h.events == []


def test_non_key_events_pass():
    h = Harness()
    assert not h.combo.feed(InputEvent("encoder", "encoder.1", 3, "cherry")).swallow
    assert not h.combo.feed(InputEvent("value", "mc_fader_1", 0.5, "midi")).swallow


def test_first_chord_key_passes_second_is_withheld():
    h = Harness()
    first = h.combo.feed(press("ma"))
    assert not first.swallow and first.forward == ()
    assert h.combo.feed(press("off")).swallow
    assert h.combo.phase == ShutdownCombo.HOLDING


def test_chord_order_does_not_matter():
    h = Harness()
    assert not h.combo.feed(press("off")).swallow
    assert h.combo.feed(press("ma")).swallow
    assert h.combo.phase == ShutdownCombo.HOLDING


def test_holding_has_no_time_limit():
    h = Harness()
    h.hold()
    # Nothing but key events changes the state; there is no clock at all.
    assert h.combo.phase == ShutdownCombo.HOLDING
    assert h.events == []
    assert h.combo.feed(press("please_big")).swallow
    assert h.combo.feed(release("please_big")).swallow
    assert h.combo.feed(press("please_big")).swallow
    assert h.names() == ["progress", "confirmed"]


def test_double_please_while_holding_confirms():
    h = Harness()
    h.hold()

    assert h.combo.feed(press("please_big")).swallow
    assert h.combo.feed(release("please_big")).swallow
    assert h.events == [("progress", {"remaining": 1})]

    assert h.combo.feed(press("please_big")).swallow
    assert h.names() == ["progress", "confirmed"]
    assert h.combo.phase == ShutdownCombo.IDLE
    # Every release is handled: Please and the withheld Off are swallowed,
    # MA reaches the engine because its press did.
    assert h.combo.feed(release("please_big")).swallow
    assert h.combo.feed(release("off")).swallow
    assert not h.combo.feed(release("ma")).swallow
    # Afterwards Please is an ordinary key again.
    assert not h.combo.feed(press("please_big")).swallow


def test_please_without_the_chord_is_ordinary():
    h = Harness()
    h.combo.feed(press("ma"))
    assert not h.combo.feed(press("please_big")).swallow
    assert not h.combo.feed(press("please_big")).swallow
    assert h.events == []


def test_single_please_does_not_trigger():
    h = Harness()
    h.hold()
    h.combo.feed(press("please_big"))
    h.combo.feed(release("please_big"))
    assert "confirmed" not in h.names()
    assert h.combo.phase == ShutdownCombo.HOLDING


def test_releasing_before_any_please_replays_the_withheld_press():
    h = Harness()
    withheld = h.hold()
    # Releasing the *other* chord key: Off is handed back as a press.
    result = h.combo.feed(release("ma"))
    assert not result.swallow
    assert result.forward == (withheld,)
    assert h.combo.phase == ShutdownCombo.IDLE
    # The release of Off now travels normally.
    assert h.combo.feed(release("off")) == PASS
    assert h.events == []


def test_releasing_the_withheld_key_first_replays_press_before_release():
    h = Harness()
    withheld = h.hold()
    result = h.combo.feed(release("off"))
    assert not result.swallow
    assert result.forward == (withheld,)
    assert h.combo.feed(release("ma")).forward == ()


def test_releasing_after_one_please_cancels_and_drops_the_withheld_key():
    h = Harness()
    h.hold()
    h.combo.feed(press("please_big"))
    h.combo.feed(release("please_big"))
    result = h.combo.feed(release("ma"))
    assert not result.swallow
    # Off never reaches the console, not even as a late press.
    assert result.forward == ()
    assert h.combo.phase == ShutdownCombo.IDLE
    assert h.names() == ["progress", "cancelled"]
    assert h.combo.feed(release("off")).swallow
    # The counter starts over for the next hold.
    h.hold()
    h.combo.feed(press("please_big"))
    assert h.events[-1] == ("progress", {"remaining": 1})


def test_swallowed_release_still_clears_the_held_state():
    h = Harness()
    h.hold()
    h.combo.feed(release("ma"))  # cancels without a Please: Off is replayed
    h.combo.feed(release("off"))
    # Off is up, so MA alone must not look like a complete chord.
    assert h.combo.feed(press("ma")) == PASS
    assert h.combo.phase == ShutdownCombo.IDLE


def test_foreign_press_while_holding_aborts_and_replays():
    h = Harness()
    withheld = h.hold()
    result = h.combo.feed(press("fix"))
    assert not result.swallow
    assert result.forward == (withheld,)
    assert h.combo.phase == ShutdownCombo.IDLE


def test_foreign_press_after_one_please_cancels_without_replay():
    h = Harness()
    h.hold()
    h.combo.feed(press("please_big"))
    result = h.combo.feed(press("fix"))
    assert not result.swallow and result.forward == ()
    assert h.names() == ["progress", "cancelled"]


def test_encoder_turn_does_not_cancel():
    h = Harness()
    h.hold()
    h.combo.feed(InputEvent("encoder", "encoder.1", 1, "cherry"))
    assert h.combo.phase == ShutdownCombo.HOLDING


def test_reset_clears_key_state():
    h = Harness()
    h.hold()
    h.combo.feed(press("please_big"))
    h.combo.reset()
    assert h.combo.phase == ShutdownCombo.IDLE
    assert h.names() == ["progress", "cancelled"]
    assert not h.combo.feed(press("please_big")).swallow
    # Nothing is held any more, so Off alone does not complete the chord.
    assert not h.combo.feed(press("off")).swallow


def test_confirm_presses_setting():
    h = Harness(confirm_presses=1)
    h.hold()
    h.combo.feed(press("please_big"))
    assert h.names() == ["confirmed"]


def test_three_confirm_presses():
    h = Harness(confirm_presses=3)
    h.hold()
    for _ in range(2):
        h.combo.feed(press("please_big"))
        h.combo.feed(release("please_big"))
    assert "confirmed" not in h.names()
    h.combo.feed(press("please_big"))
    assert h.names() == ["progress", "progress", "confirmed"]


def test_chord_works_across_devices():
    h = Harness()
    h.combo.feed(press("ma", "cherry"))
    assert h.combo.feed(press("off", "other")).swallow


def test_listener_errors_do_not_break_input():
    def boom(name, info):
        raise RuntimeError("kaputt")

    combo = ShutdownCombo(PowerSettings(), listener=boom)
    combo.feed(press("ma"))
    combo.feed(press("off"))
    assert combo.feed(press("please_big")).swallow
    assert combo.phase == ShutdownCombo.HOLDING


# -- power service ------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.calls = 0
        self.fail: Exception | None = None

    async def __call__(self) -> None:
        self.calls += 1
        if self.fail is not None:
            raise self.fail


def make_service(**kwargs):
    recorder = kwargs.pop("executor", None) or Recorder()
    notices: list[str] = []
    records: list[str] = []
    syncs: list[int] = []
    settings = kwargs.pop("settings", PowerSettings())
    service = PowerService(
        settings,
        executor=recorder,
        notify=notices.append,
        record=records.append,
        delay=0.0,
        sync=lambda: syncs.append(1),
        **kwargs,
    )
    return service, recorder, notices, records, syncs


async def settle(service: PowerService) -> None:
    for _ in range(100):
        if not service._tasks:
            return
        await asyncio.sleep(0.005)
    raise AssertionError("shutdown task did not finish")


async def test_shutdown_syncs_notifies_and_powers_off():
    service, recorder, notices, records, syncs = make_service()
    await service.shutdown("Test")
    assert service.status()["state"] == "shutting_down"
    await settle(service)
    assert recorder.calls == 1
    assert syncs == [1]
    assert notices == ["gMA2PiControl: Pi faehrt jetzt herunter"]
    assert any("Test" in line for line in records)
    # The machine is going down, the state stays.
    assert service.status()["state"] == "shutting_down"


async def test_second_shutdown_is_rejected():
    service, recorder, *_ = make_service()
    await service.shutdown("a")
    with pytest.raises(ShutdownPending):
        await service.shutdown("b")
    await settle(service)
    assert recorder.calls == 1


async def test_failed_poweroff_resets_state_and_reports():
    recorder = Recorder()
    recorder.fail = RuntimeError("polkit sagt nein")
    service, _, notices, *_ = make_service(executor=recorder)
    await service.shutdown("Test")
    await settle(service)
    status = service.status()
    assert status["state"] == "idle"
    assert status["error"] == "polkit sagt nein"
    assert notices[-1] == "gMA2PiControl: Herunterfahren fehlgeschlagen"
    # A new attempt is possible.
    recorder.fail = None
    await service.shutdown("Test")
    await settle(service)
    assert recorder.calls == 2
    assert service.status()["error"] is None


async def test_disabled_service_refuses():
    service, recorder, *_ = make_service(
        settings=dataclasses.replace(PowerSettings(), enabled=False)
    )
    assert service.status()["available"] is False
    with pytest.raises(PowerDisabled):
        await service.shutdown("Test")
    assert recorder.calls == 0


async def test_unavailable_host_refuses(monkeypatch):
    monkeypatch.setattr("ma2pi.power._can_power_off", lambda: False)
    service = PowerService(PowerSettings())
    assert service.available is False
    with pytest.raises(PowerUnavailable):
        await service.shutdown("Test")


async def test_dry_run_never_powers_off():
    service, recorder, *_ = make_service(dry_run=True)
    await service.shutdown("Test")
    await settle(service)
    assert recorder.calls == 0
    assert service.status()["state"] == "idle"


async def test_console_notice_can_be_silenced():
    service, _, notices, *_ = make_service(
        settings=dataclasses.replace(PowerSettings(), console_notice=False)
    )
    await service.shutdown("Test")
    await settle(service)
    assert notices == []


async def test_chord_confirmation_triggers_shutdown_and_notifies():
    service, recorder, notices, *_ = make_service()

    assert not service.filter(press("ma")).swallow
    assert service.filter(press("off")).swallow
    assert service.status()["state"] == "holding"
    assert service.status()["confirm_remaining"] == 2

    assert service.filter(press("please_big")).swallow
    assert notices[-1] == "gMA2PiControl: Pi ausschalten? Please noch 1x"
    assert service.status()["confirm_remaining"] == 1
    assert recorder.calls == 0
    assert service.filter(press("please_big")).swallow
    await settle(service)
    assert recorder.calls == 1


async def test_cancel_notifies():
    service, recorder, notices, *_ = make_service()
    service.filter(press("ma"))
    service.filter(press("off"))
    service.filter(press("please_big"))
    service.filter(release("ma"))
    assert notices[-1] == "gMA2PiControl: Ausschalten abgebrochen"
    assert service.status()["state"] == "idle"
    assert recorder.calls == 0


async def test_combo_off_lets_everything_pass():
    service, *_ = make_service(
        settings=dataclasses.replace(PowerSettings(), combo=False)
    )
    service.filter(press("ma"))
    assert not service.filter(press("off")).swallow
    assert service.status()["combo"] is False


# -- configuration ------------------------------------------------------------


def test_example_config_has_power_defaults(config):
    assert config.power == PowerSettings()


def test_power_section_is_validated(make_config):
    def set_power(**values):
        def mutate(data):
            data["power"] = values

        return mutate

    for bad in (
        {"hold_controls": ["ma"]},
        {"hold_controls": ["ma", "ma"]},
        {"hold_controls": "ma"},
        {"hold_controls": ["ma", "off"], "confirm_control": "off"},
        {"confirm_presses": 0},
        {"confirm_presses": 6},
        {"hold_seconds": 2},
        {"confirm_window": 10},
        {"hold_controls": ["ma", "gibt_es_nicht"]},
        {"confirm_control": "gibt_es_nicht"},
        {"unbekannt": 1},
        {"enabled": "ja"},
    ):
        with pytest.raises(ConfigError):
            make_config(set_power(**bad))


def test_power_section_may_be_omitted(make_config):
    config = make_config(lambda data: data.pop("power"))
    assert config.power == PowerSettings()


def test_power_section_overrides(make_config):
    config = make_config(
        lambda data: data.update(
            power={
                "enabled": False,
                "hold_controls": ["ma", "fix"],
                "confirm_control": "go_plus",
                "confirm_presses": 3,
            }
        )
    )
    assert config.power.enabled is False
    assert config.power.hold_controls == ("ma", "fix")
    assert config.power.confirm_presses == 3
    assert config.power.confirm_presses == 3


# -- web API ------------------------------------------------------------------

HEADERS = {"X-Ma2pi-Request": "1"}


@pytest.fixture
async def api(config):
    service, recorder, *_ = make_service()
    client = TestClient(
        TestServer(
            create_app(config, dist_dir=Path("/nonexistent"), power_service=service)
        )
    )
    await client.start_server()
    client.service = service
    client.recorder = recorder
    yield client
    await client.close()


async def test_get_power_reports_status(api):
    response = await api.get("/api/power")
    assert response.status == 200
    body = await response.json()
    assert body["state"] == "idle"
    assert body["enabled"] is True
    assert body["available"] is True


async def test_shutdown_requires_confirmation(api):
    response = await api.post("/api/power/shutdown", json={}, headers=HEADERS)
    assert response.status == 422
    assert (await response.json())["error"] == "confirmation_required"
    response = await api.post(
        "/api/power/shutdown", json={"confirm": "yes"}, headers=HEADERS
    )
    assert response.status == 422
    assert api.recorder.calls == 0


async def test_shutdown_requires_request_header(api):
    response = await api.post("/api/power/shutdown", json={"confirm": True})
    assert response.status == 403
    assert api.recorder.calls == 0


async def test_shutdown_accepts_and_powers_off(api):
    response = await api.post(
        "/api/power/shutdown", json={"confirm": True}, headers=HEADERS
    )
    assert response.status == 202
    assert (await response.json())["state"] == "shutting_down"
    await settle(api.service)
    assert api.recorder.calls == 1

    again = await api.post(
        "/api/power/shutdown", json={"confirm": True}, headers=HEADERS
    )
    assert again.status == 409
    assert (await again.json())["error"] == "shutdown_pending"


async def test_shutdown_disabled_is_forbidden(config):
    service, recorder, *_ = make_service(
        settings=dataclasses.replace(PowerSettings(), enabled=False)
    )
    client = TestClient(
        TestServer(
            create_app(config, dist_dir=Path("/nonexistent"), power_service=service)
        )
    )
    await client.start_server()
    try:
        response = await client.post(
            "/api/power/shutdown", json={"confirm": True}, headers=HEADERS
        )
        assert response.status == 403
        assert (await response.json())["error"] == "power_disabled"
        assert recorder.calls == 0
    finally:
        await client.close()


async def test_shutdown_without_service_is_unavailable(config):
    client = TestClient(TestServer(create_app(config, dist_dir=Path("/nonexistent"))))
    await client.start_server()
    try:
        assert (await client.get("/api/power")).status == 503
        response = await client.post(
            "/api/power/shutdown", json={"confirm": True}, headers=HEADERS
        )
        assert response.status == 503
    finally:
        await client.close()


async def test_shutdown_needs_the_pin_when_enabled(config):
    pinned = dataclasses.replace(
        config, web=dataclasses.replace(config.web, pin_enabled=True, pin="1234")
    )
    service, recorder, *_ = make_service()
    client = TestClient(
        TestServer(
            create_app(pinned, dist_dir=Path("/nonexistent"), power_service=service)
        )
    )
    await client.start_server()
    try:
        response = await client.post(
            "/api/power/shutdown", json={"confirm": True}, headers=HEADERS
        )
        assert response.status == 401
        assert recorder.calls == 0
    finally:
        await client.close()


# -- input path ---------------------------------------------------------------


class StubEngine:
    def __init__(self) -> None:
        self.handled: list[InputEvent] = []
        self.released: list[str] = []

    def handle(self, event: InputEvent) -> None:
        self.handled.append(event)

    def release_device(self, device: str) -> None:
        self.released.append(device)


class StubLearn:
    active = False

    def cancel(self):
        return None

    def feed(self, item):
        return None


async def drain(queue: asyncio.Queue) -> None:
    for _ in range(200):
        if queue.empty():
            await asyncio.sleep(0.01)
            return
        await asyncio.sleep(0.005)
    raise AssertionError("queue not drained")


async def run_input(events, power, learn=None, engine=None):
    engine = engine or StubEngine()
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _process_input(
            queue, engine, learn or StubLearn(), None, None, None, None, power
        )
    )
    try:
        for event in events:
            await queue.put(event)
        await drain(queue)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return engine


async def test_input_path_hides_chord_and_confirm_from_the_engine():
    service, recorder, *_ = make_service()
    events = [
        press("ma"),
        press("off"),
        press("please_big"),
        release("please_big"),
        press("please_big"),
        release("please_big"),
        release("off"),
        release("ma"),
    ]
    engine = await run_input(events, service)
    await settle(service)
    assert recorder.calls == 1
    # MA reached the console (press and release); Off, its release and every
    # Please were held back.
    assert engine.handled == [press("ma"), release("ma")]


async def test_input_path_replays_an_abandoned_chord():
    service, *_ = make_service()
    engine = await run_input(
        [press("ma"), press("off"), release("off"), release("ma")], service
    )
    assert engine.handled == [
        press("ma"),
        press("off"),
        release("off"),
        release("ma"),
    ]


async def test_input_path_without_power_is_unchanged():
    engine = await run_input([press("ma"), press("off")], None)
    assert engine.handled == [press("ma"), press("off")]


async def test_learn_and_device_loss_reset_the_chord():
    service, *_ = make_service()

    class ActiveLearn(StubLearn):
        active = True

    engine = await run_input([press("ma"), press("off")], service, learn=ActiveLearn())
    assert engine.handled == []
    assert service.status()["state"] == "idle"
    # Nothing is held any more, so Off alone does not complete the chord.
    assert not service.filter(press("off")).swallow

    service.filter(press("ma"))
    assert service.filter(press("fix")).swallow is False
    engine = await run_input([DeviceLost("cherry")], service)
    assert engine.released == ["cherry"]


# -- status -------------------------------------------------------------------


class StatusClient:
    connected = False
    authenticated = False
    session = None
    queue: list = []
    screen_mode = False
    frames_sent = 0
    last_frame_types: list = []
    reconnects = 0
    last_error = None

    class limiter:
        effective_rate = 25


def test_status_snapshot_carries_power_state():
    service, *_ = make_service()
    snapshot = _status_snapshot(StatusClient(), power=service)
    assert snapshot["power"]["state"] == "idle"
    assert snapshot["power"]["available"] is True
    bare = _status_snapshot(StatusClient())
    assert bare["power"] == {"enabled": False, "available": False, "state": "idle"}
