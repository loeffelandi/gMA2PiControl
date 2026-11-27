"""Controlled shutdown of the Raspberry Pi.

The Pi has no power button, so it is switched off by pulling the plug.  This
module offers two clean ways to power it down instead:

* :class:`PowerService.shutdown`, used by ``POST /api/power/shutdown``, and
* :class:`ShutdownCombo`, a key chord on the Cherry keyboard: keep the chord
  controls (default MA + Off) held and press the confirm control (default
  Please) ``confirm_presses`` times (default twice).  There are no timers;
  letting go of any chord key cancels.

The key that completes the chord is withheld from the console while the chord
is held, and every confirm press is swallowed, so a shutdown never executes a
half-typed command line on the onPC.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .config import AppConfig, PowerSettings
from .events import InputEvent

LOGGER = logging.getLogger("ma2pi.power")

#: Seconds between the request and ``systemctl poweroff``.  It lets the HTTP
#: response, the console notice and pending frames leave first.
SHUTDOWN_DELAY = 1.5

PowerExecutor = Callable[[], Awaitable[None]]
ComboListener = Callable[[str, dict[str, Any]], None]


class PowerError(RuntimeError):
    """Shutting down failed or is not possible."""


class PowerDisabled(PowerError):
    """``[power].enabled`` is false."""


class PowerUnavailable(PowerError):
    """This host cannot power itself off (no Linux/systemd)."""


class ShutdownPending(PowerError):
    """A shutdown has already been requested."""


async def systemctl_poweroff() -> None:
    """Ask systemd (via logind and polkit) to power the machine off."""

    systemctl = shutil.which("systemctl")
    if systemctl is None:
        raise PowerUnavailable("systemctl wurde nicht gefunden")
    process = await asyncio.create_subprocess_exec(
        systemctl,
        "poweroff",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=20.0)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise PowerError("systemctl poweroff: Zeitüberschreitung") from None
    if process.returncode != 0:
        detail = stderr.decode("utf-8", "replace").strip() or (
            f"Exit-Code {process.returncode}"
        )
        raise PowerError(
            f"systemctl poweroff fehlgeschlagen: {detail} "
            "(ist deploy/50-ma2pi-power.rules installiert?)"
        )


def _can_power_off() -> bool:
    return sys.platform.startswith("linux") and shutil.which("systemctl") is not None


@dataclass(frozen=True, slots=True)
class ComboResult:
    """What to do with one input event after the chord looked at it.

    ``forward`` events were withheld earlier and must reach the mapping engine
    *before* the current event; ``swallow`` drops the current event.
    """

    swallow: bool = False
    forward: tuple[InputEvent, ...] = ()


PASS = ComboResult()
SWALLOW = ComboResult(swallow=True)


class ShutdownCombo:
    """Held chord plus confirm presses as a small state machine.

    Phases: ``idle`` -> ``holding`` (all chord controls down, the completing
    press withheld) -> ``idle`` again when a chord key is released, a foreign
    key is pressed, or the confirm presses are complete.
    """

    IDLE = "idle"
    HOLDING = "holding"

    def __init__(
        self,
        settings: PowerSettings,
        *,
        listener: ComboListener | None = None,
    ) -> None:
        self.settings = settings
        self._listener = listener
        self._phase = self.IDLE
        self._down: set[tuple[str, str]] = set()
        self._swallowed: set[tuple[str, str]] = set()
        self._withheld: InputEvent | None = None
        self._presses = 0

    # -- introspection ----------------------------------------------------

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def remaining(self) -> int:
        """Confirm presses still missing while the chord is held."""

        return max(0, self.settings.confirm_presses - self._presses)

    # -- control ----------------------------------------------------------

    def configure(self, settings: PowerSettings) -> None:
        self.settings = settings
        self.reset()

    def reset(self) -> None:
        """Forget all key state, e.g. while Learn owns the input."""

        was_counting = self._phase == self.HOLDING and self._presses > 0
        self._phase = self.IDLE
        self._down.clear()
        self._swallowed.clear()
        self._withheld = None
        self._presses = 0
        if was_counting:
            self._emit("cancelled")

    def feed(self, event: InputEvent) -> ComboResult:
        if event.kind != "key" or event.value not in (0, 1):
            return PASS
        key = (event.device, event.control)
        if event.value == 1:
            return self._press(event, key)
        return self._release(event, key)

    # -- internals --------------------------------------------------------

    def _emit(self, name: str, **info: Any) -> None:
        if self._listener is None:
            return
        try:
            self._listener(name, info)
        except Exception as exc:  # feedback must never break input
            LOGGER.error("Ausschalt-Listener fehlgeschlagen: %s", exc)

    def _chord_complete(self) -> bool:
        held = {control for _, control in self._down}
        return all(control in held for control in self.settings.hold_controls)

    def _abort(self) -> tuple[InputEvent, ...]:
        """Leave ``holding``.

        Without any confirm press the withheld key was an ordinary keystroke
        and is handed back to the engine.  After a confirm press the user was
        clearly shutting down, so it is dropped and its release swallowed.
        """

        withheld = self._withheld
        counted = self._presses > 0
        self._withheld = None
        self._phase = self.IDLE
        self._presses = 0
        if counted:
            self._emit("cancelled")
        if withheld is None:
            return ()
        if counted:
            self._swallowed.add((withheld.device, withheld.control))
            return ()
        return (withheld,)

    def _press(self, event: InputEvent, key: tuple[str, str]) -> ComboResult:
        settings = self.settings
        control = event.control
        if self._phase == self.HOLDING:
            if control == settings.confirm_control:
                self._swallowed.add(key)
                self._presses += 1
                if self.remaining <= 0:
                    withheld = self._withheld
                    if withheld is not None:
                        self._swallowed.add((withheld.device, withheld.control))
                    self._withheld = None
                    self._phase = self.IDLE
                    self._presses = 0
                    self._emit("confirmed")
                else:
                    self._emit("progress", remaining=self.remaining)
                return SWALLOW
            if control in settings.hold_controls:
                self._down.add(key)
                return PASS
            return ComboResult(False, self._abort())

        if control in settings.hold_controls:
            self._down.add(key)
            if self._chord_complete():
                self._phase = self.HOLDING
                self._withheld = event
                self._presses = 0
                return SWALLOW
        return PASS

    def _release(self, event: InputEvent, key: tuple[str, str]) -> ComboResult:
        self._down.discard(key)
        if key in self._swallowed:
            self._swallowed.discard(key)
            return SWALLOW
        if self._phase == self.HOLDING and (
            event.control in self.settings.hold_controls
        ):
            return ComboResult(False, self._abort())
        return PASS


class PowerService:
    """Owns the shutdown request, the key chord and their status."""

    def __init__(
        self,
        settings: PowerSettings,
        *,
        dry_run: bool = False,
        executor: PowerExecutor | None = None,
        notify: Callable[[str], None] | None = None,
        record: Callable[[str], None] | None = None,
        delay: float = SHUTDOWN_DELAY,
        sync: Callable[[], None] = os.sync,
    ) -> None:
        self.settings = settings
        self.dry_run = dry_run
        self._custom_executor = executor is not None
        self._executor: PowerExecutor = executor or systemctl_poweroff
        self._notify = notify
        self._record = record
        self._delay = delay
        self._sync = sync
        self._shutting_down = False
        self._error: str | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._combo = ShutdownCombo(settings, listener=self._on_combo)

    # -- configuration ----------------------------------------------------

    def set_config(self, config: AppConfig) -> None:
        self.settings = config.power
        self._combo.configure(config.power)

    @property
    def available(self) -> bool:
        if not self.settings.enabled:
            return False
        return self.dry_run or self._custom_executor or _can_power_off()

    @property
    def combo_active(self) -> bool:
        return self.available and self.settings.combo

    # -- status -----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        combo = self._combo
        holding = combo.phase == ShutdownCombo.HOLDING
        state = "shutting_down" if self._shutting_down else combo.phase
        return {
            "enabled": self.settings.enabled,
            "available": self.available,
            "combo": self.combo_active,
            "state": state,
            "confirm_remaining": combo.remaining if holding else None,
            "error": self._error,
        }

    # -- input ------------------------------------------------------------

    def filter(self, event: InputEvent) -> ComboResult:
        """Run an input event through the chord (before the mapping engine)."""

        if not self.combo_active:
            return PASS
        return self._combo.feed(event)

    def reset_combo(self) -> None:
        self._combo.reset()

    # -- shutdown ---------------------------------------------------------

    async def shutdown(self, source: str) -> None:
        """Schedule the power-off; returns before the machine goes down."""

        if not self.settings.enabled:
            raise PowerDisabled("Herunterfahren ist in [power] abgeschaltet")
        if not self.available:
            raise PowerUnavailable(
                "Dieser Rechner kann sich nicht selbst herunterfahren "
                "(Linux mit systemd erforderlich)"
            )
        if self._shutting_down:
            raise ShutdownPending("Der Pi fährt bereits herunter")
        self._shutting_down = True
        self._error = None
        LOGGER.warning("Herunterfahren angefordert (%s)", source)
        self._log(f"Herunterfahren angefordert ({source})")
        self._say("gMA2PiControl: Pi faehrt jetzt herunter")
        self._spawn(self._execute(source))

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # -- internals --------------------------------------------------------

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _execute(self, source: str) -> None:
        try:
            await asyncio.sleep(self._delay)
            await asyncio.to_thread(self._sync)
            if self.dry_run:
                LOGGER.info("dry-run: Herunterfahren (%s) wird nicht ausgeführt", source)
                self._shutting_down = False
                return
            await self._executor()
            LOGGER.info("Herunterfahren an systemd übergeben (%s)", source)
        except asyncio.CancelledError:
            self._shutting_down = False
            raise
        except Exception as exc:
            self._shutting_down = False
            self._error = str(exc)
            LOGGER.error("Herunterfahren fehlgeschlagen: %s", exc)
            self._log(f"Herunterfahren fehlgeschlagen: {exc}")
            self._say("gMA2PiControl: Herunterfahren fehlgeschlagen")

    def _say(self, text: str) -> None:
        """Show ``text`` on the onPC; the Pi has no display of its own."""

        if not self.settings.console_notice or self._notify is None:
            return
        try:
            self._notify(text)
        except Exception as exc:
            LOGGER.debug("Konsolenhinweis fehlgeschlagen: %s", exc)

    def _log(self, text: str) -> None:
        if self._record is None:
            return
        try:
            self._record(text)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("Aktivitätseintrag fehlgeschlagen: %s", exc)

    def _on_combo(self, name: str, info: dict[str, Any]) -> None:
        settings = self.settings
        if name == "progress":
            remaining = info["remaining"]
            LOGGER.warning(
                "Ausschalt-Kombination: noch %dx %s", remaining, settings.confirm_control
            )
            self._log(f"Ausschalten: noch {remaining}x {settings.confirm_control}")
            self._say(f"gMA2PiControl: Pi ausschalten? Please noch {remaining}x")
        elif name == "cancelled":
            LOGGER.info("Ausschalt-Kombination abgebrochen")
            self._log("Ausschalten abgebrochen")
            self._say("gMA2PiControl: Ausschalten abgebrochen")
        elif name == "confirmed":
            try:
                asyncio.get_running_loop()
            except RuntimeError:  # pragma: no cover - always inside the daemon loop
                LOGGER.error("Ausschalten ohne laufende Ereignisschleife nicht möglich")
                return
            self._spawn(self._shutdown_from_combo())

    async def _shutdown_from_combo(self) -> None:
        try:
            await self.shutdown("Tastenkombination")
        except PowerError as exc:
            self._error = str(exc)
            LOGGER.error("Ausschalten per Tastenkombination abgelehnt: %s", exc)
