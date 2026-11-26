"""Learn mode for keys and encoders.

At most one session is active at a time.  While it is active the caller must
route all input events through :meth:`LearnManager.feed` instead of the
mapping engine, so no MA2 frame is produced.  The manager itself never touches
the client or the configuration; it only reports what was seen.
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
    device: str | None = None
    control: str | None = None
    raw: str | None = None
    first_event: float | None = None
    direction: int = 0
    detents: int = 0
    done: bool = False
    reported: bool = False
    awaiting_release: tuple[str, str] | None = None


def _resolve_raw(config: AppConfig, device: str, control: str) -> str | None:
    """Map a logical control back to its physical key code or encoder axis."""

    device_config = config.devices.get(device)
    if device_config is None:
        return None
    profile = config.profiles.get(device_config.profile)
    if profile is None:
        return None

    for code, name in profile.keys.items():
        if name == control:
            return code
    for note, name in profile.notes.items():
        if name == control:
            return str(note)
    if control.startswith("encoder."):
        try:
            encoder_id = int(control.split(".", 1)[1])
        except ValueError:
            return None
        for encoder in profile.encoders:
            if encoder.id == encoder_id:
                return encoder.control
        for encoder in profile.midi_encoders:
            if encoder.id == encoder_id:
                return f"note {encoder.note}"
    return None


class LearnManager:
    """Collect one key or encoder gesture without changing any configuration."""

    def __init__(
        self,
        config: AppConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = DEFAULT_TIMEOUT,
        encoder_window: float = DEFAULT_ENCODER_WINDOW,
    ) -> None:
        self.config = config
        self._clock = clock
        self.timeout = timeout
        self.encoder_window = encoder_window
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
        if self.active:
            raise LearnBusy("Es läuft bereits eine Learn-Sitzung")
        moment = self._clock() if now is None else now
        self._session = _Session(
            kind=kind,
            started=moment,
            timeout=self.timeout,
            window=self.encoder_window,
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

    def feed(self, event: InputEvent, now: float | None = None) -> LearnResult | None:
        """Consume one event; only call while :attr:`active`.

        Returns a result when the session finished or timed out.  ``None``
        means "still learning" or "not learning"; callers check
        :attr:`active` before routing, so the distinction is unambiguous.
        """

        session = self._session
        if session is None:
            return None
        moment = self._clock() if now is None else now

        if session.done:
            # The key-up belonging to a captured press is swallowed so it
            # cannot trigger a mapping action.
            if (
                session.awaiting_release is not None
                and event.kind == "key"
                and event.value == 0
                and (event.device, event.control) == session.awaiting_release
            ):
                self._session = None
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
                session.raw = _resolve_raw(self.config, event.device, event.control)
                session.awaiting_release = (event.device, event.control)
                return self._finish(session, moment)
            return None

        # Encoder session: collect within the window starting at the first feed.
        if event.kind != "encoder":
            return None
        if session.device is not None and event.device != session.device:
            return None
        if event.value == 0:
            return None
        if session.first_event is None:
            session.first_event = moment
        session.control = event.control
        session.device = event.device
        session.raw = _resolve_raw(self.config, event.device, event.control)
        session.direction += 1 if event.value > 0 else -1
        session.detents += abs(int(event.value))
        return self._poll_session(moment)

    def poll(self, now: float | None = None) -> LearnResult | None:
        """Finish an encoder window or an idle session without a new event."""

        session = self._session
        if session is None or session.done:
            return None
        moment = self._clock() if now is None else now
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
