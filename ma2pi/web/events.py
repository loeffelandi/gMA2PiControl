"""In-process event bus and WebSocket fan-out for the configuration UI.

The daemon publishes status, learn and log events here; every connected UI
client gets its own bounded queue plus an overflow/disconnect signal.  A slow
client never blocks the daemon: its queue is dropped when full, its WebSocket
is actively closed, and the client resynchronises from ``/api/status``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from aiohttp import WSMsgType, web

LOGGER = logging.getLogger("ma2pi.web.events")

#: Bounded per-client queue; a stalled browser is disconnected instead of
#: growing without limit.
QUEUE_SIZE = 200


class EventBus:
    """Fan-out of JSON events to all subscribed UI clients."""

    def __init__(self, queue_size: int = QUEUE_SIZE) -> None:
        self._queue_size = queue_size
        self._subscribers: dict[asyncio.Queue[dict[str, Any]], asyncio.Event] = {}

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue, _ = self.subscribe_with_signal()
        return queue

    def subscribe_with_signal(
        self,
    ) -> tuple[asyncio.Queue[dict[str, Any]], asyncio.Event]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        dropped = asyncio.Event()
        self._subscribers[queue] = dropped
        return queue, dropped

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        dropped = self._subscribers.pop(queue, None)
        if dropped is not None:
            dropped.set()

    def close_all(self) -> None:
        """Disconnect every active WebSocket subscriber (logout / PIN change / shutdown)."""

        for queue in list(self._subscribers):
            self.unsubscribe(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Deliver an event to every subscriber without blocking."""
        for queue, dropped in list(self._subscribers.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                LOGGER.warning("UI-Client zu langsam, trenne Verbindung")
                dropped.set()
                self._subscribers.pop(queue, None)


async def _drain(ws: web.WebSocketResponse) -> None:
    """Consume incoming frames until the client closes the socket."""
    async for message in ws:
        if message.type == WSMsgType.ERROR:
            return


async def events_handler(
    request: web.Request,
    bus: EventBus,
    *,
    initial: dict[str, Any] | None = None,
) -> web.WebSocketResponse:
    """Stream bus events to one client until it disconnects or overflows."""
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    queue, dropped = bus.subscribe_with_signal()
    reader = asyncio.create_task(_drain(ws), name="ma2pi-events-reader")
    drop_waiter = asyncio.create_task(dropped.wait(), name="ma2pi-events-dropped")
    try:
        if initial is not None:
            await asyncio.wait_for(ws.send_json(initial), timeout=5.0)
        while not reader.done() and not drop_waiter.done():
            getter = asyncio.create_task(queue.get(), name="ma2pi-events-get")
            done, _ = await asyncio.wait(
                {getter, reader, drop_waiter}, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done and not drop_waiter.done():
                try:
                    await asyncio.wait_for(ws.send_json(getter.result()), timeout=5.0)
                except TimeoutError:
                    LOGGER.warning("UI-Client nimmt WebSocket-Frames nicht ab, trenne Verbindung")
                    break
            else:
                getter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await getter
                break
    except TimeoutError:
        LOGGER.warning("UI-Client nimmt initialen WebSocket-Frame nicht ab, trenne Verbindung")
    finally:
        bus.unsubscribe(queue)
        drop_waiter.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await drop_waiter
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ws.close(), timeout=0.5)
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reader
    return ws
