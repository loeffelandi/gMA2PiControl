from __future__ import annotations

import asyncio

from ma2pi.feedback import (
    ExecutorFeedback,
    LedTarget,
    PALETTE,
    RequestBlock,
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


class FakeMidi:
    def __init__(self, accept: bool = True) -> None:
        self.open_devices = {"midicraft": "/dev/snd/midiC4D0"}
        self.accept = accept
        self.sent: list[tuple[str, bytes]] = []

    def send(self, device: str, data: bytes) -> bool:
        if not self.accept:
            return False
        self.sent.append((device, data))
        return True


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
    assert by_control["mc_row1_1"] == LedTarget("mc_row1_1", "midicraft", 65, "current", 1)
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
    midi = FakeMidi()
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep)

    await feedback.step()

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
    assert len(midi.sent) == 15


async def _noop_sleep(_delay: float) -> None:
    return None


async def test_step_resets_after_connection_loss(config):
    payload = playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    other = playbacks_payload(1, 3, [{"iExec": 100, "isRun": False, "bC": "#ff0000"}])
    client = FakeClient([payload, other])
    midi = FakeMidi()
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep)
    await feedback.step()
    assert len(midi.sent) == 3
    feedback.reset()
    client._responses = [payload, other]
    await feedback.step()
    assert len(midi.sent) == 6


async def test_step_without_device_keeps_state_for_retry(config):
    payload = playbacks_payload(1, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    other = playbacks_payload(1, 3, [{"iExec": 100, "isRun": True, "bC": "#ff0000"}])
    client = FakeClient([payload, other])
    midi = FakeMidi(accept=False)
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep)
    await feedback.step()
    assert midi.sent == []
    midi.accept = True
    client._responses = [payload, other]
    await feedback.step()
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
    payload = playbacks_payload(2, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}])
    snapshot = parse_playbacks(payload)
    assert snapshot is not None
    feedback._apply(snapshot, RequestBlock(2, 0, 5, 2, 2))
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
        2, 2, [{"iExec": 0, "isRun": True, "bC": "#ff0000"}]
    )
    snapshot = parse_playbacks(payload)
    assert snapshot is not None

    feedback._apply(snapshot, RequestBlock(2, 0, 5, 2, 2))
    assert feedback._midi.sent == []

    feedback._apply(snapshot, RequestBlock("current", 0, 5, 2, 2))
    assert len(feedback._midi.sent) == 1


class ManualClient:
    authenticated = True

    def __init__(self) -> None:
        self.playback_responses: asyncio.Queue = asyncio.Queue()
        self.requests: list[tuple] = []

    def request_playbacks(self, page, start, count, items_type, view) -> None:
        self.requests.append((page, start, count, items_type, view))


async def test_step_drops_answer_for_a_different_block(config):
    client = ManualClient()
    midi = FakeMidi()
    feedback = ExecutorFeedback(
        config, client, midi, sleep=_noop_sleep, timeout=0.05
    )
    task = asyncio.create_task(feedback.step())
    await asyncio.sleep(0)
    assert client.requests[0][3] == 2
    # A bottom-button answer arrives while the page block is in flight.
    client.playback_responses.put_nowait(
        playbacks_payload(1, 3, [{"iExec": 100, "isRun": True, "bC": "#ff0000"}])
    )
    await asyncio.wait_for(task, timeout=2.0)

    assert len(client.requests) == 2
    assert midi.sent == []


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
    midi = FakeMidi()
    feedback = ExecutorFeedback(config, client, midi, sleep=_noop_sleep)

    await feedback.step()
    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent[65] == 16
    assert sent[75] == 16

    midi.sent.clear()
    await feedback.step()
    sent = {frame[1]: frame[2] for _, frame in midi.sent}
    assert sent == {65: 2, 75: 2}
