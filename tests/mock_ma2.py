"""Small grandMA2 Web Remote mock server for integration tests.

It implements just enough of the handshake (server ready, session request,
session information, login, keepalive) and records every received frame.  It
can reject logins, delay responses or drop the connection after N frames.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import websockets


DEFAULT_PRESET_TYPES: dict[str, Any] = {
    "responseType": "presetTypes",
    "type": "full",
    "pre": [
        {
            "i": 1,
            "np": "Dimmer",
            "s": True,
            "fea": [
                {
                    "i": 1,
                    "np": "Dimmer",
                    "s": True,
                    "att": [
                        {"n": "DIM", "np": "Dim", "s": True},
                        {"n": "DIMMERCURVE", "np": "Curve", "s": False},
                    ],
                }
            ],
        }
    ],
}


class MockMa2Server:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        username: str = "ma2pi",
        password: str = "secret",
        session_id: int = 1,
        login_result: bool = True,
        delay: float = 0.0,
        drop_after: int | None = None,
        record_path: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.session_id = session_id
        self.login_result = login_result
        self.delay = delay
        self.drop_after = drop_after
        self.record_path = record_path
        self.frames: list[dict[str, Any]] = []
        self.preset_types: dict[str, Any] = DEFAULT_PRESET_TYPES
        self.playbacks: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None
        self.logins: list[dict[str, Any]] = []
        self.connections = 0
        self._server: Any = None
        self._record_file = None

    async def start(self) -> "MockMa2Server":
        if self.record_path is not None:
            self._record_file = self.record_path.open("w", encoding="utf-8")
        self._server = await websockets.serve(self._handler, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._record_file is not None:
            self._record_file.close()
            self._record_file = None

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}/?ma=1"

    def _record(self, frame: dict[str, Any]) -> None:
        self.frames.append(frame)
        if self._record_file is not None:
            self._record_file.write(json.dumps(frame, ensure_ascii=False) + "\n")
            self._record_file.flush()

    async def _handler(self, websocket) -> None:
        self.connections += 1
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            await websocket.send(
                json.dumps({"status": "server ready", "appType": "gma2"})
            )
            raw = await websocket.recv()
            request = json.loads(raw)
            self._record(request)
            if request.get("session") != 0:
                await websocket.close(code=1002, reason="session expected")
                return
            await websocket.send(
                json.dumps(
                    {
                        "requestType": "sessionInformation",
                        "session": self.session_id,
                        "forceLogin": True,
                    }
                )
            )
            raw = await websocket.recv()
            login = json.loads(raw)
            self._record(login)
            self.logins.append(login)
            expected = hashlib.md5(self.password.encode("utf-8")).hexdigest()
            ok = (
                login.get("requestType") == "login"
                and login.get("username") == self.username
                and login.get("password") == expected
                and self.login_result
            )
            await websocket.send(
                json.dumps(
                    {
                        "requestType": "loginResponse",
                        "result": ok,
                        "session": self.session_id,
                        **({} if ok else {"error": "invalid credentials"}),
                    }
                )
            )
            if not ok:
                await websocket.close(code=1008, reason="login failed")
                return

            count = 0
            async for raw in websocket:
                frame = json.loads(raw)
                self._record(frame)
                if frame.get("requestType") == "presetTypes":
                    await websocket.send(json.dumps(self.preset_types))
                    continue
                if frame.get("requestType") == "playbacks":
                    if self.playbacks is not None:
                        response = self.playbacks(frame)
                        if response is not None:
                            await websocket.send(json.dumps(response))
                    continue
                count += 1
                if self.drop_after is not None and count >= self.drop_after:
                    await websocket.close(code=1001, reason="test drop")
                    return
        except websockets.ConnectionClosed:
            return
        except Exception:
            raise
