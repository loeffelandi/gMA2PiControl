"""Route normalised inputs to executor playbacks before the mapping engine."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import Callable

from .acceleration import ValueAccelerator
from .events import InputEvent
from .mapping import MappingEngine
from .topology import FLOATING_START, ExecutorTopology

LOGGER = logging.getLogger("ma2pi.playback")


@dataclass(frozen=True, slots=True)
class _Target:
    page: int | str
    executor: int
    kind: str
    button: int
    accelerated: bool


class PlaybackRouter:
    """Consume events that have a ``[mapping.playbacks]`` target.

    The router runs before the mapping engine: a control with a playback target
    must not additionally trigger a hardkey or command.  Pressed buttons bind
    their resolved target per ``(device, control)`` so releases always hit the
    pressed executor even across bank changes or ``DeviceLost``.
    """

    def __init__(
        self,
        engine: MappingEngine,
        client,
        *,
        clock: Callable[[], float] = time.monotonic,
        topology: ExecutorTopology | None = None,
    ) -> None:
        self._engine = engine
        self._client = client
        self._clock = clock
        self._topology = topology
        self._last_value: dict[tuple[str, int | str, int], float] = {}
        self._pressed: dict[tuple[str, str], _Target] = {}
        self._warned: set[tuple[str, str]] = set()
        self._last_bank: dict[str, int] = {}
        self._accelerator = ValueAccelerator(engine.config.mapping.value_acceleration)
        self._config_id = id(engine.config)

    def _bank_size(self, device: str) -> int:
        settings = self._engine.config.mapping.device_banks.get(device)
        if settings is not None and settings.bank_size is not None:
            return settings.bank_size
        device_config = self._engine.config.devices.get(device)
        if device_config is None:
            return 1
        profile = self._engine.config.profiles[device_config.profile]
        kinds = profile.control_kinds
        faders = sum(1 for kind in kinds.values() if kind == "fader")
        if faders:
            return faders
        buttons = sum(1 for kind in kinds.values() if kind == "button")
        return max(1, buttons)

    def _resolve(self, event: InputEvent) -> _Target | None:
        config = self._engine.config
        base = config.mapping.playbacks.get(event.control)
        settings = config.mapping.device_banks.get(event.device)
        layer = settings.banks.get(event.bank) if settings is not None else None
        override = layer.playbacks.get(event.control) if layer is not None else None
        if base is None and override is None:
            return None
        page = (
            override.page
            if override is not None and override.page is not None
            else (base.page if base is not None else None)
        )
        executor = (
            override.executor
            if override is not None and override.executor is not None
            else (base.executor if base is not None else None)
        )
        if page is None or executor is None:
            return None
        if (
            settings is not None
            and event.bank > 1
            and (override is None or override.executor is None)
            and (layer is None or layer.ma_page is None)
        ):
            executor += (event.bank - 1) * self._bank_size(event.device)
        kind = (
            override.kind
            if override is not None and override.kind is not None
            else (base.kind if base is not None else "button")
        )
        button = (
            override.button
            if override is not None and override.button is not None
            else (base.button if base is not None else 1)
        )
        accelerated = (
            override.accelerated
            if override is not None and override.accelerated is not None
            else (base.accelerated if base is not None else False)
        )
        return _Target(page, executor, kind, button, accelerated)

    def _combined_enabled(self) -> bool:
        mapping = self._engine.config.mapping
        return getattr(mapping, "combined_executors", "auto") != "off"

    def _follow_lead(self, target: _Target) -> _Target:
        """Send a press on a covered Floating slot to the leading executor.

        The Floating tile of a wide executor has a single button and the MA has
        no executor for the covered slot, so the Web Remote sends the leading
        ``execIndex`` with ``buttonId 0``.  The fader view is left alone: every
        slot of a wide fader executor keeps its own executor, buttons and fader.
        """

        if (
            self._topology is None
            or target.kind != "button"
            or target.executor < FLOATING_START
            or not self._combined_enabled()
        ):
            return target
        resolution = self._topology.resolve(target.page, target.executor)
        if not resolution.covered:
            return target
        LOGGER.debug(
            "Executor %d auf Page %s ist von %d überdeckt; Taste geht an %d",
            target.executor,
            target.page,
            resolution.executor,
            resolution.executor,
        )
        return replace(target, executor=resolution.executor, button=1)

    def _client_live(self) -> bool:
        return bool(
            getattr(self._client, "connected", True)
            or getattr(self._client, "dry_run", False)
        )

    def _maybe_page(self, event: InputEvent) -> None:
        if event.kind == "key" and event.value < 0.5:
            return
        settings = self._engine.config.mapping.device_banks.get(event.device)
        layer = settings.banks.get(event.bank) if settings is not None else None
        if layer is not None and layer.ma_page is not None:
            if self._last_bank.get(event.device) != event.bank:
                if hasattr(self._client, "command"):
                    self._client.command(f"Page {layer.ma_page}")
        if self._client_live():
            self._last_bank[event.device] = event.bank

    def release_device(self, device: str, *, send: bool = True) -> None:
        """Release any held playback buttons belonging to ``device``."""

        keys = [key for key in self._pressed if key[0] == device]
        for key in reversed(keys):
            target = self._pressed.pop(key)
            if send:
                self._client.playback_button(
                    target.page, target.executor, target.button, False
                )

    def cleanup(self, *, send: bool = True) -> None:
        """Release all held playback buttons (e.g. on config swap or shutdown)."""

        for key in reversed(list(self._pressed)):
            target = self._pressed.pop(key)
            if send:
                self._client.playback_button(
                    target.page, target.executor, target.button, False
                )
        self._pressed.clear()

    def on_connection_lost(self) -> None:
        """Reset cached page, fader and button state after session loss."""

        self._pressed.clear()
        self._last_bank.clear()
        self._last_value.clear()

    def handle(self, event: InputEvent) -> bool:
        if getattr(self._engine, "frozen", False):
            return True
        config = self._engine.config
        if id(config) != self._config_id:
            self._last_value.clear()
            self._warned.clear()
            self._last_bank.clear()
            self._accelerator = ValueAccelerator(config.mapping.value_acceleration)
            self._config_id = id(config)

        if event.kind == "key":
            press_key = (event.device, event.control)
            if event.value < 0.5:
                bound = self._pressed.pop(press_key, None)
                if bound is not None:
                    self._client.playback_button(
                        bound.page, bound.executor, bound.button, False
                    )
                    return True
                is_held = getattr(self._engine, "is_held", None)
                if is_held is not None and is_held(event.device, event.control):
                    return False
                settings = config.mapping.device_banks.get(event.device)
                layer = settings.banks.get(event.bank) if settings is not None else None
                if layer is not None and event.control in layer.keys:
                    return False
                target = self._resolve(event)
                if target is None:
                    return False
                if target.kind == "button":
                    LOGGER.debug(
                        "Playback-Release ohne Press verworfen: %s (%s)",
                        event.control,
                        event.device,
                    )
                    return True
                self._warn_mismatch(event, target)
                return True

            settings = config.mapping.device_banks.get(event.device)
            layer = settings.banks.get(event.bank) if settings is not None else None
            if layer is not None and event.control in layer.keys:
                return False

        self._maybe_page(event)
        target = self._resolve(event)
        if target is None:
            return False

        if target.kind == "button":
            if event.kind != "key":
                self._warn_mismatch(event, target)
                return True
            pressed = event.value >= 0.5
            if pressed:
                target = self._follow_lead(target)
                self._pressed[(event.device, event.control)] = target
            self._client.playback_button(
                target.page,
                target.executor,
                target.button,
                pressed,
            )
            return True

        if event.kind != "value":
            self._warn_mismatch(event, target)
            return True

        value = float(event.value)
        if target.accelerated:
            accel_key = (event.device, event.bank, event.control)
            value = self._accelerator.apply(accel_key, value, self._clock())
            LOGGER.debug(
                "Wert-Beschleunigung %s (Gerät=%s, Bank=%d): roh=%.5f virtuell=%.5f",
                event.control,
                event.device,
                event.bank,
                float(event.value),
                value,
            )
        value = max(0.0, min(1.0, value))
        key = (event.control, target.page, target.executor)
        if self._last_value.get(key) == value:
            return True
        if self._client_live():
            self._last_value[key] = value
        self._client.playback_fader(target.page, target.executor, value)
        return True

    def _warn_mismatch(self, event: InputEvent, target) -> None:
        key = (event.control, event.kind)
        if key in self._warned:
            return
        self._warned.add(key)
        LOGGER.warning(
            "Playback-Ziel für %s erwartet %s, empfängt aber %s; Ereignis wird verworfen",
            event.control,
            "einen Tastenwert" if target.kind == "button" else "einen absoluten Wert",
            event.kind,
        )
