from __future__ import annotations

import pytest

from ma2pi.acceleration import (
    ValueAccelerationSettings,
    ValueAccelerator,
    multiplier,
)


def test_linear_multiplier_reaches_maximum_at_fast_rate():
    settings = ValueAccelerationSettings(slow_rate=2, fast_rate=10, max_multiplier=8)
    assert multiplier(settings, 1) == 1.0
    assert multiplier(settings, 2) == 1.0
    assert multiplier(settings, 6) == pytest.approx(4.5)
    assert multiplier(settings, 10) == pytest.approx(8.0)
    assert multiplier(settings, 50) == pytest.approx(8.0)


def test_exponential_multiplier_uses_normalised_progress():
    settings = ValueAccelerationSettings(
        curve="exponential", slow_rate=2, fast_rate=10, max_multiplier=8
    )
    assert multiplier(settings, 2) == 1.0
    assert multiplier(settings, 6) == pytest.approx(8**0.5)
    assert multiplier(settings, 10) == pytest.approx(8.0)


def test_none_multiplier_is_always_one():
    settings = ValueAccelerationSettings(curve="none", max_multiplier=8)
    assert multiplier(settings, 1) == 1.0
    assert multiplier(settings, 50) == 1.0


def test_accelerator_starts_at_raw_value():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    assert accelerator.apply("encoder", 0.4, 0.0) == pytest.approx(0.4)


def test_accelerator_clamps_first_value():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    assert accelerator.apply("encoder", 2.0, 0.0) == 1.0
    assert accelerator.apply("encoder", -1.0, 0.5) == 0.0


def test_accelerator_slow_movement_is_one_to_one():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("encoder", 0.0, 0.0)
    assert accelerator.apply("encoder", 1 / 127, 0.5) == pytest.approx(1 / 127)
    assert accelerator.apply("encoder", 2 / 127, 1.0) == pytest.approx(2 / 127)


def test_accelerator_fast_movement_is_amplified():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("encoder", 0.0, 0.0)
    accelerator.apply("encoder", 1 / 127, 0.01)
    value = accelerator.apply("encoder", 2 / 127, 0.02)
    assert value > 2 / 127
    assert value == pytest.approx(1 / 127 + 1.875 / 127)


def test_accelerator_ignores_unchanged_values_for_rate():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("encoder", 0.5, 0.0)
    assert accelerator.apply("encoder", 0.5, 0.01) == pytest.approx(0.5)
    assert accelerator.apply("encoder", 0.51, 0.02) == pytest.approx(0.51)


def test_accelerator_clamps_to_full_range():
    accelerator = ValueAccelerator(ValueAccelerationSettings(max_multiplier=8))
    accelerator.apply("encoder", 0.0, 0.0)
    value = 0.0
    for index in range(1, 100):
        value = accelerator.apply("encoder", index / 127, index * 0.001)
    assert value == 1.0


def test_accelerator_keeps_controls_separate():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("slow", 0.0, 0.0)
    slow = accelerator.apply("slow", 1 / 127, 0.5)
    accelerator.apply("fast", 0.0, 0.0)
    accelerator.apply("fast", 1 / 127, 0.01)
    fast = accelerator.apply("fast", 2 / 127, 0.02)
    assert fast > slow


def test_accelerator_reset_returns_to_raw_value():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("encoder", 0.0, 0.0)
    accelerator.apply("encoder", 1 / 127, 0.01)
    accelerator.reset()
    assert accelerator.apply("encoder", 0.7, 0.02) == pytest.approx(0.7)


def test_accelerator_resynchronises_at_upper_stop():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("encoder", 1.0, 0.0)

    raw = 1.0
    now = 0.0
    value = 1.0
    while raw > 0.4 + 1e-9:
        raw = max(0.4, raw - 1 / 127)
        now += 0.005
        value = accelerator.apply("encoder", raw, now)
    assert value < raw

    while raw < 1.0:
        raw = min(1.0, raw + 1 / 127)
        now += 0.2
        value = accelerator.apply("encoder", raw, now)

    assert raw == 1.0
    assert value == pytest.approx(1.0)


def test_accelerator_resynchronises_at_lower_stop():
    accelerator = ValueAccelerator(ValueAccelerationSettings())
    accelerator.apply("encoder", 0.0, 0.0)

    raw = 0.0
    now = 0.0
    value = 0.0
    while raw < 0.6 - 1e-9:
        raw = min(0.6, raw + 1 / 127)
        now += 0.005
        value = accelerator.apply("encoder", raw, now)
    assert value > raw

    while raw > 0.0:
        raw = max(0.0, raw - 1 / 127)
        now += 0.2
        value = accelerator.apply("encoder", raw, now)

    assert raw == 0.0
    assert value == pytest.approx(0.0)
