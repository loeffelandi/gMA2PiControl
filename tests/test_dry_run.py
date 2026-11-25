"""End-to-end dry-run: a typical programming gesture produces exact frames.

The sequence is documented in the README ("Dry-Run: erwartete Frame-Folge").
No socket is opened and no HID device is required.
"""

from __future__ import annotations

import asyncio
import dataclasses

from ma2pi.events import InputEvent
from ma2pi.ma2_client import DryRunTransport, Ma2Client
from ma2pi.mapping import MappingEngine


async def wait_until(predicate, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.005)


def key(control: str, value: int) -> InputEvent:
    return InputEvent("key", control, value, "cherry")


def encoder(encoder_id: int, delta: int) -> InputEvent:
    return InputEvent("encoder", f"encoder.{encoder_id}", delta, "asl")


async def test_dry_run_programming_sequence(config):
    config = dataclasses.replace(
        config, ma2=dataclasses.replace(config.ma2, hardkey_transport="native")
    )
    transport = DryRunTransport()
    client = Ma2Client(config, transport=transport, dry_run=True)
    engine = MappingEngine(config, client)
    await client.start()
    client._page.update(
        {
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
                                {"n": "PAN", "np": "Pan", "s": False},
                            ],
                        }
                    ],
                }
            ],
        }
    )
    try:
        # MA + Fix (Desk Lock), Store hold, Clear hold, Go+, number 1.
        engine.handle(key("ma", 1))
        engine.handle(key("fix", 1))
        engine.handle(key("fix", 0))
        engine.handle(key("ma", 0))
        engine.handle(key("store_big", 1))
        engine.handle(key("store_big", 0))
        engine.handle(key("clear", 1))
        engine.handle(key("clear", 0))
        engine.handle(key("go_plus_big", 1))
        engine.handle(key("go_plus_big", 0))
        engine.handle(key("num_1", 1))
        engine.handle(key("num_1", 0))
        # One wheel detent and one attribute detent.
        engine.handle(encoder(1, 1), now=0.0)
        engine.handle(encoder(2, 1), now=0.0)
        engine.flush_all(0.05)

        await wait_until(lambda: len(transport.sent) >= 14)
        assert transport.sent == [
            {"requestType": "keyname", "keyname": "MA", "value": 1.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "FIX", "value": 1.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "FIX", "value": 0.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "MA", "value": 0.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "STORE", "value": 1.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "STORE", "value": 0.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "CLEAR", "value": 1.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "CLEAR", "value": 0.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "GO_PLUS", "value": 1.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "GO_PLUS", "value": 0.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "1", "value": 1.0, "session": 0, "maxRequests": 0},
            {"requestType": "keyname", "keyname": "1", "value": 0.0, "session": 0, "maxRequests": 0},
            {
                "requestType": "encoder",
                "name": "DIM",
                "value": 1.0,
                "session": 0,
                "maxRequests": 0,
            },
            {
                "requestType": "encoder",
                "name": "PAN",
                "value": 1.0,
                "session": 0,
                "maxRequests": 0,
            },
        ]
    finally:
        engine.cleanup(send=False)
        await client.shutdown()
