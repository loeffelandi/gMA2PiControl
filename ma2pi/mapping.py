"""Mapping engine: logical controls to MA2 actions.

The engine is strictly sequential.  It owns the held-key register, modifier
chords, CMD keys and the encoder accumulation/flush pipeline.  Frames are
submitted through the same small action interface the MA2 client exposes, which
keeps the engine testable without sockets.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Protocol

from . import hardkeys
from .actions import EncoderAttribute, EncoderSlot
from .config import (
    AppConfig,
    EncoderMapping,
    EncoderProfile,
    KeyMapping,
    MidiEncoderProfile,
    ModifierMapping,
)
from .events import InputEvent

LOGGER = logging.getLogger("ma2pi.mapping")

ENCODER_PREFIX = "encoder."

#: Holding this hardkey turns the slot encoders into screen encoders.
SCREEN_ENCODER_MODIFIER = "MA"


def encoder_control(encoder_id: int) -> str:
    return f"{ENCODER_PREFIX}{encoder_id}"


class ActionSink(Protocol):
    def press(self, keyname: str, hold: bool = False) -> None: ...
    def release(self, keyname: str) -> None: ...
    def command(self, text: str) -> None: ...
    def encoder_slot(self, slot: int, delta: float, screen: bool = False) -> None: ...
    def encoder_attribute(self, name: str, value: float) -> None: ...
    def toggle_screen_mode(self) -> None: ...
    def encoder_press(self, slot: int, pressed: bool, screen: bool = False) -> None: ...
    def encoder_resolution(self, slot: int, screen: bool = False) -> None: ...
    def screen_shortcut(self, screen: int) -> None: ...


@dataclass(frozen=True, slots=True)
class HeldKey:
    control: str
    device: str
    order: int
    keyname: str | None
    is_command: bool
    is_local_modifier: bool


@dataclass
class EncoderState:
    profile: EncoderProfile | MidiEncoderProfile
    mapping: EncoderMapping
    pending: float = 0.0
    first_feed: float | None = None
    last_feed: float | None = None
    last_send: float = -1e9
    detent_times: deque[float] = field(default_factory=deque)
    dropped: int = 0
    screen: bool = False

    @property
    def is_slot(self) -> bool:
        return self.mapping.slot is not None


class MappingEngine:
    def __init__(
        self,
        config: AppConfig,
        sink: ActionSink,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.sink = sink
        self._clock = clock
        self._held: dict[str, HeldKey] = {}
        self._order = 0
        self._pending_hold: dict[str, float] = {}
        self._press_targets: dict[str, tuple[int, bool]] = {}
        self.modifier_hook: Callable[[str, bool], None] | None = None
        self._encoders: dict[int, EncoderState] = {}
        self._bank_encoder_states: dict[tuple[str, int, int], EncoderState] = {}
        self._encoder_profiles: dict[int, EncoderProfile | MidiEncoderProfile] = {}
        self._stop = asyncio.Event()
        self._frozen = False
        self._build_encoders()

    def _build_encoders(self) -> None:
        profiles: dict[int, EncoderProfile | MidiEncoderProfile] = {}
        for profile in self.config.profiles.values():
            for encoder in profile.encoders:
                profiles.setdefault(encoder.id, encoder)
            for encoder in profile.midi_encoders:
                profiles.setdefault(encoder.id, encoder)
        self._encoder_profiles = profiles
        for mapping in self.config.mapping.encoders:
            profile = profiles.get(mapping.id)
            if profile is None:  # already validated, defensive
                continue
            self._encoders[mapping.id] = EncoderState(profile=profile, mapping=mapping)

    def _all_states(self):
        yield from self._encoders.values()
        yield from self._bank_encoder_states.values()

    def _bank_layer(self, device: str, bank: int):
        settings = self.config.mapping.device_banks.get(device)
        if settings is None:
            return None
        return settings.banks.get(bank)

    def _key_mapping(self, control: str, device: str, bank: int) -> KeyMapping | None:
        layer = self._bank_layer(device, bank)
        if layer is not None and control in layer.keys:
            return layer.keys[control]
        return self.config.mapping.keys.get(control)

    def _bank_encoder_override(
        self, device: str, bank: int, encoder_id: int
    ) -> EncoderMapping | None:
        layer = self._bank_layer(device, bank)
        if layer is None:
            return None
        return layer.encoders.get(encoder_id)

    # -- input ------------------------------------------------------------

    def handle(self, event: InputEvent, now: float | None = None) -> None:
        if self._frozen:
            # A configuration apply is in progress; dropping the event avoids
            # half a chord crossing the switch-over.
            LOGGER.debug("Apply läuft, Eingabe verworfen: %s %s", event.kind, event.control)
            return
        moment = self._clock() if now is None else now
        if event.kind == "key":
            if event.value == 1:
                self._press(event.control, event.device, moment, event.bank)
            elif event.value == 0:
                self._release(event.control, event.device, moment)
            else:
                LOGGER.debug("ignoriere Key-Wert %s für %s", event.value, event.control)
        elif event.kind == "encoder":
            self._feed_encoder(
                event.control, event.value, moment, event.device, event.bank
            )
        else:
            LOGGER.debug("ignoriere unbekannten Event-Typ %s", event.kind)

    def _press(self, control: str, device: str, now: float, bank: int = 1) -> None:
        if control in self._held:
            LOGGER.debug("Doppel-Press ignoriert: %s", control)
            return
        modifier = self.config.mapping.modifiers.get(control)
        key = self._key_mapping(control, device, bank)

        if modifier is None and key is None:
            LOGGER.debug("unmapptes Control ignoriert: %s", control)
            return

        if modifier is not None and modifier.local:
            self.flush_all(now)
            self._add_held(
                control, device, None, is_command=False, is_local_modifier=True
            )
            LOGGER.debug("lokaler Modifier %s gedrückt", control)
            self._notify_modifier(control, True)
            return

        if modifier is not None:
            if modifier.hardkey is None:  # defensive
                return
            self._add_held(
                control,
                device,
                hardkeys.resolve(modifier.hardkey),
                is_command=False,
                is_local_modifier=False,
            )
            keyname = hardkeys.resolve(modifier.hardkey)
            if self.config.ma2.hardkey_transport == "lua":
                self._emit_press(control, keyname, hold=False)
                self._emit_press(control, keyname, hold=True)
            else:
                self._emit_press(control, keyname)
            return

        assert key is not None
        if key.screen_mode:
            self.flush_all(now)
            self._add_held(control, device, None, True, False)
            self.sink.toggle_screen_mode()
            return
        if key.encoder_press is not None:
            cycle = self.config.mapping.resolution.cycle_modifier
            if cycle and cycle in self._held:
                self.flush_all(now)
                self._add_held(control, device, None, True, False)
                self.sink.encoder_resolution(
                    key.encoder_press, self._screen_encoder_requested()
                )
                return
            screen = self._screen_encoder_requested()
            self._add_held(control, device, None, True, False)
            self._press_targets[control] = (key.encoder_press, screen)
            self.sink.encoder_press(key.encoder_press, True, screen)
            return
        if key.screen is not None:
            self._add_held(control, device, None, True, False)
            self.sink.screen_shortcut(key.screen)
            return
        if key.hardkey is not None:
            keyname = hardkeys.resolve(key.hardkey)
            self._add_held(control, device, keyname, False, False)
            self._emit_press(control, keyname, hold=False)
            if self.config.ma2.hardkey_transport == "lua":
                self._pending_hold[control] = now
        elif key.command is not None:
            self._add_held(control, device, None, True, False)
            LOGGER.debug("CMD-Key %s -> %s", control, key.command)
            self.sink.command(key.command)

    def _release(self, control: str, device: str, now: float) -> None:
        held = self._held.get(control)
        if held is None:
            LOGGER.debug("Release ohne Press ignoriert: %s", control)
            return
        if device and held.device and held.device != device:
            # The control name is shared between devices; a release from a
            # different device must not end the hold of the one that pressed.
            LOGGER.debug(
                "Release von %s ignoriert, %s wird von %s gehalten",
                device,
                control,
                held.device,
            )
            return
        if held.is_local_modifier:
            self.flush_all(now)
            self._notify_modifier(control, False)
        if held.keyname is not None:
            self._emit_release(control, held.keyname)
        target = self._press_targets.pop(control, None)
        if target is not None:
            self.sink.encoder_press(target[0], False, target[1])
        self._held.pop(control, None)
        self._pending_hold.pop(control, None)

    def _notify_modifier(self, control: str, pressed: bool) -> None:
        if self.modifier_hook is not None:
            try:
                self.modifier_hook(control, pressed)
            except Exception as exc:  # LED feedback must never break input
                LOGGER.debug("Modifier-Hook fehlgeschlagen: %s", exc)

    def _add_held(
        self,
        control: str,
        device: str,
        keyname: str | None,
        is_command: bool,
        is_local_modifier: bool,
    ) -> None:
        self._order += 1
        self._held[control] = HeldKey(
            control=control,
            device=device,
            order=self._order,
            keyname=keyname,
            is_command=is_command,
            is_local_modifier=is_local_modifier,
        )

    def _emit_press(self, control: str, keyname: str, hold: bool = False) -> None:
        LOGGER.debug("Press %s -> Keyname %s (hold=%s)", control, keyname, hold)
        self.sink.press(keyname, hold)

    def _emit_release(self, control: str, keyname: str) -> None:
        LOGGER.debug("Release %s -> Keyname %s", control, keyname)
        self.sink.release(keyname)

    # -- cleanup ----------------------------------------------------------

    def release_device(self, device: str, *, send: bool = True) -> None:
        keys = sorted(
            (held for held in self._held.values() if held.device == device),
            key=lambda held: held.order,
            reverse=True,
        )
        for held in keys:
            if send and held.keyname is not None:
                self._emit_release(held.control, held.keyname)
            target = self._press_targets.pop(held.control, None)
            if send and target is not None:
                self.sink.encoder_press(target[0], False, target[1])
            self._held.pop(held.control, None)
            self._pending_hold.pop(held.control, None)
        if keys:
            LOGGER.warning("Gerät %s verloren: %d Taste(n) freigegeben", device, len(keys))

    def cleanup(self, *, send: bool = True) -> None:
        keys = sorted(self._held.values(), key=lambda held: held.order, reverse=True)
        for held in keys:
            if send and held.keyname is not None:
                self._emit_release(held.control, held.keyname)
        if send:
            for slot, screen in self._press_targets.values():
                self.sink.encoder_press(slot, False, screen)
        self._press_targets.clear()
        if keys:
            LOGGER.info("%d gehaltene Taste(n) freigegeben", len(keys))
        self._held.clear()
        self._order = 0
        self._pending_hold.clear()
        self.clear_encoder_pending()

    def on_connection_lost(self) -> None:
        """Clear local state without replaying frames on the new session."""

        if self._held:
            LOGGER.warning(
                "Session verloren: %d gehaltene Taste(n) lokal verworfen", len(self._held)
            )
        self._press_targets.clear()
        self._held.clear()
        self._order = 0
        self._pending_hold.clear()
        self.clear_encoder_pending()

    def clear_encoder_pending(self) -> None:
        for state in self._all_states():
            state.pending = 0.0
            state.first_feed = None
            state.last_feed = None

    # -- hot reload -------------------------------------------------------

    @property
    def frozen(self) -> bool:
        """True while an apply owns the engine and input is being discarded."""

        return self._frozen

    def freeze(self) -> None:
        """Discard input and deferred encoder work until :meth:`unfreeze`."""

        self._frozen = True

    def unfreeze(self) -> None:
        self._frozen = False

    def swap_config(self, config: AppConfig) -> None:
        """Activate ``config`` and rebuild the encoder state from it.

        Held keys must already have been released and pending encoder deltas
        dropped (see :meth:`cleanup`); this method only swaps the static
        configuration so no frame is replayed from the old one.
        """

        self.config = config
        self._encoders.clear()
        self._bank_encoder_states.clear()
        self._build_encoders()

    # -- resolution -------------------------------------------------------

    def _resolution_modifier(self, state: EncoderState) -> tuple[str, float]:
        resolution = self.config.mapping.resolution
        ultra = self.config.mapping.resolution.ultra_modifier
        fine = self.config.mapping.resolution.fine_modifier
        values = resolution.attribute
        if ultra and ultra in self._held:
            return "ultra", values.ultra
        if fine and fine in self._held:
            return "fine", values.fine
        return "normal", values.normal

    # -- encoders ---------------------------------------------------------

    def _screen_encoder_requested(self) -> bool:
        """True while the MA modifier is held (MA + turn = screen encoder)."""

        ma = hardkeys.resolve(SCREEN_ENCODER_MODIFIER)
        return any(held.keyname == ma for held in self._held.values())

    def _feed_encoder(
        self, control: str, delta: int, now: float, device: str = "", bank: int = 1
    ) -> None:
        if not control.startswith(ENCODER_PREFIX):
            LOGGER.debug("unbekanntes Encoder-Control %s", control)
            return
        try:
            encoder_id = int(control[len(ENCODER_PREFIX) :])
        except ValueError:
            LOGGER.debug("ungültiges Encoder-Control %s", control)
            return
        state = self._encoders.get(encoder_id)
        override = self._bank_encoder_override(device, bank, encoder_id)
        if override is not None:
            key = (device, bank, encoder_id)
            state = self._bank_encoder_states.get(key)
            if state is None:
                profile = self._encoder_profiles.get(encoder_id)
                if profile is None:
                    LOGGER.debug("Encoder %s ist nicht gemappt", encoder_id)
                    return
                state = EncoderState(profile=profile, mapping=override)
                self._bank_encoder_states[key] = state
        if state is None:
            LOGGER.debug("Encoder %s ist nicht gemappt", encoder_id)
            return
        if delta == 0:
            return

        screen = self._screen_encoder_requested()
        if state.is_slot and state.pending != 0 and state.screen != screen:
            # Never mix attribute and screen detents in one frame; the target
            # changed between feeds (MA pressed or released).
            self._flush_state(state, now)
        state.screen = screen if state.is_slot else False

        state.detent_times.append(now)
        window = self.config.mapping.acceleration.window
        while state.detent_times and now - state.detent_times[0] > window:
            state.detent_times.popleft()
        multiplier = self._acceleration_multiplier(len(state.detent_times))
        if state.is_slot:
            resolution = 1.0
        else:
            _, resolution = self._resolution_modifier(state)
        state.pending += delta * multiplier * resolution
        state.first_feed = now if state.first_feed is None else state.first_feed
        state.last_feed = now

        limit = float(self.config.rate_limit.max_pending_delta)
        if abs(state.pending) > limit:
            state.pending = math.copysign(limit, state.pending)
            state.dropped += 1
            LOGGER.warning(
                "Encoder %d Pending auf %d gekappt (ingesamt %d Kappungen)",
                encoder_id,
                int(limit),
                state.dropped,
            )
        LOGGER.debug(
            "Encoder %d delta=%+d rate=%d multiplier=%.2f pending=%.3f",
            encoder_id,
            delta,
            len(state.detent_times),
            multiplier,
            state.pending,
        )

    def _acceleration_multiplier(self, rate: int) -> float:
        settings = self.config.mapping.acceleration
        if settings.curve == "none" or rate <= 1:
            return 1.0
        maximum = settings.max_multiplier
        if settings.curve == "linear":
            # Reaches max_multiplier at ten detents inside the window.
            value = 1.0 + (rate - 1) * (maximum - 1.0) / 9.0
        else:
            value = rate ** (math.log(maximum) / math.log(10.0))
        return max(1.0, min(maximum, value))

    @property
    def active_encoders(self) -> int:
        return sum(1 for state in self._all_states() if state.pending != 0)

    def flush_due(self, now: float) -> int:
        """Flush every encoder whose interval or idle deadline is due."""

        if self._frozen:
            return 0
        sent = 0
        active = max(1, self.active_encoders)
        rate = self.config.rate_limit
        min_interval = rate.encoder_base_interval + rate.encoder_stream_penalty * active
        idle_interval = rate.encoder_idle_base + rate.encoder_idle_penalty * active
        flush_interval = rate.encoder_idle_base

        for state in self._all_states():
            if state.pending == 0 or state.last_feed is None:
                continue
            since_last = now - state.last_send
            if since_last < min_interval:
                continue
            first = state.first_feed if state.first_feed is not None else state.last_feed
            idle_due = now - state.last_feed >= idle_interval
            batch_due = now - first >= flush_interval
            if not (idle_due or batch_due):
                continue
            if self._flush_state(state, now):
                sent += 1
                active = max(1, self.active_encoders)
                min_interval = rate.encoder_base_interval + rate.encoder_stream_penalty * active
                idle_interval = rate.encoder_idle_base + rate.encoder_idle_penalty * active
        return sent

    def flush_all(self, now: float) -> int:
        """Flush all pending encoder units, e.g. before a resolution change."""

        if self._frozen:
            return 0
        sent = 0
        for state in self._all_states():
            if state.pending != 0 and self._flush_state(state, now):
                sent += 1
        return sent

    def _flush_state(self, state: EncoderState, now: float) -> bool:
        if state.pending == 0:
            return False
        if state.is_slot:
            value = state.pending
            state.pending = 0.0
            self.sink.encoder_slot(
                state.mapping.slot, value, screen=state.screen  # type: ignore[arg-type]
            )
            LOGGER.debug(
                "Encoder %d Slot %s%s %+.4f",
                state.mapping.id,
                state.mapping.slot,
                " (Screen)" if state.screen else "",
                value,
            )
        else:
            value = state.pending
            state.pending = 0.0
            self.sink.encoder_attribute(state.mapping.attribute, value)  # type: ignore[arg-type]
            LOGGER.debug("Encoder %d Attribut %s %+.4f", state.mapping.id, state.mapping.attribute, value)
        state.last_send = now
        state.first_feed = None if state.pending == 0 else now
        state.last_feed = now if state.pending != 0 else None
        return True

    def flush_hold_upgrades(self, now: float) -> int:
        """Send a ``hold=true`` press for keys held past the threshold.

        A tap keeps ``hold=false`` (press + release).  A key still down after
        ``ma2.hardkey_hold_threshold`` gets an extra ``hold=true`` press so the
        console treats it as held (Store Options).  Modifiers are pressed as
        held immediately and never appear here.
        """

        if self.config.ma2.hardkey_transport != "lua":
            return 0
        if self._frozen:
            return 0
        threshold = self.config.ma2.hardkey_hold_threshold
        sent = 0
        for control in list(self._pending_hold):
            if now - self._pending_hold[control] < threshold:
                continue
            del self._pending_hold[control]
            held = self._held.get(control)
            if held is not None and held.keyname is not None:
                self._emit_press(control, held.keyname, hold=True)
                sent += 1
        return sent

    async def run_encoder_loop(self, interval: float = 0.005) -> None:
        try:
            while not self._stop.is_set():
                moment = self._clock()
                self.flush_due(moment)
                self.flush_hold_upgrades(moment)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise

    def stop(self) -> None:
        self._stop.set()

    # -- introspection ----------------------------------------------------

    @property
    def held(self) -> dict[str, HeldKey]:
        return dict(self._held)

    def pending_for(self, encoder_id: int) -> float:
        return self._encoders[encoder_id].pending
