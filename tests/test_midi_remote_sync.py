from __future__ import annotations

import dataclasses

from ma2pi.ma2_telnet import CommandError, MidiRemoteEntry
from ma2pi.midi_remote import MidiAddress
from ma2pi.midi_remote_sync import RemoteOp, plan_sync, sync_table, synced_targets


def own(number, note, page, executor, button=1, channel=16):
    return MidiRemoteEntry(number, note, channel, "Exec", page, executor, f"Button {button}")


FOREIGN = MidiRemoteEntry(1, 0, 1, "Exec", 1, 102, "Button 1")


class FakeTable:
    """MA semantics as measured: silent assign on missing entries, store → All."""

    def __init__(self, entries=(), reject_executor=None):
        self.entries = {entry.number: entry for entry in entries}
        self.reject_executor = reject_executor
        self.writes: list[str] = []

    async def enter(self):
        pass

    async def list(self, number=None):
        return [self.entries[key] for key in sorted(self.entries)]

    async def store(self, number):
        self.writes.append(f"store {number}")
        self.entries[number] = MidiRemoteEntry(
            number, 0, None, "None", "current", 1, "Button 1"
        )

    async def assign_exec(self, number, *, note, channel, page, executor, button):
        self.writes.append(f"assign {number}")
        if executor == self.reject_executor:
            raise CommandError(f"assign {number}", 7, "NUMBER TOO LONG")
        if number in self.entries:
            self.entries[number] = MidiRemoteEntry(
                number, note, channel, "Exec", page, executor, f"Button {button}"
            )

    async def delete(self, number):
        self.writes.append(f"delete {number}")
        self.entries.pop(number, None)


def test_plan_creates_behind_the_highest_number():
    ops = plan_sync({(1, 102, 1): MidiAddress(16, 0)}, [FOREIGN], [16])
    assert ops == [RemoteOp("create", 2, (1, 102, 1), MidiAddress(16, 0))]


def test_plan_reuses_spare_entries_and_deletes_highest_first():
    entries = [FOREIGN, own(5, 0, 1, 1), own(6, 1, 1, 2), own(7, 2, 1, 3), own(8, 2, 1, 3)]
    desired = {(1, 1, 1): MidiAddress(16, 0), (2, 9, 1): MidiAddress(16, 9)}
    assert plan_sync(desired, entries, [16]) == [
        RemoteOp("change", 6, (2, 9, 1), MidiAddress(16, 9)),
        RemoteOp("delete", 8),
        RemoteOp("delete", 7),
    ]


def test_double_address_is_not_synced():
    desired = {(1, 1, 1): MidiAddress(16, 0)}
    assert synced_targets(desired, [own(5, 0, 1, 1)]) == {(1, 1, 1)}
    assert synced_targets(desired, [own(5, 0, 1, 1), own(6, 0, 1, 1)]) == frozenset()


async def test_new_target_is_created():
    table = FakeTable([FOREIGN])
    desired = {(1, 102, 1): MidiAddress(16, 0)}
    result = await sync_table(table, desired, [16], "auto")
    assert table.entries[2] == own(2, 0, 1, 102)
    assert (result.created, result.changed, result.removed, result.failed) == (1, 0, 0, 0)
    assert result.synced == {(1, 102, 1)}


async def test_removed_target_is_deleted():
    table = FakeTable([FOREIGN, own(2, 0, 1, 102)])
    result = await sync_table(table, {}, [16], "auto")
    assert sorted(table.entries) == [1]
    assert result.removed == 1


async def test_foreign_entry_on_same_executor_stays():
    table = FakeTable([FOREIGN, own(2, 0, "current", 7)])
    await sync_table(table, {(1, 102, 1): MidiAddress(16, 0)}, [16], "auto")
    assert table.entries[1] == FOREIGN
    assert table.entries[2] == own(2, 0, 1, 102)
    assert "delete 1" not in table.writes and "assign 1" not in table.writes


async def test_rejected_entry_counts_as_failed_and_is_cleaned_up():
    table = FakeTable([FOREIGN], reject_executor=99999)
    desired = {
        (1, 1, 1): MidiAddress(16, 0),
        (1, 2, 1): MidiAddress(16, 1),
        (1, 99999, 1): MidiAddress(16, 2),
    }
    result = await sync_table(table, desired, [16], "auto")
    assert (result.created, result.failed) == (2, 1)
    assert result.synced == {(1, 1, 1), (1, 2, 1)}
    # The freshly stored entry would sit on channel All, outside ma2pi's channels.
    assert sorted(table.entries) == [1, 2, 3]


async def test_silently_ignored_write_is_found_on_read_back():
    table = FakeTable([FOREIGN])

    async def drop(number, **_):
        table.writes.append(f"assign {number}")

    table.assign_exec = drop
    result = await sync_table(table, {(1, 1, 1): MidiAddress(16, 0)}, [16], "auto")
    assert result.created == 1
    assert result.failed == 1
    assert result.synced == frozenset()


async def test_check_reports_without_writing():
    table = FakeTable([FOREIGN, own(2, 0, 1, 1), own(3, 5, 1, 50)])
    desired = {(1, 1, 1): MidiAddress(16, 0), (1, 2, 1): MidiAddress(16, 1)}
    result = await sync_table(table, desired, [16], "check")
    assert table.writes == []
    assert result.synced == {(1, 1, 1)}
    # Entry 3 would be rewritten for the missing target: one change.
    assert (result.failed, result.deviations) == (1, 1)


async def test_second_run_is_a_no_op():
    table = FakeTable([FOREIGN])
    desired = {(1, 1, 1): MidiAddress(16, 0), ("current", 3, 2): MidiAddress(16, 1)}
    await sync_table(table, desired, [16], "auto")
    table.writes.clear()
    result = await sync_table(table, desired, [16], "auto")
    assert table.writes == []
    assert dataclasses.astuple(result)[2:7] == (2, 0, 0, 0, 0)
