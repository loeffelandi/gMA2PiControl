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


def lua_hardkey_frame(
    code: int, pressed: bool, session: int, hold: bool = False
) -> dict[str, Any]:
    """Hardkey press/release through the onPC command line.

    The onPC only injects a real hardware key event when the command is sent
    as a command frame.  Press and release are separate calls.  ``hold`` marks
    a key as being held down: a tap uses ``hold=false`` on press and release;
    a held key gets an extra ``hold=true`` press event so the console keeps it
    down (Store Options, MA chords).  ``hold=true`` on every press would turn
    even a quick tap into a hold, so it is only sent after the hold threshold.
    """

    flag = "true" if pressed else "false"
    hold_flag = "true" if hold else "false"
    return command_frame(
        f"LUA 'gma.canbus.hardkey({code}, {flag}, {hold_flag})'", session
    )


def lua_encoder_frame(index: int, steps: int, session: int) -> dict[str, Any]:
    """Turn a hardware encoder through the onPC command line.

    ``index`` is the encoder number minus one (0-3 attribute encoders, 4-9
    screen encoders), matching what ShowCockpit sends.
    """

    return command_frame(f"LUA 'gma.canbus.encoder({index},{steps},nil)'", session)


def lua_encoder_press_frame(index: int, pressed: bool, session: int) -> dict[str, Any]:
    """Press or release a hardware encoder (the onPC cycles its resolution)."""

    flag = "true" if pressed else "false"
    return command_frame(f"LUA 'gma.canbus.encoder({index},0,{flag})'", session)


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


def playbacks_user_input_button(
    page: int | str,
    executor: int,
    button: int,
    pressed: bool,
    released: bool,
    session: int,
) -> dict[str, Any]:
    """Press or release an executor button.

    ``page`` is a 1-based page number or ``"current"`` for the active master
    page.  ``executor`` and ``button`` are 1-based; the Web Remote expects
    0-based indices, and ``"current"`` is sent as ``-1``.
    """

    return {
        "requestType": "playbacks_userInput",
        "execIndex": executor - 1,
        "pageIndex": _page_index(page),
        "buttonId": button - 1,
        "pressed": pressed,
        "released": released,
        "type": 0,
        "session": session,
    }


def playbacks_user_input_fader(
    page: int | str, executor: int, value: float, session: int
) -> dict[str, Any]:
    """Set an executor fader to an absolute value between 0.0 and 1.0."""

    return {
        "requestType": "playbacks_userInput",
        "execIndex": executor - 1,
        "pageIndex": _page_index(page),
        "faderValue": value,
        "type": 1,
        "session": session,
    }


def playbacks_request(
    start: int,
    count: int,
    page: int | str,
    items_type: int,
    view: int,
    session: int,
) -> dict[str, Any]:
    """Ask for executor states of one page and one Web Remote view.

    The arrays carry a single block each; ``start`` is 0-based and should be a
    multiple of five because the console groups executors in blocks of five.
    ``items_type``/``view`` are 2 for executors below 100 and 3 for button or
    floating executors.  This mirrors the requests midimonster and the Q-SYS
    MA2 driver use.
    """

    return {
        "requestType": "playbacks",
        "startIndex": [start],
        "itemsCount": [count],
        "pageIndex": _page_index(page),
        "itemsType": [items_type],
        "view": view,
        "execButtonViewMode": 2,
        "buttonsViewMode": 0,
        "session": session,
    }


def _page_index(page: int | str) -> int:
    return -1 if page == "current" else page - 1

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
