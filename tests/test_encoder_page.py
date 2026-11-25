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


def test_bank_advances_by_four():
    instance = EncoderPage()
    instance.update(page([feature("Color", ["A", "B", "C", "D", "E", "F", "G", "H"])]))
    assert [instance.name_for(slot) for slot in range(1, 5)] == ["A", "B", "C", "D"]
    assert instance.bank == 1
    instance.advance(1)
    assert [instance.name_for(slot) for slot in range(1, 5)] == ["E", "F", "G", "H"]
    assert instance.bank == 2
    instance.advance(1)
    assert [instance.name_for(slot) for slot in range(1, 5)] == ["A", "B", "C", "D"]


def test_bank_is_ignored_for_short_features():
    instance = EncoderPage()
    instance.update(page([feature("Dimmer", ["DIM", "CURVE"])]))
    instance.advance(1)
    assert instance.name_for(1) == "DIM"


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


def test_change_of_feature_resets_bank():
    instance = EncoderPage()
    instance.update(page([feature("Color", ["A", "B", "C", "D", "E", "F", "G", "H"])]))
    instance.advance(1)
    instance.update(
        page([feature("Position", ["PAN", "TILT", "P1", "P2", "P3"], index=2)])
    )
    assert instance.bank == 1
    assert instance.name_for(1) == "PAN"
