"""Guided hardware learn mode for control-to-note bindings.

A session walks the unbound controls of one device bank in layout order.  The
caller taps the raw MIDI stream before normalisation: while a session is active,
note events from the selected device are consumed and paired with the active
control instead of reaching the mapping engine.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from .config import AppConfig
from .hid_input import RawEvent

LOGGER = logging.getLogger("ma2pi.device_learn")

DEFAULT_TIMEOUT = 60.0


class DeviceLearnError(RuntimeError):
    """A session cannot be started or a request is invalid."""


@dataclass
class _Session:
    device: str
    bank: int
    channel: int
    controls: list[str]
    index: int = 0
    captured: dict[int, str] = field(default_factory=dict)
    started: float = 0.0
    last_event: float = 0.0
    paused: bool = False
    error: str | None = None

    @property
    def current(self) -> str | None:
        if self.index >= len(self.controls):
            return None
        return self.controls[self.index]


class DeviceLearnManager:
    """Collect a note for each unbound control of one bank."""

    def __init__(
        self,
        config: AppConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.config = config
        self._clock = clock
        self.timeout = timeout
        self._session: _Session | None = None

    @property
    def active(self) -> bool:
        return self._session is not None

    @property
    def session(self) -> _Session | None:
        return self._session

    def set_config(self, config: AppConfig) -> None:
        self.config = config

    def _controls_in_order(self, device: str, bank: int) -> list[str]:
        profile_name = self.config.devices[device].profile
        profile = self.config.profiles[profile_name]
        bank_profile = profile.bank(bank)
        bound = set(bank_profile.notes.values()) if bank_profile is not None else set()
        order: list[str] = []
        layout = self.config.layouts.get(profile_name)
        if layout is not None:
            for row in layout.rows:
                for cell in row.cells:
                    if cell.control and cell.control not in order:
                        order.append(cell.control)
        else:
            order = [control.id for control in profile.controls]
        for control in profile.controls:
            if control.id not in order:
                order.append(control.id)
        return [control for control in order if control not in bound]

    def start(self, device: str, bank: int, control: str | None = None) -> dict:
        if self._session is not None:
            raise DeviceLearnError("Es läuft bereits eine Learn-Sitzung")
        if device not in self.config.devices:
            raise DeviceLearnError(f"unbekanntes Gerät {device!r}")
        if self.config.devices[device].backend != "midi":
            raise DeviceLearnError(f"Gerät {device!r} ist kein MIDI-Gerät")
        if bank < 1 or bank > 16:
            raise DeviceLearnError("Bank muss zwischen 1 und 16 liegen")
        profile = self.config.profiles[self.config.devices[device].profile]
        bank_profile = profile.bank(bank)
        if bank_profile is None:
            raise DeviceLearnError(f"Bank {bank} ist im Profil nicht definiert")
        if control is not None:
            if control not in profile.control_names:
                raise DeviceLearnError(
                    f"Control {control!r} kommt im Profil nicht vor"
                )
            controls = [control]
        else:
            controls = self._controls_in_order(device, bank)
        moment = self._clock()
        self._session = _Session(
            device=device,
            bank=bank,
            channel=bank_profile.channel,
            controls=controls,
            started=moment,
            last_event=moment,
        )
        LOGGER.info(
            "Geräte-Learn gestartet: %s Bank %d, %d Controls",
            device,
            bank,
            len(controls),
        )
        return self.status()

    def skip(self) -> dict:
        session = self._require()
        if session.current is not None:
            session.index += 1
            session.error = None
            session.paused = False
            session.last_event = self._clock()
        return self.status()

    def cancel(self) -> dict | None:
        if self._session is None:
            return None
        result = self.status()
        self._session = None
        LOGGER.info("Geräte-Learn abgebrochen")
        return result

    def finish(self) -> tuple[str, int, dict[int, str]]:
        session = self._require()
        captured = dict(session.captured)
        bank = session.bank
        device = session.device
        self._session = None
        return device, bank, captured

    def peek(self) -> tuple[str, int, dict[int, str]]:
        """Return the pending result without ending the session."""

        session = self._require()
        return session.device, session.bank, dict(session.captured)

    def clear(self) -> None:
        self._session = None

    def device_lost(self, device: str) -> None:
        session = self._session
        if session is not None and session.device == device:
            session.paused = True
            session.error = "Gerät getrennt; Sitzung pausiert"

    def handle_raw(self, device: str, raw: RawEvent) -> bool:
        session = self._session
        if session is None or session.device != device:
            return False
        # Own every event of the selected device while learning so nothing
        # reaches the mapping engine or the onPC.
        if raw.kind not in ("note_on", "note_off"):
            return True
        try:
            note = int(raw.code)
        except ValueError:
            return True
        if raw.kind == "note_off" or raw.value < 1:
            return True
        if session.paused:
            # A timeout or a reconnect must not end the session permanently;
            # the next usable note resumes it.
            session.paused = False
            session.error = None
            session.last_event = self._clock()
        if session.current is None:
            return True
        if raw.channel != session.channel:
            session.error = (
                f"Gerät sendet auf Kanal {raw.channel}, erwartet wird "
                f"Kanal {session.channel}"
            )
            return True
        conflict = self._conflict(device, session, raw.channel, note)
        if conflict is not None:
            session.error = f"Note {note} ist bereits {conflict} zugeordnet"
            return True
        session.captured[note] = session.current
        session.index += 1
        session.last_event = self._clock()
        session.error = None
        LOGGER.info(
            "Geräte-Learn: %s -> Note %d (Kanal %d)",
            session.captured[note],
            note,
            raw.channel,
        )
        return True

    def poll(self, now: float | None = None) -> None:
        session = self._session
        if session is None or session.paused or session.current is None:
            return
        moment = self._clock() if now is None else now
        if moment - session.last_event >= self.timeout:
            session.paused = True
            session.error = "Zeitüberschreitung; Sitzung pausiert"

    def status(self) -> dict:
        session = self._require()
        return {
            "active": True,
            "device": session.device,
            "bank": session.bank,
            "channel": session.channel,
            "current": session.current,
            "total": len(session.controls),
            "index": session.index,
            "captured": [
                {"note": note, "control": control}
                for note, control in sorted(session.captured.items())
            ],
            "paused": session.paused,
            "error": session.error,
            "elapsed": max(0.0, self._clock() - session.started),
        }

    def _conflict(
        self, device: str, session: _Session, channel: int, note: int
    ) -> str | None:
        profile = self.config.profiles[self.config.devices[device].profile]
        for bank in profile.banks:
            if bank.channel != channel:
                continue
            existing = bank.notes.get(note)
            if existing is not None and existing != session.current:
                return f"in Bank {bank.number} dem Control {existing}"
        for captured_note, control in session.captured.items():
            if captured_note == note:
                return f"in dieser Sitzung dem Control {control}"
        return None

    def _require(self) -> _Session:
        if self._session is None:
            raise DeviceLearnError("Es läuft keine Learn-Sitzung")
        return self._session
