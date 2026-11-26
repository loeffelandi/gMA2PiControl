"""CLI entry point and daemon orchestration."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import logging
import signal
import sys
from pathlib import Path
from typing import Sequence

from . import PRODUCT_NAME, __version__
from .activity import (
    ActivityTracker,
    describe_input,
    describe_midi,
    record_ma2_frame,
)
from .config import AppConfig, ConfigError, find_config
from .config_store import DEFAULT_ETC_DIR, ConfigPaths
from .events import DeviceLost, InputEvent, format_input
from .feedback import ExecutorFeedback
from .hid_input import HidManager, device_matches, format_devices, list_devices
from .learn import LearnManager
from .led_output import LedOutput
from .logging_setup import setup_logging
from .ma2_client import Ma2Client
from .mapping import MappingEngine
from .device_learn import DeviceLearnManager
from .midi_input import MidiManager, list_midi_devices
from .network import NetworkManagerBackend, NetworkService, PendingStore
from .playback import PlaybackRouter
from .recovery import (
    MONITOR_INTERVAL as RECOVERY_MONITOR_INTERVAL,
    RecoveryBackend,
    RecoveryService,
    RecoveryStore,
)
from .runtime import ConfigStore

LOGGER = logging.getLogger("ma2pi")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PRODUCT_NAME,
        description=(
            "Cherry POS Keyboard (evdev) und ASL-Encoder (MIDI) über die "
            "grandMA2 Web-Remote-WebSocket-API an onPC anbinden."
        ),
    )
    parser.add_argument("--config", "-c", help="Pfad zur config.toml")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Konfiguration validieren und beenden",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Frames nur loggen, keine WebSocket-Verbindung öffnen",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log-Level überschreiben",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Erkannte Eingabegeräte auflisten",
    )
    parser.add_argument(
        "--dump-input",
        action="store_true",
        help="Normalisierte Eingabeereignisse live ausgeben",
    )
    parser.add_argument(
        "--version", action="version", version=f"{PRODUCT_NAME} {__version__}"
    )
    return parser


def _load(args: argparse.Namespace) -> AppConfig:
    return find_config(args.config)


async def _process_input(
    queue: "asyncio.Queue[InputEvent | DeviceLost]",
    engine: MappingEngine,
    learn: LearnManager,
    bus,
    playback: PlaybackRouter | None = None,
    device_learn: DeviceLearnManager | None = None,
    activity: ActivityTracker | None = None,
) -> None:
    while True:
        item = await queue.get()
        if activity is not None:
            if isinstance(item, DeviceLost):
                activity.record_rx(
                    "system", "device-lost", f"{item.device}: {item.reason}"
                )
            else:
                activity.record_rx(
                    item.device or "system", item.kind, describe_input(item)
                )
        if isinstance(item, DeviceLost):
            if learn.active:
                _publish_learn(bus, learn.cancel())
            if device_learn is not None:
                device_learn.device_lost(item.device)
            engine.release_device(item.device)
        elif learn.active:
            # Learn owns all input while a session is open; no mapping action
            # may reach the onPC, including the captured key's release.
            _publish_learn(bus, learn.feed(item))
        elif (
            device_learn is not None
            and device_learn.session is not None
            and device_learn.session.device == item.device
        ):
            # A device learn session consumes the selected device completely,
            # including events that were queued before it started.
            continue
        elif playback is None or not playback.handle(item):
            engine.handle(item)


def _publish_learn(bus, result) -> None:
    if bus is None or result is None:
        return
    from .web import learn_event

    bus.publish(learn_event(result))


async def _learn_loop(learn: LearnManager, bus) -> None:
    """Finish encoder windows and idle sessions even without new input."""

    while True:
        await asyncio.sleep(0.1)
        if learn.active:
            _publish_learn(bus, learn.poll())


def _status_snapshot(
    client: Ma2Client,
    store: ConfigStore | None = None,
    activity: ActivityTracker | None = None,
) -> dict:
    """Runtime status for the UI; never contains credentials."""
    snapshot = {
        "connected": client.connected,
        "authenticated": client.authenticated,
        "session": client.session,
        "queue_depth": len(client.queue),
        "rate": client.limiter.effective_rate,
        "screen_mode": client.screen_mode,
        "frames_sent": client.frames_sent,
        "last_frame_types": list(client.last_frame_types)[-10:],
        "reconnects": client.reconnects,
        "last_error": client.last_error,
        "generation": store.generation if store is not None else 0,
        "busy": store.busy if store is not None else False,
        "activity": (
            activity.snapshot()
            if activity is not None
            else {"devices": {}, "log": []}
        ),
    }
    return snapshot


def _activity_event(activity: ActivityTracker) -> dict | None:
    """Drain pending activity into one bounded WebSocket event."""

    entries = activity.take_pending()
    if not entries:
        return None
    return {
        "type": "activity",
        "data": {"devices": activity.devices(), "entries": entries},
    }


def _config_paths(config: AppConfig) -> ConfigPaths:
    """Pick the writable state directory for the active configuration."""

    source = Path(config.source_path) if config.source_path else None
    if source is not None and source.parent != DEFAULT_ETC_DIR:
        return ConfigPaths(state_dir=source.parent)
    return ConfigPaths()


def _find_led_target(config: AppConfig) -> tuple[str, str] | None:
    """Return ``(midi node, device name)`` for the LED output."""

    try:
        infos = list_midi_devices()
    except Exception as exc:  # pragma: no cover - hardware dependent
        LOGGER.warning("MIDI-Enumeration für LED fehlgeschlagen: %s", exc)
        return None
    for name, device in config.devices.items():
        if device.backend != "midi":
            continue
        for info in infos:
            if device_matches(device, info):
                return info.path, name
    return (infos[0].path, "asl") if infos else None


def _resolve_led_target(config: AppConfig) -> tuple[str, str] | None:
    """Resolve ``[led].device`` (a configured name) to ``(path, name)``."""

    if config.led.device is None:
        return _find_led_target(config)
    device = config.devices.get(config.led.device)
    if device is None or device.backend != "midi":
        return None
    try:
        infos = list_midi_devices()
    except Exception as exc:  # pragma: no cover - hardware dependent
        LOGGER.warning("MIDI-Enumeration für LED fehlgeschlagen: %s", exc)
        return None
    for info in infos:
        if device_matches(device, info):
            return info.path, config.led.device
    return None


def _start_led(config: AppConfig) -> LedOutput | None:
    """Open the LED output; a failure must never stop the daemon."""

    if not config.led.enabled:
        return None
    target = _resolve_led_target(config)
    if target is None:
        LOGGER.warning("LED-Ausgabe aktiviert, aber kein MIDI-Gerät gefunden")
        return None
    path, name = target
    led = LedOutput(path, config.led)
    led.device_name = name
    try:
        led.open()
    except OSError as exc:
        LOGGER.error("LED-Ausgabe konnte %s nicht öffnen: %s", path, exc)
        return None
    led.enable()
    led.apply_mode(False)
    LOGGER.info("LED-Ausgabe aktiv auf %s (Note %d)", path, config.led.note)
    return led


def _attach_led_activity(led: LedOutput | None, activity: ActivityTracker) -> None:
    """Report LED writes as TX activity under the resolved device name."""

    if led is None:
        return
    led.on_write = lambda label: activity.record_tx(
        led.device_name, "led", label
    )


async def _led_loop(
    config: AppConfig,
    client: Ma2Client,
    holder: dict,
    activity: ActivityTracker | None = None,
) -> None:
    """Open the LED output as soon as the (re)plugged device appears."""

    while True:
        await asyncio.sleep(2.0)
        current = holder.get("led")
        if current is not None and current.is_open and current.still_attached():
            continue
        target = _resolve_led_target(config)
        if target is None:
            continue
        path, name = target
        if not Path(path).exists():
            continue
        if current is not None:
            current.close()  # toten Handle nach Replug freigeben
        led = LedOutput(path, config.led)
        led.device_name = name
        try:
            led.open()
        except OSError:
            continue
        led.enable()
        led.apply_mode(bool(client.screen_mode))
        if activity is not None:
            _attach_led_activity(led, activity)
        holder["led"] = led
        client.set_led(led)
        LOGGER.info("LED-Ausgabe aktiv auf %s (Note %d)", path, config.led.note)


async def _device_learn_loop(device_learn: DeviceLearnManager, engine: MappingEngine) -> None:
    """Timeout the active device learn session and follow hot reloads."""

    while True:
        await asyncio.sleep(0.2)
        device_learn.set_config(engine.config)
        device_learn.poll()


async def _start_web(
    config: AppConfig,
    client: Ma2Client,
    store: ConfigStore,
    learn: LearnManager,
    device_learn: DeviceLearnManager | None = None,
    activity: ActivityTracker | None = None,
):
    """Start the embedded UI; return ``(runner, broadcast_task, bus)`` or ``None``."""
    from aiohttp import web as aiohttp_web

    from .web import BUS_KEY, create_app

    paths = _config_paths(config)
    network = NetworkService(
        NetworkManagerBackend(),
        PendingStore(paths.state_dir / "network-pending.json"),
        port=config.web.port,
    )
    recovery = RecoveryService(
        RecoveryBackend(),
        RecoveryStore(paths.state_dir / "recovery.json"),
        port=config.web.port,
    )
    app = create_app(
        config,
        status_provider=lambda: _status_snapshot(client, store, activity),
        config_store=store,
        learn_manager=learn,
        device_learn_manager=device_learn,
        network_service=network,
        recovery_service=recovery,
    )
    runner = aiohttp_web.AppRunner(app, access_log=None)
    await runner.setup()
    site = aiohttp_web.TCPSite(runner, config.web.bind, config.web.port)
    try:
        await site.start()
    except OSError as exc:
        LOGGER.error(
            "Web-UI konnte %s:%s nicht binden: %s", config.web.bind, config.web.port, exc
        )
        await runner.cleanup()
        return None

    bus = app[BUS_KEY]
    network.publish = bus.publish
    recovery.publish = bus.publish
    try:
        await network.resume()
    except Exception as exc:  # a broken pending file must not stop the daemon
        LOGGER.error("Netzwerk-Pending-Zustand konnte nicht geladen werden: %s", exc)
    try:
        await recovery.resume()
    except Exception as exc:
        LOGGER.error("Rettungs-WLAN konnte nicht geladen werden: %s", exc)

    async def broadcast() -> None:
        """Push status once per second and activity deltas every 250 ms."""
        tick = 0
        while True:
            await asyncio.sleep(0.25)
            event = _activity_event(activity) if activity is not None else None
            if event is not None and bus.subscriber_count:
                bus.publish(event)
            tick += 1
            if tick % 4 == 0 and bus.subscriber_count:
                bus.publish(
                    {"type": "status", "data": _status_snapshot(client, store, activity)}
                )

    task = asyncio.create_task(broadcast(), name="ma2pi-web-status")
    recovery_task = asyncio.create_task(
        recovery_loop(network, recovery), name="ma2pi-recovery"
    )
    LOGGER.info("Web-UI erreichbar unter http://%s:%s/", config.web.bind, config.web.port)
    return runner, task, bus, network, recovery_task


async def recovery_loop(network: NetworkService, recovery: RecoveryService) -> None:
    """Enable the recovery hotspot only after a sustained wired outage."""
    while True:
        await asyncio.sleep(RECOVERY_MONITOR_INTERVAL)
        try:
            await recovery.auto_cycle(await network.wired_ok())
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Rettungs-WLAN-Prüfung fehlgeschlagen: %s", exc)


async def run_daemon(config: AppConfig, dry_run: bool) -> int:
    level = config.logging.level
    setup_logging(level)
    LOGGER.info("%s %s startet (dry_run=%s)", PRODUCT_NAME, __version__, dry_run)

    queue: asyncio.Queue[InputEvent | DeviceLost] = asyncio.Queue(maxsize=1000)
    client = Ma2Client(config, dry_run=dry_run)
    activity = ActivityTracker()
    client.on_frame = lambda kind, frame: record_ma2_frame(activity, kind, frame)
    engine = MappingEngine(config, client)
    store = ConfigStore(config, engine, _config_paths(config), client=client)
    learn = LearnManager(config)
    device_learn = DeviceLearnManager(config)
    playback = PlaybackRouter(engine, client)
    client.add_connection_lost_callback(engine.on_connection_lost)
    hid = HidManager(config)
    midi = MidiManager(config)
    midi.set_raw_hook(device_learn.handle_raw)
    midi.set_send_hook(
        lambda device, data: activity.record_tx(device, "midi", describe_midi(data))
    )
    feedback = ExecutorFeedback(config, client, midi, dry_run=dry_run)
    client.add_connection_lost_callback(feedback.reset)
    store.add_activate_hook(hid.set_config)
    store.add_activate_hook(midi.set_config)
    store.add_activate_hook(feedback.set_config)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):  # pragma: no cover
            pass

    await client.start()
    led_holder: dict = {"led": _start_led(config)}
    _attach_led_activity(led_holder["led"], activity)
    client.set_led(led_holder["led"])
    led_task = (
        asyncio.create_task(
            _led_loop(config, client, led_holder, activity), name="ma2pi-led"
        )
        if config.led.enabled
        else None
    )
    def _modifier_led(control: str, pressed: bool) -> None:
        led = led_holder.get("led")
        if led is not None and control == engine.config.mapping.resolution.cycle_modifier:
            led.set_fine(pressed)

    engine.modifier_hook = _modifier_led
    web_service = await _start_web(
        config, client, store, learn, device_learn, activity
    )
    bus = web_service[2] if web_service is not None else None
    encoder_task = asyncio.create_task(engine.run_encoder_loop(), name="ma2pi-encoder")
    hid_task = asyncio.create_task(hid.run(queue), name="ma2pi-hid")
    midi_task = asyncio.create_task(midi.run(queue), name="ma2pi-midi")
    input_task = asyncio.create_task(
        _process_input(queue, engine, learn, bus, playback, device_learn, activity),
        name="ma2pi-input",
    )
    learn_task = asyncio.create_task(_learn_loop(learn, bus), name="ma2pi-learn")
    device_learn_task = asyncio.create_task(
        _device_learn_loop(device_learn, engine), name="ma2pi-device-learn"
    )
    feedback_task = asyncio.create_task(feedback.run(), name="ma2pi-feedback")

    failure: list[BaseException] = []

    def _watch(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            failure.append(exc)
            LOGGER.error("Hintergrund-Task %s fehlgeschlagen: %s", task.get_name(), exc)
            stop.set()

    for task in (
        encoder_task,
        hid_task,
        midi_task,
        input_task,
        learn_task,
        device_learn_task,
        feedback_task,
    ):
        task.add_done_callback(_watch)

    try:
        await stop.wait()
    finally:
        LOGGER.info("Shutdown angefordert")
        input_task.cancel()
        hid_task.cancel()
        midi_task.cancel()
        learn_task.cancel()
        engine.stop()
        encoder_task.cancel()
        feedback_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await feedback_task
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await input_task
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await hid_task
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await midi_task
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await learn_task
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await encoder_task
        engine.cleanup(send=client.authenticated)
        await client.shutdown()
        if led_task is not None:
            led_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await led_task
        if led_holder["led"] is not None:
            led_holder["led"].close()
        if web_service is not None:
            web_runner, web_task, _, network, recovery_task = web_service
            recovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await recovery_task
            await network.close()
            web_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await web_task
            with contextlib.suppress(Exception):
                await web_runner.cleanup()
        await hid.close()
        await midi.close()
    if failure:
        LOGGER.error("%s wegen Fehler beendet: %s", PRODUCT_NAME, failure[0])
        return 1
    LOGGER.info("%s beendet", PRODUCT_NAME)
    return 0


async def run_dump_input(config: AppConfig) -> int:
    from .hid_input import evdev

    setup_logging("DEBUG")
    queue: asyncio.Queue[InputEvent | DeviceLost] = asyncio.Queue()
    hid = HidManager(config)
    midi = MidiManager(config)
    tasks: list[asyncio.Task[None]] = []
    if evdev is not None:
        tasks.append(asyncio.create_task(hid.run(queue), name="ma2pi-hid-dump"))
    tasks.append(asyncio.create_task(midi.run(queue), name="ma2pi-midi-dump"))
    print("Eingabeereignisse (Ctrl-C zum Beenden):", flush=True)
    try:
        while True:
            item = await queue.get()
            if isinstance(item, InputEvent):
                print(format_input(item), flush=True)
            else:
                print(repr(item), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await hid.close()
        await midi.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = _load(args)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    if args.check_config:
        print(f"Konfiguration gültig: {config.source_path}")
        return 0

    if args.list_devices:
        devices = []
        errors = []
        try:
            devices.extend(list_devices())
        except Exception as exc:
            errors.append(f"evdev: {exc}")
        try:
            devices.extend(list_midi_devices())
        except Exception as exc:
            errors.append(f"MIDI: {exc}")
        if not devices:
            for error in errors:
                print(f"Geräte-Enumeration fehlgeschlagen: {error}", file=sys.stderr)
            return 1
        print(format_devices(devices))
        return 0

    if args.dump_input:
        try:
            return asyncio.run(run_dump_input(config))
        except Exception as exc:
            print(f"--dump-input fehlgeschlagen: {exc}", file=sys.stderr)
            return 1

    if args.log_level:
        config = dataclasses.replace(
            config, logging=dataclasses.replace(config.logging, level=args.log_level)
        )

    try:
        return asyncio.run(run_daemon(config, args.dry_run))
    except KeyboardInterrupt:  # pragma: no cover
        return 0
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
