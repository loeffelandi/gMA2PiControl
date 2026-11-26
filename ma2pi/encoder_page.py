"""The encoder page the onPC reports for the current selection.

The web remote shows four attribute encoders per page.  Which attributes they
are is not fixed: it depends on the selected preset type and feature.  The
console publishes this model as a ``presetTypes`` response:

```
{"responseType": "presetTypes", "type": "full",
 "pre": [{"i": 1, "np": "Dimmer",
          "fea": [{"i": 1, "np": "Dimmer", "s": true,
                   "att": [{"n": "DIM", "np": "Dim", "s": true}, ...]}],
          "s": false}, ...]}
```

``n`` is the attribute name the ``encoder`` request expects (``DIM``, ``PAN``,
``TILT``, ``SHUTTER`` …).  This class keeps that model, the selected feature and
the 4-wide window the physical encoders address.
"""

from __future__ import annotations

from typing import Any

WINDOW = 4


def _selected(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    for item in items:
        if item.get("s"):
            return item
    return items[0]


def _merge_by(items: list[dict[str, Any]], new_items: list[dict[str, Any]], key: str) -> None:
    index = {item.get(key): item for item in items}
    for new in new_items:
        existing = index.get(new.get(key))
        if existing is None:
            items.append(new)
            index[new.get(key)] = new
        else:
            _merge(existing, new)


def _merge(target: dict[str, Any], new: dict[str, Any]) -> None:
    for key, value in new.items():
        if key == "fea" and isinstance(value, list):
            _merge_by(target.setdefault("fea", []), value, "i")
        elif key == "att" and isinstance(value, list):
            _merge_by(target.setdefault("att", []), value, "n")
        else:
            target[key] = value


class EncoderPage:
    """Attribute model for the four physical encoders."""

    def __init__(self) -> None:
        self._preset_types: list[dict[str, Any]] = []
        self._window_start = 0

    @property
    def known(self) -> bool:
        return bool(self.attributes())

    def attributes(self) -> list[dict[str, Any]]:
        preset_type = _selected(self._preset_types)
        if preset_type is None:
            return []
        feature = _selected(preset_type.get("fea") or [])
        if feature is None:
            return []
        attrs = [att for att in (feature.get("att") or []) if att.get("n")]
        # The onPC shows the window that contains the selected attribute; the
        # daemon follows it instead of keeping its own bank counter.  This way
        # scrolling the attribute bank in the UI moves the physical encoders.
        selected = next(
            (index for index, att in enumerate(attrs) if att.get("s")), 0
        )
        self._window_start = (selected // WINDOW) * WINDOW
        return attrs

    def update(self, frame: dict[str, Any]) -> bool:
        if frame.get("responseType") != "presetTypes":
            return False
        presets = frame.get("pre")
        if not isinstance(presets, list):
            return False
        if frame.get("type") == "full" or not self._preset_types:
            self._preset_types = [pt for pt in presets if isinstance(pt, dict)]
        else:
            _merge_by(self._preset_types, [pt for pt in presets if isinstance(pt, dict)], "i")
        # Re-evaluate the selection so a changed feature resets the bank.
        self.attributes()
        return True

    def _at(self, slot: int) -> dict[str, Any] | None:
        attrs = self.attributes()
        if not attrs or slot < 1:
            return None
        index = self._window_start + slot - 1
        if index >= len(attrs):
            return None
        return attrs[index]

    def name_for(self, slot: int) -> str | None:
        att = self._at(slot)
        return str(att["n"]) if att is not None else None

    def resolution_for(self, slot: int) -> int:
        att = self._at(slot)
        if att is None:
            return 0
        value = att.get("encoder_resolution", 0)
        return value if value in (0, 1, 2) else 0

    def label_for(self, slot: int) -> str | None:
        att = self._at(slot)
        if att is None:
            return None
        return str(att.get("np") or att["n"])

    @property
    def bank(self) -> int:
        self.attributes()
        return self._window_start // WINDOW + 1
