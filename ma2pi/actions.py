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
    ``screen`` forces the configured screen-encoder target for this delta, even
    when the global screen-mode toggle is off (MA held + turn).
    """

    slot: int
    delta: float
    screen: bool = False


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
class EncoderResolution:
    """Cycle the onPC resolution of the attribute behind a slot.

    ``screen`` marks a screen-encoder target (MA held or screen mode); screen
    encoders have no attribute name and therefore no resolution.
    """

    slot: int
    screen: bool = False


@dataclass(frozen=True, slots=True)
class EncoderPress:
    """Press or release one of the four physical encoders.

    ``screen`` is fixed when the press happens so the release addresses the
    same hardware encoder even if MA changes in between.
    """

    slot: int
    pressed: bool
    screen: bool = False


@dataclass(frozen=True, slots=True)
class PlaybackButton:
    """Press or release an executor button through ``playbacks_userInput``.

    ``page``, ``executor`` and ``button`` are 1-based like the MA UI; the
    frame builder converts them to the 0-based Web Remote indices.
    """

    page: int | str
    executor: int
    button: int
    pressed: bool
    released: bool


@dataclass(frozen=True, slots=True)
class PlaybackFader:
    """Set an executor fader to an absolute value between 0.0 and 1.0."""

    page: int | str
    executor: int
    value: float


@dataclass(frozen=True, slots=True)
class PlaybacksRequest:
    """Ask the console for executor states (faders and buttons).

    ``start`` is the 0-based executor index and ``count`` the number of
    executors to read.  ``items_type`` and ``view`` select the Web Remote view:
    2 for executors below 100, 3 for button/floating executors.
    """

    page: int | str
    start: int
    count: int
    items_type: int
    view: int


Action = Union[
    Press,
    Release,
    Command,
    EncoderSlot,
    EncoderAttribute,
    ToggleScreenMode,
    EncoderPress,
    EncoderResolution,
    PlaybackButton,
    PlaybackFader,
    PlaybacksRequest,
]

EncoderAction = Union[EncoderSlot, EncoderAttribute]


def is_encoder(action: Action) -> bool:
    return isinstance(action, (EncoderSlot, EncoderAttribute))


def encoder_key(action: EncoderAction) -> tuple[str, str | int]:
    if isinstance(action, EncoderSlot):
        return ("screen" if action.screen else "slot", action.slot)
    return ("attribute", action.name)


def merge_encoder(left: EncoderAction, right: EncoderAction) -> EncoderAction | None:
    """Coalesce two encoder actions for the same target.

    Returns ``None`` when the summed delta is zero.
    """

    if isinstance(left, EncoderSlot) and isinstance(right, EncoderSlot):
        if left.slot != right.slot or left.screen != right.screen:
            raise ValueError("encoder actions have different targets")
        delta = left.delta + right.delta
        return (
            EncoderSlot(left.slot, delta, screen=left.screen) if delta else None
        )
    if isinstance(left, EncoderAttribute) and isinstance(right, EncoderAttribute):
        if left.name != right.name:
            raise ValueError("encoder actions have different targets")
        value = left.value + right.value
        return EncoderAttribute(left.name, value) if value else None
    raise ValueError("encoder actions have different targets")
