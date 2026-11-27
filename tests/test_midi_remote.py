from __future__ import annotations

import asyncio

import pytest

from ma2pi.config import ConfigError
from ma2pi.midi_remote import (
    AddressSpaceExhausted,
    MidiAddress,
    MidiRemoteOutput,
    assign_addresses,
    note_message,
)
from ma2pi.playback_targets import midi_button_targets, resolve_target


class FakeSender:
    def __init__(self) -> None:
        self.connected = True
        self.sent: list[str] = []

    def send(self, midi: bytes) -> bool:
        if not self.connected:
            return False
        self.sent.append(midi.hex(" ").upper())
        return True


def _output(sender: FakeSender) -> MidiRemoteOutput:
    output = MidiRemoteOutput(sender)
    table = {(1, 5, 1): MidiAddress(16, 5), (1, 6, 1): MidiAddress(16, 6)}
    output.set_table(table, synced=table)
    return output


def test_note_messages_use_channel_and_full_velocity():
    assert note_message(MidiAddress(16, 5), True).hex(" ").upper() == "9F 05 7F"
    assert note_message(MidiAddress(16, 5), False).hex(" ").upper() == "8F 05 00"
    assert note_message(MidiAddress(1, 127), True).hex(" ").upper() == "90 7F 7F"


async def test_release_is_repeated_once():
    sender = FakeSender()
    output = _output(sender)
    assert output.press((1, 5, 1), True)
    assert output.press((1, 5, 1), False)
    assert sender.sent == ["9F 05 7F", "8F 05 00"]
    await asyncio.sleep(0.05)
    assert sender.sent == ["9F 05 7F", "8F 05 00", "8F 05 00"]


async def test_fast_tapping_keeps_order_per_target():
    sender = FakeSender()
    output = _output(sender)
    output.press((1, 5, 1), True)
    output.press((1, 5, 1), False)
    output.press((1, 6, 1), True)
    output.press((1, 5, 1), True)
    await asyncio.sleep(0.05)
    # The pending repeat of 5 must not land after its next Note-On.
    assert sender.sent == ["9F 05 7F", "8F 05 00", "9F 06 7F", "9F 05 7F"]


async def test_press_needs_synced_target_and_session():
    sender = FakeSender()
    output = MidiRemoteOutput(sender)
    output.set_table({(1, 5, 1): MidiAddress(16, 5)}, synced=[])
    assert not output.press((1, 5, 1), True)
    assert not output.press((9, 9, 1), True)
    output.set_table({(1, 5, 1): MidiAddress(16, 5)}, synced=[(1, 5, 1)])
    sender.connected = False
    assert not output.press((1, 5, 1), True)
    assert sender.sent == []


async def test_close_cancels_pending_repeats():
    sender = FakeSender()
    output = _output(sender)
    output.press((1, 5, 1), False)
    output.close()
    await asyncio.sleep(0.05)
    assert sender.sent == ["8F 05 00"]


def test_addresses_follow_sorted_targets():
    addresses = assign_addresses(
        [(2, 101, 1), ("current", 6, 1), (1, 5, 2), ("current", 1, 3)], (16,)
    )
    assert addresses == {
        ("current", 1, 3): MidiAddress(16, 0),
        ("current", 6, 1): MidiAddress(16, 1),
        (1, 5, 2): MidiAddress(16, 2),
        (2, 101, 1): MidiAddress(16, 3),
    }


def test_duplicate_targets_share_one_address():
    addresses = assign_addresses([(1, 101, 1), (1, 101, 1), (1, 102, 1)], (16,))
    assert len(addresses) == 2
    assert addresses[(1, 101, 1)] != addresses[(1, 102, 1)]


def test_addresses_continue_on_the_next_channel():
    targets = [(1, executor, 1) for executor in range(1, 131)]
    addresses = assign_addresses(targets, (15, 16))
    assert addresses[(1, 128, 1)] == MidiAddress(15, 127)
    assert addresses[(1, 129, 1)] == MidiAddress(16, 0)


def test_exhausted_address_space_names_counts():
    targets = [(1, executor, 1) for executor in range(1, 130)]
    with pytest.raises(AddressSpaceExhausted, match="129 MIDI-Ziele, aber nur 128"):
        assign_addresses(targets, (16,))


def test_same_target_from_two_banks_shares_an_address(make_config):
    def edit(data):
        data["midi_remote"] = {"enabled": True, "channels": [13, 14, 15, 16]}
        data["mapping"]["device_banks"] = {
            "midicraft-enc": {
                "2": {"playbacks": {"mc_click_1": {"executor": 6}}},
            }
        }

    config = make_config(edit)
    bank1 = resolve_target(config, "midicraft-enc", 1, "mc_click_1")
    bank2 = resolve_target(config, "midicraft-enc", 2, "mc_click_1")
    assert (bank1.page, bank1.executor) == (bank2.page, bank2.executor) == ("current", 6)
    assert bank1.transport == "midi"
    addresses = assign_addresses(midi_button_targets(config), config.midi_remote.channels)
    assert ("current", 6, 1) in addresses


def test_midi_targets_follow_bank_offsets(make_config):
    def edit(data):
        data["midi_remote"] = {"enabled": True, "channels": [13, 14, 15, 16]}
        data["mapping"]["device_banks"] = {"midicraft-enc": {"bank_size": 5}}

    targets = midi_button_targets(make_config(edit))
    assert ("current", 101, 1) in targets
    assert ("current", 101 + 15 * 5, 1) in targets
    assert len(targets) == 20 * 16


def test_web_and_fader_targets_are_not_midi_targets(make_config):
    def edit(data):
        data["midi_remote"] = {"enabled": True}
        data["mapping"]["playbacks"]["mc_click_1"]["transport"] = "web"

    targets = midi_button_targets(make_config(edit))
    assert ("current", 6, 1) not in targets
    assert ("current", 7, 1) in targets
    assert all(executor != 0 for _, executor, _ in targets)
    assert len(targets) == 19


def test_no_midi_targets_without_midi_remote(config):
    assert midi_button_targets(config) == set()


def test_config_rejects_exhausted_address_space(make_config):
    def edit(data):
        data["midi_remote"] = {"enabled": True, "channels": [16]}
        data["mapping"]["device_banks"] = {"midicraft-enc": {"bank_size": 5}}

    with pytest.raises(ConfigError, match=r"midi_remote\.channels.*320 MIDI-Ziele"):
        make_config(edit)
