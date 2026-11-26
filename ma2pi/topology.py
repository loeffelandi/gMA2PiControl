"""Executor topology: which slots are covered by a wide (combined) executor.

The MA reports a wide executor as one item with ``combinedItems = n`` and omits
the items of the ``n - 1`` slots it covers.  This module keeps that knowledge
per page and region and answers "is this executor covered, and by whom" without
any I/O, so the input path can consult it synchronously.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, NamedTuple

#: First executor number of the floating (button) region.
FLOATING_START = 101

#: Region keys: executors 1..100 (faders) and 101.. (floating buttons).
REGION_FADER = 0
REGION_FLOATING = 100


def region_of(executor: int) -> int:
    """Return the region key for a 1-based executor number."""

    return REGION_FLOATING if executor >= FLOATING_START else REGION_FADER


class Resolution(NamedTuple):
    """Answer of :meth:`ExecutorTopology.resolve`."""

    #: Executor to address (the leading one when ``covered``).
    executor: int
    #: The asked executor is a slot covered by a wide executor.
    covered: bool
    #: A response for the region has been seen; ``False`` means "no data yet".
    known: bool
    #: Region key of the asked executor.
    region: int


@dataclass(frozen=True, slots=True)
class _Entry:
    covered: dict[int, int]
    present: frozenset[int]
    answered: range


class ExecutorTopology:
    """Per-(page, region) record of leading and covered executors."""

    def __init__(self) -> None:
        self._entries: dict[tuple[int | str, int], _Entry] = {}

    def update(
        self,
        page: int | str,
        region: int,
        combined: Mapping[int, int],
        present: Iterable[int],
        answered: range,
    ) -> None:
        """Replace the entry of ``(page, region)`` with a fresh response.

        ``combined`` maps a leading executor (1-based) to its ``combinedItems``
        (only values above 1 matter), ``present`` is every executor the response
        contained an item for, and ``answered`` the executor numbers the request
        asked for.  A slot that still has its own item stays a regular executor.
        """

        items = frozenset(present)
        covered: dict[int, int] = {}
        for lead, count in combined.items():
            for slot in range(lead + 1, lead + max(count, 1)):
                if slot not in items:
                    covered[slot] = lead
        self._entries[(page, region)] = _Entry(covered, items, answered)

    def resolve(self, page: int | str, executor: int) -> Resolution:
        """Resolve ``executor`` on ``page`` against the recorded topology."""

        region = region_of(executor)
        entry = self._entries.get((page, region))
        if entry is None:
            return Resolution(executor, False, False, region)
        lead = entry.covered.get(executor)
        if lead is not None:
            return Resolution(lead, True, True, region)
        return Resolution(executor, False, True, region)

    def status(self, page: int | str, executor: int) -> str:
        """Classify an executor: ``unknown``, ``present``, ``covered`` or ``absent``.

        ``absent`` is only reported for executors inside the range the last
        response was asked for; anything else stays ``unknown`` because the
        response says nothing about it.
        """

        entry = self._entries.get((page, region_of(executor)))
        if entry is None:
            return "unknown"
        if executor in entry.covered:
            return "covered"
        if executor in entry.present:
            return "present"
        if executor in entry.answered:
            return "absent"
        return "unknown"

    def invalidate(self, page: int | str | None = None) -> None:
        """Forget one page, or everything when ``page`` is ``None``."""

        if page is None:
            self._entries.clear()
            return
        for key in [key for key in self._entries if key[0] == page]:
            del self._entries[key]
