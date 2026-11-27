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

from . import frames, hardkeys
from .screen_helper import ScreenHelper
from .actions import (
    Action,
    Command,
    EncoderAction,
    EncoderAttribute,
    ToggleScreenMode,
    EncoderSlot,
    PlaybackButton,
    PlaybackFader,
    PlaybacksRequest,
    Press,
    Release,
    EncoderPress,
    EncoderResolution,
    encoder_key,
    is_encoder,
    merge_encoder,
)
from .config import AppConfig, Ma2Settings
from .encoder_page import EncoderPage
from .logging_setup import log_frame

LOGGER = logging.getLogger("ma2pi.client")

#: Resolution values the onPC accepts on an ``encoder`` request.


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
        import socket as _socket
        import websockets

        if self._ws is not None:
            await self.close()
        # grandMA2 onPC's embedded WebSocket server does not answer RFC 6455
        # PING control frames (verified on hardware: ping_interval=10 drops the
        # session after 20 s with 1011 keepalive ping timeout).  Keep
        # ping_interval=None and enable OS-level TCP keepalive instead.
        self._ws = await websockets.connect(
            uri,
            open_timeout=10,
            ping_interval=None,
            close_timeout=2.0,
            max_size=2 * 1024 * 1024,
        )
        transport = getattr(self._ws, "transport", None)
        sock = transport.get_extra_info("socket") if transport is not None else None
        if sock is not None:
            with contextlib.suppress(OSError):
                sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_KEEPALIVE, 1)

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


def ma2_uri(ma2: Ma2Settings) -> str:
    """Return the WebSocket URI for a MA2 target."""

    return f"ws://{ma2.host}:{ma2.port}{ma2.path}"


async def _read_json(transport: Transport, timeout: float | None) -> dict[str, Any]:
    try:
        if timeout is None:
            raw = await transport.recv()
        else:
            raw = await asyncio.wait_for(transport.recv(), timeout)
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


def _server_ready(message: dict[str, Any]) -> bool:
    return message.get("status") == "server ready" or message.get("appType") == "gma2"


def _login_response(message: dict[str, Any]) -> bool:
    return message.get("requestType") == "loginResponse" or "result" in message


async def authenticate(
    transport: Transport,
    ma2: Ma2Settings,
    *,
    password: str | None = None,
) -> int:
    """Run the session/login handshake and return the session id.

    A password passed explicitly is used instead of ``ma2.read_password()`` so
    the configuration UI can test new credentials before they are stored.  The
    password never appears in an error or log message.
    """

    await transport.connect(ma2_uri(ma2))
    try:
        async with asyncio.timeout(ma2.login_timeout):
            message = await _read_json(transport, ma2.login_timeout)
            while not _server_ready(message):
                message = await _read_json(transport, ma2.login_timeout)

            await transport.send(frames.session_request_frame())

            message = await _read_json(transport, ma2.login_timeout)
            while "session" not in message:
                message = await _read_json(transport, ma2.login_timeout)
            session = message.get("session")
            if not isinstance(session, int) or session <= 0:
                raise HandshakeError(f"ungültige Session-ID in {message!r}")

            secret = password if password is not None else ma2.read_password()
            digest = hashlib.md5(secret.encode("utf-8")).hexdigest()
            await transport.send(frames.login_frame(ma2.username, digest, session))

            message = await _read_json(transport, ma2.login_timeout)
            while not _login_response(message):
                message = await _read_json(transport, ma2.login_timeout)
            result = message.get("result")
            if isinstance(result, dict):
                result = result.get("result")
            if result is not True:
                raise LoginError(message.get("error") or "ungültige Zugangsdaten")

            return session
    except BaseException:
        with contextlib.suppress(Exception):
            await transport.close()
        raise


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    """Result of a connection test; never carries the password."""

    session: int
    username: str
    target: str
    reused: bool = False


def _secret(ma2: Ma2Settings) -> str | None:
    try:
        return ma2.read_password()
    except Exception:
        return None


async def check_connection(
    config: AppConfig,
    *,
    password: str | None = None,
    active: "Ma2Client | None" = None,
    transport_factory: Callable[[], Transport] | None = None,
) -> ConnectionCheck:
    """Test credentials without disturbing a running session.

    When ``active`` is already authenticated with the same target, user and
    password, its session is reused and no second connection is opened.  For a
    different target or changed credentials a short-lived session is opened,
    logged in and closed again with ``closeConnection``.
    """

    ma2 = config.ma2
    target = ma2_uri(ma2)
    secret = password if password is not None else ma2.read_password()

    if active is not None and active.authenticated and active.session is not None:
        current = active.config.ma2
        if ma2_uri(current) == target and current.username == ma2.username:
            if _secret(current) == secret:
                return ConnectionCheck(
                    session=active.session,
                    username=ma2.username,
                    target=target,
                    reused=True,
                )

    transport = (transport_factory or WebSocketTransport)()
    try:
        session = await authenticate(transport, ma2, password=secret)
        with contextlib.suppress(Exception):
            await transport.send(frames.close_frame(session))
        return ConnectionCheck(session=session, username=ma2.username, target=target)
    finally:
        with contextlib.suppress(Exception):
            await transport.close()



class SendQueue:
    """One queue, four priorities; encoders, faders and requests coalesce."""

    def __init__(self) -> None:
        self._control: deque[Action] = deque()
        self._encoder: OrderedDict[tuple[str, str | int], EncoderAction] = OrderedDict()
        self._playback: OrderedDict[tuple[int | str, int], PlaybackFader] = OrderedDict()
        self._requests: OrderedDict[tuple[int | str, int, int, int], PlaybacksRequest] = OrderedDict()
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
        elif isinstance(action, PlaybackFader):
            # Absolute values: only the latest value per executor matters.
            self._playback[(action.page, action.executor)] = action
        elif isinstance(action, PlaybacksRequest):
            # Background polling sits below live controls and coalesces per block.
            self._requests[(action.page, action.start, action.count, action.items_type)] = action
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
            if self._playback:
                _, action = self._playback.popitem(last=False)
                return action
            if self._requests:
                _, action = self._requests.popitem(last=False)
                return action
            self._ready.clear()
            await self._ready.wait()

    def clear(self) -> None:
        self._control.clear()
        self._encoder.clear()
        self._playback.clear()
        self._requests.clear()

    @property
    def control_depth(self) -> int:
        return len(self._control)

    @property
    def total_depth(self) -> int:
        return (
            len(self._control)
            + len(self._encoder)
            + len(self._playback)
            + len(self._requests)
        )

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
        self._playback_responses: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=16
        )
        self._page = EncoderPage()
        self._page_updated = asyncio.Event()
        self._page_task: asyncio.Task[None] | None = None
        self._screen_mode = False
        self._ma_held = False
        self._cmdline_text = ""
        self._led = None
        self._screen_helper = ScreenHelper(config.screen_helper)
        self._rest: dict[tuple[str, int], float] = {}
        self.frames_sent = 0
        self.by_type: Counter[str] = Counter()
        self.last_frame_types: deque[str] = deque(maxlen=50)
        self.sent_frames: list[dict[str, Any]] = []
        self.on_frame: Callable[[str, dict[str, Any]], None] | None = None
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
    def screen_encoder_active(self) -> bool:
        """True while encoders act as screen encoders (toggle or held MA)."""

        return self._screen_mode or self._ma_held

    @property
    def connected(self) -> bool:
        return self._authenticated

    def add_connection_lost_callback(self, callback: Callable[[], None]) -> None:
        self._connection_lost_callbacks.append(callback)

    @property
    def playback_responses(self) -> "asyncio.Queue[dict[str, Any]]":
        """Playback snapshots pushed by the console, in arrival order."""

        return self._playback_responses

    # -- action entry points ---------------------------------------------

    def press(self, keyname: str, hold: bool = False) -> None:
        self._submit(Press(keyname, hold))

    def release(self, keyname: str) -> None:
        self._submit(Release(keyname))

    def command(self, text: str) -> None:
        self._submit(Command(text))

    def encoder_slot(self, slot: int, delta: float, screen: bool = False) -> None:
        self._submit(EncoderSlot(slot, delta, screen=screen))

    def encoder_attribute(self, name: str, value: float) -> None:
        self._submit(EncoderAttribute(name, value))

    def toggle_screen_mode(self) -> None:
        self._submit(ToggleScreenMode())

    def set_led(self, led) -> None:
        """Attach an LED output; it follows the encoder mode."""

        self._led = led

    def set_screen_modifier(self, held: bool) -> None:
        """Follow the engine's momentary screen-encoder modifier (MA)."""

        if held == self._ma_held:
            return
        self._ma_held = held
        LOGGER.info("Screen-Encoder-Modifier %s", "gehalten" if held else "losgelassen")
        self._refresh_mode_led()

    def _refresh_mode_led(self) -> None:
        """Show the effective encoder mode on the ASL LED."""

        if self._led is None:
            LOGGER.debug("Modus-LED: kein LED-Ausgang verbunden")
            return
        try:
            self._led.set_mode_color(self.screen_encoder_active)
        except Exception:
            LOGGER.exception("Modus-LED konnte nicht gesetzt werden")

    def encoder_press(self, slot: int, pressed: bool, screen: bool = False) -> None:
        self._submit(EncoderPress(slot, pressed, screen=screen))

    def encoder_resolution(self, slot: int, screen: bool = False) -> None:
        self._submit(EncoderResolution(slot, screen=screen))

    def playback_button(
        self, page: int, executor: int, button: int, pressed: bool
    ) -> None:
        self._submit(
            PlaybackButton(page, executor, button, pressed, released=not pressed)
        )

    def playback_fader(self, page: int, executor: int, value: float) -> None:
        self._submit(PlaybackFader(page, executor, value))

    def request_playbacks(
        self,
        page: int | str,
        start: int,
        count: int,
        items_type: int,
        view: int,
    ) -> None:
        """Ask for the executor states of one page block."""

        self._submit(PlaybacksRequest(page, start, count, items_type, view))

    def screen_shortcut(self, screen: int) -> None:
        """Select an onPC screen via the PC-keyboard helper (not the WebSocket)."""

        if self.dry_run:
            LOGGER.info("dry-run: Screen-Shortcut %d", screen)
            return
        self._screen_helper.send(screen)

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
        drain_budget = max(0.0, min(timeout, 5.0) * 0.8)
        deadline = self._clock() + drain_budget
        while self._queue.total_depth and self._authenticated and self._clock() < deadline:
            await self._sleep(0.01)
        if self._authenticated:
            session = self._session or 0
            with contextlib.suppress(Exception):
                await asyncio.wait_for(
                    self._send_raw(frames.close_frame(session), "closeConnection"),
                    timeout=max(0.1, min(timeout * 0.2, 1.0)),
                )
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                self._transport.close(),
                timeout=max(0.1, min(timeout, 2.0)),
            )
        self._authenticated = False
        self._stop_sender = True
        for task in (
            self._keepalive_task,
            self._page_task,
            self._backpressure_task,
            self._session_task,
            self._sender_task,
        ):
            if task is not None and not task.done():
                task.cancel()
        for task in (
            self._keepalive_task,
            self._page_task,
            self._backpressure_task,
            self._session_task,
            self._sender_task,
        ):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._queue.clear()
        self._screen_helper.close()

    # -- session loop -----------------------------------------------------

    def apply_config(self, config: AppConfig) -> None:
        """Use ``config`` for subsequent dispatch and reconnects."""

        self.config = config
        self._limiter.rate = float(config.rate_limit.messages_per_second)
        self._limiter.burst = float(config.rate_limit.burst)
        self._screen_helper.close()
        self._screen_helper = ScreenHelper(config.screen_helper)

    async def reconnect(self) -> None:
        """Close the current session so the loop reconnects with the new config.

        The running session loop notices the closed transport and performs the
        normal handshake again, now using :attr:`config`.
        """

        if self.dry_run:
            return
        if self._authenticated and self._session is not None:
            with contextlib.suppress(Exception):
                await self._send_raw(frames.close_frame(self._session), "closeConnection")
        with contextlib.suppress(Exception):
            await self._transport.close()

    async def _session_loop(self) -> None:
        attempt = 0
        while not self._shutting_down:
            login_failed = False
            try:
                await self.connect_once()
                attempt = 0
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

        session = await authenticate(self._transport, self.config.ma2)

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
        return _server_ready(message)

    @staticmethod
    def _is_login_response(message: dict[str, Any]) -> bool:
        return _login_response(message)

    async def _read_loop(self) -> None:
        while not self._shutting_down:
            message = await self._recv_json(None)
            if message.get("responseType") == "playbacks":
                self._deliver_playbacks(message)
                continue
            text = message.get("text")
            if isinstance(text, str):
                # The console echoes the session's command line after every key.
                self._cmdline_text = text
            if self._page.update(message):
                self._page_updated.set()
            else:
                LOGGER.debug("rx message type=%s", frames.frame_type(message))

    def _deliver_playbacks(self, message: dict[str, Any]) -> None:
        """Hand a playback snapshot to the feedback task, dropping stale ones."""

        LOGGER.debug("rx playbacks: %s", message)
        try:
            self._playback_responses.put_nowait(message)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self._playback_responses.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self._playback_responses.put_nowait(message)
            LOGGER.debug("Playback-Antwort verworfen: Warteschlange voll")

    async def _recv_json(self, timeout: float | None) -> dict[str, Any]:
        return await _read_json(self._transport, timeout)

    async def _keepalive_loop(self, session: int) -> None:
        try:
            while not self._shutting_down and self._authenticated:
                interval = self.config.ma2.keepalive_interval
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
        for attr in ("_keepalive_task", "_page_task"):
            task = getattr(self, attr, None)
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
                setattr(self, attr, None)
        if was_connected:
            with contextlib.suppress(Exception):
                await self._transport.close()
        self._page = EncoderPage()
        self._page_updated.clear()
        self._cmdline_text = ""
        self._rest.clear()
        self._queue.clear()
        while True:
            try:
                self._playback_responses.get_nowait()
            except asyncio.QueueEmpty:
                break
        if was_connected:
            LOGGER.warning("Session beendet: %s", reason)
            if self._ma_held:
                self._ma_held = False
                self._refresh_mode_led()
            if self._led is not None:
                with contextlib.suppress(Exception):
                    self._led.set_nipple(False)
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
        hold: bool = False,
    ) -> dict[str, Any] | None:
        if ma2.hardkey_transport == "native":
            if keyname not in hardkeys.WEB_REMOTE_KEYNAMES:
                LOGGER.error(
                    "Hardkey %s hat keinen Web-Remote-Keyname; native Transport nicht möglich",
                    keyname,
                )
                return None
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
        return frames.lua_hardkey_frame(entry.code, pressed, session, hold)

    def _encoder_index(self, slot: int, *, screen: bool = False) -> int | None:
        """Resolve the hardware encoder index (number - 1) a slot addresses.

        Attribute mode uses the four attribute encoders (0-3) and the onPC
        routes them to the current feature.  Screen mode, or ``screen`` forced
        for one action (MA held), uses the configured screen encoder 5-10.
        """

        if screen or self._screen_mode:
            number = self.config.mapping.screen_encoders.get(slot)
            if number is None:
                LOGGER.warning(
                    "Screen-Modus aktiv, aber kein screen_encoders.%d konfiguriert",
                    slot,
                )
                return None
            return number - 1
        return slot - 1

    async def _dispatch(self, action: Action) -> None:
        assert self._session is not None
        session = self._session
        ma2 = self.config.ma2

        if isinstance(action, Press):
            frame = self._hardkey_frame(action.keyname, True, session, ma2, action.hold)
            if frame is None:
                return
            kind = "hardkeyPress"
        elif isinstance(action, Release):
            frame = self._hardkey_frame(action.keyname, False, session, ma2, False)
            if frame is None:
                return
            kind = "hardkeyRelease"
        elif isinstance(action, Command):
            frame = frames.command_frame(action.text, session)
            kind = "command"
        elif isinstance(action, PlaybackButton):
            frame = frames.playbacks_user_input_button(
                action.page,
                action.executor,
                action.button,
                action.pressed,
                action.released,
                session,
                cmdline=self._cmdline_text,
            )
            kind = "playbackButton"
        elif isinstance(action, PlaybackFader):
            frame = frames.playbacks_user_input_fader(
                action.page,
                action.executor,
                max(0.0, min(1.0, action.value)),
                session,
            )
            kind = "playbackFader"
        elif isinstance(action, PlaybacksRequest):
            frame = frames.playbacks_request(
                action.start,
                action.count,
                action.page,
                action.items_type,
                action.view,
                session,
            )
            kind = "playbacksRequest"
        elif isinstance(action, EncoderAttribute):
            frame = frames.encoder_attribute_frame(action.name, action.value, session)
            kind = "encoderAttribute"
        elif isinstance(action, EncoderSlot):
            index = self._encoder_index(action.slot, screen=action.screen)
            if index is None:
                return
            key = ("screen" if action.screen or self._screen_mode else "slot", action.slot)
            total = self._rest.get(key, 0.0) + action.delta
            steps = int(total)
            self._rest[key] = total - steps
            if steps == 0:
                return
            frame = frames.lua_encoder_frame(index, steps, session)
            kind = "encoderCanbus"
        elif isinstance(action, EncoderResolution):
            if action.screen or self._screen_mode:
                LOGGER.warning(
                    "Screen-Encoder haben keine Auflösung; Slot %d wird nicht umgeschaltet",
                    action.slot,
                )
                return
            if (
                not self.dry_run
                and self._authenticated
                and self._session_task is not None
                and not self._session_task.done()
            ):
                self._page_updated.clear()
                with contextlib.suppress(Exception):
                    await self._send_raw(
                        frames.preset_types_frame("full", session), "encoderPage"
                    )
                    await asyncio.wait_for(self._page_updated.wait(), timeout=0.2)
            name = self._page.name_for(action.slot)
            if name is None:
                LOGGER.warning(
                    "Encoder-Slot %d: kein Attribut bekannt, Auflösung nicht umgeschaltet",
                    action.slot,
                )
                return
            level = (self._page.resolution_for(action.slot) + 1) % 3
            frame = frames.encoder_resolution_frame(name, level, session)
            kind = "encoderResolution"
            LOGGER.info(
                "Encoder-Slot %d %s Auflösung: %s",
                action.slot,
                name,
                ("Normal", "Fine", "Ultra")[level],
            )
        elif isinstance(action, EncoderPress):
            index = self._encoder_index(action.slot, screen=action.screen)
            if index is None:
                return
            frame = frames.lua_encoder_press_frame(index, action.pressed, session)
            kind = "encoderPress"
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
                self._led.set_mode_color(self.screen_encoder_active)
            return
        else:  # pragma: no cover - exhaustive
            raise TypeError(f"unbekannte Aktion {action!r}")

        await self._send_raw(frame, kind)
        if kind == "encoderResolution":
            self._schedule_page_refresh()
        if kind in ("hardkeyPress", "hardkeyRelease") and self._led is not None:
            if isinstance(action, (Press, Release)) and action.keyname == hardkeys.resolve("NIPPLE"):
                with contextlib.suppress(Exception):
                    self._led.set_nipple(kind == "hardkeyPress")

    def _schedule_page_refresh(self) -> None:
        """Re-read the attribute model once, shortly after a resolution change."""

        if self.dry_run or self._shutting_down or not self._authenticated:
            return
        if self._page_task is not None and not self._page_task.done():
            return
        self._page_task = asyncio.create_task(
            self._refresh_page(), name="ma2pi-encoder-page"
        )

    async def _refresh_page(self) -> None:
        await asyncio.sleep(0.3)
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
        if frame.get("requestType") == "playbacks_userInput":
            # Which executor was really addressed; the covered-slot redirect
            # and the bank offset are only visible here.
            fields["execIndex"] = frame.get("execIndex")
            fields["pageIndex"] = frame.get("pageIndex")
            fields["buttonId"] = frame.get("buttonId")
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
        if self.on_frame is not None:
            try:
                self.on_frame(kind, frame)
            except Exception:  # pragma: no cover - a hook must not break sending
                LOGGER.debug("Frame-Hook fehlgeschlagen", exc_info=True)

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
