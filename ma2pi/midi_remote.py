"""MIDI addresses for executor buttons sent to MA MIDI remotes.

Every ``(page, executor, button)`` target gets one ``(channel, note)`` from the
reserved channels.  Targets are sorted, so the same configuration always
produces the same table; the remote sync rewrites the MA table when the target
set changes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Protocol

NOTES_PER_CHANNEL = 128
RELEASE_REPEAT_DELAY = 0.02

TargetKey = tuple[int | str, int, int]


@dataclass(frozen=True, slots=True)
class MidiAddress:
    channel: int  # 1..16
    note: int  # 0..127


class AddressSpaceExhausted(ValueError):
    def __init__(self, targets: int, capacity: int) -> None:
        super().__init__(
            f"{targets} MIDI-Ziele, aber nur {capacity} freie Adressen "
            f"({capacity // NOTES_PER_CHANNEL} Kanäle zu je {NOTES_PER_CHANNEL} Noten)"
        )
        self.targets = targets
        self.capacity = capacity


def _sort_key(target: TargetKey) -> tuple[int, int, int, int]:
    page, executor, button = target
    if page == "current":
        return (0, 0, executor, button)
    return (1, int(page), executor, button)


def assign_addresses(
    targets: Iterable[TargetKey], channels: tuple[int, ...]
) -> dict[TargetKey, MidiAddress]:
    ordered = sorted(set(targets), key=_sort_key)
    capacity = len(channels) * NOTES_PER_CHANNEL
    if len(ordered) > capacity:
        raise AddressSpaceExhausted(len(ordered), capacity)
    return {
        target: MidiAddress(
            channels[index // NOTES_PER_CHANNEL], index % NOTES_PER_CHANNEL
        )
        for index, target in enumerate(ordered)
    }


def note_message(address: MidiAddress, pressed: bool) -> bytes:
    status = (0x90 if pressed else 0x80) | (address.channel - 1)
    return bytes([status, address.note, 0x7F if pressed else 0x00])


class MidiSender(Protocol):
    @property
    def connected(self) -> bool: ...

    def send(self, midi: bytes) -> bool: ...


class MidiRemoteOutput:
    """Turn executor button presses into notes for the synced MA remotes.

    RTP-MIDI without journal cannot recover a lost packet, so every Note-Off is
    sent a second time; a stuck Flash is worse than a doubled release.
    """

    def __init__(self, sender: MidiSender) -> None:
        self.sender = sender
        self._addresses: dict[TargetKey, MidiAddress] = {}
        self._synced: frozenset[TargetKey] = frozenset()
        self._repeats: dict[TargetKey, asyncio.TimerHandle] = {}

    @property
    def connected(self) -> bool:
        return self.sender.connected

    def set_table(
        self, addresses: dict[TargetKey, MidiAddress], synced: Iterable[TargetKey]
    ) -> None:
        self._addresses = dict(addresses)
        self._synced = frozenset(synced) & frozenset(addresses)

    def address(self, target: TargetKey) -> MidiAddress | None:
        return self._addresses.get(target)

    def is_synced(self, target: TargetKey) -> bool:
        return target in self._synced

    def press(self, target: TargetKey, pressed: bool) -> bool:
        """Send the note for ``target``; False if it cannot reach the MA."""

        address = self._addresses.get(target)
        if address is None or target not in self._synced or not self.sender.connected:
            return False
        pending = self._repeats.pop(target, None)
        if pending is not None:
            pending.cancel()
        message = note_message(address, pressed)
        if not self.sender.send(message):
            return False
        if not pressed:
            self._repeats[target] = asyncio.get_running_loop().call_later(
                RELEASE_REPEAT_DELAY, self._repeat, target, message
            )
        return True

    def close(self) -> None:
        for handle in self._repeats.values():
            handle.cancel()
        self._repeats.clear()

    def _repeat(self, target: TargetKey, message: bytes) -> None:
        self._repeats.pop(target, None)
        self.sender.send(message)
