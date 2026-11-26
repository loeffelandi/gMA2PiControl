"""Learn mode for keys and encoders.

At most one session is active at a time.  While it is active the caller must
route all input events through :meth:`LearnManager.feed` instead of the
mapping engine, so no MA2 frame is produced.  A bounded post-capture release
timeout guarantees a missing key-up can never block rig inputs indefinitely.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Literal

from .config import AppConfig
from .events import InputEvent

LOGGER = logging.getLogger("ma2pi.learn")

DEFAULT_TIMEOUT = 15.0
DEFAULT_ENCODER_WINDOW = 2.0
DEFAULT_RELEASE_TIMEOUT = 2.0

LearnKind = Literal["key", "encoder"]
LearnStatus = Literal["active", "captured", "timeout", "cancelled"]


class LearnBusy(RuntimeError):
    """A learn session is already active."""


@dataclass(frozen=True, slots=True)
class LearnResult:
    kind: LearnKind
    status: LearnStatus
    control: str | None = None
    device: str | None = None
    raw: str | None = None
    direction: int = 0
    detents: int = 0
    elapsed: float = 0.0
    timed_out: bool = False


@dataclass
class _Session:
    kind: LearnKind
    started: float
    timeout: float
    window: float
    release_timeout: float = DEFAULT_RELEASE_TIMEOUT
    device: str | None = None
    control: str | None = None
    raw: str | None = None
    first_event: float | None = None
    direction: int = 0
    detents: int = 0
    done: bool = False
    reported: bool = False
    awaiting_release: tuple[str, str] | None = None
    release_deadline: float | None = None


def _resolve_raw(
    config: AppConfig,
    device: str,
    control: str,
    note: int | None = None,
) -> str | None:
    """Map a logical control back to its physical key code, MIDI note or axis."""

    if note is not None:
        device_cfg = config.devices.get(device)
        prof = config.profiles.get(device_cfg.profile) if device_cfg else None
        if prof is not None and prof.banks:
            return str(note)

    device_config = config.devices.get(device)
    if device_config is None:
        return None
    profile = config.profiles.get(device_config.profile)
    if profile is None:
        return None

    for code, name in profile.keys.items():
        if name == control:
            return code
    for midi_note, name in profile.notes.items():
        if name == control:
            return str(midi_note)
    for mv in profile.midi_values:
        if mv.control == control:
            return str(mv.note)
    for bank in profile.banks:
        for bank_note, name in bank.notes.items():
            if name == control:
                return str(bank_note)
    enc_id = profile.relative_encoder_ids.get(control)
    if enc_id is None and control.startswith("encoder."):
        try:
            enc_id = int(control.split(".", 1)[1])
        except ValueError:
            enc_id = None
    if enc_id is not None:
        for encoder in profile.encoders:
            if encoder.id == enc_id:
                return encoder.control
        for encoder in profile.midi_encoders:
            if encoder.id == enc_id:
                return f"note {encoder.note}"
    return None if note is None else str(note)


class LearnManager:
    """Collect one key or encoder gesture without changing any configuration."""

    def __init__(
        self,
        config: AppConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = DEFAULT_TIMEOUT,
        encoder_window: float = DEFAULT_ENCODER_WINDOW,
        release_timeout: float = DEFAULT_RELEASE_TIMEOUT,
        on_start: Callable[[str | None], None] | None = None,
    ) -> None:
        self.config = config
        self._clock = clock
        self.timeout = timeout
        self.encoder_window = encoder_window
        self.release_timeout = release_timeout
        self.on_start = on_start
        self._session: _Session | None = None

    # -- state -----------------------------------------------------------

    @property
    def active(self) -> bool:
        """True while events must be suppressed from the mapping engine."""

        return self._session is not None

    @property
    def current(self) -> LearnResult | None:
        session = self._session
        if session is None or not session.done or session.reported:
            return None
        return self._snapshot(session)

    def set_config(self, config: AppConfig) -> None:
        self.config = config

    # -- lifecycle -------------------------------------------------------

    def start(
        self,
        kind: LearnKind,
        *,
        device: str | None = None,
        now: float | None = None,
    ) -> LearnResult:
        if kind not in ("key", "encoder"):
            raise ValueError(f"unbekannter Learn-Typ: {kind!r}")
        moment = self._clock() if now is None else now
        self._expire_release(moment)
        if self.active:
            raise LearnBusy("Es läuft bereits eine Learn-Sitzung")
        if self.on_start is not None:
            try:
                self.on_start(device)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("Learn-Start-Hook fehlgeschlagen", exc_info=True)
        self._session = _Session(
            kind=kind,
            started=moment,
            timeout=self.timeout,
            window=self.encoder_window,
            release_timeout=self.release_timeout,
            device=device,
        )
        LOGGER.info("Learn-Sitzung für %s gestartet", kind)
        return self._snapshot(self._session)

    def cancel(self, *, now: float | None = None) -> LearnResult | None:
        session = self._session
        if session is None:
            return None
        moment = self._clock() if now is None else now
        result = LearnResult(
            kind=session.kind,
            status="cancelled",
            control=session.control,
            device=session.device,
            raw=session.raw,
            direction=session.direction,
            detents=session.detents,
            elapsed=max(0.0, moment - session.started),
        )
        self._session = None
        LOGGER.info("Learn-Sitzung abgebrochen")
        return result

    # -- input -----------------------------------------------------------

    def _expire_release(self, moment: float) -> bool:
        session = self._session
        if (
            session is not None
            and session.done
            and session.release_deadline is not None
            and moment >= session.release_deadline
        ):
            self._session = None
            return True
        return False

    def feed(self, event: InputEvent, now: float | None = None) -> LearnResult | None:
        """Consume one event; only call while :attr:`active`."""

        session = self._session
        if session is None:
            return None
        moment = self._clock() if now is None else now

        if session.done:
            if (
                session.awaiting_release is not None
                and event.kind == "key"
                and event.value == 0
                and (event.device, event.control) == session.awaiting_release
            ):
                self._session = None
                return None
            self._expire_release(moment)
            return None

        result = self._poll_session(moment)
        if result is not None:
            return result
        if self._session is None:
            return None
        session = self._session

        if session.kind == "key":
            if session.device is not None and event.device != session.device:
                return None
            if event.kind == "key" and event.value == 1:
                session.control = event.control
                session.device = event.device
                session.raw = _resolve_raw(
                    self.config, event.device, event.control, event.note
                )
                session.awaiting_release = (event.device, event.control)
                session.release_deadline = moment + session.release_timeout
                return self._finish(session, moment)
            return None

        # Encoder session: lock onto the first encoder control moved.
        if event.kind != "encoder":
            return None
        if session.device is not None and event.device != session.device:
            return None
        if session.control is not None and event.control != session.control:
            return None
        if event.value == 0:
            return None
        if session.first_event is None:
            session.first_event = moment
        session.control = event.control
        session.device = event.device
        session.raw = _resolve_raw(
            self.config, event.device, event.control, event.note
        )
        session.direction += 1 if event.value > 0 else -1
        session.detents += abs(int(event.value))
        return self._poll_session(moment)

    def poll(self, now: float | None = None) -> LearnResult | None:
        """Finish an encoder window, release wait or idle session."""

        session = self._session
        if session is None:
            return None
        moment = self._clock() if now is None else now
        if session.done:
            self._expire_release(moment)
            return None
        return self._poll_session(moment)

    # -- helpers ---------------------------------------------------------

    def _poll_session(self, moment: float) -> LearnResult | None:
        session = self._session
        if session is None or session.done:
            return None
        if (
            session.kind == "encoder"
            and session.first_event is not None
            and moment - session.first_event >= session.window
        ):
            return self._finish(session, moment)
        if moment - session.started >= session.timeout:
            session.done = True
            session.reported = True
            result = LearnResult(
                kind=session.kind,
                status="timeout",
                control=session.control,
                device=session.device,
                raw=session.raw,
                direction=session.direction,
                detents=session.detents,
                elapsed=max(0.0, moment - session.started),
                timed_out=True,
            )
            self._session = None
            LOGGER.info("Learn-Sitzung nach %.1f s abgelaufen", result.elapsed)
            return result
        return None

    def _finish(self, session: _Session, moment: float) -> LearnResult | None:
        if session.done:
            return None
        session.done = True
        session.reported = True
        result = LearnResult(
            kind=session.kind,
            status="captured",
            control=session.control,
            device=session.device,
            raw=session.raw,
            direction=(1 if session.direction > 0 else -1) if session.direction else 0,
            detents=session.detents,
            elapsed=max(0.0, moment - session.started),
        )
        if session.kind == "encoder":
            self._session = None
        LOGGER.info(
            "Learn erfasst: %s %s (roh %s)", session.kind, session.control, session.raw
        )
        return result

    @staticmethod
    def _snapshot(session: _Session) -> LearnResult:
        return LearnResult(
            kind=session.kind,
            status="captured" if session.done else "active",
            control=session.control,
            device=session.device,
            raw=session.raw,
            direction=session.direction,
            detents=session.detents,
            elapsed=0.0,
        )
