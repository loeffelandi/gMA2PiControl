from __future__ import annotations

import pytest

from ma2pi import hardkeys


def test_required_names_are_present():
    for name in hardkeys.REQUIRED_NAMES:
        assert hardkeys.is_known(name), name


def test_keynames_are_unique_and_non_empty():
    assert "" not in hardkeys.KEYNAMES
    assert len(hardkeys.KEYNAMES) == len(set(hardkeys.KEYNAMES))


def test_resolve_returns_keynames():
    assert hardkeys.resolve("MA") == "MA"
    assert hardkeys.resolve("Fix") == "FIXTURE"
    assert hardkeys.resolve("Store") == "STORE"
    assert hardkeys.resolve("Clear") == "CLEAR"
    assert hardkeys.resolve("Please") == "ENTER"
    assert hardkeys.resolve("At") == "AT"
    assert hardkeys.resolve("Thru") == "THRU"
    assert hardkeys.resolve("Go +") == "GO_PLUS"
    assert hardkeys.resolve("Go -") == "GO_MINUS"
    assert hardkeys.resolve("Pause") == "PAUSE"
    assert hardkeys.resolve("0") == "0"
    assert hardkeys.resolve("9") == "9"


def test_aliases_and_case_insensitivity():
    assert hardkeys.resolve("Go+") == "GO_PLUS"
    assert hardkeys.resolve("go_minus") == "GO_MINUS"
    assert hardkeys.resolve("fixture") == "FIXTURE"
    assert hardkeys.resolve("  enter  ") == "ENTER"
    assert hardkeys.resolve("go_plus") == "GO_PLUS"
    assert hardkeys.canonical_name("Go+") == "GO_PLUS"


def test_every_alias_targets_a_keyname():
    for alias, target in hardkeys.ALIASES.items():
        assert target in hardkeys.KEYNAMES, alias


def test_unknown_name_raises():
    with pytest.raises(hardkeys.UnknownHardkey):
        hardkeys.resolve("NoSuchKey")


def test_numeric_ids_are_rejected():
    with pytest.raises(hardkeys.UnknownHardkey):
        hardkeys.resolve(68)  # type: ignore[arg-type]


def test_no_x_keys_in_web_remote():
    # The web remote has no X1..X20 keynames; those must be commands.
    assert not hardkeys.is_known("X1")
    assert not hardkeys.is_known("X20")
