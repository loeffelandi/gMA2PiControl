"""Rate-based acceleration for absolute MIDI values.

An absolute encoder reports a position, not a velocity.  To make a fast turn
travel further than its raw delta, the router keeps a virtual value per control
and amplifies each raw change by a multiplier derived from how often the
control changed inside a short time window.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ValueAccelerationSettings:
    curve: str = "linear"
    window: float = 0.12
    slow_rate: int = 2
    fast_rate: int = 10
    max_multiplier: float = 8.0


def multiplier(settings: ValueAccelerationSettings, rate: int) -> float:
    """Map an event rate to a multiplier, capped by the configured maximum."""

    if settings.curve == "none" or rate <= settings.slow_rate:
        return 1.0
    span = max(1, settings.fast_rate - settings.slow_rate)
    progress = min(1.0, (rate - settings.slow_rate) / span)
    if settings.curve == "linear":
        value = 1.0 + (settings.max_multiplier - 1.0) * progress
    else:
        value = settings.max_multiplier**progress
    return max(1.0, min(settings.max_multiplier, value))


@dataclass
class _State:
    last_raw: float
    value: float
    times: deque[float] = field(default_factory=deque)


class ValueAccelerator:
    """Turn raw absolute values into a rate-accelerated virtual value."""

    def __init__(self, settings: ValueAccelerationSettings) -> None:
        self._settings = settings
        self._states: dict[str, _State] = {}

    @property
    def settings(self) -> ValueAccelerationSettings:
        return self._settings

    def reset(self) -> None:
        self._states.clear()

    def apply(self, control: str, raw: float, now: float) -> float:
        raw = max(0.0, min(1.0, raw))
        state = self._states.get(control)
        if state is None:
            self._states[control] = _State(raw, raw, deque([now]))
            return raw

        delta = raw - state.last_raw
        state.last_raw = raw
        if delta == 0:
            return state.value

        state.times.append(now)
        cutoff = now - self._settings.window
        while state.times and state.times[0] < cutoff:
            state.times.popleft()

        rate = len(state.times)
        value = state.value + delta * multiplier(self._settings, rate)
        if raw <= 0.0 or raw >= 1.0:
            # Physical stop: re-synchronise the virtual value.  A previous fast
            # turn can leave it short of the stop, and without the anchor it
            # would never catch up again because the raw value cannot grow.
            value = raw
        state.value = max(0.0, min(1.0, value))
        return state.value
