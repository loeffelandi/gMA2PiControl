"""In-process event bus and WebSocket fan-out for the configuration UI.

The daemon publishes status, learn and log events here; every connected UI
client gets its own bounded queue.  A slow client never blocks the daemon: its
queue is dropped when full and the client resynchronises from ``/api/status``.
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
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        """Deliver an event to every subscriber without blocking."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                LOGGER.warning("UI-Client zu langsam, trenne Verbindung")
                self.unsubscribe(queue)


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
    """Stream bus events to one client until it disconnects."""
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    queue = bus.subscribe()
    reader = asyncio.create_task(_drain(ws), name="ma2pi-events-reader")
    try:
        if initial is not None:
            await ws.send_json(initial)
        while not reader.done():
            getter = asyncio.create_task(queue.get(), name="ma2pi-events-get")
            done, _ = await asyncio.wait(
                {getter, reader}, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in done:
                await ws.send_json(getter.result())
            else:
                getter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await getter
                break
    finally:
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await reader
        bus.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await ws.close()
    return ws
