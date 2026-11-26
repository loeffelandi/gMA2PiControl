from __future__ import annotations

from ma2pi.encoder_page import EncoderPage


def page(pre):
    return {"responseType": "presetTypes", "type": "full", "pre": pre}


def feature(name: str, attrs: list[str], selected: bool = True, index: int = 1) -> dict:
    return {
        "i": index,
        "np": name,
        "s": selected,
        "fea": [
            {
                "i": index,
                "np": name,
                "s": True,
                "att": [{"n": attr, "np": attr} for attr in attrs],
            }
        ],
    }


def test_unknown_page_has_no_attributes():
    instance = EncoderPage()
    assert instance.attributes() == []
    assert instance.name_for(1) is None


def test_slots_map_to_attribute_names():
    instance = EncoderPage()
    assert instance.update(page([feature("Position", ["PAN", "TILT"])]))
    assert instance.name_for(1) == "PAN"
    assert instance.name_for(2) == "TILT"
    # Slots without an attribute stay empty, like the web remote.
    assert instance.name_for(3) is None


def _feature_with_selection(names: list[str], selected: int, index: int = 1) -> dict:
    return {
        "i": index,
        "np": "Feature",
        "s": True,
        "fea": [
            {
                "i": index,
                "np": "Feature",
                "s": True,
                "att": [
                    {"n": name, "np": name, "s": position == selected}
                    for position, name in enumerate(names)
                ],
            }
        ],
    }


def test_window_follows_selected_attribute():
    """The onPC window follows the selected attribute, not a local counter."""
    instance = EncoderPage()
    instance.update(
        page([_feature_with_selection(["A", "B", "C", "D", "E", "F", "G", "H"], 0)])
    )
    assert [instance.name_for(slot) for slot in range(1, 5)] == ["A", "B", "C", "D"]
    assert instance.bank == 1

    # User scrolls the attribute bank in onPC and selects E (index 4).
    instance.update(
        page([_feature_with_selection(["A", "B", "C", "D", "E", "F", "G", "H"], 4)])
    )
    assert [instance.name_for(slot) for slot in range(1, 5)] == ["E", "F", "G", "H"]
    assert instance.bank == 2


def test_short_feature_stays_on_first_window():
    instance = EncoderPage()
    instance.update(page([_feature_with_selection(["DIM", "CURVE"], 1)]))
    assert instance.name_for(1) == "DIM"
    assert instance.bank == 1


def test_selected_feature_wins():
    instance = EncoderPage()
    instance.update(
        page(
            [
                {
                    "i": 2,
                    "np": "Position",
                    "s": True,
                    "fea": [
                        {
                            "i": 1,
                            "np": "Position",
                            "s": True,
                            "att": [{"n": "PAN"}, {"n": "TILT"}],
                        },
                        {
                            "i": 2,
                            "np": "Position 2",
                            "s": False,
                            "att": [{"n": "OTHER"}],
                        },
                    ],
                }
            ]
        )
    )
    assert instance.name_for(1) == "PAN"


def test_update_merges_by_id():
    instance = EncoderPage()
    instance.update(page([feature("Dimmer", ["DIM"])]))
    instance.update(
        {
            "responseType": "presetTypes",
            "type": "update",
            "pre": [
                {
                    "i": 1,
                    "np": "Dimmer",
                    "s": True,
                    "fea": [{"i": 1, "np": "Dimmer", "s": True, "att": [{"n": "DIM"}, {"n": "CURVE"}]}],
                }
            ],
        }
    )
    assert instance.name_for(2) == "CURVE"


def test_ignores_other_frames():
    instance = EncoderPage()
    assert instance.update({"responseType": "login", "result": True}) is False


def test_feature_change_uses_new_selection():
    instance = EncoderPage()
    instance.update(
        page([_feature_with_selection(["A", "B", "C", "D", "E", "F", "G", "H"], 6)])
    )
    assert instance.bank == 2

    instance.update(
        page(
            [
                _feature_with_selection(
                    ["PAN", "TILT", "P1", "P2", "P3"], 0, index=2
                )
            ]
        )
    )
    assert instance.bank == 1
    assert instance.name_for(1) == "PAN"


def test_resolution_for_reads_encoder_resolution():
    page = EncoderPage()
    page.update(
        {
            "responseType": "presetTypes",
            "type": "full",
            "pre": [
                {
                    "i": 1,
                    "np": "Dimmer",
                    "s": True,
                    "fea": [
                        {
                            "i": 1,
                            "np": "Dimmer",
                            "s": True,
                            "att": [
                                {"n": "DIM", "np": "Dim", "s": True, "encoder_resolution": 2},
                                {"n": "CURVE", "np": "Curve", "s": False},
                            ],
                        }
                    ],
                }
            ],
        }
    )
    assert page.resolution_for(1) == 2
    assert page.resolution_for(2) == 0
    assert page.resolution_for(4) == 0


def test_incremental_update_clears_previous_sibling_selection():
    from ma2pi.encoder_page import EncoderPage

    page = EncoderPage()
    page.update(
        {
            "responseType": "presetTypes",
            "type": "full",
            "pre": [
                {
                    "i": 1,
                    "np": "Dimmer",
                    "s": True,
                    "fea": [{"i": 1, "np": "Dimmer", "s": True, "att": [{"n": "DIM", "s": True}]}],
                },
                {
                    "i": 2,
                    "np": "Position",
                    "s": False,
                    "fea": [{"i": 1, "np": "Position", "s": True, "att": [{"n": "PAN", "s": True}]}],
                },
            ],
        }
    )
    assert page.name_for(1) == "DIM"

    # Incremental update selects Position (i=2) without explicitly sending i=1 s=False
    page.update(
        {
            "responseType": "presetTypes",
            "type": "update",
            "pre": [{"i": 2, "s": True}],
        }
    )
    assert page.name_for(1) == "PAN"
