"""Strict TOML configuration loading and validation.

Every unknown key is an error.  References between devices, profiles and the
mapping are checked before the daemon starts, so an invalid file can never
produce frames.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import hardkeys
from .led_output import LedSettings, parse_color

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
    running server keeps its listener.  ``pin_enabled`` is a prepared extension
    point and stays disabled in v1.
    """

    bind: str = "0.0.0.0"
    port: int = 8080
    pin_enabled: bool = False


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
class ProfileConfig:
    keys: Mapping[str, str] = field(default_factory=dict)
    encoders: tuple[EncoderProfile, ...] = ()
    notes: Mapping[int, str] = field(default_factory=dict)
    midi_encoders: tuple[MidiEncoderProfile, ...] = ()


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
    encoder_fine: int | None = None


@dataclass(frozen=True, slots=True)
class EncoderMapping:
    id: int
    slot: int | None = None
    attribute: str | None = None


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


@dataclass(frozen=True, slots=True)
class MappingSettings:
    modifiers: Mapping[str, ModifierMapping] = field(default_factory=dict)
    keys: Mapping[str, KeyMapping] = field(default_factory=dict)
    encoders: tuple[EncoderMapping, ...] = ()
    screen_encoders: Mapping[int, str] = field(default_factory=dict)
    acceleration: AccelerationSettings = field(default_factory=AccelerationSettings)
    resolution: ResolutionSettings = field(default_factory=ResolutionSettings)


@dataclass(frozen=True, slots=True)
class AppConfig:
    schema_version: int
    ma2: Ma2Settings
    devices: Mapping[str, DeviceConfig]
    profiles: Mapping[str, ProfileConfig]
    mapping: MappingSettings
    hardkeys: Mapping[str, HardkeyCode] = field(default_factory=dict)
    reconnect: ReconnectSettings = field(default_factory=ReconnectSettings)
    rate_limit: RateLimitSettings = field(default_factory=RateLimitSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    web: WebSettings = field(default_factory=WebSettings)
    led: LedSettings = field(default_factory=LedSettings)
    source_path: str = ""

    def profile_for_device(self, name: str) -> ProfileConfig:
        return self.profiles[self.devices[name].profile]

    @property
    def mapped_controls(self) -> set[str]:
        controls: set[str] = set()
        for profile in self.profiles.values():
            controls.update(profile.keys.values())
            controls.update(profile.notes.values())
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
    return float(value)


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
        screen_color = parse_color(data.get("screen_color", "green"))
    except ValueError as exc:
        raise ConfigError(f"{path}.attribute_color", str(exc)) from exc
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

    return LedSettings(
        enabled=enabled,
        device=device,
        note=note,
        attribute_color=attribute_color,
        screen_color=screen_color,
        brightness=brightness,
        brightness_channel=brightness_channel,
        color_channel=color_channel,
    )


def _parse_web(raw: Any) -> WebSettings:
    path = "web"
    data = _table(raw, path)
    _reject_unknown(data, {"bind", "port", "pin_enabled"}, path)
    bind = _string(data.get("bind", "0.0.0.0"), f"{path}.bind")
    port = _int(data.get("port", 8080), f"{path}.port")
    if not 1 <= port <= 65535:
        raise ConfigError(f"{path}.port", "muss zwischen 1 und 65535 liegen")
    pin_enabled = _bool(data.get("pin_enabled", False), f"{path}.pin_enabled")
    if pin_enabled:
        raise ConfigError(
            f"{path}.pin_enabled",
            "PIN-Sperre ist in dieser Version noch nicht implementiert",
        )
    return WebSettings(bind=bind, port=port, pin_enabled=pin_enabled)


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
    for name, entry in data.items():
        item_path = f"{path}.{name}"
        item = _table(entry, item_path)
        _reject_unknown(item, {"keys", "encoders", "notes", "midi_encoders"}, item_path)
        keys_raw = _table(item.get("keys", {}), f"{item_path}.keys")
        keys: dict[str, str] = {}
        for code, control in keys_raw.items():
            control = _string(control, f"{item_path}.keys.{code}")
            keys[code] = control
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
            notes[note] = _string(control, note_path)

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

        profiles[name] = ProfileConfig(
            keys=keys,
            encoders=tuple(encoders),
            notes=notes,
            midi_encoders=tuple(midi_encoders),
        )
    return profiles


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

    for control, value in sorted(used.items()):
        canonical = hardkeys.resolve(value)
        if canonical not in codes:
            raise ConfigError(
                f"hardkeys.{canonical}",
                f"fehlender Keycode für Hardkey {canonical!r} (verwendet von {control})",
            )


def _parse_mapping(raw: Any, profiles: Mapping[str, ProfileConfig]) -> MappingSettings:
    path = "mapping"
    data = _table(raw, path)
    _reject_unknown(
        data,
        {
            "modifiers",
            "keys",
            "encoders",
            "screen_encoders",
            "encoder_acceleration",
            "encoder_resolution",
        },
        path,
    )
    controls: set[str] = set()
    encoder_ids: set[int] = set()
    for profile in profiles.values():
        controls.update(profile.keys.values())
        controls.update(profile.notes.values())
        encoder_ids.update(enc.id for enc in profile.encoders)
        encoder_ids.update(enc.id for enc in profile.midi_encoders)

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
        item = _table(entry, item_path)
        _reject_unknown(
            item, {"hardkey", "command", "screen_mode", "encoder_fine"}, item_path
        )
        if control not in controls:
            raise ConfigError(item_path, f"Control {control!r} kommt in keinem Profil vor")
        kinds = [
            name
            for name in ("hardkey", "command", "screen_mode", "encoder_fine")
            if name in item
        ]
        if len(kinds) != 1:
            raise ConfigError(
                item_path,
                "genau eines von hardkey, command, screen_mode oder encoder_fine angeben",
            )
        kind = kinds[0]
        if kind == "hardkey":
            _validate_hardkey(item["hardkey"], f"{item_path}.hardkey")
            keys[control] = KeyMapping(hardkey=item["hardkey"])
        elif kind == "command":
            keys[control] = KeyMapping(
                command=_string(item["command"], f"{item_path}.command")
            )
        elif kind == "screen_mode":
            keys[control] = KeyMapping(
                screen_mode=_bool(item["screen_mode"], f"{item_path}.screen_mode")
            )
        else:
            slot = _int(item["encoder_fine"], f"{item_path}.encoder_fine")
            if not 1 <= slot <= 8:
                raise ConfigError(f"{item_path}.encoder_fine", "muss zwischen 1 und 8 liegen")
            keys[control] = KeyMapping(encoder_fine=slot)

    encoders_raw = data.get("encoders", [])
    if not isinstance(encoders_raw, list):
        raise ConfigError(f"{path}.encoders", "muss ein Array of Tables sein")
    encoders: list[EncoderMapping] = []
    seen_ids: set[int] = set()
    for index, raw_encoder in enumerate(encoders_raw):
        item_path = f"{path}.encoders[{index}]"
        item = _table(raw_encoder, item_path)
        _reject_unknown(item, {"id", "slot", "attribute"}, item_path)
        enc_id = _int(_require(item, "id", item_path), f"{item_path}.id")
        if enc_id <= 0:
            raise ConfigError(f"{item_path}.id", "muss größer 0 sein")
        if enc_id in seen_ids:
            raise ConfigError(f"{item_path}.id", f"doppelte Encoder-ID {enc_id}")
        seen_ids.add(enc_id)
        if enc_id not in encoder_ids:
            raise ConfigError(f"{item_path}.id", f"Encoder-ID {enc_id} kommt in keinem Profil vor")
        has_slot = "slot" in item
        has_attribute = "attribute" in item
        if has_slot == has_attribute:
            raise ConfigError(item_path, "genau eines von slot oder attribute angeben")
        if has_slot:
            slot = _int(item["slot"], f"{item_path}.slot")
            if not 1 <= slot <= 8:
                raise ConfigError(f"{item_path}.slot", "muss zwischen 1 und 8 liegen")
            encoders.append(EncoderMapping(id=enc_id, slot=slot))
        else:
            attribute = _string(item["attribute"], f"{item_path}.attribute")
            encoders.append(EncoderMapping(id=enc_id, attribute=attribute))

    screen_raw = _table(data.get("screen_encoders", {}), f"{path}.screen_encoders")
    screen_encoders: dict[int, str] = {}
    for slot_key, name in screen_raw.items():
        slot_path = f"{path}.screen_encoders.{slot_key}"
        try:
            slot = int(slot_key)
        except (TypeError, ValueError) as exc:
            raise ConfigError(slot_path, "muss zwischen 1 und 4 liegen") from exc
        if not 1 <= slot <= 4:
            raise ConfigError(slot_path, "muss zwischen 1 und 4 liegen")
        screen_encoders[slot] = _string(name, slot_path)

    acceleration = _parse_acceleration(data.get("encoder_acceleration"))
    resolution = _parse_resolution(data.get("encoder_resolution"), modifiers)
    return MappingSettings(
        modifiers=modifiers,
        keys=keys,
        encoders=tuple(encoders),
        screen_encoders=screen_encoders,
        acceleration=acceleration,
        resolution=resolution,
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
    _reject_unknown(mods, {"fine", "ultra"}, f"{path}.modifiers")
    fine = _string(mods["fine"], f"{path}.modifiers.fine") if "fine" in mods else ""
    ultra = _string(mods["ultra"], f"{path}.modifiers.ultra") if "ultra" in mods else ""
    for key, name in (("fine", fine), ("ultra", ultra)):
        if not name:
            continue
        if name not in modifiers:
            raise ConfigError(f"{path}.modifiers.{key}", f"Modifier {name!r} ist nicht definiert")
        if not modifiers[name].local:
            raise ConfigError(f"{path}.modifiers.{key}", f"Modifier {name!r} muss local sein")
    return ResolutionSettings(wheel=wheel, attribute=attribute, fine_modifier=fine, ultra_modifier=ultra)


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
            "encoder",
            "web",
            "led",
        },
        "config",
    )
    version = _int(_require(data, "schema_version", "config"), "schema_version")
    if version != 1:
        raise ConfigError("schema_version", "wird nur Version 1 unterstützt")

    profiles = _parse_profiles(_require(data, "profiles", "config"))
    devices = _parse_devices(_require(data, "devices", "config"), profiles)
    ma2 = _parse_ma2(_require(data, "ma2", "config"))
    mapping = _parse_mapping(_require(data, "mapping", "config"), profiles)
    hardkey_codes = _parse_hardkeys(data.get("hardkeys"))
    if ma2.hardkey_transport == "lua":
        _require_hardkey_codes(mapping, hardkey_codes)
    reconnect = _parse_reconnect(data.get("reconnect", {}))
    rate_limit = _parse_rate_limit(data.get("rate_limit", {}))
    logging_settings = _parse_logging(data.get("logging", {}))
    web_settings = _parse_web(data.get("web", {}))
    led_settings = _parse_led(data.get("led", {}))

    return AppConfig(
        schema_version=version,
        ma2=ma2,
        devices=devices,
        profiles=profiles,
        mapping=mapping,
        hardkeys=hardkey_codes,
        reconnect=reconnect,
        rate_limit=rate_limit,
        logging=logging_settings,
        web=web_settings,
        led=led_settings,
        source_path=source_path,
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
