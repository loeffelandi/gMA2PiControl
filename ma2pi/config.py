"""Strict TOML configuration loading and validation.

Every unknown key is an error.  References between devices, profiles and the
mapping are checked before the daemon starts, so an invalid file can never
produce frames.
"""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import hardkeys
from .acceleration import ValueAccelerationSettings
from .led_output import LedSettings, parse_color
from .feedback import PALETTE, build_feedback_targets

DEFAULT_CONFIG_PATHS = (
    Path("/var/lib/ma2pi/config.toml"),
    Path("/etc/ma2pi/config.toml"),
    Path("config.toml"),
)


class ConfigError(ValueError):
    """A schema or reference error with a TOML path."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.detail = message
        super().__init__(f"{path}: {message}" if path else message)


@dataclass(frozen=True, slots=True)
class Ma2Settings:
    host: str
    username: str
    port: int = 80
    path: str = "/?ma=1"
    password_file: str | None = None
    password_env: str | None = None
    keepalive_interval: float = 5.0
    login_timeout: float = 10.0
    hardkey_transport: str = "lua"
    hardkey_hold_threshold: float = 0.5
    hardkey_press_value: float = 1.0
    hardkey_release_value: float = 0.0
    page_refresh_interval: float = 1.0

    def read_password(self) -> str:
        if self.password_file:
            try:
                return Path(self.password_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise ConfigError(
                    "ma2.password_file",
                    f"Passwortdatei {self.password_file!r} ist nicht lesbar: {exc}",
                ) from exc
        if self.password_env:
            value = os.environ.get(self.password_env)
            if not value:
                raise ConfigError(
                    "ma2.password_env",
                    f"Umgebungsvariable {self.password_env!r} ist nicht gesetzt",
                )
            return value
        raise ConfigError("ma2", "keine Passwortquelle konfiguriert")


@dataclass(frozen=True, slots=True)
class ReconnectSettings:
    initial_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.2
    login_failure_delay: float = 10.0


@dataclass(frozen=True, slots=True)
class RateLimitSettings:
    messages_per_second: int = 25
    burst: int = 10
    encoder_base_interval: float = 0.025
    encoder_stream_penalty: float = 0.0024
    encoder_idle_base: float = 0.040
    encoder_idle_penalty: float = 0.0022
    max_pending_delta: int = 1000


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: str = "INFO"


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Settings for the embedded configuration UI.

    ``bind``/``port`` changes only take effect after a service restart; the
    running server keeps its listener.  ``pin`` protects the API and UI with a
    simple numeric code; it is on by default.
    """

    bind: str = "0.0.0.0"
    port: int = 8080
    pin_enabled: bool = False
    pin: str = ""


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    name: str
    profile: str
    vendor_id: int
    product_id: int = 0
    name_contains: str | None = None
    backend: str = "evdev"


@dataclass(frozen=True, slots=True)
class EncoderProfile:
    id: int
    control: str
    detents_per_revolution: int = 24
    direction: int = 1
    threshold: float = 0.0


@dataclass(frozen=True, slots=True)
class MidiEncoderProfile:
    id: int
    note: int
    cw_velocity: int = 127
    ccw_velocity: int = 1
    direction: int = 1


@dataclass(frozen=True, slots=True)
class MidiValueProfile:
    control: str
    note: int
    kind: str = "fader"


@dataclass(frozen=True, slots=True)
class ControlProfile:
    """Physical control declared independently of its learned note."""

    id: str
    kind: str = "button"
    label: str | None = None
    encoder_id: int | None = None


@dataclass(frozen=True, slots=True)
class BankProfile:
    """One device bank: its MIDI channel and note-to-control bindings."""

    number: int
    channel: int
    notes: Mapping[int, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LayoutCell:
    label: str = ""
    control: str | None = None
    col_span: int = 1
    row_span: int = 1
    color: str | None = None
    row: int | None = None
    col: int | None = None


@dataclass(frozen=True, slots=True)
class LayoutRow:
    cells: tuple[LayoutCell, ...] = ()


@dataclass(frozen=True, slots=True)
class DeviceLayout:
    profile: str
    columns: int
    rows: tuple[LayoutRow, ...] = ()
    name: str = ""


@dataclass(frozen=True, slots=True)
class LedFeedbackProfile:
    """How a profile's controls report executor state as LED frames.

    ``notes`` restricts feedback to notes that actually have an LED; ``None``
    means every button note of the profile is LED-capable.  ``enabled`` turns
    the output off for this profile only, and ``frame_interval_ms`` is the
    minimum gap between two LED frames sent to one device.  ``bright_level``,
    ``dark_level`` and ``colors`` (palette name, colour index) only apply to
    ``asl-mk2``.
    """

    protocol: str = "midicraft-v2"
    notes: tuple[int, ...] | None = None
    enabled: bool = True
    frame_interval_ms: int = 20
    bright_level: int = 127
    dark_level: int = 25
    colors: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    keys: Mapping[str, str] = field(default_factory=dict)
    encoders: tuple[EncoderProfile, ...] = ()
    notes: Mapping[int, str] = field(default_factory=dict)
    midi_encoders: tuple[MidiEncoderProfile, ...] = ()
    midi_values: tuple[MidiValueProfile, ...] = ()
    controls: tuple[ControlProfile, ...] = ()
    banks: tuple[BankProfile, ...] = ()
    led_feedback: LedFeedbackProfile | None = None

    @property
    def control_kinds(self) -> dict[str, str]:
        """Logical control name to semantic kind, independent of bindings."""

        kinds: dict[str, str] = {}
        for control in self.controls:
            kinds[control.id] = control.kind
        for control in self.keys.values():
            kinds.setdefault(control, "button")
        for control in self.notes.values():
            kinds.setdefault(control, "button")
        for value in self.midi_values:
            kinds.setdefault(value.control, value.kind)
        for enc in self.midi_encoders:
            kinds.setdefault(f"encoder.{enc.id}", "relative-encoder")
        for enc in self.encoders:
            kinds.setdefault(f"encoder.{enc.id}", "relative-encoder")
        return kinds

    @property
    def relative_encoder_ids(self) -> dict[str, int]:
        """Map control name -> integer encoder id for relative encoders."""

        result: dict[str, int] = {}
        for enc in self.encoders:
            result[f"encoder.{enc.id}"] = enc.id
        for enc in self.midi_encoders:
            result[f"encoder.{enc.id}"] = enc.id
        for ctrl in self.controls:
            if ctrl.kind == "relative-encoder" and ctrl.encoder_id is not None:
                result[ctrl.id] = ctrl.encoder_id
        return result

    @property
    def control_names(self) -> set[str]:
        return set(self.control_kinds)

    def bank(self, number: int) -> BankProfile | None:
        return next((bank for bank in self.banks if bank.number == number), None)

    def bank_for_channel(self, channel: int) -> BankProfile | None:
        return next((bank for bank in self.banks if bank.channel == channel), None)


@dataclass(frozen=True, slots=True)
class ModifierMapping:
    hardkey: str | None = None
    local: bool = False


@dataclass(frozen=True, slots=True)
class HardkeyCode:
    """Canbus keycode for one hardkey and its verification state."""

    code: int
    verified: bool = False


@dataclass(frozen=True, slots=True)
class KeyMapping:
    hardkey: str | None = None
    command: str | None = None
    screen_mode: bool = False
    encoder_press: int | None = None
    screen: int | None = None


@dataclass(frozen=True, slots=True)
class EncoderMapping:
    id: int
    slot: int | None = None
    attribute: str | None = None


@dataclass(frozen=True, slots=True)
class PlaybackMapping:
    page: int | str
    executor: int
    kind: str = "button"
    button: int = 1
    accelerated: bool = False
    #: ``None`` picks the default: ``midi`` for buttons with an enabled
    #: ``[midi_remote]``, otherwise ``web``.
    transport: str | None = None


@dataclass(frozen=True, slots=True)
class PlaybackOverride:
    """Partial playback target used by a bank layer."""

    page: int | str | None = None
    executor: int | None = None
    kind: str | None = None
    button: int | None = None
    accelerated: bool | None = None
    transport: str | None = None


@dataclass(frozen=True, slots=True)
class AccelerationSettings:
    curve: str = "none"
    window: float = 0.10
    max_multiplier: float = 4.0


@dataclass(frozen=True, slots=True)
class ResolutionSet:
    normal: float = 1.0
    fine: float = 0.1
    ultra: float = 0.01


@dataclass(frozen=True, slots=True)
class ResolutionSettings:
    wheel: ResolutionSet = field(default_factory=ResolutionSet)
    attribute: ResolutionSet = field(default_factory=ResolutionSet)
    fine_modifier: str = "fine"
    ultra_modifier: str = "ultra"
    cycle_modifier: str = ""


@dataclass(frozen=True, slots=True)
class DeviceBankMapping:
    """Bank specific overrides for keys, encoders and playbacks."""

    ma_page: int | None = None
    keys: Mapping[str, KeyMapping] = field(default_factory=dict)
    encoders: Mapping[int, EncoderMapping] = field(default_factory=dict)
    playbacks: Mapping[str, PlaybackOverride] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeviceBankSettings:
    bank_size: int | None = None
    banks: Mapping[int, DeviceBankMapping] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MappingSettings:
    modifiers: Mapping[str, ModifierMapping] = field(default_factory=dict)
    keys: Mapping[str, KeyMapping] = field(default_factory=dict)
    encoders: tuple[EncoderMapping, ...] = ()
    screen_encoders: Mapping[int, int] = field(default_factory=dict)
    playbacks: Mapping[str, PlaybackMapping] = field(default_factory=dict)
    device_banks: Mapping[str, DeviceBankSettings] = field(default_factory=dict)
    acceleration: AccelerationSettings = field(default_factory=AccelerationSettings)
    value_acceleration: ValueAccelerationSettings = field(
        default_factory=ValueAccelerationSettings
    )
    resolution: ResolutionSettings = field(default_factory=ResolutionSettings)
    #: ``auto`` reads wide (combined) executors from the console and resolves
    #: covered slots; ``off`` sends every target unchanged.
    combined_executors: str = "auto"
    #: Poll gap for the executor topology while LED feedback is off.
    topology_interval_ms: int = 2000


@dataclass(frozen=True, slots=True)
class ScreenHelperSettings:
    """UDP-Helper auf dem onPC-PC, der Screen-Shortcuts als Keystrokes sendet."""

    enabled: bool = False
    host: str = "192.168.0.10"
    port: int = 5010


@dataclass(frozen=True, slots=True)
class MidiRemoteSettings:
    """Executor buttons as MIDI notes over RTP-MIDI to MA MIDI remotes."""

    enabled: bool = False
    #: ``None`` uses the host of the MA connection.
    host: str | None = None
    port: int = 5004
    channels: tuple[int, ...] = (16,)
    sync: str = "auto"
    telnet_port: int = 30000


@dataclass(frozen=True, slots=True)
class FeedbackSettings:
    """Globale Einstellungen für das Executor-Feedback an MIDI-LEDs."""

    enabled: bool = False
    interval_ms: int = 250
    off_state: str = "dark"
    fallback_color: str = "white"


@dataclass(frozen=True, slots=True)
class AppConfig:
    schema_version: int
    ma2: Ma2Settings
    devices: Mapping[str, DeviceConfig]
    profiles: Mapping[str, ProfileConfig]
    mapping: MappingSettings
    hardkeys: Mapping[str, HardkeyCode] = field(default_factory=dict)
    layouts: Mapping[str, DeviceLayout] = field(default_factory=dict)
    reconnect: ReconnectSettings = field(default_factory=ReconnectSettings)
    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    web: WebSettings = field(default_factory=WebSettings)
    led: LedSettings = field(default_factory=LedSettings)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings)
    screen_helper: ScreenHelperSettings = field(default_factory=ScreenHelperSettings)
    midi_remote: MidiRemoteSettings = field(default_factory=MidiRemoteSettings)
    source_path: str = ""

    def profile_for_device(self, name: str) -> ProfileConfig:
        return self.profiles[self.devices[name].profile]

    def layout_for_device(self, name: str) -> DeviceLayout | None:
        device = self.devices.get(name)
        if device is None:
            return None
        return self.layouts.get(device.profile)

    @property
    def mapped_controls(self) -> set[str]:
        controls: set[str] = set()
        for profile in self.profiles.values():
            controls.update(profile.control_names)
        return controls

    def logical_to_hardkey(self, control: str) -> str | None:
        entry = self.mapping.keys.get(control)
        if entry is None or entry.hardkey is None:
            return None
        return hardkeys.resolve(entry.hardkey)


def _table(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(path, "muss eine Tabelle sein")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(
            path,
            f"unbekannte Schlüssel: {', '.join(unknown)} (erlaubt: {', '.join(sorted(allowed))})",
        )


def _require(value: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in value:
        raise ConfigError(f"{path}.{key}" if path else key, "fehlt")
    return value[key]


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigError(path, "muss eine Zeichenkette sein")
    if not allow_empty and not value.strip():
        raise ConfigError(path, "darf nicht leer sein")
    return value


def _int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(path, "muss eine ganze Zahl sein")
    return value


def _float(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(path, "muss eine Zahl sein")
    result = float(value)
    if not math.isfinite(result):
        raise ConfigError(path, "muss eine endliche Zahl sein")
    return result


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(path, "muss true oder false sein")
    return value


def _choice(value: Any, path: str, choices: set[str]) -> str:
    text = _string(value, path)
    if text not in choices:
        raise ConfigError(path, f"muss einer von {', '.join(sorted(choices))} sein")
    return text


def _midi_note(value: Any, path: str) -> int:
    try:
        note = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(path, "muss eine MIDI-Notennummer zwischen 0 und 127 sein") from exc
    if not 0 <= note <= 127:
        raise ConfigError(path, "muss zwischen 0 und 127 liegen")
    return note


def _midi_velocity(value: Any, path: str) -> int:
    try:
        velocity = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(path, "muss eine MIDI-Velocity zwischen 1 und 127 sein") from exc
    if not 1 <= velocity <= 127:
        raise ConfigError(path, "muss zwischen 1 und 127 liegen")
    return velocity


def _parse_ma2(raw: Any) -> Ma2Settings:
    path = "ma2"
    data = _table(raw, path)
    allowed = {
        "host",
        "port",
        "path",
        "username",
        "password_file",
        "password_env",
        "keepalive_interval",
        "login_timeout",
        "hardkey_transport",
        "hardkey_hold_threshold",
        "hardkey_press_value",
        "hardkey_release_value",
        "page_refresh_interval",
    }
    _reject_unknown(data, allowed, path)

    host = _string(_require(data, "host", path), f"{path}.host")
    username = _string(_require(data, "username", path), f"{path}.username")
    password_file = data.get("password_file")
    password_env = data.get("password_env")
    if password_file is not None:
        password_file = _string(password_file, f"{path}.password_file")
    if password_env is not None:
        password_env = _string(password_env, f"{path}.password_env")
    if (password_file is None) == (password_env is None):
        raise ConfigError(
            path,
            "genau eine Passwortquelle angeben: password_file oder password_env",
        )

    port = _int(data.get("port", 80), f"{path}.port")
    if not 1 <= port <= 65535:
        raise ConfigError(f"{path}.port", "muss zwischen 1 und 65535 liegen")
    ws_path = _string(data.get("path", "/?ma=1"), f"{path}.path")
    if not ws_path.startswith("/"):
        raise ConfigError(f"{path}.path", "muss mit / beginnen")

    keepalive = _float(data.get("keepalive_interval", 5.0), f"{path}.keepalive_interval")
    if not 0 < keepalive < 10:
        raise ConfigError(
            f"{path}.keepalive_interval",
            "muss größer 0 und kleiner 10 Sekunden sein",
        )
    login_timeout = _float(data.get("login_timeout", 10.0), f"{path}.login_timeout")
    if login_timeout <= 0:
        raise ConfigError(f"{path}.login_timeout", "muss größer 0 sein")

    hardkey_transport = _choice(
        data.get("hardkey_transport", "lua"),
        f"{path}.hardkey_transport",
        {"lua", "native"},
    )

    hold_threshold = _float(
        data.get("hardkey_hold_threshold", 0.5), f"{path}.hardkey_hold_threshold"
    )
    if hold_threshold <= 0:
        raise ConfigError(f"{path}.hardkey_hold_threshold", "muss größer 0 sein")

    press = _float(data.get("hardkey_press_value", 1.0), f"{path}.hardkey_press_value")
    release = _float(
        data.get("hardkey_release_value", 0.0), f"{path}.hardkey_release_value"
    )
    if press <= 0.9:
        raise ConfigError(f"{path}.hardkey_press_value", "muss größer als 0.9 sein")
    if release >= 0.9:
        raise ConfigError(f"{path}.hardkey_release_value", "muss kleiner als 0.9 sein")

    page_refresh = _float(
        data.get("page_refresh_interval", 1.0), f"{path}.page_refresh_interval"
    )
    if page_refresh <= 0:
        raise ConfigError(f"{path}.page_refresh_interval", "muss größer 0 sein")

    return Ma2Settings(
        host=host,
        username=username,
        port=port,
        path=ws_path,
        password_file=password_file,
        password_env=password_env,
        keepalive_interval=keepalive,
        login_timeout=login_timeout,
        hardkey_transport=hardkey_transport,
        hardkey_hold_threshold=hold_threshold,
        hardkey_press_value=press,
        hardkey_release_value=release,
        page_refresh_interval=page_refresh,
    )


def _parse_reconnect(raw: Any) -> ReconnectSettings:
    path = "reconnect"
    data = _table(raw, path)
    _reject_unknown(data, {"initial_delay", "max_delay", "jitter", "login_failure_delay"}, path)
    initial = _float(data.get("initial_delay", 1.0), f"{path}.initial_delay")
    maximum = _float(data.get("max_delay", 30.0), f"{path}.max_delay")
    jitter = _float(data.get("jitter", 0.2), f"{path}.jitter")
    login_delay = _float(data.get("login_failure_delay", 10.0), f"{path}.login_failure_delay")
    if initial <= 0:
        raise ConfigError(f"{path}.initial_delay", "muss größer 0 sein")
    if maximum < initial:
        raise ConfigError(f"{path}.max_delay", "darf nicht kleiner als initial_delay sein")
    if not 0 <= jitter <= 1:
        raise ConfigError(f"{path}.jitter", "muss zwischen 0 und 1 liegen")
    if login_delay <= 0:
        raise ConfigError(f"{path}.login_failure_delay", "muss größer 0 sein")
    return ReconnectSettings(initial, maximum, jitter, login_delay)


def _parse_rate_limit(raw: Any) -> RateLimitSettings:
    path = "rate_limit"
    data = _table(raw, path)
    allowed = {
        "messages_per_second",
        "burst",
        "encoder_base_interval",
        "encoder_stream_penalty",
        "encoder_idle_base",
        "encoder_idle_penalty",
        "max_pending_delta",
    }
    _reject_unknown(data, allowed, path)
    rate = _int(data.get("messages_per_second", 25), f"{path}.messages_per_second")
    if not 5 <= rate <= 40:
        raise ConfigError(f"{path}.messages_per_second", "muss zwischen 5 und 40 liegen")
    burst = _int(data.get("burst", 10), f"{path}.burst")
    if not 1 <= burst <= 200:
        raise ConfigError(f"{path}.burst", "muss zwischen 1 und 200 liegen")
    values = {
        "encoder_base_interval": _float(data.get("encoder_base_interval", 0.025), f"{path}.encoder_base_interval"),
        "encoder_stream_penalty": _float(data.get("encoder_stream_penalty", 0.0024), f"{path}.encoder_stream_penalty"),
        "encoder_idle_base": _float(data.get("encoder_idle_base", 0.040), f"{path}.encoder_idle_base"),
        "encoder_idle_penalty": _float(data.get("encoder_idle_penalty", 0.0022), f"{path}.encoder_idle_penalty"),
    }
    for key, value in values.items():
        if value < 0:
            raise ConfigError(f"{path}.{key}", "darf nicht negativ sein")
    if values["encoder_base_interval"] <= 0 or values["encoder_idle_base"] <= 0:
        raise ConfigError(path, "encoder_base_interval und encoder_idle_base müssen größer 0 sein")
    pending = _int(data.get("max_pending_delta", 1000), f"{path}.max_pending_delta")
    if pending <= 0:
        raise ConfigError(f"{path}.max_pending_delta", "muss größer 0 sein")
    return RateLimitSettings(rate, burst, values["encoder_base_interval"], values["encoder_stream_penalty"], values["encoder_idle_base"], values["encoder_idle_penalty"], pending)


def _parse_logging(raw: Any) -> LoggingSettings:
    path = "logging"
    data = _table(raw, path)
    _reject_unknown(data, {"level"}, path)
    level = _string(data.get("level", "INFO"), f"{path}.level").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(f"{path}.level", "muss ein gültiges Log-Level sein")
    return LoggingSettings(level)


def _parse_led(raw: Any) -> LedSettings:
    path = "led"
    data = _table(raw, path)
    _reject_unknown(
        data,
        {
            "enabled",
            "device",
            "note",
            "attribute_color",
            "screen_color",
            "brightness",
            "brightness_channel",
            "color_channel",
            "nipple_note",
            "nipple_idle_color",
            "nipple_idle_brightness",
            "nipple_pressed_color",
            "nipple_pressed_brightness",
            "fine_note",
            "fine_color",
            "fine_idle_brightness",
            "fine_pressed_brightness",
        },
        path,
    )
    enabled = _bool(data.get("enabled", False), f"{path}.enabled")
    device = data.get("device")
    if device is not None:
        device = _string(device, f"{path}.device")
    note = _int(data.get("note", 9), f"{path}.note")
    if not 1 <= note <= 127:
        raise ConfigError(f"{path}.note", "muss zwischen 1 und 127 liegen")
    try:
        attribute_color = parse_color(data.get("attribute_color", "red"))
    except ValueError as exc:
        raise ConfigError(f"{path}.attribute_color", str(exc)) from exc
    try:
        screen_color = parse_color(data.get("screen_color", "green"))
    except ValueError as exc:
        raise ConfigError(f"{path}.screen_color", str(exc)) from exc
    brightness = _int(data.get("brightness", 127), f"{path}.brightness")
    if not 0 <= brightness <= 127:
        raise ConfigError(f"{path}.brightness", "muss zwischen 0 und 127 liegen")

    channels = []
    for key, default in (("brightness_channel", 1), ("color_channel", 2)):
        value = _int(data.get(key, default), f"{path}.{key}")
        if not 1 <= value <= 16:
            raise ConfigError(f"{path}.{key}", "muss zwischen 1 und 16 liegen")
        channels.append(value)
    brightness_channel, color_channel = channels
    if brightness_channel == color_channel:
        raise ConfigError(path, "brightness_channel und color_channel müssen verschieden sein")

    nipple_note = _int(data.get("nipple_note", 11), f"{path}.nipple_note")
    if not 1 <= nipple_note <= 127:
        raise ConfigError(f"{path}.nipple_note", "muss zwischen 1 und 127 liegen")
    nipple: dict[str, int] = {}
    for key, default in (
        ("nipple_idle_color", 121),
        ("nipple_pressed_color", 116),
    ):
        try:
            nipple[key] = parse_color(data.get(key, default))
        except ValueError as exc:
            raise ConfigError(f"{path}.{key}", str(exc)) from exc
    for key, default in (
        ("nipple_idle_brightness", 25),
        ("nipple_pressed_brightness", 127),
    ):
        value = _int(data.get(key, default), f"{path}.{key}")
        if not 0 <= value <= 127:
            raise ConfigError(f"{path}.{key}", "muss zwischen 0 und 127 liegen")
        nipple[key] = value

    fine_note = _int(data.get("fine_note", 10), f"{path}.fine_note")
    if not 1 <= fine_note <= 127:
        raise ConfigError(f"{path}.fine_note", "muss zwischen 1 und 127 liegen")
    try:
        fine_color = parse_color(data.get("fine_color", 123))
    except ValueError as exc:
        raise ConfigError(f"{path}.fine_color", str(exc)) from exc
    fine_levels: dict[str, int] = {}
    for key, default in (("fine_idle_brightness", 25), ("fine_pressed_brightness", 127)):
        value = _int(data.get(key, default), f"{path}.{key}")
        if not 0 <= value <= 127:
            raise ConfigError(f"{path}.{key}", "muss zwischen 0 und 127 liegen")
        fine_levels[key] = value

    return LedSettings(
        enabled=enabled,
        device=device,
        note=note,
        attribute_color=attribute_color,
        screen_color=screen_color,
        brightness=brightness,
        brightness_channel=brightness_channel,
        color_channel=color_channel,
        nipple_note=nipple_note,
        nipple_idle_color=nipple["nipple_idle_color"],
        nipple_idle_brightness=nipple["nipple_idle_brightness"],
        nipple_pressed_color=nipple["nipple_pressed_color"],
        nipple_pressed_brightness=nipple["nipple_pressed_brightness"],
        fine_note=fine_note,
        fine_color=fine_color,
        fine_idle_brightness=fine_levels["fine_idle_brightness"],
        fine_pressed_brightness=fine_levels["fine_pressed_brightness"],
    )


def _parse_feedback(raw: Any) -> FeedbackSettings:
    path = "feedback"
    data = _table(raw, path)
    _reject_unknown(
        data, {"enabled", "interval_ms", "off_state", "fallback_color"}, path
    )
    enabled = _bool(data.get("enabled", False), f"{path}.enabled")
    interval_ms = _int(data.get("interval_ms", 250), f"{path}.interval_ms")
    if not 100 <= interval_ms <= 2000:
        raise ConfigError(f"{path}.interval_ms", "muss zwischen 100 und 2000 liegen")
    off_state = _choice(
        data.get("off_state", "dark"), f"{path}.off_state", {"off", "dark"}
    )
    fallback_color = _string(
        data.get("fallback_color", "white"), f"{path}.fallback_color"
    )
    if fallback_color not in PALETTE:
        raise ConfigError(
            f"{path}.fallback_color",
            f"unbekannte Farbe {fallback_color!r}; erlaubt: {', '.join(PALETTE)}",
        )
    return FeedbackSettings(enabled, interval_ms, off_state, fallback_color)


def _parse_web(raw: Any) -> WebSettings:
    path = "web"
    data = _table(raw, path)
    _reject_unknown(data, {"bind", "port", "pin_enabled", "pin"}, path)
    bind = _string(data.get("bind", "0.0.0.0"), f"{path}.bind")
    port = _int(data.get("port", 8080), f"{path}.port")
    if not 1 <= port <= 65535:
        raise ConfigError(f"{path}.port", "muss zwischen 1 und 65535 liegen")
    pin_enabled = _bool(data.get("pin_enabled", False), f"{path}.pin_enabled")
    pin = _string(data.get("pin", ""), f"{path}.pin", allow_empty=True)
    if pin and (not pin.isdigit() or not 4 <= len(pin) <= 12):
        raise ConfigError(f"{path}.pin", "muss aus 4 bis 12 Ziffern bestehen")
    if pin_enabled and not pin:
        raise ConfigError(
            f"{path}.pin", "muss gesetzt sein, wenn pin_enabled true ist"
        )
    return WebSettings(bind=bind, port=port, pin_enabled=pin_enabled, pin=pin)


def _parse_screen_helper(raw: Any) -> ScreenHelperSettings:
    path = "screen_helper"
    data = _table(raw, path)
    _reject_unknown(data, {"enabled", "host", "port"}, path)
    enabled = _bool(data.get("enabled", False), f"{path}.enabled")
    host = _string(data.get("host", "192.168.0.10"), f"{path}.host")
    port = _int(data.get("port", 5010), f"{path}.port")
    if not 1 <= port <= 65535:
        raise ConfigError(f"{path}.port", "muss zwischen 1 und 65535 liegen")
    return ScreenHelperSettings(enabled=enabled, host=host, port=port)


def _parse_midi_remote(raw: Any) -> MidiRemoteSettings:
    path = "midi_remote"
    data = _table(raw, path)
    _reject_unknown(
        data, {"enabled", "host", "port", "channels", "sync", "telnet_port"}, path
    )
    enabled = _bool(data.get("enabled", False), f"{path}.enabled")
    host = None
    if "host" in data:
        host = _string(data["host"], f"{path}.host")
    port = _int(data.get("port", 5004), f"{path}.port")
    if not 1 <= port <= 65534:
        # The data port is port + 1.
        raise ConfigError(f"{path}.port", "muss zwischen 1 und 65534 liegen")
    raw_channels = data.get("channels", [16])
    if not isinstance(raw_channels, list) or not raw_channels:
        raise ConfigError(f"{path}.channels", "muss eine nicht leere Liste sein")
    channels: list[int] = []
    for value in raw_channels:
        channel = _int(value, f"{path}.channels")
        if not 1 <= channel <= 16:
            raise ConfigError(f"{path}.channels", "Kanäle müssen zwischen 1 und 16 liegen")
        if channel in channels:
            raise ConfigError(f"{path}.channels", f"Kanal {channel} doppelt")
        channels.append(channel)
    sync = _choice(data.get("sync", "auto"), f"{path}.sync", {"auto", "check", "off"})
    telnet_port = _int(data.get("telnet_port", 30000), f"{path}.telnet_port")
    if not 1 <= telnet_port <= 65535:
        raise ConfigError(f"{path}.telnet_port", "muss zwischen 1 und 65535 liegen")
    return MidiRemoteSettings(
        enabled=enabled,
        host=host,
        port=port,
        channels=tuple(channels),
        sync=sync,
        telnet_port=telnet_port,
    )


def _transport(item: Mapping[str, Any], item_path: str) -> str | None:
    if "transport" not in item:
        return None
    return _choice(item["transport"], f"{item_path}.transport", {"midi", "web"})


def effective_transport(kind: str, transport: str | None, midi_enabled: bool) -> str:
    """Transport of a resolved playback target (``midi`` or ``web``)."""

    if transport is not None:
        return transport
    return "midi" if kind == "button" and midi_enabled else "web"


def _check_playback_transports(config: AppConfig) -> None:
    """``transport = "midi"`` needs an enabled ``[midi_remote]`` and a button."""

    mapping = config.mapping
    enabled = config.midi_remote.enabled
    entries: list[tuple[str, str, str | None]] = []
    for control, base in mapping.playbacks.items():
        entries.append((f"mapping.playbacks.{control}", base.kind, base.transport))
    for device, settings in mapping.device_banks.items():
        for number, layer in settings.banks.items():
            for control, override in layer.playbacks.items():
                base = mapping.playbacks.get(control)
                kind = override.kind or (base.kind if base is not None else "button")
                transport = override.transport
                if transport is None and base is not None:
                    transport = base.transport
                entries.append(
                    (
                        f"mapping.device_banks.{device}.{number}.playbacks.{control}",
                        kind,
                        transport,
                    )
                )
    for item_path, kind, transport in entries:
        if transport != "midi":
            continue
        if not enabled:
            raise ConfigError(
                f"{item_path}.transport",
                'transport = "midi" braucht [midi_remote] enabled = true',
            )
        if kind != "button":
            raise ConfigError(
                f"{item_path}.transport", 'transport = "midi" nur bei kind = "button"'
            )


def _check_midi_address_space(config: AppConfig) -> None:
    if not config.midi_remote.enabled:
        return
    from .midi_remote import AddressSpaceExhausted, assign_addresses
    from .playback_targets import midi_button_targets

    try:
        assign_addresses(midi_button_targets(config), config.midi_remote.channels)
    except AddressSpaceExhausted as exc:
        raise ConfigError("midi_remote.channels", str(exc)) from exc


def _parse_devices(raw: Any, profiles: Mapping[str, ProfileConfig]) -> Mapping[str, DeviceConfig]:
    path = "devices"
    data = _table(raw, path)
    if not data:
        raise ConfigError(path, "mindestens ein Gerät konfigurieren")
    devices: dict[str, DeviceConfig] = {}
    for name, entry in data.items():
        item_path = f"{path}.{name}"
        item = _table(entry, item_path)
        _reject_unknown(
            item,
            {"vendor_id", "product_id", "name_contains", "profile", "backend"},
            item_path,
        )
        backend = _choice(
            item.get("backend", "evdev"),
            f"{item_path}.backend",
            {"evdev", "midi"},
        )
        vendor = _int(_require(item, "vendor_id", item_path), f"{item_path}.vendor_id")
        product = _int(item.get("product_id", 0), f"{item_path}.product_id")
        name_contains = item.get("name_contains")
        if name_contains is not None:
            name_contains = _string(name_contains, f"{item_path}.name_contains")
        if not 0 <= vendor <= 0xFFFF:
            raise ConfigError(f"{item_path}.vendor_id", "muss zwischen 0 und 0xFFFF liegen")
        if not 0 <= product <= 0xFFFF:
            raise ConfigError(f"{item_path}.product_id", "muss zwischen 0 und 0xFFFF liegen")
        if vendor == 0 and not name_contains:
            raise ConfigError(
                f"{item_path}.vendor_id",
                "vendor_id 0 ist nur mit name_contains erlaubt",
            )
        profile = _string(_require(item, "profile", item_path), f"{item_path}.profile")
        if profile not in profiles:
            raise ConfigError(f"{item_path}.profile", f"unbekanntes Profil {profile!r}")
        devices[name] = DeviceConfig(
            name=name,
            profile=profile,
            vendor_id=vendor,
            product_id=product,
            name_contains=name_contains,
            backend=backend,
        )
    return devices


def _parse_profiles(raw: Any) -> Mapping[str, ProfileConfig]:
    path = "profiles"
    data = _table(raw, path)
    if not data:
        raise ConfigError(path, "mindestens ein Profil konfigurieren")
    profiles: dict[str, ProfileConfig] = {}
    global_encoder_ids: set[int] = set()
    control_owner: dict[str, str] = {}
    for name, entry in data.items():
        item_path = f"{path}.{name}"
        item = _table(entry, item_path)
        _reject_unknown(
            item,
            {
                "keys",
                "encoders",
                "notes",
                "midi_encoders",
                "midi_values",
                "controls",
                "banks",
                "led_feedback",
            },
            item_path,
        )
        keys_raw = _table(item.get("keys", {}), f"{item_path}.keys")
        keys: dict[str, str] = {}
        for code, control in keys_raw.items():
            control = _string(control, f"{item_path}.keys.{code}")
            keys[code] = control

        controls_raw = item.get("controls", [])
        if not isinstance(controls_raw, list):
            raise ConfigError(f"{item_path}.controls", "muss ein Array of Tables sein")
        controls: list[ControlProfile] = []
        seen_control_ids: set[str] = set()
        for index, raw_control in enumerate(controls_raw):
            control_path = f"{item_path}.controls[{index}]"
            control_item = _table(raw_control, control_path)
            _reject_unknown(
                control_item, {"id", "kind", "label", "encoder_id"}, control_path
            )
            control_id = _string(
                _require(control_item, "id", control_path), f"{control_path}.id"
            )
            if control_id in seen_control_ids:
                raise ConfigError(
                    f"{control_path}.id", f"Control {control_id!r} doppelt im Profil"
                )
            seen_control_ids.add(control_id)
            kind = _choice(
                control_item.get("kind", "button"),
                f"{control_path}.kind",
                {"button", "fader", "poti", "encoder", "relative-encoder"},
            )
            label = control_item.get("label")
            if label is not None:
                label = _string(label, f"{control_path}.label", allow_empty=True)
            ctrl_enc_id: int | None = None
            if "encoder_id" in control_item:
                if kind != "relative-encoder":
                    raise ConfigError(
                        f"{control_path}.encoder_id",
                        'nur bei kind = "relative-encoder" erlaubt',
                    )
                ctrl_enc_id = _int(
                    control_item["encoder_id"], f"{control_path}.encoder_id"
                )
                if ctrl_enc_id <= 0:
                    raise ConfigError(
                        f"{control_path}.encoder_id", "muss größer 0 sein"
                    )
            elif kind == "relative-encoder" and control_id.startswith("encoder."):
                suffix = control_id[len("encoder.") :]
                if suffix.isdigit() and int(suffix) > 0:
                    ctrl_enc_id = int(suffix)
            controls.append(ControlProfile(control_id, kind, label, ctrl_enc_id))
        declared_controls = {control.id for control in controls}
        encoders_raw = item.get("encoders", [])
        if not isinstance(encoders_raw, list):
            raise ConfigError(f"{item_path}.encoders", "muss ein Array of Tables sein")
        encoders: list[EncoderProfile] = []
        seen_ids: set[int] = set()
        seen_controls: set[str] = set()
        for index, raw_encoder in enumerate(encoders_raw):
            enc_path = f"{item_path}.encoders[{index}]"
            enc = _table(raw_encoder, enc_path)
            _reject_unknown(
                enc,
                {"id", "control", "detents_per_revolution", "direction", "threshold"},
                enc_path,
            )
            enc_id = _int(_require(enc, "id", enc_path), f"{enc_path}.id")
            if enc_id <= 0:
                raise ConfigError(f"{enc_path}.id", "muss größer 0 sein")
            if enc_id in seen_ids:
                raise ConfigError(f"{enc_path}.id", f"doppelte Encoder-ID {enc_id}")
            if enc_id in global_encoder_ids:
                raise ConfigError(
                    f"{enc_path}.id",
                    f"Encoder-ID {enc_id} ist bereits in einem anderen Profil definiert",
                )
            seen_ids.add(enc_id)
            global_encoder_ids.add(enc_id)
            control = _string(_require(enc, "control", enc_path), f"{enc_path}.control")
            if control in seen_controls:
                raise ConfigError(f"{enc_path}.control", f"Control {control!r} doppelt im Profil")
            seen_controls.add(control)
            detents = _int(
                enc.get("detents_per_revolution", 24),
                f"{enc_path}.detents_per_revolution",
            )
            if detents <= 0:
                raise ConfigError(f"{enc_path}.detents_per_revolution", "muss größer 0 sein")
            direction = _int(enc.get("direction", 1), f"{enc_path}.direction")
            if direction not in (-1, 1):
                raise ConfigError(f"{enc_path}.direction", "muss 1 oder -1 sein")
            threshold = _float(enc.get("threshold", 0.0), f"{enc_path}.threshold")
            if threshold < 0:
                raise ConfigError(f"{enc_path}.threshold", "darf nicht negativ sein")
            encoders.append(EncoderProfile(enc_id, control, detents, direction, threshold))

        notes_raw = _table(item.get("notes", {}), f"{item_path}.notes")
        notes: dict[int, str] = {}
        for note_key, control in notes_raw.items():
            note_path = f"{item_path}.notes.{note_key}"
            note = _midi_note(note_key, note_path)
            if note in notes:
                raise ConfigError(note_path, f"MIDI-Note {note} ist doppelt")
            control = _string(control, note_path)
            if declared_controls and control not in declared_controls:
                raise ConfigError(
                    note_path, f"Control {control!r} fehlt im Control-Inventar"
                )
            notes[note] = control

        midi_encoders_raw = item.get("midi_encoders", [])
        if not isinstance(midi_encoders_raw, list):
            raise ConfigError(f"{item_path}.midi_encoders", "muss ein Array of Tables sein")
        midi_encoders: list[MidiEncoderProfile] = []
        used_notes = set(notes)
        for index, raw_encoder in enumerate(midi_encoders_raw):
            enc_path = f"{item_path}.midi_encoders[{index}]"
            enc = _table(raw_encoder, enc_path)
            _reject_unknown(
                enc,
                {"id", "note", "cw_velocity", "ccw_velocity", "direction"},
                enc_path,
            )
            enc_id = _int(_require(enc, "id", enc_path), f"{enc_path}.id")
            if enc_id <= 0:
                raise ConfigError(f"{enc_path}.id", "muss größer 0 sein")
            if enc_id in global_encoder_ids:
                raise ConfigError(
                    f"{enc_path}.id",
                    f"Encoder-ID {enc_id} ist bereits in einem anderen Profil definiert",
                )
            global_encoder_ids.add(enc_id)
            note = _midi_note(_require(enc, "note", enc_path), f"{enc_path}.note")
            if note in used_notes:
                raise ConfigError(
                    enc_path,
                    f"MIDI-Note {note} wird bereits von einer Taste oder einem Encoder verwendet",
                )
            used_notes.add(note)
            cw_velocity = _midi_velocity(
                enc.get("cw_velocity", 127), f"{enc_path}.cw_velocity"
            )
            ccw_velocity = _midi_velocity(
                enc.get("ccw_velocity", 1), f"{enc_path}.ccw_velocity"
            )
            if cw_velocity == ccw_velocity:
                raise ConfigError(
                    enc_path, "cw_velocity und ccw_velocity müssen verschieden sein"
                )
            direction = _int(enc.get("direction", 1), f"{enc_path}.direction")
            if direction not in (-1, 1):
                raise ConfigError(f"{enc_path}.direction", "muss 1 oder -1 sein")
            midi_encoders.append(
                MidiEncoderProfile(
                    enc_id, note, cw_velocity, ccw_velocity, direction
                )
            )

        midi_values_raw = item.get("midi_values", [])
        if not isinstance(midi_values_raw, list):
            raise ConfigError(f"{item_path}.midi_values", "muss ein Array of Tables sein")
        midi_values: list[MidiValueProfile] = []
        value_controls: set[str] = set()
        for index, raw_value in enumerate(midi_values_raw):
            value_path = f"{item_path}.midi_values[{index}]"
            value = _table(raw_value, value_path)
            _reject_unknown(value, {"control", "note", "kind"}, value_path)
            control = _string(_require(value, "control", value_path), f"{value_path}.control")
            if control in value_controls:
                raise ConfigError(value_path, f"Control {control!r} doppelt im Profil")
            if declared_controls and control not in declared_controls:
                raise ConfigError(
                    value_path, f"Control {control!r} fehlt im Control-Inventar"
                )
            value_controls.add(control)
            note = _midi_note(_require(value, "note", value_path), f"{value_path}.note")
            if note in used_notes:
                raise ConfigError(
                    value_path,
                    f"MIDI-Note {note} wird bereits von einer Taste oder einem Encoder verwendet",
                )
            used_notes.add(note)
            kind = _choice(value.get("kind", "fader"), f"{value_path}.kind", {"fader", "encoder"})
            midi_values.append(MidiValueProfile(control, note, kind))

        banks_raw = item.get("banks", [])
        if not isinstance(banks_raw, list):
            raise ConfigError(f"{item_path}.banks", "muss ein Array of Tables sein")
        banks: list[BankProfile] = []
        seen_bank_numbers: set[int] = set()
        seen_channels: set[int] = set()
        for index, raw_bank in enumerate(banks_raw):
            bank_path = f"{item_path}.banks[{index}]"
            bank_item = _table(raw_bank, bank_path)
            _reject_unknown(bank_item, {"number", "channel", "notes"}, bank_path)
            number = _int(_require(bank_item, "number", bank_path), f"{bank_path}.number")
            if not 1 <= number <= 16:
                raise ConfigError(f"{bank_path}.number", "muss zwischen 1 und 16 liegen")
            if number in seen_bank_numbers:
                raise ConfigError(f"{bank_path}.number", f"Bank {number} ist doppelt")
            seen_bank_numbers.add(number)
            channel = _int(bank_item.get("channel", number), f"{bank_path}.channel")
            if not 1 <= channel <= 16:
                raise ConfigError(f"{bank_path}.channel", "muss zwischen 1 und 16 liegen")
            if channel in seen_channels:
                raise ConfigError(
                    f"{bank_path}.channel",
                    f"MIDI-Kanal {channel} wird bereits von einer anderen Bank verwendet",
                )
            seen_channels.add(channel)
            if not controls:
                raise ConfigError(
                    bank_path, "eine Bank erfordert ein Control-Inventar im Profil"
                )
            bank_notes_raw = _table(bank_item.get("notes", {}), f"{bank_path}.notes")
            bank_notes: dict[int, str] = {}
            for note_key, control in bank_notes_raw.items():
                note_path = f"{bank_path}.notes.{note_key}"
                note = _midi_note(note_key, note_path)
                if note in bank_notes:
                    raise ConfigError(note_path, f"MIDI-Note {note} ist doppelt")
                control = _string(control, note_path)
                if control not in declared_controls:
                    raise ConfigError(
                        note_path, f"Control {control!r} fehlt im Control-Inventar"
                    )
                bank_notes[note] = control
            banks.append(BankProfile(number, channel, bank_notes))

        if banks and (notes or midi_encoders or midi_values):
            raise ConfigError(
                item_path,
                "Bänke und flache Noten schließen sich aus; Noten je Bank definieren",
            )

        # Check explicit integer encoder IDs for banked relative-encoder controls first;
        # automatic IDs are assigned in a second pass after every explicit ID is registered.
        if banks and controls:
            for ctrl in controls:
                if ctrl.kind == "relative-encoder" and ctrl.encoder_id is not None:
                    if ctrl.encoder_id in global_encoder_ids:
                        raise ConfigError(
                            f"{item_path}.controls",
                            f"Encoder-ID {ctrl.encoder_id} ist bereits in einem anderen Profil definiert",
                        )
                    global_encoder_ids.add(ctrl.encoder_id)

        led_feedback: LedFeedbackProfile | None = None
        if "led_feedback" in item:
            fb_path = f"{item_path}.led_feedback"
            fb_raw = _table(item["led_feedback"], fb_path)
            _reject_unknown(
                fb_raw,
                {
                    "protocol",
                    "led_notes",
                    "enabled",
                    "frame_interval_ms",
                    "bright_level",
                    "dark_level",
                    "colors",
                },
                fb_path,
            )
            protocol = _choice(
                fb_raw.get("protocol", "midicraft-v2"),
                f"{fb_path}.protocol",
                {"midicraft-v2", "asl-mk2"},
            )
            if protocol != "asl-mk2":
                for key in ("bright_level", "dark_level", "colors"):
                    if key in fb_raw:
                        raise ConfigError(
                            f"{fb_path}.{key}", "gilt nur für protocol = \"asl-mk2\""
                        )
            levels: dict[str, int] = {}
            for key, default in (("bright_level", 127), ("dark_level", 25)):
                level = _int(fb_raw.get(key, default), f"{fb_path}.{key}")
                if not 0 <= level <= 127:
                    raise ConfigError(f"{fb_path}.{key}", "muss zwischen 0 und 127 liegen")
                levels[key] = level
            colors_raw = _table(fb_raw.get("colors", {}), f"{fb_path}.colors")
            colors: list[tuple[str, int]] = []
            for color_name, raw_index in colors_raw.items():
                color_path = f"{fb_path}.colors.{color_name}"
                if color_name not in PALETTE:
                    raise ConfigError(
                        color_path,
                        f"unbekannte Farbe {color_name!r}; erlaubt: {', '.join(PALETTE)}",
                    )
                color_index = _int(raw_index, color_path)
                if not 0 <= color_index <= 127:
                    raise ConfigError(color_path, "muss zwischen 0 und 127 liegen")
                colors.append((color_name, color_index))
            led_enabled = _bool(fb_raw.get("enabled", True), f"{fb_path}.enabled")
            frame_interval_ms = _int(
                fb_raw.get("frame_interval_ms", 20), f"{fb_path}.frame_interval_ms"
            )
            if not 1 <= frame_interval_ms <= 500:
                raise ConfigError(
                    f"{fb_path}.frame_interval_ms", "muss zwischen 1 und 500 liegen"
                )
            led_notes_raw = fb_raw.get("led_notes")
            led_notes: tuple[int, ...] | None = None
            if led_notes_raw is not None:
                if not isinstance(led_notes_raw, list):
                    raise ConfigError(f"{fb_path}.led_notes", "muss ein Array sein")
                profile_notes = set(notes)
                for bank in banks:
                    profile_notes.update(bank.notes)
                parsed: list[int] = []
                seen_led_notes: set[int] = set()
                for index, raw_note in enumerate(led_notes_raw):
                    note_path = f"{fb_path}.led_notes[{index}]"
                    note = _midi_note(raw_note, note_path)
                    if note in seen_led_notes:
                        raise ConfigError(note_path, f"MIDI-Note {note} ist doppelt")
                    if note not in profile_notes:
                        raise ConfigError(
                            note_path, f"MIDI-Note {note} gehört nicht zum Profil"
                        )
                    seen_led_notes.add(note)
                    parsed.append(note)
                led_notes = tuple(parsed)
            led_feedback = LedFeedbackProfile(
                protocol,
                led_notes,
                led_enabled,
                frame_interval_ms,
                levels["bright_level"],
                levels["dark_level"],
                tuple(colors),
            )

        if not controls:
            derived: dict[str, str] = {}
            for control in keys.values():
                derived.setdefault(control, "button")
            for control in notes.values():
                derived.setdefault(control, "button")
            for value in midi_values:
                derived.setdefault(value.control, value.kind)
            for encoder in midi_encoders:
                derived.setdefault(f"encoder.{encoder.id}", "relative-encoder")
            for encoder in encoders:
                derived.setdefault(f"encoder.{encoder.id}", "relative-encoder")
            controls = [
                ControlProfile(control_id, kind) for control_id, kind in derived.items()
            ]

        profile_controls = {control.id for control in controls}
        profile_controls.update(keys.values())
        profile_controls.update(notes.values())
        profile_controls.update(value.control for value in midi_values)
        for control_id in sorted(profile_controls):
            previous = control_owner.get(control_id)
            if previous is not None:
                raise ConfigError(
                    f"{item_path}.controls",
                    f"Control {control_id!r} ist bereits in Profil {previous!r} definiert",
                )
            control_owner[control_id] = name

        profiles[name] = ProfileConfig(
            keys=keys,
            encoders=tuple(encoders),
            notes=notes,
            midi_encoders=tuple(midi_encoders),
            midi_values=tuple(midi_values),
            controls=tuple(controls),
            banks=tuple(banks),
            led_feedback=led_feedback,
        )

    next_auto_id = 1
    for name, profile in list(profiles.items()):
        if not profile.banks or not profile.controls:
            continue
        if not any(
            ctrl.kind == "relative-encoder" and ctrl.encoder_id is None
            for ctrl in profile.controls
        ):
            continue
        resolved_controls: list[ControlProfile] = []
        for ctrl in profile.controls:
            if ctrl.kind == "relative-encoder" and ctrl.encoder_id is None:
                while next_auto_id in global_encoder_ids:
                    next_auto_id += 1
                chosen_id = next_auto_id
                next_auto_id += 1
                global_encoder_ids.add(chosen_id)
                resolved_controls.append(
                    ControlProfile(ctrl.id, ctrl.kind, ctrl.label, chosen_id)
                )
            else:
                resolved_controls.append(ctrl)
        profiles[name] = ProfileConfig(
            keys=profile.keys,
            encoders=profile.encoders,
            notes=profile.notes,
            midi_encoders=profile.midi_encoders,
            midi_values=profile.midi_values,
            controls=tuple(resolved_controls),
            banks=profile.banks,
            led_feedback=profile.led_feedback,
        )
    return profiles


def _parse_layouts(
    raw: Any, profiles: Mapping[str, ProfileConfig]
) -> Mapping[str, DeviceLayout]:
    path = "layouts"
    if raw is None:
        return {}
    data = _table(raw, path)
    layouts: dict[str, DeviceLayout] = {}
    colors = {"green", "blue", "red", "yellow", "grey", "black", "white"}
    for name, entry in data.items():
        item_path = f"{path}.{name}"
        item = _table(entry, item_path)
        _reject_unknown(item, {"profile", "columns", "rows"}, item_path)
        profile_name = _string(
            _require(item, "profile", item_path), f"{item_path}.profile"
        )
        profile = profiles.get(profile_name)
        if profile is None:
            raise ConfigError(
                f"{item_path}.profile", f"unbekanntes Profil {profile_name!r}"
            )
        if profile_name in layouts:
            raise ConfigError(
                f"{item_path}.profile",
                f"Profil {profile_name!r} hat bereits ein Layout",
            )
        columns = _int(item.get("columns", 1), f"{item_path}.columns")
        if columns < 1:
            raise ConfigError(f"{item_path}.columns", "muss mindestens 1 sein")
        rows_raw = item.get("rows", [])
        if not isinstance(rows_raw, list):
            raise ConfigError(f"{item_path}.rows", "muss ein Array of Tables sein")
        rows: list[LayoutRow] = []
        seen_controls: set[str] = set()
        for row_index, raw_row in enumerate(rows_raw):
            row_path = f"{item_path}.rows[{row_index}]"
            row_item = _table(raw_row, row_path)
            _reject_unknown(row_item, {"cells"}, row_path)
            cells_raw = row_item.get("cells", [])
            if not isinstance(cells_raw, list):
                raise ConfigError(f"{row_path}.cells", "muss ein Array sein")
            cells: list[LayoutCell] = []
            for cell_index, raw_cell in enumerate(cells_raw):
                cell_path = f"{row_path}.cells[{cell_index}]"
                cell_item = _table(raw_cell, cell_path)
                _reject_unknown(
                    cell_item,
                    {"label", "control", "col_span", "row_span", "color", "row", "col"},
                    cell_path,
                )
                label = _string(
                    cell_item.get("label", ""),
                    f"{cell_path}.label",
                    allow_empty=True,
                )
                control = cell_item.get("control")
                if control is not None:
                    control = _string(control, f"{cell_path}.control")
                    if control not in profile.control_names:
                        raise ConfigError(
                            f"{cell_path}.control",
                            f"Control {control!r} kommt im Profil {profile_name!r} nicht vor",
                        )
                    if control in seen_controls:
                        raise ConfigError(
                            f"{cell_path}.control",
                            f"Control {control!r} ist doppelt im Layout",
                        )
                    seen_controls.add(control)
                col_span = _int(cell_item.get("col_span", 1), f"{cell_path}.col_span")
                row_span = _int(cell_item.get("row_span", 1), f"{cell_path}.row_span")
                if col_span < 1 or row_span < 1:
                    raise ConfigError(cell_path, "Spannen müssen mindestens 1 sein")
                color = cell_item.get("color")
                if color is not None:
                    color = _choice(color, f"{cell_path}.color", colors)
                row = cell_item.get("row")
                if row is not None:
                    row = _int(row, f"{cell_path}.row")
                    if row < 1:
                        raise ConfigError(f"{cell_path}.row", "muss mindestens 1 sein")
                col = cell_item.get("col")
                if col is not None:
                    col = _int(col, f"{cell_path}.col")
                    if col < 1:
                        raise ConfigError(f"{cell_path}.col", "muss mindestens 1 sein")
                    if col + col_span - 1 > columns:
                        raise ConfigError(
                            f"{cell_path}.col",
                            "Zelle ragt über die Bezugsbreite hinaus",
                        )
                if (row is None) != (col is None):
                    raise ConfigError(
                        cell_path, "row und col müssen gemeinsam angegeben werden"
                    )
                cells.append(
                    LayoutCell(label, control, col_span, row_span, color, row, col)
                )
            if cells and all(cell.row is None for cell in cells):
                total_span = sum(cell.col_span for cell in cells)
                if total_span > columns:
                    raise ConfigError(
                        row_path,
                        f"Zellen benötigen {total_span} Spalten, Layout hat {columns}",
                    )
            rows.append(LayoutRow(tuple(cells)))
        occupied: set[tuple[int, int]] = set()
        for layout_row in rows:
            for cell in layout_row.cells:
                if cell.row is None or cell.col is None:
                    continue
                for grid_row in range(cell.row, cell.row + cell.row_span):
                    for grid_col in range(cell.col, cell.col + cell.col_span):
                        if (grid_row, grid_col) in occupied:
                            raise ConfigError(
                                item_path,
                                f"Zellen überlappen sich bei Zeile {grid_row}, Spalte {grid_col}",
                            )
                        occupied.add((grid_row, grid_col))
        layouts[profile_name] = DeviceLayout(
            profile_name, columns, tuple(rows), name=name
        )
    return layouts


def _parse_hardkeys(raw: Any) -> Mapping[str, HardkeyCode]:
    path = "hardkeys"
    if raw is None:
        return {}
    data = _table(raw, path)
    codes: dict[str, HardkeyCode] = {}
    for name, entry in data.items():
        item_path = f"{path}.{name}"
        try:
            canonical = hardkeys.resolve(name)
        except hardkeys.UnknownHardkey as exc:
            raise ConfigError(item_path, f"unbekannter Hardkey {name!r}") from exc
        if canonical != name:
            raise ConfigError(
                item_path,
                f"Keycode muss unter dem kanonischen Namen {canonical!r} stehen",
            )
        item = _table(entry, item_path)
        _reject_unknown(item, {"code", "verified"}, item_path)
        code = _int(_require(item, "code", item_path), f"{item_path}.code")
        if not 1 <= code <= 255:
            raise ConfigError(f"{item_path}.code", "muss zwischen 1 und 255 liegen")
        verified = _bool(_require(item, "verified", item_path), f"{item_path}.verified")
        codes[name] = HardkeyCode(code, verified)
    return codes


def _require_hardkey_codes(
    mapping: MappingSettings, codes: Mapping[str, HardkeyCode]
) -> None:
    used: dict[str, str] = {}
    for control, entry in mapping.keys.items():
        if entry.hardkey is not None:
            used[control] = entry.hardkey
    for control, entry in mapping.modifiers.items():
        if entry.hardkey is not None:
            used[control] = entry.hardkey
    for dev_name, dev_banks in mapping.device_banks.items():
        for bank_num, layer in dev_banks.banks.items():
            for control, entry in layer.keys.items():
                if entry.hardkey is not None:
                    used[f"{dev_name}.{bank_num}.{control}"] = entry.hardkey

    for control, value in sorted(used.items()):
        canonical = hardkeys.resolve(value)
        if canonical not in codes:
            raise ConfigError(
                f"hardkeys.{canonical}",
                f"fehlender Keycode für Hardkey {canonical!r} (verwendet von {control})",
            )


def _parse_key_mapping(
    item: Mapping[str, Any],
    item_path: str,
    control: str,
    controls: set[str],
) -> KeyMapping:
    _reject_unknown(
        item, {"hardkey", "command", "screen_mode", "encoder_press", "screen"}, item_path
    )
    if control not in controls:
        raise ConfigError(item_path, f"Control {control!r} kommt in keinem Profil vor")
    kinds = [
        name
        for name in ("hardkey", "command", "screen_mode", "encoder_press", "screen")
        if name in item
    ]
    if len(kinds) != 1:
        raise ConfigError(
            item_path,
            "genau eines von hardkey, command, screen_mode, encoder_press oder screen angeben",
        )
    kind = kinds[0]
    if kind == "hardkey":
        _validate_hardkey(item["hardkey"], f"{item_path}.hardkey")
        return KeyMapping(hardkey=item["hardkey"])
    if kind == "command":
        return KeyMapping(command=_string(item["command"], f"{item_path}.command"))
    if kind == "screen_mode":
        return KeyMapping(
            screen_mode=_bool(item["screen_mode"], f"{item_path}.screen_mode")
        )
    if kind == "screen":
        screen = _int(item["screen"], f"{item_path}.screen")
        if not 1 <= screen <= 6:
            raise ConfigError(f"{item_path}.screen", "muss zwischen 1 und 6 liegen")
        return KeyMapping(screen=screen)
    slot = _int(item["encoder_press"], f"{item_path}.encoder_press")
    if not 1 <= slot <= 8:
        raise ConfigError(f"{item_path}.encoder_press", "muss zwischen 1 und 8 liegen")
    return KeyMapping(encoder_press=slot)


def _parse_encoder_mapping(
    item: Mapping[str, Any], item_path: str, encoder_ids: set[int]
) -> EncoderMapping:
    _reject_unknown(item, {"id", "slot", "attribute"}, item_path)
    enc_id = _int(_require(item, "id", item_path), f"{item_path}.id")
    if enc_id <= 0:
        raise ConfigError(f"{item_path}.id", "muss größer 0 sein")
    if enc_id not in encoder_ids:
        raise ConfigError(
            f"{item_path}.id", f"Encoder-ID {enc_id} kommt in keinem Profil vor"
        )
    has_slot = "slot" in item
    has_attribute = "attribute" in item
    if has_slot == has_attribute:
        raise ConfigError(item_path, "genau eines von slot oder attribute angeben")
    if has_slot:
        slot = _int(item["slot"], f"{item_path}.slot")
        if not 1 <= slot <= 8:
            raise ConfigError(f"{item_path}.slot", "muss zwischen 1 und 8 liegen")
        return EncoderMapping(id=enc_id, slot=slot)
    attribute = _string(item["attribute"], f"{item_path}.attribute")
    return EncoderMapping(id=enc_id, attribute=attribute)


def _parse_mapping(
    raw: Any,
    profiles: Mapping[str, ProfileConfig],
    devices: Mapping[str, DeviceConfig] | None = None,
) -> MappingSettings:
    path = "mapping"
    data = _table(raw, path)
    _reject_unknown(
        data,
        {
            "modifiers",
            "keys",
            "encoders",
            "screen_encoders",
            "playbacks",
            "device_banks",
            "encoder_acceleration",
            "value_acceleration",
            "encoder_resolution",
            "combined_executors",
            "topology_interval_ms",
        },
        path,
    )
    controls: set[str] = set()
    value_kinds: dict[str, str] = {}
    encoder_ids: set[int] = set()
    for profile in profiles.values():
        controls.update(profile.control_names)
        value_kinds.update(profile.control_kinds)
        encoder_ids.update(profile.relative_encoder_ids.values())

    modifiers_raw = _table(data.get("modifiers", {}), f"{path}.modifiers")
    modifiers: dict[str, ModifierMapping] = {}
    for control, entry in modifiers_raw.items():
        item_path = f"{path}.modifiers.{control}"
        item = _table(entry, item_path)
        _reject_unknown(item, {"hardkey", "local"}, item_path)
        if control not in controls:
            raise ConfigError(item_path, f"Control {control!r} kommt in keinem Profil vor")
        if "hardkey" in item and "local" in item:
            raise ConfigError(item_path, "hardkey und local schließen sich aus")
        if "local" in item:
            modifiers[control] = ModifierMapping(local=_bool(item["local"], f"{item_path}.local"))
            continue
        hardkey = _require(item, "hardkey", item_path)
        _validate_hardkey(hardkey, f"{item_path}.hardkey")
        modifiers[control] = ModifierMapping(hardkey=hardkey)

    keys_raw = _table(data.get("keys", {}), f"{path}.keys")
    keys: dict[str, KeyMapping] = {}
    for control, entry in keys_raw.items():
        item_path = f"{path}.keys.{control}"
        keys[control] = _parse_key_mapping(
            _table(entry, item_path), item_path, control, controls
        )

    encoders_raw = data.get("encoders", [])
    if not isinstance(encoders_raw, list):
        raise ConfigError(f"{path}.encoders", "muss ein Array of Tables sein")
    encoders: list[EncoderMapping] = []
    seen_ids: set[int] = set()
    for index, raw_encoder in enumerate(encoders_raw):
        item_path = f"{path}.encoders[{index}]"
        mapping = _parse_encoder_mapping(
            _table(raw_encoder, item_path), item_path, encoder_ids
        )
        if mapping.id in seen_ids:
            raise ConfigError(f"{item_path}.id", f"doppelte Encoder-ID {mapping.id}")
        seen_ids.add(mapping.id)
        encoders.append(mapping)

    screen_raw = _table(data.get("screen_encoders", {}), f"{path}.screen_encoders")
    screen_encoders: dict[int, int] = {}
    for slot_key, name in screen_raw.items():
        slot_path = f"{path}.screen_encoders.{slot_key}"
        try:
            slot = int(slot_key)
        except (TypeError, ValueError) as exc:
            raise ConfigError(slot_path, "muss zwischen 1 und 4 liegen") from exc
        if not 1 <= slot <= 4:
            raise ConfigError(slot_path, "muss zwischen 1 und 4 liegen")
        if isinstance(name, str) and name.strip().isdigit():
            name = int(name)
        number = _int(name, slot_path)
        if not 5 <= number <= 10:
            raise ConfigError(slot_path, "Screen-Encoder muss zwischen 5 und 10 liegen")
        screen_encoders[slot] = number

    acceleration = _parse_acceleration(data.get("encoder_acceleration"))
    value_acceleration = _parse_value_acceleration(data.get("value_acceleration"))
    resolution = _parse_resolution(data.get("encoder_resolution"), modifiers)
    combined_executors = _choice(
        data.get("combined_executors", "auto"),
        f"{path}.combined_executors",
        {"auto", "off"},
    )
    topology_interval_ms = _int(
        data.get("topology_interval_ms", 2000), f"{path}.topology_interval_ms"
    )
    if not 500 <= topology_interval_ms <= 10000:
        raise ConfigError(
            f"{path}.topology_interval_ms", "muss zwischen 500 und 10000 liegen"
        )

    playbacks_raw = _table(data.get("playbacks", {}), f"{path}.playbacks")
    playbacks: dict[str, PlaybackMapping] = {}
    for control, entry in playbacks_raw.items():
        item_path = f"{path}.playbacks.{control}"
        item = _table(entry, item_path)
        _reject_unknown(
            item, {"page", "executor", "kind", "button", "accelerated", "transport"}, item_path
        )
        if control not in controls:
            raise ConfigError(item_path, f"Control {control!r} kommt in keinem Profil vor")
        page_raw = _require(item, "page", item_path)
        if page_raw == "current":
            page: int | str = "current"
        else:
            page = _int(page_raw, f"{item_path}.page")
            if page < 1:
                raise ConfigError(f"{item_path}.page", "muss mindestens 1 sein oder \"current\"")
        executor = _int(_require(item, "executor", item_path), f"{item_path}.executor")
        if executor < 1:
            raise ConfigError(f"{item_path}.executor", "muss mindestens 1 sein")
        kind = _choice(item.get("kind", "button"), f"{item_path}.kind", {"button", "fader"})
        if kind == "fader":
            if "button" in item:
                raise ConfigError(
                    f"{item_path}.button", "button ist nur bei kind = \"button\" erlaubt"
                )
            button = 1
        else:
            button = _int(item.get("button", 1), f"{item_path}.button")
            if not 1 <= button <= 3:
                raise ConfigError(f"{item_path}.button", "muss zwischen 1 und 3 liegen")
        accelerated = _bool(
            item.get("accelerated", False), f"{item_path}.accelerated"
        )
        if accelerated:
            if kind != "fader":
                raise ConfigError(
                    f"{item_path}.accelerated",
                    'nur bei kind = "fader" erlaubt',
                )
            if value_kinds.get(control) != "encoder":
                raise ConfigError(
                    f"{item_path}.accelerated",
                    "nur für absolute Encoder erlaubt",
                )
        transport = _transport(item, item_path)
        playbacks[control] = PlaybackMapping(
            page, executor, kind, button, accelerated, transport
        )

    device_banks: dict[str, DeviceBankSettings] = {}
    banks_raw = _table(data.get("device_banks", {}), f"{path}.device_banks")
    for device_name, raw_device in banks_raw.items():
        device_path = f"{path}.device_banks.{device_name}"
        device_item = _table(raw_device, device_path)
        if not devices or device_name not in devices:
            raise ConfigError(device_path, f"unbekanntes Gerät {device_name!r}")
        profile = profiles[devices[device_name].profile]
        valid_banks = {bank.number for bank in profile.banks} or {1}
        for key in device_item:
            if key != "bank_size":
                try:
                    int(key)
                except (TypeError, ValueError) as exc:
                    raise ConfigError(
                        device_path, f"unbekannter Schlüssel: {key}"
                    ) from exc
        bank_size: int | None = None
        if "bank_size" in device_item:
            bank_size = _int(device_item["bank_size"], f"{device_path}.bank_size")
            if bank_size < 1:
                raise ConfigError(f"{device_path}.bank_size", "muss mindestens 1 sein")
        layers: dict[int, DeviceBankMapping] = {}
        for key, raw_layer in device_item.items():
            if key == "bank_size":
                continue
            number = int(key)
            layer_path = f"{device_path}.{key}"
            if not 1 <= number <= 16:
                raise ConfigError(layer_path, "Bank muss zwischen 1 und 16 liegen")
            if number not in valid_banks:
                raise ConfigError(
                    layer_path, f"Bank {number} ist im Profil nicht definiert"
                )
            layer_item = _table(raw_layer, layer_path)
            _reject_unknown(
                layer_item, {"ma_page", "keys", "encoders", "playbacks"}, layer_path
            )
            ma_page: int | None = None
            if "ma_page" in layer_item:
                ma_page = _int(layer_item["ma_page"], f"{layer_path}.ma_page")
                if ma_page < 1:
                    raise ConfigError(f"{layer_path}.ma_page", "muss mindestens 1 sein")
            layer_keys: dict[str, KeyMapping] = {}
            layer_controls = profile.control_names
            layer_keys_raw = _table(
                layer_item.get("keys", {}), f"{layer_path}.keys"
            )
            for control, entry in layer_keys_raw.items():
                item_path = f"{layer_path}.keys.{control}"
                layer_keys[control] = _parse_key_mapping(
                    _table(entry, item_path), item_path, control, layer_controls
                )
            layer_encoders: dict[int, EncoderMapping] = {}
            profile_encoder_ids = set(profile.relative_encoder_ids.values())
            layer_encoders_raw = layer_item.get("encoders", [])
            if not isinstance(layer_encoders_raw, list):
                raise ConfigError(
                    f"{layer_path}.encoders", "muss ein Array of Tables sein"
                )
            for index, raw_encoder in enumerate(layer_encoders_raw):
                item_path = f"{layer_path}.encoders[{index}]"
                mapping = _parse_encoder_mapping(
                    _table(raw_encoder, item_path),
                    item_path,
                    profile_encoder_ids,
                )
                if mapping.id in layer_encoders:
                    raise ConfigError(
                        f"{item_path}.id", f"doppelte Encoder-ID {mapping.id}"
                    )
                layer_encoders[mapping.id] = mapping
            layer_playbacks: dict[str, PlaybackOverride] = {}
            layer_playbacks_raw = _table(
                layer_item.get("playbacks", {}), f"{layer_path}.playbacks"
            )
            for control, entry in layer_playbacks_raw.items():
                item_path = f"{layer_path}.playbacks.{control}"
                item = _table(entry, item_path)
                _reject_unknown(
                    item,
                    {"page", "executor", "kind", "button", "accelerated", "transport"},
                    item_path,
                )
                if control not in layer_controls:
                    raise ConfigError(
                        item_path,
                        f"Control {control!r} kommt im Profil {device_name!r} nicht vor",
                    )
                if not item:
                    raise ConfigError(item_path, "mindestens ein Feld angeben")
                page: int | str | None = None
                if "page" in item:
                    if item["page"] == "current":
                        page = "current"
                    else:
                        page = _int(item["page"], f"{item_path}.page")
                        if page < 1:
                            raise ConfigError(
                                f"{item_path}.page",
                                'muss mindestens 1 sein oder "current"',
                            )
                executor: int | None = None
                if "executor" in item:
                    executor = _int(item["executor"], f"{item_path}.executor")
                    if executor < 1:
                        raise ConfigError(
                            f"{item_path}.executor", "muss mindestens 1 sein"
                        )
                kind: str | None = None
                if "kind" in item:
                    kind = _choice(
                        item["kind"], f"{item_path}.kind", {"button", "fader"}
                    )
                button: int | None = None
                if "button" in item:
                    button = _int(item["button"], f"{item_path}.button")
                    if not 1 <= button <= 3:
                        raise ConfigError(
                            f"{item_path}.button", "muss zwischen 1 und 3 liegen"
                        )
                    if kind == "fader":
                        raise ConfigError(
                            f"{item_path}.button",
                            'button ist nur bei kind = "button" erlaubt',
                        )
                base = playbacks.get(control)
                effective_kind = kind or (base.kind if base is not None else "button")
                if button is not None and effective_kind == "fader":
                    raise ConfigError(
                        f"{item_path}.button",
                        'button ist nur bei kind = "button" erlaubt',
                    )
                accelerated: bool | None = None
                if "accelerated" in item:
                    accelerated = _bool(
                        item["accelerated"], f"{item_path}.accelerated"
                    )
                    if accelerated:
                        if effective_kind != "fader":
                            raise ConfigError(
                                f"{item_path}.accelerated",
                                'nur bei kind = "fader" erlaubt',
                            )
                        if value_kinds.get(control) != "encoder":
                            raise ConfigError(
                                f"{item_path}.accelerated",
                                "nur für absolute Encoder erlaubt",
                            )
                if executor is None and base is None:
                    raise ConfigError(item_path, "Executor fehlt und es gibt kein globales Ziel")
                if page is None and base is None:
                    raise ConfigError(item_path, "Page fehlt und es gibt kein globales Ziel")
                layer_playbacks[control] = PlaybackOverride(
                    page, executor, kind, button, accelerated, _transport(item, item_path)
                )
            layers[number] = DeviceBankMapping(
                ma_page, layer_keys, layer_encoders, layer_playbacks
            )
        device_banks[device_name] = DeviceBankSettings(bank_size, layers)

    return MappingSettings(
        modifiers=modifiers,
        keys=keys,
        encoders=tuple(encoders),
        screen_encoders=screen_encoders,
        playbacks=playbacks,
        device_banks=device_banks,
        acceleration=acceleration,
        value_acceleration=value_acceleration,
        resolution=resolution,
        combined_executors=combined_executors,
        topology_interval_ms=topology_interval_ms,
    )


def _validate_hardkey(value: Any, path: str) -> None:
    if not isinstance(value, str):
        raise ConfigError(path, "muss ein Hardkey-Name sein")
    try:
        hardkeys.resolve(value)
    except hardkeys.UnknownHardkey as exc:
        raise ConfigError(path, f"unbekannter Hardkey {value!r}") from exc


def _parse_acceleration(raw: Any) -> AccelerationSettings:
    if raw is None:
        return AccelerationSettings()
    path = "mapping.encoder_acceleration"
    data = _table(raw, path)
    _reject_unknown(data, {"curve", "window", "max_multiplier"}, path)
    curve = _choice(
        data.get("curve", "none"),
        f"{path}.curve",
        {"none", "linear", "exponential", "exponentiell"},
    )
    window = _float(data.get("window", 0.10), f"{path}.window")
    if window <= 0:
        raise ConfigError(f"{path}.window", "muss größer 0 sein")
    maximum = _float(data.get("max_multiplier", 4.0), f"{path}.max_multiplier")
    if maximum < 1:
        raise ConfigError(f"{path}.max_multiplier", "muss mindestens 1 sein")
    return AccelerationSettings(curve, window, maximum)


def _parse_value_acceleration(raw: Any) -> ValueAccelerationSettings:
    defaults = ValueAccelerationSettings()
    if raw is None:
        return defaults
    path = "mapping.value_acceleration"
    data = _table(raw, path)
    _reject_unknown(
        data, {"curve", "window", "slow_rate", "fast_rate", "max_multiplier"}, path
    )
    curve = _choice(
        data.get("curve", defaults.curve),
        f"{path}.curve",
        {"none", "linear", "exponential", "exponentiell"},
    )
    if curve == "exponentiell":
        curve = "exponential"
    window = _float(data.get("window", defaults.window), f"{path}.window")
    if window <= 0:
        raise ConfigError(f"{path}.window", "muss größer 0 sein")
    slow_rate = _int(data.get("slow_rate", defaults.slow_rate), f"{path}.slow_rate")
    if slow_rate < 1:
        raise ConfigError(f"{path}.slow_rate", "muss mindestens 1 sein")
    fast_rate = _int(data.get("fast_rate", defaults.fast_rate), f"{path}.fast_rate")
    if fast_rate <= slow_rate:
        raise ConfigError(f"{path}.fast_rate", "muss größer als slow_rate sein")
    maximum = _float(
        data.get("max_multiplier", defaults.max_multiplier), f"{path}.max_multiplier"
    )
    if maximum < 1:
        raise ConfigError(f"{path}.max_multiplier", "muss mindestens 1 sein")
    return ValueAccelerationSettings(curve, window, slow_rate, fast_rate, maximum)


def _parse_resolution(raw: Any, modifiers: Mapping[str, ModifierMapping]) -> ResolutionSettings:
    if raw is None:
        return ResolutionSettings()
    path = "mapping.encoder_resolution"
    data = _table(raw, path)
    _reject_unknown(data, {"wheel", "attribute", "modifiers"}, path)

    def parse_set(value: Any, sub_path: str, default: ResolutionSet) -> ResolutionSet:
        if value is None:
            return default
        item = _table(value, sub_path)
        _reject_unknown(item, {"normal", "fine", "ultra"}, sub_path)
        values = {}
        for key, fallback in (
            ("normal", default.normal),
            ("fine", default.fine),
            ("ultra", default.ultra),
        ):
            number = _float(item.get(key, fallback), f"{sub_path}.{key}")
            if number <= 0:
                raise ConfigError(f"{sub_path}.{key}", "muss größer 0 sein")
            values[key] = number
        return ResolutionSet(**values)

    wheel = parse_set(data.get("wheel"), f"{path}.wheel", ResolutionSet(1.0, 0.25, 0.1))
    attribute = parse_set(data.get("attribute"), f"{path}.attribute", ResolutionSet(1.0, 0.1, 0.01))
    mods = _table(data.get("modifiers", {}), f"{path}.modifiers")
    _reject_unknown(mods, {"fine", "ultra", "cycle"}, f"{path}.modifiers")
    fine = _string(mods["fine"], f"{path}.modifiers.fine") if "fine" in mods else ""
    ultra = _string(mods["ultra"], f"{path}.modifiers.ultra") if "ultra" in mods else ""
    cycle = _string(mods["cycle"], f"{path}.modifiers.cycle") if "cycle" in mods else ""
    for key, name in (("fine", fine), ("ultra", ultra), ("cycle", cycle)):
        if not name:
            continue
        if name not in modifiers:
            raise ConfigError(f"{path}.modifiers.{key}", f"Modifier {name!r} ist nicht definiert")
        if not modifiers[name].local:
            raise ConfigError(f"{path}.modifiers.{key}", f"Modifier {name!r} muss local sein")
    return ResolutionSettings(
        wheel=wheel,
        attribute=attribute,
        fine_modifier=fine,
        ultra_modifier=ultra,
        cycle_modifier=cycle,
    )


def parse_config(raw: Any, source_path: str = "") -> AppConfig:
    data = _table(raw, "config")
    _reject_unknown(
        data,
        {
            "schema_version",
            "ma2",
            "reconnect",
            "rate_limit",
            "logging",
            "devices",
            "profiles",
            "mapping",
            "hardkeys",
            "layouts",
            "encoder",
            "web",
            "led",
            "feedback",
            "screen_helper",
            "midi_remote",
        },
        "config",
    )
    version = _int(_require(data, "schema_version", "config"), "schema_version")
    if version != 1:
        raise ConfigError("schema_version", "wird nur Version 1 unterstützt")

    profiles = _parse_profiles(_require(data, "profiles", "config"))
    devices = _parse_devices(_require(data, "devices", "config"), profiles)
    ma2 = _parse_ma2(_require(data, "ma2", "config"))
    mapping = _parse_mapping(_require(data, "mapping", "config"), profiles, devices)
    layouts = _parse_layouts(data.get("layouts"), profiles)
    hardkey_codes = _parse_hardkeys(data.get("hardkeys"))
    if ma2.hardkey_transport == "lua":
        _require_hardkey_codes(mapping, hardkey_codes)
    reconnect = _parse_reconnect(data.get("reconnect", {}))
    rate_limit = _parse_rate_limit(data.get("rate_limit", {}))
    logging_settings = _parse_logging(data.get("logging", {}))
    web_settings = _parse_web(data.get("web", {}))
    led_settings = _parse_led(data.get("led", {}))
    feedback_settings = _parse_feedback(data.get("feedback", {}))
    midi_devices = [name for name, device in devices.items() if device.backend == "midi"]
    if led_settings.device is not None and led_settings.device not in devices:
        raise ConfigError(
            "led.device",
            f"unbekanntes Gerät {led_settings.device!r}",
        )
    if len(midi_devices) > 1 and led_settings.device is None and led_settings.enabled:
        raise ConfigError(
            "led.device",
            "bei mehreren MIDI-Geräten muss das LED-Gerät explizit gesetzt sein "
            f"(konfiguriert: {', '.join(sorted(midi_devices))})",
        )
    screen_helper_settings = _parse_screen_helper(data.get("screen_helper", {}))
    midi_remote_settings = _parse_midi_remote(data.get("midi_remote", {}))

    config = AppConfig(
        schema_version=version,
        ma2=ma2,
        devices=devices,
        profiles=profiles,
        mapping=mapping,
        hardkeys=hardkey_codes,
        layouts=layouts,
        reconnect=reconnect,
        rate_limit=rate_limit,
        logging=logging_settings,
        web=web_settings,
        led=led_settings,
        feedback=feedback_settings,
        screen_helper=screen_helper_settings,
        midi_remote=midi_remote_settings,
        source_path=source_path,
    )
    _check_led_note_owner(config)
    _check_playback_transports(config)
    _check_midi_address_space(config)
    return config


def _check_led_note_owner(config: AppConfig) -> None:
    """A button LED belongs either to a fixed ``[led]`` function or to feedback."""

    led = config.led
    if not led.enabled:
        return
    device = led.device
    if device is None:
        midi_devices = [
            name for name, item in config.devices.items() if item.backend == "midi"
        ]
        if len(midi_devices) != 1:
            return
        device = midi_devices[0]
    owners = {
        led.note: "led.note",
        led.fine_note: "led.fine_note",
        led.nipple_note: "led.nipple_note",
    }
    targets, _ = build_feedback_targets(config)
    for target in targets:
        owner = owners.get(target.note) if target.device == device else None
        if owner is not None:
            raise ConfigError(
                owner,
                f"Note {target.note} an {device} ist zugleich LED-Feedback-Ziel "
                f"mapping.playbacks.{target.control}",
            )


def load_config(path: str | Path) -> AppConfig:
    source = Path(path)
    try:
        with source.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(str(source), "Datei nicht gefunden") from exc
    except OSError as exc:
        raise ConfigError(str(source), f"Datei nicht lesbar: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(str(source), f"ungültiges TOML: {exc}") from exc
    try:
        return parse_config(raw, source_path=str(source))
    except ConfigError as exc:
        location = f"{source}:{exc.path}" if exc.path else str(source)
        raise ConfigError(location, exc.detail) from exc


def find_config(explicit: str | None = None) -> AppConfig:
    if explicit:
        return load_config(explicit)
    for candidate in DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return load_config(candidate)
    raise ConfigError("config", "keine Konfigurationsdatei gefunden; --config angeben")
