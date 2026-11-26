from __future__ import annotations

import pytest

from ma2pi.config import load_config


def _controls(layout):
    return [
        cell.control
        for row in layout.rows
        for cell in row.cells
        if cell.control is not None
    ]


def test_cherry_layout_matches_photo(config):
    layout = config.layouts["cherry-g86"]
    assert layout.columns == 18
    assert len(layout.rows) == 8
    controls = _controls(layout)
    for control in ("pause_big", "go_plus_big", "go_minus_big", "store_big", "please_big"):
        assert control in controls
    pause = next(
        cell
        for row in layout.rows
        for cell in row.cells
        if cell.control == "pause_big"
    )
    assert (pause.col_span, pause.row_span, pause.color) == (2, 2, "green")
    assert (pause.row, pause.col) == (1, 2)
    cells = {
        cell.control: cell
        for row in layout.rows
        for cell in row.cells
        if cell.control is not None
    }
    assert (cells["user1"].row_span, cells["user1"].row, cells["user1"].col) == (
        2,
        5,
        5,
    )
    assert (cells["store_big"].row_span, cells["store_big"].row, cells["store_big"].col) == (
        2,
        7,
        11,
    )
    assert (cells["list"].col_span, cells["list"].row, cells["list"].col) == (2, 6, 7)
    assert (
        cells["please_big"].col_span,
        cells["please_big"].row,
        cells["please_big"].col,
    ) == (2, 8, 14)
    assert (cells["down"].row, cells["down"].col) == (8, 17)
    assert cells["x13"].color == "green"
    assert all(cells[f"x{n}"].color == "green" for n in range(11, 16))
    assert all(cells[f"x{n}"].color == "blue" for n in range(16, 21))
    labels = [cell.label for row in layout.rows for cell in row.cells]
    assert "Ch Pg+" in labels
    assert "Please" in labels


def test_asl_layout_has_encoders_and_buttons(config):
    layout = config.layouts["asl-mk2-e4b3"]
    controls = _controls(layout)
    assert [f"encoder.{index}" for index in range(1, 5)] == [
        control for control in controls if control.startswith("encoder.")
    ]
    for control in ("asl_click_1", "asl_click_4", "asl_button_2", "asl_button_3"):
        assert control in controls


@pytest.mark.parametrize(
    "profile,prefix,kind_count",
    [
        ("midicraft-push", "mcp", {"button": 30}),
        ("midicraft-fade", "mcf", {"fader": 5, "button": 20}),
        ("midicraft-turn", "mct", {"button": 15, "poti": 15}),
        ("midicraft-mix", "mcm", {"fader": 5, "button": 15, "poti": 5}),
        ("midicraft-enc", "mc", {"fader": 5, "button": 20, "encoder": 5}),
        ("midicraft-spot", "mcs", {"fader": 5, "button": 10, "poti": 10}),
    ],
)
def test_midicraft_layout_control_counts(config, profile, prefix, kind_count):
    layout = config.layouts[profile]
    controls = _controls(layout)
    assert len(controls) == sum(kind_count.values())
    for kind, expected in kind_count.items():
        actual = [
            control
            for control in controls
            if config.profiles[profile].control_kinds[control] == kind
        ]
        assert len(actual) == expected


@pytest.mark.parametrize(
    "profile",
    [
        "midicraft-push",
        "midicraft-fade",
        "midicraft-turn",
        "midicraft-mix",
        "midicraft-enc",
        "midicraft-spot",
    ],
)
def test_midicraft_profiles_have_16_banks(config, profile):
    banks = config.profiles[profile].banks
    assert [bank.number for bank in banks] == list(range(1, 17))
    assert [bank.channel for bank in banks] == list(range(1, 17))
    assert all(bank.notes for bank in banks[:1] if profile == "midicraft-enc")
    if profile != "midicraft-enc":
        assert all(not bank.notes for bank in banks)


def test_enc_bank_two_is_empty_until_learned(config):
    profile = config.profiles["midicraft-enc"]
    assert profile.banks[1].number == 2
    assert profile.banks[1].channel == 2
    assert profile.banks[1].notes == {}


def test_overlapping_absolute_cells_are_rejected(make_config):
    from ma2pi.config import ConfigError

    def mutate(data):
        data["layouts"]["asl"]["rows"] = [
            {"cells": [{"label": "A", "row": 1, "col": 1, "row_span": 2}]},
            {"cells": [{"label": "B", "row": 2, "col": 1}]},
        ]

    with pytest.raises(ConfigError, match="überlappen"):
        make_config(mutate)


def test_auto_row_wider_than_columns_is_rejected(make_config):
    from ma2pi.config import ConfigError

    def mutate(data):
        data["layouts"]["asl"]["columns"] = 2
        data["layouts"]["asl"]["rows"] = [
            {"cells": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}
        ]

    with pytest.raises(ConfigError, match="Spalten"):
        make_config(mutate)


def test_midicraft_enc_row_order_matches_hardware(config):
    rows = [
        [cell.control for cell in row.cells]
        for row in config.layouts["midicraft-enc"].rows
    ]
    assert rows[0][0] == "mc_encoder_1"
    assert rows[1][0] == "mc_click_1"
    assert rows[2][0] == "mc_row1_1"
    assert rows[3][0] == "mc_fader_1"
    assert rows[4][0] == "mc_row2_1"
    assert rows[5][0] == "mc_row3_1"
