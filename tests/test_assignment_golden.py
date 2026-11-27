"""Golden cases shared with the web UI resolver (``web/src/lib/assignment.ts``).

The daemon resolution in ``playback_targets``/``mapping`` is the reference. The
same JSON cases run in ``web/src/lib/assignment.test.ts``; a case that resolves
differently in either place fails there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ma2pi.mapping import MappingEngine
from ma2pi.playback_targets import bank_size, resolve_target

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "assignment_golden.json").read_text(
        encoding="utf-8"
    )
)
CASES = [
    pytest.param(case, id=case["name"]) for case in FIXTURE["cases"]
]


class _Sink:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def _expected_key(entry) -> dict:
    return {
        name: value
        for name, value in (
            ("hardkey", entry.hardkey),
            ("command", entry.command),
            ("screen", entry.screen),
            ("encoder_press", entry.encoder_press),
        )
        if value is not None
    }


@pytest.mark.parametrize("case", CASES)
def test_daemon_resolution_matches_golden(make_config, case):
    device = FIXTURE["device"]

    def mutate(data):
        mapping = case["mapping"]
        data["mapping"]["playbacks"] = mapping.get("playbacks", {})
        data["mapping"]["keys"] = mapping.get("keys", {})
        data["mapping"]["device_banks"] = mapping.get("device_banks", {})
        data["midi_remote"]["enabled"] = case.get("midi_remote_enabled", False)

    config = make_config(mutate)
    assert bank_size(config, device) == FIXTURE["bank_size"]
    engine = MappingEngine(config, _Sink())

    for query in case["queries"]:
        bank, control = query["bank"], query["control"]
        if "playback" in query:
            target = resolve_target(config, device, bank, control)
            expected = query["playback"]
            if expected is None:
                assert target is None
                continue
            assert target is not None
            assert target.page == expected["page"]
            assert target.executor == expected["executor"]
            assert target.kind == expected["kind"]
            assert target.accelerated == expected["accelerated"]
            assert target.transport == expected["transport"]
            if expected["kind"] == "button":
                assert target.button == expected["button"]
        if "key" in query:
            key = engine._key_mapping(control, device, bank)
            assert key is not None
            assert _expected_key(key) == query["key"]
