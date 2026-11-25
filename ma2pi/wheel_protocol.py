"""Native wheel/encoder frame builders.

The native wheel frame format of the grandMA2 Web Remote is **not** documented
and has not been captured yet.  Until ``NATIVE_WHEEL_CONFIRMED`` is flipped by
a real capture (see README), the daemon must use the CMD wrapper.  This module
is the single place where the native format will live, so the rest of the code
never has to guess.
"""

from __future__ import annotations

from typing import Any

# Set to True only after a captured wheel frame has been added as a fixture and
# this module has been updated to reproduce it (ADR-0002).
NATIVE_WHEEL_CONFIRMED = False

# Placeholder request type.  Do not treat this as a verified protocol value.
REQUEST_TYPE_WHEEL = "wheel"


class NativeWheelUnavailable(RuntimeError):
    """Raised when the native wheel mode is used without a verified capture."""


def ensure_native_wheel_available() -> None:
    if not NATIVE_WHEEL_CONFIRMED:
        raise NativeWheelUnavailable(
            "Das native Wheel-Frame-Format ist nicht verifiziert. Führe zuerst "
            "den Wheel-Capture-Workflow aus (README) und aktualisiere "
            "wheel_protocol.py sowie ADR-0002, oder nutze den CMD-Modus."
        )


def build_wheel_frame(wheel: int, delta: int, session: int) -> dict[str, Any]:
    """Build a native wheel frame.

    The concrete fields stay deliberately narrow until a capture exists.  The
    builder raises instead of emitting an invented frame.
    """

    ensure_native_wheel_available()
    return {
        "requestType": REQUEST_TYPE_WHEEL,
        "wheel": wheel,
        "value": delta,
        "session": session,
        "maxRequests": 0,
    }
