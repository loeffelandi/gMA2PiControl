"""Route normalised inputs to executor playbacks before the mapping engine."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from .acceleration import ValueAccelerator
from .events import InputEvent
from .mapping import MappingEngine

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
    must not additionally trigger a hardkey or command.  Events without a
    target return ``False`` so the caller can pass them to the engine.
    """

    def __init__(
        self,
        engine: MappingEngine,
        client,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._engine = engine
        self._client = client
        self._clock = clock
        self._last_value: dict[tuple[str, int | str, int], float] = {}
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

    def _maybe_page(self, event: InputEvent) -> None:
        if event.kind == "key" and event.value < 0.5:
            return
        settings = self._engine.config.mapping.device_banks.get(event.device)
        layer = settings.banks.get(event.bank) if settings is not None else None
        if layer is not None and layer.ma_page is not None:
            if self._last_bank.get(event.device) != event.bank:
                self._client.command(f"Page {layer.ma_page}")
        self._last_bank[event.device] = event.bank

    def handle(self, event: InputEvent) -> bool:
        config = self._engine.config
        if id(config) != self._config_id:
            # A runtime apply replaced the configuration.  Values of the old
            # targets must not suppress the first value of a new target.
            self._last_value.clear()
            self._warned.clear()
            self._last_bank.clear()
            self._accelerator = ValueAccelerator(config.mapping.value_acceleration)
            self._config_id = id(config)

        if event.kind == "key":
            settings = config.mapping.device_banks.get(event.device)
            layer = settings.banks.get(event.bank) if settings is not None else None
            if layer is not None and event.control in layer.keys:
                # A bank-specific key mapping wins over the global playback.
                return False

        self._maybe_page(event)
        target = self._resolve(event)
        if target is None:
            return False

        if target.kind == "button":
            if event.kind != "key":
                self._warn_mismatch(event, target)
                return True
            self._client.playback_button(
                target.page,
                target.executor,
                target.button,
                event.value >= 0.5,
            )
            return True

        if event.kind != "value":
            self._warn_mismatch(event, target)
            return True

        value = float(event.value)
        if target.accelerated:
            value = self._accelerator.apply(event.control, value, self._clock())
            LOGGER.info(
                "DEBUGACCEL %s raw=%.5f virtual=%.5f",
                event.control,
                float(event.value),
                value,
            )
        value = max(0.0, min(1.0, value))
        key = (event.control, target.page, target.executor)
        if self._last_value.get(key) == value:
            return True
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
