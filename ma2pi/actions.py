"""Actions produced by the mapping engine and consumed by the MA2 client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True, slots=True)
class Press:
    """Press a hardkey by Web Remote ``keyname``.

    ``hold`` marks the press as a held key (LUA transport only).  A tap uses
    ``hold=False``; a key held past the threshold gets an extra ``hold=True``
    press so the console keeps it down.
    """

    keyname: str
    hold: bool = False


@dataclass(frozen=True, slots=True)
class Release:
    """Release a hardkey by Web Remote ``keyname``."""

    keyname: str


@dataclass(frozen=True, slots=True)
class Command:
    text: str


@dataclass(frozen=True, slots=True)
class EncoderSlot:
    """Turn one of the four physical encoders.

    ``slot`` is 1..4 and addresses the encoder page the console reports
    (``presetTypes``); the client resolves the attribute name at dispatch time.
    """

    slot: int
    delta: float


@dataclass(frozen=True, slots=True)
class EncoderAttribute:
    """Turn a fixed attribute by name, independent of the console page."""

    name: str
    value: float


@dataclass(frozen=True, slots=True)
class ToggleScreenMode:
    """Switch the physical encoders between attribute and screen control.

    Attribute mode follows the window the onPC shows; screen mode hard-wires
    the encoders to the configured screen-encoder names.
    """


@dataclass(frozen=True, slots=True)
class ToggleFine:
    """Toggle fine resolution for one encoder slot."""

    slot: int


Action = Union[
    Press,
    Release,
    Command,
    EncoderSlot,
    EncoderAttribute,
    ToggleScreenMode,
    ToggleFine,
]

EncoderAction = Union[EncoderSlot, EncoderAttribute]


def is_encoder(action: Action) -> bool:
    return isinstance(action, (EncoderSlot, EncoderAttribute))


def encoder_key(action: EncoderAction) -> tuple[str, str | int]:
    if isinstance(action, EncoderSlot):
        return ("slot", action.slot)
    return ("attribute", action.name)


def merge_encoder(left: EncoderAction, right: EncoderAction) -> EncoderAction | None:
    """Coalesce two encoder actions for the same target.

    Returns ``None`` when the summed delta is zero.
    """

    if isinstance(left, EncoderSlot) and isinstance(right, EncoderSlot):
        if left.slot != right.slot:
            raise ValueError("encoder actions have different targets")
        delta = left.delta + right.delta
        return EncoderSlot(left.slot, delta) if delta else None
    if isinstance(left, EncoderAttribute) and isinstance(right, EncoderAttribute):
        if left.name != right.name:
            raise ValueError("encoder actions have different targets")
        value = left.value + right.value
        return EncoderAttribute(left.name, value) if value else None
    raise ValueError("encoder actions have different targets")
