from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from ma2pi.feedback import (
    ExecutorFeedback,
    LedTarget,
    RequestBlock,
    _belongs_to_block,
    parse_playbacks,
)
from ma2pi.poller import PlaybackPoller, build_playback_targets
from ma2pi.topology import ExecutorTopology

FIXTURES = Path(__file__).parent / "fixtures" / "playbacks"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def payload(page: int, items_type: int, executors: list[int]) -> dict:
    return {
        "responseType": "playbacks",
        "iPage": page,
        "itemGroups": [
            {
                "itemsType": items_type,
                "items": [[{"iExec": n - 1, "isRun": False} for n in executors]],
            }
        ],
    }


class FakeClient:
    authenticated = True

    def __init__(self, answer=None) -> None:
        self.playback_responses: asyncio.Queue = asyncio.Queue()
        self.requests: list[tuple] = []
        self._answer = answer

    def request_playbacks(self, page, start, count, items_type, view) -> None:
        self.requests.append((page, start, count, items_type, view))
        if self._answer is not None:
            response = self._answer(page, start, count, items_type)
            if response is not None:
                self.playback_responses.put_nowait(response)


def answer_from(fixtures: dict):
    """Answer by ``(page, items_type)``; everything else with its own range."""

    def answer(page, start, count, items_type):
        found = fixtures.get((page, items_type))
        if found is not None:
            return found
        number = 0 if page == "current" else page
        return payload(number, items_type, range(start + 1, start + count + 1))

    return answer


def targets_config(make_config, playbacks: dict, **mapping):
    def mutate(data):
        data["mapping"]["playbacks"] = playbacks
        data["mapping"].update(mapping)
        data["feedback"]["enabled"] = False

    return make_config(mutate)


BUTTON_115 = {
    "mc_click_1": {"page": 2, "executor": 115, "kind": "button", "button": 1}
}


# --- Parser und Fixtures (Task 2.1) ----------------------------------------


def test_floating_fixture_reports_the_wide_executor():
    snapshot = parse_playbacks(fixture("page2_button.json"))

    assert snapshot is not None
    assert snapshot.page == 2
    assert snapshot.combined == {114: 2}
    assert 115 not in snapshot.seen_executors
    assert snapshot.lead_of(115) == 114
    assert snapshot.lead_of(114) is None
    assert snapshot.lead_of(113) is None


def test_wide_fader_fixtures_report_the_wide_executor():
    snapshot = parse_playbacks(fixture("page3_fader_wide_exec6.json"))

    assert snapshot is not None
    assert snapshot.combined == {6: 2}
    assert snapshot.lead_of(7) == 6
    assert snapshot.executors[6].running is True

    older = parse_playbacks(fixture("page3_fader_wide.json"))
    assert older is not None
    assert older.combined == {3: 2}


def test_normal_fixtures_have_no_combined_executors():
    for name in ("page1_button.json", "page1_fader.json", "page2_fader.json"):
        snapshot = parse_playbacks(fixture(name))
        assert snapshot is not None
        assert snapshot.combined == {}


@pytest.mark.parametrize(
    ("name", "block"),
    [
        ("page2_button.json", RequestBlock(2, 110, 5, 3, 3)),
        ("page2_fader.json", RequestBlock(2, 0, 5, 2, 2)),
        ("current_button.json", RequestBlock("current", 110, 5, 3, 3)),
        ("current_fader.json", RequestBlock("current", 0, 5, 2, 2)),
    ],
)
def test_fixtures_belong_to_their_request(name, block):
    snapshot = parse_playbacks(fixture(name))

    assert snapshot is not None
    assert _belongs_to_block(snapshot, block) is True


def test_fixed_page_answer_is_not_taken_for_current():
    snapshot = parse_playbacks(fixture("page2_fader.json"))

    assert snapshot is not None
    assert _belongs_to_block(snapshot, RequestBlock("current", 0, 5, 2, 2)) is False
    assert _belongs_to_block(snapshot, RequestBlock(1, 0, 5, 2, 2)) is False


# --- Poller (Task 4.2, 4.3) --------------------------------------------------


async def test_feedback_off_polls_playback_targets_for_the_topology(make_config):
    cfg = targets_config(make_config, BUTTON_115)
    topology = ExecutorTopology()
    client = FakeClient(answer_from({(2, 3): fixture("page2_button.json")}))
    poller = PlaybackPoller(cfg, client, topology, timeout=0.05)

    await poller.step()

    assert (2, 110, 5, 3, 3) in client.requests
    resolution = topology.resolve(2, 115)
    assert (resolution.executor, resolution.covered) == (114, True)
    assert poller.interval() == pytest.approx(2.0)


async def test_interval_follows_topology_interval_without_feedback(make_config):
    cfg = targets_config(make_config, BUTTON_115, topology_interval_ms=750)

    poller = PlaybackPoller(cfg, FakeClient(), ExecutorTopology())

    assert poller.interval() == pytest.approx(0.75)


async def test_off_does_not_poll(make_config):
    cfg = targets_config(make_config, BUTTON_115, combined_executors="off")
    client = FakeClient(answer_from({}))
    poller = PlaybackPoller(cfg, client, ExecutorTopology(), timeout=0.05)

    await poller.step()

    assert client.requests == []


async def test_led_and_topology_are_separate_requests_with_own_clocks(make_config):
    clock = [0.0]

    def mutate(data):
        data["profiles"]["midicraft-enc"]["led_feedback"]["enabled"] = True
        data["mapping"]["playbacks"] = {
            "mc_row1_1": {"page": 2, "executor": 114, "kind": "button", "button": 1},
        }
        data["mapping"]["topology_interval_ms"] = 2000

    cfg = make_config(mutate)
    client = FakeClient(answer_from({}))
    midi = type(
        "Midi",
        (),
        {"open_devices": {}, "send": lambda self, device, data: True},
    )()
    feedback = ExecutorFeedback(cfg, client, midi, timeout=0.05)
    feedback._poller._clock = lambda: clock[0]

    await feedback.step()
    first = list(client.requests)
    clock[0] = 0.25
    await feedback.step()
    second = client.requests[len(first):]
    clock[0] = 2.25
    await feedback.step()
    third = client.requests[len(first) + len(second):]

    # LED block every LED cycle; the topology block only every topology interval.
    assert len(first) == 2 and len(second) == 1 and len(third) == 2
    assert feedback._poller.interval() == pytest.approx(cfg.feedback.interval_ms / 1000)


async def test_topology_polls_only_floating_buttons(make_config):
    cfg = targets_config(
        make_config,
        {
            "mc_click_1": {"page": 2, "executor": 103, "kind": "button", "button": 1},
            "mc_click_2": {"page": 2, "executor": 3, "kind": "button", "button": 1},
            "mc_click_3": {"page": 2, "executor": 13, "kind": "fader"},
        },
    )
    poller = PlaybackPoller(cfg, FakeClient(), ExecutorTopology())

    assert poller.blocks() == {(2, 100): RequestBlock(2, 100, 5, 3, 3)}


async def test_new_answer_replaces_the_topology(make_config):
    cfg = targets_config(make_config, BUTTON_115)
    topology = ExecutorTopology()
    answers = {(2, 3): fixture("page2_button.json")}
    client = FakeClient(answer_from(answers))
    clock = [0.0]
    poller = PlaybackPoller(
        cfg, client, topology, timeout=0.05, clock=lambda: clock[0]
    )
    await poller.step()
    assert topology.resolve(2, 115).covered is True

    # The wide executor was shrunk on the console: the next answer lists 115.
    answers[(2, 3)] = payload(2, 3, range(101, 121))
    clock[0] = 5.0
    await poller.step()

    assert topology.resolve(2, 115).covered is False
    assert topology.resolve(2, 115).known is True


async def test_topology_is_dropped_on_connection_loss_and_config_swap(make_config):
    cfg = targets_config(make_config, BUTTON_115)
    topology = ExecutorTopology()
    client = FakeClient(answer_from({(2, 3): fixture("page2_button.json")}))
    poller = PlaybackPoller(cfg, client, topology, timeout=0.05)

    await poller.step()
    assert topology.resolve(2, 115).known is True
    poller.reset()
    assert topology.resolve(2, 115).known is False

    await poller.step()
    assert topology.resolve(2, 115).known is True
    poller.set_config(cfg, {})
    assert topology.resolve(2, 115).known is False


async def test_unauthenticated_client_is_not_polled(make_config):
    cfg = targets_config(make_config, BUTTON_115)
    client = FakeClient(answer_from({}))
    client.authenticated = False
    poller = PlaybackPoller(cfg, client, ExecutorTopology(), timeout=0.05)

    await poller.step()

    assert client.requests == []


def test_playback_targets_cover_buttons_and_faders(make_config):
    cfg = targets_config(
        make_config,
        {
            "mc_click_1": {"page": 2, "executor": 115, "kind": "button", "button": 1},
            "mc_encoder_1": {"page": "current", "executor": 3, "kind": "fader"},
        },
    )

    found = {(t.control, t.page, t.executor, t.kind) for t in build_playback_targets(cfg)}

    assert ("mc_click_1", 2, 115, "button") in found
    assert ("mc_encoder_1", "current", 3, "fader") in found


# --- Diagnose (Task 6.2) -----------------------------------------------------


def _diagnosis_config(make_config, **playbacks):
    return targets_config(
        make_config,
        {
            "mc_click_1": {"page": 2, "executor": 130, "kind": "button", "button": 1},
            **playbacks,
        },
    )


async def test_missing_target_is_warned_once(make_config, caplog):
    cfg = _diagnosis_config(make_config)
    # The console answers the 126..130 block without an item for 130.
    answers = {(2, 3): payload(2, 3, [126, 127, 128])}
    client = FakeClient(answer_from(answers))
    poller = PlaybackPoller(cfg, client, ExecutorTopology(), timeout=0.05)

    with caplog.at_level("WARNING", logger="ma2pi.poller"):
        await poller.step()
        await poller.step()

    warnings = [r.getMessage() for r in caplog.records if "existiert" in r.getMessage()]
    assert len(warnings) == 1
    assert "mc_click_1" in warnings[0]
    assert "Page 2" in warnings[0]
    assert "130" in warnings[0]


async def test_empty_executor_is_not_reported_missing(make_config, caplog):
    cfg = _diagnosis_config(make_config)
    empty = payload(2, 3, [126, 127, 128, 129, 130])
    for item in empty["itemGroups"][0]["items"][0]:
        item["isEmpty"] = True
    client = FakeClient(answer_from({(2, 3): empty}))
    poller = PlaybackPoller(cfg, client, ExecutorTopology(), timeout=0.05)

    with caplog.at_level("WARNING", logger="ma2pi.poller"):
        await poller.step()

    assert not [r for r in caplog.records if "existiert" in r.getMessage()]


async def test_covered_slot_is_not_reported_missing(make_config, caplog):
    cfg = targets_config(make_config, BUTTON_115)
    client = FakeClient(answer_from({(2, 3): fixture("page2_button.json")}))
    poller = PlaybackPoller(cfg, client, ExecutorTopology(), timeout=0.05)

    with caplog.at_level("WARNING", logger="ma2pi.poller"):
        await poller.step()

    assert not [r for r in caplog.records if "existiert" in r.getMessage()]


async def test_warning_repeats_after_config_swap(make_config, caplog):
    cfg = _diagnosis_config(make_config)
    client = FakeClient(answer_from({(2, 3): payload(2, 3, [126, 127, 128])}))
    poller = PlaybackPoller(cfg, client, ExecutorTopology(), timeout=0.05)

    with caplog.at_level("WARNING", logger="ma2pi.poller"):
        await poller.step()
        poller.set_config(cfg, {})
        await poller.step()

    assert len([r for r in caplog.records if "existiert" in r.getMessage()]) == 2


# --- LED eines überdeckten Slots (Task 6.1) -----------------------------------


def _mirror_feedback(make_config, **mapping):
    cfg = make_config(
        lambda data: (
            data["profiles"]["midicraft-enc"]["led_feedback"].__setitem__("enabled", True),
            data["mapping"].update(mapping),
        )
    )

    class Midi:
        open_devices = {"midicraft-enc": "/dev/snd/midiC4D0"}

        def __init__(self) -> None:
            self.sent: list[bytes] = []

        def send(self, device, data):
            self.sent.append(data)
            return True

    midi = Midi()
    feedback = ExecutorFeedback(cfg, FakeClient(), midi)
    feedback._targets = [
        LedTarget("lead", "midicraft-enc", 65, 2, 114),
        LedTarget("covered", "midicraft-enc", 66, 2, 115),
    ]
    return feedback, midi


def _sent(midi: Midi) -> dict[int, int]:
    return {frame[1]: frame[2] for frame in midi.sent}


def test_covered_slot_led_mirrors_the_leading_executor(make_config):
    feedback, midi = _mirror_feedback(make_config)
    snapshot = parse_playbacks(fixture("page2_button.json"))
    assert snapshot is not None

    feedback._apply(snapshot, RequestBlock(2, 110, 5, 3, 3))
    while feedback.pump() is not None:
        pass

    sent = _sent(midi)
    assert sent[65] == sent[66]
    assert sent[65] >= 17  # exec 114 runs: a bright colour, not "dark"


def test_covered_slot_led_follows_a_stopped_leader(make_config):
    feedback, midi = _mirror_feedback(make_config)
    data = fixture("page2_button.json")
    for row in data["itemGroups"][0]["items"]:
        for item in row:
            if item["iExec"] == 113:
                item["isRun"] = 0
    snapshot = parse_playbacks(data)
    assert snapshot is not None

    feedback._apply(snapshot, RequestBlock(2, 110, 5, 3, 3))
    while feedback.pump() is not None:
        pass

    sent = _sent(midi)
    assert sent[65] == sent[66]
    assert 1 <= sent[65] < 17  # stopped: dark shade


def test_covered_slot_led_with_unknown_leader_sends_nothing(make_config):
    feedback, midi = _mirror_feedback(make_config)
    data = fixture("page2_button.json")
    # Drop the leader's own item; only an unrelated wide executor stays.
    data["itemGroups"][0]["items"] = [
        [item for item in row if item["iExec"] != 113]
        for row in data["itemGroups"][0]["items"]
    ]
    data["itemGroups"][0]["items"][0].append(
        {"iExec": 120, "isRun": 0, "combinedItems": 2}
    )
    snapshot = parse_playbacks(data)
    assert snapshot is not None

    feedback._apply(snapshot, RequestBlock(2, 110, 5, 3, 3))
    while feedback.pump() is not None:
        pass

    assert 66 not in _sent(midi)


def test_covered_slot_led_is_not_mirrored_when_off(make_config):
    feedback, midi = _mirror_feedback(make_config, combined_executors="off")
    snapshot = parse_playbacks(fixture("page2_button.json"))
    assert snapshot is not None

    feedback._apply(snapshot, RequestBlock(2, 110, 5, 3, 3))
    while feedback.pump() is not None:
        pass

    sent = _sent(midi)
    assert 65 in sent
    assert 66 not in sent
