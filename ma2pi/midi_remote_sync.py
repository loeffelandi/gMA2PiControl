"""Keep the MA MIDI remote table in line with the MIDI playback targets.

Ownership is the channel alone: entries on ``[midi_remote].channels`` belong to
``ma2pi``, everything else in the show is left alone.  The MA accepts several
invalid commands silently, so the result always comes from reading the table
back after writing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .ma2_telnet import CommandError, MidiRemoteEntry, MidiRemoteTable
from .midi_remote import MidiAddress, TargetKey

LOGGER = logging.getLogger("ma2pi.midi_remote_sync")


@dataclass(frozen=True, slots=True)
class RemoteOp:
    kind: Literal["create", "change", "delete"]
    number: int
    target: TargetKey | None = None
    address: MidiAddress | None = None


@dataclass(frozen=True, slots=True)
class SyncResult:
    mode: str
    synced: frozenset[TargetKey]
    targets: int
    created: int = 0
    changed: int = 0
    removed: int = 0
    failed: int = 0
    deviations: int = 0
    error: str | None = None
    at: float = field(default_factory=time.time)


def entry_matches(entry: MidiRemoteEntry, target: TargetKey, address: MidiAddress) -> bool:
    page, executor, button = target
    return (
        entry.channel == address.channel
        and entry.note == address.note
        and entry.type == "Exec"
        and entry.page == page
        and entry.executor == executor
        and entry.button == f"Button {button}"
    )


def plan_sync(
    desired: dict[TargetKey, MidiAddress],
    entries: Iterable[MidiRemoteEntry],
    channels: Iterable[int],
) -> list[RemoteOp]:
    """Operations that turn the owned entries into ``desired``."""

    owned_channels = set(channels)
    owned = sorted(
        (entry for entry in entries if entry.channel in owned_channels),
        key=lambda entry: entry.number,
    )
    next_number = max((entry.number for entry in entries), default=0) + 1
    by_address: dict[tuple[int, int], MidiRemoteEntry] = {}
    spare: list[MidiRemoteEntry] = []
    for entry in owned:
        key = (entry.channel, entry.note)
        if key in by_address:
            spare.append(entry)
        else:
            by_address[key] = entry

    ops: list[RemoteOp] = []
    unplaced: list[tuple[TargetKey, MidiAddress]] = []
    used: set[int] = set()
    for target, address in desired.items():
        entry = by_address.get((address.channel, address.note))
        if entry is None:
            unplaced.append((target, address))
            continue
        used.add(entry.number)
        if not entry_matches(entry, target, address):
            ops.append(RemoteOp("change", entry.number, target, address))
    spare.extend(entry for entry in by_address.values() if entry.number not in used)
    spare.sort(key=lambda entry: entry.number)

    for target, address in unplaced:
        if spare:
            ops.append(RemoteOp("change", spare.pop(0).number, target, address))
        else:
            ops.append(RemoteOp("create", next_number, target, address))
            next_number += 1
    # Highest first: should the MA renumber after a delete, lower ones stay put.
    for entry in sorted(spare, key=lambda entry: entry.number, reverse=True):
        ops.append(RemoteOp("delete", entry.number))
    return ops


def synced_targets(
    desired: dict[TargetKey, MidiAddress], entries: Iterable[MidiRemoteEntry]
) -> frozenset[TargetKey]:
    by_address: dict[tuple[int, int], list[MidiRemoteEntry]] = {}
    for entry in entries:
        if entry.channel is not None:
            by_address.setdefault((entry.channel, entry.note), []).append(entry)
    synced = set()
    for target, address in desired.items():
        candidates = by_address.get((address.channel, address.note), [])
        # Two entries on one address would fire twice; that is not in sync.
        if len(candidates) == 1 and entry_matches(candidates[0], target, address):
            synced.add(target)
    return frozenset(synced)


async def sync_table(
    table: MidiRemoteTable,
    desired: dict[TargetKey, MidiAddress],
    channels: Iterable[int],
    mode: str,
) -> SyncResult:
    """Read, (in ``auto``) write the difference, read back."""

    channels = tuple(channels)
    await table.enter()
    entries = await table.list()
    ops = plan_sync(desired, entries, channels)
    if mode == "check":
        synced = synced_targets(desired, entries)
        if ops:
            LOGGER.warning(
                "MIDI-Remotes weichen ab (%d Änderungen nötig, sync = check)", len(ops)
            )
        return SyncResult(
            mode,
            synced,
            len(desired),
            failed=len(desired) - len(synced),
            deviations=len(ops),
        )

    created = changed = removed = 0
    for op in ops:
        try:
            if op.kind == "delete":
                await table.delete(op.number)
                removed += 1
                continue
            if op.kind == "create":
                await table.store(op.number)
            try:
                await _assign(table, op)
            except CommandError:
                if op.kind == "create":
                    await table.delete(op.number)
                raise
            if op.kind == "create":
                created += 1
            else:
                changed += 1
        except CommandError as exc:
            LOGGER.error(
                "MIDI-Remote %d für Ziel %s abgelehnt: %s", op.number, op.target, exc
            )

    entries = await table.list()
    synced = synced_targets(desired, entries)
    for target in desired.keys() - synced:
        LOGGER.error("MIDI-Remote für Ziel %s nach dem Abgleich nicht vorhanden", target)
    result = SyncResult(
        mode,
        synced,
        len(desired),
        created=created,
        changed=changed,
        removed=removed,
        failed=len(desired) - len(synced),
    )
    if ops:
        LOGGER.info(
            "MIDI-Remotes abgeglichen: %d angelegt, %d geändert, %d entfernt, %d fehlerhaft",
            created,
            changed,
            removed,
            result.failed,
        )
    return result


async def _assign(table: MidiRemoteTable, op: RemoteOp) -> None:
    page, executor, button = op.target
    await table.assign_exec(
        op.number,
        note=op.address.note,
        channel=op.address.channel,
        page=page,
        executor=executor,
        button=button,
    )


def failed_result(mode: str, targets: int, error: str) -> SyncResult:
    return SyncResult(mode, frozenset(), targets, failed=targets, error=error)
