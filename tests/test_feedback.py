from __future__ import annotations

import asyncio

import pytest

from ma2pi.feedback import (
    ExecutorFeedback,
    LedTarget,
    PALETTE,
    RequestBlock,
    _belongs_to_block,
    _block_key,
    build_feedback_targets,
    led_velocity,
    nearest_color,
    palette_index,
    parse_playbacks,
)


def playbacks_payload(
    page: int, items_type: int, executors: list[dict]
) -> dict:
    return {
        "responseType": "playbacks",
        "iPage": page,
        "itemGroups": [
            {"itemsType": items_type, "items": [executors]},
        ],
    }


class FakeClient:
    authenticated = True

    def __init__(self, responses: list[dict]) -> None:
        self.playback_responses: asyncio.Queue = asyncio.Queue()
        self._responses = list(responses)
        self.requests: list[tuple] = []

    def request_playbacks(self, page, start, count, items_type, view) -> None:
        self.requests.append((page, start, count, items_type, view))
        if self._responses:
            self.playback_responses.put_nowait(self._responses.pop(0))


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def drain(feedback: ExecutorFeedback, clock: FakeClock) -> None:
    """Pump until every queued frame has left, advancing the fake clock."""

    for _ in range(200):
        delay = feedback.pump()
        if delay is None:
            return
        clock.now += delay
    raise AssertionError("LED output did not drain")


class FakeMidi:
    def __init__(self, accept: bool = True, clock: FakeClock | None = None) -> None:
        self.open_devices = {"midicraft-enc": "/dev/snd/midiC4D0"}
        self.accept = accept
        self.sent: list[tuple[str, bytes]] = []
        self.times: list[float] = []
        self.pending: dict[str, int | None] = {}
        self._clock = clock

    def send(self, device: str, data: bytes) -> bool:
        if not self.accept:
            return False
        self.sent.append((device, data))
        if self._clock is not None:
            self.times.append(self._clock.now)
        return True

    def output_pending(self, device: str) -> int | None:
        return self.pending.get(device, 0)


def _enable_enc_leds(data: dict) -> None:
    # The shipped example keeps the ENC LEDs off until they are measured.
    data["profiles"]["midicraft-enc"]["led_feedback"]["enabled"] = True


@pytest.fixture
def make_config(raw_config):
    import copy

    from ma2pi.config import parse_config

    def _make(mutator=None):
        data = copy.deepcopy(raw_config)
        _enable_enc_leds(data)
        if mutator is not None:
            mutator(data)
        return parse_config(data, source_path="<test>")

    return _make


@pytest.fixture
def config(make_config):
    return make_config()


def test_palette_order_matches_firmware():
    assert PALETTE[0] == "white"
    assert PALETTE[6] == "seagreen"
    assert PALETTE[-1] == "pink"
    assert palette_index("seagreen") == 6


def test_nearest_color_exact_and_approximate():
    assert nearest_color("#ff0000") == 1
    assert nearest_color("00ff00") == 5
    assert nearest_color("#fa0000") == 1
    assert nearest_color(None) is None
    assert nearest_color("#zzz") is None
    assert nearest_color("not-a-colour") is None
    assert nearest_color("#000000") is None


def test_led_velocity_table():
    # bright = 15 + index, dark = 1 + index, off = 0
    assert led_velocity(True, 6, "dark", 0) == 21
    assert led_velocity(False, 0, "dark", 0) == 1
    assert led_velocity(False, 0, "off", 0) == 0
    assert led_velocity(True, None, "dark", 0) == 15
    assert led_velocity(False, None, "dark", 0) == 1


def test_parse_playbacks_reads_state_and_colour():
    payload = playbacks_payload(
        2,
        2,
        [
            {"iExec": 0, "isRun": True, "bC": "#ff0000"},
            {"iExec": 1, "isRun": False, "bdC": "#00ff00"},
            {"iExec": 2, "isRun": False},
        ],
    )
    snapshot = parse_playbacks(payload)
    assert snapshot is not None
    assert snapshot.page == 2
    assert snapshot.items_type == 2
    assert snapshot.executors[1].running is True
    assert snapshot.executors[1].color == 1
    assert snapshot.executors[2].running is False
    assert snapshot.executors[2].color == 5
    assert snapshot.executors[3].color is None


def test_parse_playbacks_handles_nested_bottom_buttons():
    payload = {
        "responseType": "playbacks",
        "iPage": 1,
        "itemGroups": [
            {
                "itemsType": 3,
                "items": [[[{"iExec": 100, "isRun": True, "bC": "#0000ff"}]]],
            }
        ],
    }
    snapshot = parse_playbacks(payload)
    assert snapshot is not None
    assert snapshot.items_type == 3
    assert snapshot.executors[101].running is True
    assert snapshot.executors[101].color == 9


def test_parse_playbacks_rejects_empty():
    assert parse_playbacks({"responseType": "playbacks"}) is None
    assert parse_playbacks({"iPage": 1, "itemGroups": []}) is None


def test_build_targets_from_example_config(config):
    targets, blocks = build_feedback_targets(config)
    assert len(targets) == 15
    by_control = {target.control: target for target in targets}
    assert by_control["mc_row1_1"] == LedTarget("mc_row1_1", "midicraft-enc", 65, "current", 1)
    assert by_control["mc_row2_3"].note == 77
    assert by_control["mc_row3_5"].executor == 105
    # Encoder clicks have no LED and are excluded by led_notes.
    assert "mc_click_1" not in by_control
    assert blocks[("current", 0)].start == 0
    assert blocks[("current", 0)].count == 5
    assert blocks[("current", 0)].items_type == 2
    assert blocks[("current", 100)].start == 100
    assert blocks[("current", 100)].count == 5
    assert blocks[("current", 100)].items_type == 3


def test_targets_require_led_feedback_and_button_kind(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"].pop("led_feedback")

    cfg = make_config(mutate)
    targets, blocks = build_feedback_targets(cfg)
    assert targets == []
    assert blocks == {}


async def test_step_sends_only_changes(config):
    page1 = playbacks_payload(
        1,
        2,
        [
            {"iExec": 0, "isRun": True, "bC": "#ff0000"},
            {"iExec": 1, "isRun": False, "bC": "#ff0000"},
            {"iExec": 2, "isRun": True, "bC": "#00ff00"},
            {"iExec": 3, "isRun": False, "bC": "#000000"},
            {"iExec": 4, "isRun": False, "bC": "#ff0000"},
        ],
    )
    page1_buttons = playbacks_payload(
        1,
        3,
        [
            {"iExec": 100, "isRun": True, "bC": "#0000ff"},
            {"iExec": 101, "isRun": False, "bC": "#0000ff"},
            {"iExec": 102, "isRun": False, "bC": "#0000ff"},
            {"iExec": 103, "isRun": False, "bC": "#0000ff"},
            {"iExec": 104, "isRun": False, "bC": "#0000ff"},
        ],
    )
    client = FakeClient([page1, page1_buttons])
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep, clock=clock)

    await feedback.step()
    drain(feedback, clock)

    assert client.requests == [
        ("current", 0, 5, 2, 2),
        ("current", 100, 5, 3, 3),
    ]
    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent[65] == 16  # row1_1: exec 1 running, red
    assert sent[66] == 2  # row1_2: exec 2 stopped dark, red
    assert sent[67] == 20  # row1_3: exec 3 running, green
    assert sent[68] == 1  # row1_4: exec 4 stopped, black -> white dark
    assert sent[69] == 2  # row1_5: exec 5 stopped dark, red
    assert sent[75] == 16  # row2_1 same executor as row1_1
    assert sent[80] == 24  # row3_1: exec 101 running, blue
    assert sent[81] == 10  # row3_2: exec 102 stopped dark, blue
    assert len(midi.sent) == 15
    for _, frame in midi.sent:
        assert len(frame) == 3
        assert frame[0] == 0x90

    # A second identical cycle must not resend anything.
    client._responses = [page1, page1_buttons]
    await feedback.step()
    drain(feedback, clock)
    assert len(midi.sent) == 15


async def _noop_sleep(_delay: float) -> None:
    return None


async def test_step_resets_after_connection_loss(config):
    payload = playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    other = playbacks_payload(1, 3, [{"iExec": 100, "isRun": False, "bC": "#ff0000"}])
    client = FakeClient([payload, other])
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep, clock=clock)
    await feedback.step()
    drain(feedback, clock)
    assert len(midi.sent) == 3
    feedback.reset()
    client._responses = [payload, other]
    await feedback.step()
    drain(feedback, clock)
    assert len(midi.sent) == 6


async def test_step_without_device_keeps_state_for_retry(config):
    payload = playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    other = playbacks_payload(1, 3, [{"iExec": 100, "isRun": True, "bC": "#ff0000"}])
    client = FakeClient([payload, other])
    clock = FakeClock()
    midi = FakeMidi(accept=False, clock=clock)
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep, clock=clock)
    await feedback.step()
    assert midi.sent == []
    midi.accept = True
    client._responses = [payload, other]
    await feedback.step()
    drain(feedback, clock)
    assert len(midi.sent) == 3


async def test_step_times_out_without_answer(config):
    client = FakeClient([])
    feedback = ExecutorFeedback(
        config, client, FakeMidi(), sleep=_noop_sleep, timeout=0.01
    )
    await feedback.step()
    assert feedback._pending == {}
    assert len(client.requests) == 2


async def test_dry_run_only_logs(config, caplog):
    payload = playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    other = playbacks_payload(1, 3, [{"iExec": 100, "isRun": True, "bC": "#ff0000"}])
    client = FakeClient([payload, other])
    midi = FakeMidi()
    feedback = ExecutorFeedback(config, client, midi, dry_run=True, sleep=_noop_sleep)
    with caplog.at_level("INFO"):
        await feedback.step()
    assert midi.sent == []
    assert "dry-run: LED" in caplog.text


async def test_disabled_feedback_does_nothing(make_config):
    cfg = make_config(lambda data: data["feedback"].__setitem__("enabled", False))
    client = FakeClient([])
    midi = FakeMidi()
    feedback = ExecutorFeedback(cfg, client, midi, sleep=_noop_sleep)
    await feedback.step()
    assert client.requests == []
    assert midi.sent == []


def test_reset_clears_cached_velocities(config):
    feedback = ExecutorFeedback(config, FakeClient([]), FakeMidi())
    feedback._last[("midicraft", 65)] = 16
    feedback.reset()
    assert feedback._last == {}


def test_targets_follow_fixed_page(make_config):
    def mutate(data):
        data["mapping"]["playbacks"]["mc_row1_1"]["page"] = 2

    cfg = make_config(mutate)
    targets, blocks = build_feedback_targets(cfg)
    target = next(item for item in targets if item.control == "mc_row1_1")
    assert target.page == 2
    assert (2, 0) in blocks


def test_apply_skips_other_pages(config):
    feedback = ExecutorFeedback(config, FakeClient([]), FakeMidi())
    feedback._targets = [
        LedTarget("mc_row1_1", "midicraft", 65, 2, 1),
        LedTarget("mc_row1_2", "midicraft", 66, 3, 1),
    ]
    feedback._last.clear()
    midi = feedback._midi
    payload = playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    snapshot = parse_playbacks(payload)
    assert snapshot is not None
    feedback._apply(snapshot, RequestBlock(2, 0, 5, 2, 2))
    feedback.pump()
    assert [frame[1] for _, frame in midi.sent] == [65]


def test_block_boundary_keeps_executor_100_on_the_page_view():
    assert _block_key(2, 100) == (2, 0)
    assert _block_key(2, 101) == (2, 100)


def test_executor_100_is_requested_from_the_page_view(make_config):
    def mutate(data):
        data["mapping"]["playbacks"]["mc_row1_1"] = {
            "kind": "button",
            "executor": 100,
            "button": 2,
            "page": "current",
        }

    cfg = make_config(mutate)
    targets, blocks = build_feedback_targets(cfg)
    target = next(item for item in targets if item.control == "mc_row1_1")
    assert target.executor == 100
    block = blocks[("current", 0)]
    assert block.items_type == 2
    assert block.start + 1 <= 100 <= block.start + block.count


def test_apply_ignores_fixed_page_snapshot_for_current_targets(config):
    feedback = ExecutorFeedback(config, FakeClient([]), FakeMidi())
    feedback._targets = [LedTarget("mc_row1_1", "midicraft", 65, "current", 1)]
    payload = playbacks_payload(
        1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}]
    )
    snapshot = parse_playbacks(payload)
    assert snapshot is not None

    feedback._apply(snapshot, RequestBlock(2, 0, 5, 2, 2))
    feedback.pump()
    assert feedback._midi.sent == []

    feedback._apply(snapshot, RequestBlock("current", 0, 5, 2, 2))
    feedback.pump()
    assert len(feedback._midi.sent) == 1


class ManualClient:
    authenticated = True

    def __init__(self) -> None:
        self.playback_responses: asyncio.Queue = asyncio.Queue()
        self.requests: list[tuple] = []

    def request_playbacks(self, page, start, count, items_type, view) -> None:
        self.requests.append((page, start, count, items_type, view))


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.005)


async def test_step_drops_answer_for_a_different_block(config):
    client = ManualClient()
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(
        config, client, midi, sleep=_noop_sleep, timeout=0.05, clock=clock
    )
    task = asyncio.create_task(feedback.step())
    await _wait_for(lambda: len(client.requests) == 1)
    # A bottom-button answer arrives while the page block is in flight.
    client.playback_responses.put_nowait(
        playbacks_payload(1, 3, [{"iExec": 100, "isRun": True, "bC": "#ff0000"}])
    )
    client.playback_responses.put_nowait(
        playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    )
    await _wait_for(lambda: len(client.requests) == 2)
    client.playback_responses.put_nowait(
        playbacks_payload(1, 3, [{"iExec": 100, "isRun": True, "bC": "#0000ff"}])
    )
    await asyncio.wait_for(task, timeout=2.0)
    drain(feedback, clock)

    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent == {65: 16, 75: 16, 80: 24}


async def test_late_answer_does_not_stall_later_cycles(config):
    client = ManualClient()
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(
        config, client, midi, sleep=_noop_sleep, timeout=0.02, clock=clock
    )
    await feedback.step()
    assert len(client.requests) == 2
    assert midi.sent == []

    # A late bottom-button answer from the previous cycle must not shift the
    # queue and stall block A of this cycle.
    client.playback_responses.put_nowait(
        playbacks_payload(1, 3, [{"iExec": 100, "isRun": False, "bC": "#0000ff"}])
    )
    task = asyncio.create_task(feedback.step())
    await _wait_for(lambda: len(client.requests) == 3)
    client.playback_responses.put_nowait(
        playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    )
    await _wait_for(lambda: len(client.requests) == 4)
    client.playback_responses.put_nowait(
        playbacks_payload(1, 3, [{"iExec": 100, "isRun": False, "bC": "#0000ff"}])
    )
    await asyncio.wait_for(task, timeout=2.0)
    drain(feedback, clock)

    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent == {65: 16, 75: 16, 80: 10}


async def test_run_follows_config_reloads(make_config, config):
    async def tiny_sleep(_delay: float) -> None:
        await asyncio.sleep(0.005)

    client = FakeClient([])
    feedback = ExecutorFeedback(
        config, client, FakeMidi(), sleep=tiny_sleep, timeout=0.01
    )
    task = asyncio.create_task(feedback.run())
    try:
        await _wait_for(lambda: len(client.requests) >= 2)

        disabled = make_config(
            lambda data: data["feedback"].__setitem__("enabled", False)
        )
        feedback.set_config(disabled)
        await asyncio.sleep(0.02)
        count = len(client.requests)
        await asyncio.sleep(0.05)
        assert len(client.requests) == count

        feedback.set_config(config)
        await _wait_for(lambda: len(client.requests) >= count + 2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def test_reset_drains_stale_responses(config):
    client = FakeClient([])
    midi = FakeMidi()
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep)
    client.playback_responses.put_nowait(
        playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    )
    feedback.reset()
    assert client.playback_responses.empty()


async def test_current_targets_follow_page_change(config):
    page_one = playbacks_payload(
        1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}]
    )
    buttons_one = playbacks_payload(
        1, 3, [{"iExec": 100, "isRun": False, "bC": "#0000ff"}]
    )
    page_two = playbacks_payload(
        2, 2, [{"iExec": 0, "isRun": False, "bC": "#ff0000"}]
    )
    buttons_two = playbacks_payload(
        2, 3, [{"iExec": 100, "isRun": False, "bC": "#0000ff"}]
    )
    client = FakeClient([page_one, buttons_one, page_two, buttons_two])
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep, clock=clock)

    await feedback.step()
    drain(feedback, clock)
    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent[65] == 16
    assert sent[75] == 16

    midi.sent.clear()
    await feedback.step()
    drain(feedback, clock)
    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent == {65: 2, 75: 2}


def _frames_for(midi: FakeMidi, note: int) -> list[bytes]:
    return [frame[1:] for _, frame in midi.sent if frame[1] == note]


def _running_snapshot(running: bool):
    snapshot = parse_playbacks(
        playbacks_payload(1, 2, [{"iExec": 0, "isRun": running, "bC": "#ff0000"}])
    )
    assert snapshot is not None
    return snapshot


def test_frames_are_paced_per_device(config):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    snapshot = parse_playbacks(
        playbacks_payload(
            1,
            2,
            [{"iExec": n, "isRun": True, "bC": "#ff0000"} for n in range(5)],
        )
    )
    assert snapshot is not None
    feedback._apply(snapshot, block)
    drain(feedback, clock)

    assert len(midi.sent) == 10
    gaps = [b - a for a, b in zip(midi.times, midi.times[1:])]
    assert all(gap >= 0.02 - 1e-9 for gap in gaps)


def test_pending_frame_is_replaced_by_newer_state(config):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    feedback._apply(_running_snapshot(True), block)
    feedback._apply(_running_snapshot(False), block)
    drain(feedback, clock)

    assert _frames_for(midi, 65) == [bytes((65, 2))]


def test_state_returning_to_shown_drops_waiting_frame(config):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    feedback._apply(_running_snapshot(True), block)
    drain(feedback, clock)
    sent = len(midi.sent)

    feedback._apply(_running_snapshot(False), block)
    feedback._apply(_running_snapshot(True), block)
    assert feedback.pump() is None
    assert len(midi.sent) == sent


def test_stalled_output_pauses_device_until_reopened(config, caplog):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    midi.pending["midicraft-enc"] = 3
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    feedback._apply(_running_snapshot(True), block)
    feedback.pump()
    first = len(midi.sent)

    with caplog.at_level("WARNING", logger="ma2pi.feedback"):
        clock.now += 2.5
        feedback._apply(_running_snapshot(False), block)
        feedback.pump()
        clock.now += 1.0
        feedback.pump()
    assert len(midi.sent) == first
    assert sum("gestaut" in record.message for record in caplog.records) == 1

    # Reopening the device starts over with the whole state.
    midi.pending["midicraft-enc"] = 0
    midi.open_devices = {"midicraft-enc": "/dev/snd/midiC5D0"}
    feedback._sync_devices()
    feedback._apply(_running_snapshot(False), block)
    drain(feedback, clock)
    assert len(midi.sent) == first + 2


def test_slow_but_draining_output_is_not_a_stall(config):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    midi.pending["midicraft-enc"] = 3
    feedback._apply(_running_snapshot(True), block)
    feedback.pump()
    clock.now += 1.0
    midi.pending["midicraft"] = 0
    feedback._apply(_running_snapshot(False), block)
    drain(feedback, clock)
    assert len(midi.sent) == 3


def test_unknown_pending_state_never_stalls(config):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    midi.pending["midicraft"] = None
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    feedback._apply(_running_snapshot(True), block)
    drain(feedback, clock)
    clock.now += 60
    feedback._apply(_running_snapshot(False), block)
    drain(feedback, clock)
    assert len(midi.sent) == 4


def test_profile_without_led_enabled_has_no_targets(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["enabled"] = False

    assert build_feedback_targets(make_config(mutate)) == ([], {})


def test_frame_interval_comes_from_profile(make_config):
    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["frame_interval_ms"] = 50

    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    feedback = ExecutorFeedback(make_config(mutate), FakeClient([]), midi, clock=clock)
    block = RequestBlock("current", 0, 5, 2, 2)
    snapshot = parse_playbacks(
        playbacks_payload(
            1, 2, [{"iExec": n, "isRun": True, "bC": "#ff0000"} for n in range(3)]
        )
    )
    assert snapshot is not None
    feedback._apply(snapshot, block)
    drain(feedback, clock)
    gaps = [b - a for a, b in zip(midi.times, midi.times[1:])]
    assert len(gaps) == len(midi.sent) - 1 >= 2
    assert all(gap >= 0.05 - 1e-9 for gap in gaps)


def test_parse_playbacks_skips_unknown_running_state():
    payload = playbacks_payload(
        1,
        2,
        [{"iExec": 0}, {"iExec": 1, "isRun": True, "bC": "#ff0000"}],
    )
    snapshot = parse_playbacks(payload)
    assert snapshot is not None
    assert 1 not in snapshot.executors
    assert snapshot.executors[2].running is True


def test_belongs_to_block_checks_page_type_and_range():
    snapshot = parse_playbacks(
        playbacks_payload(2, 2, [{"iExec": 0, "isRun": True}])
    )
    assert snapshot is not None
    assert _belongs_to_block(snapshot, RequestBlock(3, 0, 5, 2, 2)) is True
    assert _belongs_to_block(snapshot, RequestBlock("current", 0, 5, 2, 2)) is True
    assert _belongs_to_block(snapshot, RequestBlock(2, 0, 5, 2, 2)) is False
    assert _belongs_to_block(snapshot, RequestBlock(3, 5, 5, 2, 2)) is False
    assert _belongs_to_block(snapshot, RequestBlock(3, 0, 5, 3, 3)) is False


async def test_run_pumps_queued_frames_at_device_pace(config):
    async def tiny_sleep(_delay: float) -> None:
        await asyncio.sleep(0.002)

    midi = FakeMidi()
    feedback = ExecutorFeedback(config, FakeClient([]), midi, sleep=tiny_sleep)
    task = asyncio.create_task(feedback.run())
    try:
        feedback._sync_devices()
        feedback._apply(
            _running_snapshot(True), RequestBlock("current", 0, 5, 2, 2)
        )
        await _wait_for(lambda: len(midi.sent) == 2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_stalled_device_does_not_hold_back_another_device(config):
    clock = FakeClock()
    midi = FakeMidi(clock=clock)
    midi.pending["slow"] = 4
    feedback = ExecutorFeedback(config, FakeClient([]), midi, clock=clock)
    feedback._intervals = {"slow": 0.5, "fast": 0.02}
    feedback._outbox = {
        "slow": {note: 10 for note in range(8)},
        "fast": {1: 10, 2: 10, 3: 10},
    }
    for _ in range(300):
        feedback.pump()
        clock.now += 0.02

    by_device: dict[str, int] = {}
    for device, _ in midi.sent:
        by_device[device] = by_device.get(device, 0) + 1
    assert by_device["fast"] == 3
    # The slow device stalled after 2 s of unconsumed bytes and stopped there.
    assert "slow" in feedback._stalled
    assert by_device.get("slow", 0) < 8
