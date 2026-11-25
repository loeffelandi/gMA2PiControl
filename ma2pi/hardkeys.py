"""Web Remote ``keyname`` catalog for grandMA2 onPC.

The onPC Web Remote has no numeric hardkey request.  Keys are sent as
``{"requestType": "keyname", "keyname": "<NAME>", "value": 1|0}``.  The names
below are the identifiers used by the web remote UI shipped with onPC
(``js/main.js``, ``window.commands``), verified against the served file.

``resolve`` accepts a name from :data:`KEYNAMES` directly or a friendly alias
such as ``"Fix"`` or ``"Go +"``.  Lookup is case-insensitive.  Note that the
web remote has no X1–X20 keys; map those Cherry keys to a ``command`` instead.
"""

from __future__ import annotations

# Identifiers accepted by the onPC Web Remote ``keyname`` request.
KEYNAMES: frozenset[str] = frozenset(
    {
        "SET",
        "PREV",
        "NEXT",
        "CLEAR",
        "FIXTURE_CHANNEL",
        "FIXTURE_GROUP_PRESET",
        "EXEC_CUE",
        "STORE_UPDATE",
        "OOPS",
        "ESC",
        "PUNKT",
        "PLUS",
        "MINUS",
        "THRU",
        "IF",
        "AT",
        "FULL",
        "HIGH",
        "ENTER",
        "OFF",
        "ON",
        "ASSIGN",
        "LABEL",
        "COPY",
        "TIME",
        "PAGE",
        "MACRO",
        "DELETE",
        "GOTO",
        "GO_PLUS",
        "GO_MINUS",
        "PAUSE",
        "SELECT",
        "FIXTURE",
        "FIX",
        "SEQU",
        "CUE",
        "PRESET",
        "EDIT",
        "UPDATE",
        "EXEC",
        "STORE",
        "GROUP",
        "PROG_ONLY",
        "SPECIAL_DIALOGUE",
        "SOLO",
        "ODD",
        "EVEN",
        "WINGS",
        "RESET",
        "MA",
        "UP",
        "DOWN",
        "LEFT",
        "RIGHT",
        # Number block.
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        # Web-remote only toggles (they send their own keyname).
        "layerMode",
        "featureSort",
        "fixtureSort",
        "channelSort",
        "hideName",
    }
)

# Friendly names, mostly matching the printed Cherry key labels.
ALIASES: dict[str, str] = {
    "Fix": "FIX",
    "Store": "STORE",
    "Update": "UPDATE",
    "Clear": "CLEAR",
    "At": "AT",
    "Thru": "THRU",
    "Please": "ENTER",
    "Enter": "ENTER",
    "Go +": "GO_PLUS",
    "Go -": "GO_MINUS",
    "Go+": "GO_PLUS",
    "Go-": "GO_MINUS",
    "go_plus": "GO_PLUS",
    "go_minus": "GO_MINUS",
    "Pause": "PAUSE",
    "Prev": "PREV",
    "Next": "NEXT",
    "Oops": "OOPS",
    "Esc": "ESC",
    "Full": "FULL",
    "High": "HIGH",
    "Off": "OFF",
    "On": "ON",
    "Assign": "ASSIGN",
    "Label": "LABEL",
    "Copy": "COPY",
    "Time": "TIME",
    "Page": "PAGE",
    "Macro": "MACRO",
    "Delete": "DELETE",
    "Goto": "GOTO",
    "Select": "SELECT",
    "Sequence": "SEQU",
    "Cue": "CUE",
    "Preset": "PRESET",
    "Edit": "EDIT",
    "Exec": "EXEC",
    "Group": "GROUP",
    "Solo": "SOLO",
    "Odd": "ODD",
    "Even": "EVEN",
    "Wings": "WINGS",
    "Reset": "RESET",
    "Dot": "PUNKT",
    "Plus": "PLUS",
    "Minus": "MINUS",
}

# Names that must always resolve; used by the tests and the docs.
REQUIRED_NAMES: tuple[str, ...] = (
    "MA",
    "Fix",
    "Store",
    "Clear",
    "At",
    "Thru",
    "Please",
    "Go +",
    "Go -",
    "Pause",
    "0",
    "9",
)

_LOOKUP: dict[str, str] = {name.lower(): name for name in KEYNAMES}
_LOOKUP.update({alias.lower(): target for alias, target in ALIASES.items()})


class UnknownHardkey(KeyError):
    """Raised when a hardkey name is neither a keyname nor a known alias."""


def resolve(value: str) -> str:
    """Return the Web Remote keyname for a name or alias."""

    if not isinstance(value, str):
        raise UnknownHardkey(value)
    target = _LOOKUP.get(value.strip().lower())
    if target is None:
        raise UnknownHardkey(value)
    return target


def canonical_name(value: str) -> str:
    """Return the exact keyname spelling for a name or alias."""

    return resolve(value)


def is_known(value: str) -> bool:
    return isinstance(value, str) and value.strip().lower() in _LOOKUP
