"""Exact JSON frames for the grandMA2 Web Remote API.

All builders are pure functions so tests can compare the resulting objects
exactly.  Nothing here logs or reads secrets.
"""

from __future__ import annotations

from typing import Any


def session_request_frame() -> dict[str, Any]:
    return {"session": 0}


def keepalive_frame(session: int) -> dict[str, Any]:
    return {"session": session}


def login_frame(
    username: str,
    password_md5: str,
    session: int,
    max_requests: int = 1,
) -> dict[str, Any]:
    return {
        "requestType": "login",
        "username": username,
        "password": password_md5,
        "session": session,
        "maxRequests": max_requests,
    }


def command_frame(command: str, session: int) -> dict[str, Any]:
    return {
        "command": command,
        "session": session,
        "requestType": "command",
        "maxRequests": 0,
    }


def keyname_frame(
    keyname: str,
    pressed: bool,
    session: int,
    press_value: float = 1.0,
    release_value: float = 0.0,
) -> dict[str, Any]:
    """Key press/release as the onPC Web Remote expects it.

    Live capture showed that the press edge must be sent with value ``1`` and
    the release edge with value ``0``; the console echoes the resulting command
    line text for a short moment.
    """

    return {
        "requestType": "keyname",
        "keyname": keyname,
        "value": press_value if pressed else release_value,
        "session": session,
        "maxRequests": 0,
    }


def encoder_attribute_frame(name: str, value: float, session: int) -> dict[str, Any]:
    """Turn an attribute encoder by a relative delta.

    Verified against onPC: the web remote sends ``value`` only; ``resolution``
    travels in its own frame.
    """

    return {
        "requestType": "encoder",
        "name": name,
        "value": value,
        "session": session,
        "maxRequests": 0,
    }


def encoder_resolution_frame(name: str, resolution: int, session: int) -> dict[str, Any]:
    """Set the encoder resolution: 0 = normal, 1 = fine, 2 = ultra."""

    return {
        "requestType": "encoder",
        "name": name,
        "resolution": resolution,
        "session": session,
        "maxRequests": 0,
    }


def preset_types_frame(kind: str, session: int) -> dict[str, Any]:
    """Ask for the encoder page model (``kind`` = "full" or "update")."""

    return {
        "requestType": "presetTypes",
        "type": kind,
        "session": session,
        "maxRequests": 1,
    }


def close_frame(session: int) -> dict[str, Any]:
    return {"requestType": "close", "session": session, "maxRequests": 1}


def frame_type(frame: dict[str, Any]) -> str:
    if "requestType" in frame:
        return str(frame["requestType"])
    if "command" in frame:
        return "command"
    if "session" in frame and len(frame) == 1:
        return "keepalive" if frame["session"] else "session"
    if "status" in frame:
        return "status"
    return "unknown"
