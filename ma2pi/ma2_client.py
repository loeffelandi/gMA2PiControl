"""grandMA2 Web Remote WebSocket client.

Responsibilities: session handshake, keepalive, reconnect with backoff, a
single globally rate-limited send queue with control priority, dry-run mode and
graceful shutdown.  It knows nothing about HID devices or mapping.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import random
import time
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from . import frames
from .actions import (
    Action,
    Command,
    EncoderAction,
    EncoderAttribute,
    ToggleScreenMode,
    EncoderSlot,
    Press,
    Release,
    ToggleFine,
    encoder_key,
    is_encoder,
    merge_encoder,
)
from .config import AppConfig
from .encoder_page import WINDOW, EncoderPage
from .logging_setup import log_frame

LOGGER = logging.getLogger("ma2pi.client")

#: Resolution values the onPC accepts on an ``encoder`` request.
RESOLUTION_NAMES = {0: "Normal", 1: "Fine", 2: "Ultra"}


def encode_frame(payload: dict[str, Any]) -> str:
    """Serialise a frame exactly the way the onPC Web Remote expects it.

    onPC matches the ``login`` request against the raw JSON text: a frame with
    spaces after ``:`` or ``,`` (``json.dumps``' default) is answered with
    ``{"result": false}`` even for correct credentials, while the compact form
    logs in successfully.  Measured against onPC 3.9 with the same session id
    and password hash, so the separators are not cosmetic.
    """

    return json.dumps(payload, separators=(",", ":"))


class LoginError(RuntimeError):
    """The server rejected the credentials."""


class HandshakeError(RuntimeError):
    """The server did not complete the expected handshake."""


class ConnectionClosed(RuntimeError):
    """The peer closed the connection."""


class Transport(Protocol):
    async def connect(self, uri: str) -> None: ...
    async def recv(self) -> str | bytes | None: ...
    async def send(self, payload: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...
    def write_buffer_size(self) -> int: ...


class WebSocketTransport:
    """Production transport based on the ``websockets`` package."""

    def __init__(self) -> None:
        self._ws: Any = None

    async def connect(self, uri: str) -> None:
        import websockets

        self._ws = await websockets.connect(
            uri,
            open_timeout=10,
            ping_interval=None,
            max_size=2 * 1024 * 1024,
        )

    async def recv(self) -> str | bytes | None:
        assert self._ws is not None
        try:
            return await self._ws.recv()
        except Exception as exc:  # websockets ConnectionClosed
            raise ConnectionClosed(str(exc)) from exc

    async def send(self, payload: dict[str, Any]) -> None:
        assert self._ws is not None
        try:
            await self._ws.send(encode_frame(payload))
        except Exception as exc:
            raise ConnectionClosed(str(exc)) from exc

    async def close(self) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

    def write_buffer_size(self) -> int:
        if self._ws is None:
            return 0
        transport = getattr(self._ws, "transport", None)
        if transport is None:
            return 0
        try:
            return int(transport.get_write_buffer_size())
        except Exception:
            return 0


class DryRunTransport:
    """Logs frames and never opens a socket."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def connect(self, uri: str) -> None:  # pragma: no cover - never used
        raise AssertionError("DryRunTransport must not connect")

    async def recv(self) -> str | bytes | None:  # pragma: no cover
        raise AssertionError("DryRunTransport must not receive")

    async def send(self, payload: dict[str, Any]) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        return None

    def write_buffer_size(self) -> int:
        return 0


class SendQueue:
    """One queue, two priorities; encoder actions coalesce per target."""

    def __init__(self) -> None:
        self._control: deque[Action] = deque()
        self._encoder: OrderedDict[tuple[str, str | int], EncoderAction] = OrderedDict()
        self._ready = asyncio.Event()
        self.closed = False

    def put(self, action: Action) -> None:
        if self.closed:
            return
        if is_encoder(action):
            assert isinstance(action, (EncoderSlot, EncoderAttribute))
            key = encoder_key(action)
            existing = self._encoder.get(key)
            if existing is None:
                self._encoder[key] = action
            else:
                merged = merge_encoder(existing, action)
                if merged is None:
                    self._encoder.pop(key, None)
                else:
                    self._encoder[key] = merged
        else:
            self._control.append(action)
        self._ready.set()

    async def get(self) -> Action:
        while True:
            if self._control:
                return self._control.popleft()
            if self._encoder:
                _, action = self._encoder.popitem(last=False)
                return action
            self._ready.clear()
            await self._ready.wait()

    def clear(self) -> None:
        self._control.clear()
        self._encoder.clear()

    @property
    def control_depth(self) -> int:
        return len(self._control)

    @property
    def total_depth(self) -> int:
        return len(self._control) + len(self._encoder)

    def __len__(self) -> int:
        return self.total_depth


class TokenBucket:
    """Global token bucket with an injectable clock for deterministic tests."""

    def __init__(
        self,
        rate: int,
        burst: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.rate = float(rate)
        self.burst = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._updated = clock()
        self.multiplier = 1.0

    @property
    def effective_rate(self) -> float:
        return max(0.1, self.rate * self.multiplier)

    async def acquire(self) -> None:
        while True:
            now = self._clock()
            elapsed = max(0.0, now - self._updated)
            self._tokens = min(self.burst, self._tokens + elapsed * self.effective_rate)
            self._updated = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait = (1.0 - self._tokens) / self.effective_rate
            await self._sleep(max(wait, 0.001))


@dataclass
class BackpressureGuard:
    """Halves the rate while the control queue or socket buffer is saturated."""

    depth_threshold: int = 100
    buffer_threshold: int = 64 * 1024
    hold_seconds: float = 2.0
    recover_seconds: float = 5.0
    active: bool = False
    _high_since: float | None = field(default=None, init=False)
    _low_since: float | None = field(default=None, init=False)

    def observe(self, now: float, control_depth: int, buffer_bytes: int) -> str | None:
        high = control_depth > self.depth_threshold or buffer_bytes > self.buffer_threshold
        if high:
            self._low_since = None
            if self._high_since is None:
                self._high_since = now
            if not self.active and now - self._high_since >= self.hold_seconds:
                self.active = True
                return "engaged"
            return None
        self._high_since = None
        if self.active:
            if self._low_since is None:
                self._low_since = now
            if now - self._low_since >= self.recover_seconds:
                self.active = False
                self._low_since = None
                return "released"
        return None


def _format_delta(value: float) -> str:
    text = f"{value:+.6f}".rstrip("0").rstrip(".")
    if text in {"+0", "-0"}:
        return "+0"
    return text


class Ma2Client:
    """Rate-limited, reconnecting client for one onPC target."""

    def __init__(
        self,
        config: AppConfig,
        *,
        transport: Transport | None = None,
        dry_run: bool = False,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter_source: Callable[[], float] = random.random,
    ) -> None:
        self.config = config
        self._transport = transport or (DryRunTransport() if dry_run else WebSocketTransport())
        self.dry_run = dry_run
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter_source
        self._queue = SendQueue()
        self._limiter = TokenBucket(
            config.rate_limit.messages_per_second,
            config.rate_limit.burst,
            clock=clock,
            sleep=sleep,
        )
        self._guard = BackpressureGuard()
        self._session: int | None = None
        self._authenticated = False
        self._shutting_down = False
        self._stop_sender = False
        self._sender_task: asyncio.Task[None] | None = None
        self._session_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._backpressure_task: asyncio.Task[None] | None = None
        self._connection_lost_callbacks: list[Callable[[], None]] = []
        self._page = EncoderPage()
        self._screen_mode = False
        self._led = None
        self._fine: dict[int, int] = {}
        self._page_task: asyncio.Task[None] | None = None
        self._page_poll_task: asyncio.Task[None] | None = None
        self._page_signature: tuple[int, tuple[str | None, ...]] | None = None
        self.frames_sent = 0
        self.by_type: Counter[str] = Counter()
        self.last_frame_types: deque[str] = deque(maxlen=50)
        self.sent_frames: list[dict[str, Any]] = []
        self.reconnects = 0
        self.login_failures = 0
        self.last_error: str | None = None

    # -- public state -----------------------------------------------------

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def session(self) -> int | None:
        return self._session

    @property
    def queue(self) -> SendQueue:
        return self._queue

    @property
    def limiter(self) -> TokenBucket:
        return self._limiter

    @property
    def screen_mode(self) -> bool:
        """True while the encoders are hard-wired to the screen encoders."""

        return self._screen_mode

    @property
    def connected(self) -> bool:
        return self._authenticated

    def add_connection_lost_callback(self, callback: Callable[[], None]) -> None:
        self._connection_lost_callbacks.append(callback)

    # -- action entry points ---------------------------------------------

    def press(self, keyname: str) -> None:
        self._submit(Press(keyname))

    def release(self, keyname: str) -> None:
        self._submit(Release(keyname))

    def command(self, text: str) -> None:
        self._submit(Command(text))

    def encoder_slot(self, slot: int, delta: float) -> None:
        self._submit(EncoderSlot(slot, delta))

    def encoder_attribute(self, name: str, value: float) -> None:
        self._submit(EncoderAttribute(name, value))

    def toggle_screen_mode(self) -> None:
        self._submit(ToggleScreenMode())

    def set_led(self, led) -> None:
        """Attach an LED output; it follows the encoder mode."""

        self._led = led

    def toggle_fine(self, slot: int) -> None:
        self._submit(ToggleFine(slot))

    def _submit(self, action: Action) -> None:
        if self._shutting_down:
            return
        if not self._authenticated and not self.dry_run:
            LOGGER.debug("verwerfe Aktion ohne Session: %s", action)
            return
        self._queue.put(action)

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if self._sender_task is not None:
            return
        self.warn_unverified_hardkeys()
        self._sender_task = asyncio.create_task(self._sender_loop(), name="ma2pi-sender")
        self._backpressure_task = asyncio.create_task(
            self._backpressure_loop(), name="ma2pi-backpressure"
        )
        if self.dry_run:
            self._authenticated = True
            self._session = 0
            LOGGER.info("Dry-Run aktiv: keine WebSocket-Verbindung")
            return
        self._session_task = asyncio.create_task(self._session_loop(), name="ma2pi-session")

    async def run(self) -> None:
        """Run until shutdown is requested."""

        await self.start()
        assert self._session_task is not None
        with contextlib.suppress(asyncio.CancelledError):
            await self._session_task

    async def shutdown(self, timeout: float = 5.0) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        deadline = self._clock() + min(timeout, 5.0) - 1.0
        while self._queue.total_depth and self._authenticated and self._clock() < deadline:
            await self._sleep(0.01)
        if self._authenticated:
            session = self._session or 0
            with contextlib.suppress(Exception):
                await self._send_raw(frames.close_frame(session), "closeConnection")
        await self._transport.close()
        self._authenticated = False
        self._stop_sender = True
        for task in (
            self._keepalive_task,
            self._page_poll_task,
            self._backpressure_task,
            self._session_task,
            self._sender_task,
        ):
            if task is not None and not task.done():
                task.cancel()
        for task in (
            self._keepalive_task,
            self._page_poll_task,
            self._backpressure_task,
            self._session_task,
            self._sender_task,
        ):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._queue.clear()

    # -- session loop -----------------------------------------------------

    async def _session_loop(self) -> None:
        attempt = 0
        while not self._shutting_down:
            login_failed = False
            try:
                await self.connect_once()
                attempt = 0
                self._page_poll_task = asyncio.create_task(
                    self._page_poll_loop(self._session or 0), name="ma2pi-page-poll"
                )
                await self._read_loop()
                reason = "Verbindung vom Server beendet"
            except LoginError as exc:
                login_failed = True
                self.login_failures += 1
                self.last_error = str(exc)
                LOGGER.error("Login fehlgeschlagen: %s", exc)
                reason = f"login: {exc}"
            except (ConnectionClosed, OSError, HandshakeError, asyncio.TimeoutError) as exc:
                self.last_error = str(exc)
                LOGGER.warning("Verbindung fehlgeschlagen: %s", exc)
                reason = str(exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                self.last_error = str(exc)
                LOGGER.exception("Unerwarteter Session-Fehler")
                reason = str(exc)
            await self._handle_disconnect(reason)
            if self._shutting_down:
                break
            attempt += 1
            delay = self._backoff_delay(attempt, login_failed)
            LOGGER.info("Reconnect in %.2f s (Versuch %d)", delay, attempt)
            self.reconnects += 1
            await self._sleep(delay)

    def _backoff_delay(self, attempt: int, login_failed: bool) -> float:
        cfg = self.config.reconnect
        base = min(cfg.max_delay, cfg.initial_delay * (2 ** min(attempt, 16)))
        jitter = base * cfg.jitter * (self._jitter() * 2.0 - 1.0)
        delay = max(0.05, base + jitter)
        if login_failed:
            delay = max(delay, cfg.login_failure_delay)
        return delay

    async def connect_once(self) -> None:
        """Perform one connect + handshake.  Exposed for tests and tooling."""

        ma2 = self.config.ma2
        uri = f"ws://{ma2.host}:{ma2.port}{ma2.path}"
        await self._transport.connect(uri)

        message = await self._recv_json(self.config.ma2.login_timeout)
        while not self._is_server_ready(message):
            message = await self._recv_json(self.config.ma2.login_timeout)

        await self._send_raw(frames.session_request_frame(), "sessionRequest")

        message = await self._recv_json(self.config.ma2.login_timeout)
        while "session" not in message:
            message = await self._recv_json(self.config.ma2.login_timeout)
        session = message.get("session")
        if not isinstance(session, int) or session <= 0:
            raise HandshakeError(f"ungültige Session-ID in {message!r}")

        password = hashlib.md5(ma2.read_password().encode("utf-8")).hexdigest()
        await self._send_raw(
            frames.login_frame(ma2.username, password, session),
            "login",
            extra={"username": ma2.username},
        )

        message = await self._recv_json(self.config.ma2.login_timeout)
        while not self._is_login_response(message):
            message = await self._recv_json(self.config.ma2.login_timeout)
        result = message.get("result")
        if isinstance(result, dict):
            result = result.get("result")
        if result is not True:
            raise LoginError(message.get("error") or "ungültige Zugangsdaten")

        self._session = session
        self._authenticated = True
        self.last_error = None
        LOGGER.info("MA2-Session %d authentifiziert", session)
        await self._send_raw(frames.preset_types_frame("full", session), "encoderPage")
        self._keepalive_task = asyncio.create_task(
            self._keepalive_loop(session), name="ma2pi-keepalive"
        )

    @staticmethod
    def _is_server_ready(message: dict[str, Any]) -> bool:
        return message.get("status") == "server ready" or message.get("appType") == "gma2"

    @staticmethod
    def _is_login_response(message: dict[str, Any]) -> bool:
        return message.get("requestType") == "loginResponse" or "result" in message

    async def _read_loop(self) -> None:
        while not self._shutting_down:
            message = await self._recv_json(None)
            if self._page.update(message):
                self._log_page_if_changed()
            else:
                LOGGER.debug("rx message type=%s", frames.frame_type(message))

    def _log_page_if_changed(self) -> None:
        labels = tuple(self._page.label_for(slot) for slot in range(1, WINDOW + 1))
        signature = (self._page.bank, labels)
        if signature == self._page_signature:
            return
        self._page_signature = signature
        LOGGER.info("Encoder-Seite: Bank %d %s", self._page.bank, list(labels))

    async def _page_poll_loop(self, session: int) -> None:
        """Poll the encoder page so external selection changes are noticed."""

        interval = self.config.ma2.page_refresh_interval
        try:
            while not self._shutting_down and self._authenticated:
                await self._sleep(interval)
                if (
                    self._shutting_down
                    or not self._authenticated
                    or self._session != session
                ):
                    break
                await self._send_raw(
                    frames.preset_types_frame("full", session), "encoderPage"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning("Encoder-Seiten-Polling fehlgeschlagen: %s", exc)

    async def _recv_json(self, timeout: float | None) -> dict[str, Any]:
        try:
            if timeout is None:
                raw = await self._transport.recv()
            else:
                raw = await asyncio.wait_for(self._transport.recv(), timeout)
        except asyncio.TimeoutError:
            raise
        if raw is None:
            raise ConnectionClosed("Server hat die Verbindung geschlossen")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HandshakeError(f"ungültiges JSON: {raw[:120]!r}") from exc
        if not isinstance(value, dict):
            raise HandshakeError("JSON-Frame ist kein Objekt")
        return value

    async def _keepalive_loop(self, session: int) -> None:
        interval = self.config.ma2.keepalive_interval
        try:
            while not self._shutting_down and self._authenticated:
                await self._sleep(interval)
                if not self._authenticated or self._shutting_down:
                    break
                await self._send_raw(frames.keepalive_frame(session), "keepalive")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning("Keepalive fehlgeschlagen: %s", exc)
            await self._transport.close()

    async def _handle_disconnect(self, reason: str) -> None:
        was_connected = self._authenticated or self._session is not None
        self._authenticated = False
        self._session = None
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._keepalive_task
            self._keepalive_task = None
        if self._page_poll_task is not None:
            self._page_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._page_poll_task
            self._page_poll_task = None
        self._page_signature = None
        self._queue.clear()
        if was_connected:
            LOGGER.warning("Session beendet: %s", reason)
            for callback in list(self._connection_lost_callbacks):
                try:
                    callback()
                except Exception:
                    LOGGER.exception("Connection-Lost-Callback fehlgeschlagen")

    # -- sending ----------------------------------------------------------

    async def _sender_loop(self) -> None:
        while not self._stop_sender:
            try:
                action = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            if not self._authenticated:
                LOGGER.debug("verwerfe gepufferte Aktion nach Disconnect: %s", action)
                continue
            await self._limiter.acquire()
            try:
                await self._dispatch(action)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.warning("Senden fehlgeschlagen: %s", exc)
                self.last_error = str(exc)
                await self._transport.close()

    def warn_unverified_hardkeys(self) -> None:
        """Log all configured but unverified hardkeys once at startup."""

        if self.dry_run or self.config.ma2.hardkey_transport != "lua":
            return
        for name, entry in sorted(self.config.hardkeys.items()):
            if not entry.verified:
                LOGGER.warning(
                    "Hardkey %s (code %d) ist nicht verifiziert und wird nicht gesendet",
                    name,
                    entry.code,
                )

    def _hardkey_frame(
        self,
        keyname: str,
        pressed: bool,
        session: int,
        ma2: Any,
    ) -> dict[str, Any] | None:
        if ma2.hardkey_transport == "native":
            return frames.keyname_frame(
                keyname,
                pressed,
                session,
                ma2.hardkey_press_value,
                ma2.hardkey_release_value,
            )

        entry = self.config.hardkeys.get(keyname)
        if entry is None:
            LOGGER.error("Kein Keycode für Hardkey %s konfiguriert", keyname)
            return None
        if not entry.verified:
            LOGGER.warning(
                "Hardkey %s (code %d) ist nicht verifiziert; Frame verworfen",
                keyname,
                entry.code,
            )
            return None
        return frames.lua_hardkey_frame(entry.code, pressed, session)

    async def _dispatch(self, action: Action) -> None:
        assert self._session is not None
        session = self._session
        ma2 = self.config.ma2

        if isinstance(action, Press):
            frame = self._hardkey_frame(action.keyname, True, session, ma2)
            if frame is None:
                return
            kind = "hardkeyPress"
        elif isinstance(action, Release):
            frame = self._hardkey_frame(action.keyname, False, session, ma2)
            if frame is None:
                return
            kind = "hardkeyRelease"
        elif isinstance(action, Command):
            frame = frames.command_frame(action.text, session)
            kind = "command"
        elif isinstance(action, EncoderAttribute):
            frame = frames.encoder_attribute_frame(action.name, action.value, session)
            kind = "encoderAttribute"
        elif isinstance(action, EncoderSlot):
            if self._screen_mode:
                name = self.config.mapping.screen_encoders.get(action.slot)
                if name is None:
                    LOGGER.warning(
                        "Screen-Modus aktiv, aber kein screen_encoders.%d konfiguriert",
                        action.slot,
                    )
                    return
            else:
                name = self._page.name_for(action.slot)
            if name is None:
                LOGGER.debug(
                    "Encoder-Slot %d noch unbekannt, Delta verworfen", action.slot
                )
                return
            frame = frames.encoder_attribute_frame(name, action.delta, session)
            kind = "encoderAttribute"
        elif isinstance(action, ToggleScreenMode):
            if not self._screen_mode and not self.config.mapping.screen_encoders:
                LOGGER.warning(
                    "Screen-Modus ohne mapping.screen_encoders: Modus wechselt, "
                    "es werden aber keine Encoder-Frames gesendet"
                )
            self._screen_mode = not self._screen_mode
            LOGGER.info(
                "Encoder-Modus: %s",
                "Screen" if self._screen_mode else "Attribut",
            )
            if self._led is not None:
                self._led.apply_mode(self._screen_mode)
            return
        elif isinstance(action, ToggleFine):
            name = self._page.name_for(action.slot)
            if name is None:
                LOGGER.debug("Encoder-Slot %d noch unbekannt, Fine ignoriert", action.slot)
                return
            resolution = (self._fine.get(action.slot, 0) + 1) % 3
            self._fine[action.slot] = resolution
            frame = frames.encoder_resolution_frame(name, resolution, session)
            kind = "encoderResolution"
            LOGGER.info(
                "Encoder %d %s: %s",
                action.slot,
                name,
                RESOLUTION_NAMES[resolution],
            )
        else:  # pragma: no cover - exhaustive
            raise TypeError(f"unbekannte Aktion {action!r}")

        await self._send_raw(frame, kind)
        if kind in ("hardkeyPress", "hardkeyRelease"):
            self._schedule_page_refresh()

    def _schedule_page_refresh(self) -> None:
        """Re-read the encoder page after a selection change (debounced)."""

        if self.dry_run or self._shutting_down or not self._authenticated:
            return
        if self._page_task is not None and not self._page_task.done():
            return
        self._page_task = asyncio.create_task(
            self._refresh_page(), name="ma2pi-encoder-page"
        )

    async def _refresh_page(self) -> None:
        await asyncio.sleep(0.4)
        if not self._authenticated or self._shutting_down or self._session is None:
            return
        with contextlib.suppress(Exception):
            await self._send_raw(
                frames.preset_types_frame("full", self._session), "encoderPage"
            )

    async def _send_raw(
        self,
        frame: dict[str, Any],
        kind: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        await self._transport.send(frame)
        session = frame.get("session")
        fields = dict(extra or {})
        if "command" in frame:
            fields["command"] = frame["command"]
        if "keyname" in frame:
            fields["keyname"] = frame["keyname"]
            fields["value"] = frame["value"]
        if "name" in frame:
            fields["name"] = frame["name"]
            if "value" in frame:
                fields["value"] = frame["value"]
            if "resolution" in frame:
                fields["resolution"] = frame["resolution"]
        log_frame(
            LOGGER,
            "tx",
            kind,
            session if isinstance(session, int) else None,
            **fields,
        )
        self.frames_sent += 1
        self.by_type[kind] += 1
        self.last_frame_types.append(kind)
        self.sent_frames.append(frame)
        if len(self.sent_frames) > 1000:
            del self.sent_frames[:500]

    async def _backpressure_loop(self) -> None:
        try:
            while not self._stop_sender:
                await self._sleep(0.25)
                state = self._guard.observe(
                    self._clock(),
                    self._queue.control_depth,
                    self._transport.write_buffer_size(),
                )
                if state == "engaged":
                    self._limiter.multiplier = 0.5
                    LOGGER.warning(
                        "Backpressure aktiv: Rate auf %.1f/s halbiert (Queue %d)",
                        self._limiter.effective_rate,
                        self._queue.control_depth,
                    )
                elif state == "released":
                    self._limiter.multiplier = 1.0
                    LOGGER.info(
                        "Backpressure beendet: Rate wieder %.1f/s",
                        self._limiter.effective_rate,
                    )
        except asyncio.CancelledError:
            raise
