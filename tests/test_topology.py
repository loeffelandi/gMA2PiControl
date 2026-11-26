from __future__ import annotations

from ma2pi.topology import (
    REGION_FADER,
    REGION_FLOATING,
    ExecutorTopology,
    Resolution,
    region_of,
)


def floating_page_two() -> ExecutorTopology:
    """Exec 114 is two wide; the response has no item for Exec 115."""

    topology = ExecutorTopology()
    present = [n for n in range(101, 121) if n != 115]
    topology.update(2, REGION_FLOATING, {114: 2}, present, range(101, 121))
    return topology


def test_region_of():
    assert region_of(100) == REGION_FADER
    assert region_of(101) == REGION_FLOATING


def test_two_wide_executor_covers_next_slot():
    topology = floating_page_two()

    assert topology.resolve(2, 115) == Resolution(114, True, True, REGION_FLOATING)
    assert topology.resolve(2, 114) == Resolution(114, False, True, REGION_FLOATING)
    assert topology.resolve(2, 113) == Resolution(113, False, True, REGION_FLOATING)


def test_three_wide_executor_covers_two_slots():
    topology = ExecutorTopology()
    topology.update(1, REGION_FADER, {6: 3}, [1, 2, 3, 4, 5, 6, 9, 10], range(1, 11))

    assert topology.resolve(1, 7).executor == 6
    assert topology.resolve(1, 8).executor == 6
    assert topology.resolve(1, 9) == Resolution(9, False, True, REGION_FADER)


def test_slot_with_own_item_is_not_covered():
    topology = ExecutorTopology()
    topology.update(1, REGION_FADER, {3: 2}, [1, 2, 3, 4, 5], range(1, 6))

    assert topology.resolve(1, 4).covered is False


def test_unknown_region_and_page():
    topology = floating_page_two()

    # Other page, and the fader region of a known page, have no data.
    assert topology.resolve(3, 115) == Resolution(115, False, False, REGION_FLOATING)
    assert topology.resolve(2, 5) == Resolution(5, False, False, REGION_FADER)


def test_current_is_a_page_of_its_own():
    topology = ExecutorTopology()
    topology.update("current", REGION_FLOATING, {114: 2}, [114], range(101, 121))

    assert topology.resolve("current", 115).covered is True
    assert topology.resolve(2, 115).known is False


def test_new_response_replaces_the_entry():
    topology = floating_page_two()
    topology.update(2, REGION_FLOATING, {}, range(101, 121), range(101, 121))

    assert topology.resolve(2, 115) == Resolution(115, False, True, REGION_FLOATING)


def test_invalidate_one_page_and_all():
    topology = floating_page_two()
    topology.update(3, REGION_FLOATING, {}, [101], range(101, 106))

    topology.invalidate(2)
    assert topology.resolve(2, 115).known is False
    assert topology.resolve(3, 101).known is True

    topology.invalidate()
    assert topology.resolve(3, 101).known is False


def test_status_classification():
    topology = floating_page_two()

    assert topology.status(2, 114) == "present"
    assert topology.status(2, 115) == "covered"
    assert topology.status(2, 130) == "unknown"  # outside the asked range
    assert topology.status(3, 114) == "unknown"

    topology.update(2, REGION_FLOATING, {}, [101, 102], range(101, 106))
    assert topology.status(2, 104) == "absent"
    assert topology.status(2, 102) == "present"
