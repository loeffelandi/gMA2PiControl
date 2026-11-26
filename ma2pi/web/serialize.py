"""Safe, canonical TOML-shaped JSON representation of the configuration."""

from __future__ import annotations

from typing import Any

from ..config import (
    AppConfig,
    DeviceBankMapping,
    EncoderMapping,
    KeyMapping,
    LayoutCell,
    PlaybackMapping,
    PlaybackOverride,
    ProfileConfig,
)


def _serialize_key(entry: KeyMapping) -> dict[str, Any]:
    if entry.hardkey is not None:
        return {"hardkey": entry.hardkey}
    if entry.command is not None:
        return {"command": entry.command}
    if entry.screen_mode:
        return {"screen_mode": True}
    if entry.encoder_press is not None:
        return {"encoder_press": entry.encoder_press}
    if entry.screen is not None:
        return {"screen": entry.screen}
    return {}


def _serialize_encoder(entry: EncoderMapping) -> dict[str, Any]:
    if entry.slot is not None:
        return {"id": entry.id, "slot": entry.slot}
    return {"id": entry.id, "attribute": entry.attribute}


def _serialize_playback(entry: PlaybackMapping) -> dict[str, Any]:
    out: dict[str, Any] = {
        "page": entry.page,
        "executor": entry.executor,
        "kind": entry.kind,
    }
    if entry.kind == "button":
        out["button"] = entry.button
    elif entry.accelerated:
        out["accelerated"] = True
    return out


def _serialize_playback_override(entry: PlaybackOverride) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if entry.page is not None:
        out["page"] = entry.page
    if entry.executor is not None:
        out["executor"] = entry.executor
    if entry.kind is not None:
        out["kind"] = entry.kind
    if entry.button is not None:
        out["button"] = entry.button
    if entry.accelerated is not None:
        out["accelerated"] = entry.accelerated
    return out


def _serialize_bank_layer(layer: DeviceBankMapping) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if layer.ma_page is not None:
        out["ma_page"] = layer.ma_page
    if layer.keys:
        out["keys"] = {
            ctrl: _serialize_key(entry) for ctrl, entry in layer.keys.items()
        }
    if layer.encoders:
        out["encoders"] = [
            _serialize_encoder(entry)
            for _, entry in sorted(layer.encoders.items())
        ]
    if layer.playbacks:
        out["playbacks"] = {
            ctrl: _serialize_playback_override(entry)
            for ctrl, entry in layer.playbacks.items()
        }
    return out


def _serialize_cell(cell: LayoutCell) -> dict[str, Any]:
    out: dict[str, Any] = {"label": cell.label}
    if cell.control is not None:
        out["control"] = cell.control
    if cell.col_span != 1:
        out["col_span"] = cell.col_span
    if cell.row_span != 1:
        out["row_span"] = cell.row_span
    if cell.color is not None:
        out["color"] = cell.color
    if cell.row is not None:
        out["row"] = cell.row
    if cell.col is not None:
        out["col"] = cell.col
    return out


def _serialize_profile(profile: ProfileConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if profile.keys:
        out["keys"] = dict(profile.keys)
    if profile.encoders:
        out["encoders"] = [
            {
                "id": enc.id,
                "control": enc.control,
                "detents_per_revolution": enc.detents_per_revolution,
                "direction": enc.direction,
                "threshold": enc.threshold,
            }
            for enc in profile.encoders
        ]
    if profile.controls:
        out["controls"] = [
            {
                "id": ctrl.id,
                "kind": ctrl.kind,
                **({"label": ctrl.label} if ctrl.label is not None else {}),
                **(
                    {"encoder_id": ctrl.encoder_id}
                    if ctrl.encoder_id is not None
                    and ctrl.id != f"encoder.{ctrl.encoder_id}"
                    else {}
                ),
            }
            for ctrl in profile.controls
        ]
    if profile.banks:
        out["banks"] = [
            {
                "number": bank.number,
                "channel": bank.channel,
                "notes": {str(note): ctrl for note, ctrl in bank.notes.items()},
            }
            for bank in profile.banks
        ]
    else:
        if profile.notes:
            out["notes"] = {
                str(note): ctrl for note, ctrl in profile.notes.items()
            }
        if profile.midi_encoders:
            out["midi_encoders"] = [
                {
                    "id": enc.id,
                    "note": enc.note,
                    "cw_velocity": enc.cw_velocity,
                    "ccw_velocity": enc.ccw_velocity,
                    "direction": enc.direction,
                }
                for enc in profile.midi_encoders
            ]
        if profile.midi_values:
            out["midi_values"] = [
                {"control": val.control, "note": val.note, "kind": val.kind}
                for val in profile.midi_values
            ]
    if profile.led_feedback is not None:
        fb = profile.led_feedback
        fb_out: dict[str, Any] = {
            "protocol": fb.protocol,
            "enabled": fb.enabled,
            "frame_interval_ms": fb.frame_interval_ms,
        }
        if fb.notes is not None:
            fb_out["led_notes"] = list(fb.notes)
        out["led_feedback"] = fb_out
    return out


def redacted_config(config: AppConfig) -> dict[str, Any]:
    """Return the configuration in canonical TOML shape without secrets.

    The password value, its file and its environment variable name never leave
    the daemon.  ``password_set`` and ``pin_set`` tell the UI whether secrets
    are configured, while every other section matches the schema accepted by
    ``PUT /api/config`` and ``POST /api/config/validate``.
    """

    ma2 = config.ma2
    mapping = config.mapping
    res = mapping.resolution
    acc = mapping.acceleration
    vacc = mapping.value_acceleration
    led = config.led

    led_out: dict[str, Any] = {
        "enabled": led.enabled,
        "note": led.note,
        "attribute_color": led.attribute_color,
        "screen_color": led.screen_color,
        "brightness": led.brightness,
        "brightness_channel": led.brightness_channel,
        "color_channel": led.color_channel,
        "nipple_note": led.nipple_note,
        "nipple_idle_color": led.nipple_idle_color,
        "nipple_idle_brightness": led.nipple_idle_brightness,
        "nipple_pressed_color": led.nipple_pressed_color,
        "nipple_pressed_brightness": led.nipple_pressed_brightness,
        "fine_note": led.fine_note,
        "fine_color": led.fine_color,
        "fine_idle_brightness": led.fine_idle_brightness,
        "fine_pressed_brightness": led.fine_pressed_brightness,
    }
    if led.device is not None:
        led_out["device"] = led.device

    res_mods = {
        key: value
        for key, value in (
            ("fine", res.fine_modifier),
            ("ultra", res.ultra_modifier),
            ("cycle", res.cycle_modifier),
        )
        if value
    }

    device_banks_out: dict[str, Any] = {}
    for dev_name, settings in mapping.device_banks.items():
        dev_table: dict[str, Any] = {}
        if settings.bank_size is not None:
            dev_table["bank_size"] = settings.bank_size
        for bank_num, layer in sorted(settings.banks.items()):
            dev_table[str(bank_num)] = _serialize_bank_layer(layer)
        device_banks_out[dev_name] = dev_table

    layouts_out: dict[str, Any] = {}
    for profile_key, layout in config.layouts.items():
        layout_key = layout.name or profile_key
        layouts_out[layout_key] = {
            "profile": layout.profile,
            "columns": layout.columns,
            "rows": [
                {"cells": [_serialize_cell(cell) for cell in row.cells]}
                for row in layout.rows
            ],
        }

    return {
        "schema_version": config.schema_version,
        "ma2": {
            "host": ma2.host,
            "port": ma2.port,
            "path": ma2.path,
            "username": ma2.username,
            "keepalive_interval": ma2.keepalive_interval,
            "login_timeout": ma2.login_timeout,
            "hardkey_transport": ma2.hardkey_transport,
            "hardkey_hold_threshold": ma2.hardkey_hold_threshold,
            "hardkey_press_value": ma2.hardkey_press_value,
            "hardkey_release_value": ma2.hardkey_release_value,
            "page_refresh_interval": ma2.page_refresh_interval,
            "password_set": bool(ma2.password_file or ma2.password_env),
        },
        "devices": {
            name: {
                "vendor_id": dev.vendor_id,
                "product_id": dev.product_id,
                **(
                    {"name_contains": dev.name_contains}
                    if dev.name_contains is not None
                    else {}
                ),
                "profile": dev.profile,
                "backend": dev.backend,
            }
            for name, dev in config.devices.items()
        },
        "profiles": {
            name: _serialize_profile(prof)
            for name, prof in config.profiles.items()
        },
        "mapping": {
            "modifiers": {
                ctrl: ({"local": True} if mod.local else {"hardkey": mod.hardkey})
                for ctrl, mod in mapping.modifiers.items()
            },
            "keys": {
                ctrl: _serialize_key(entry)
                for ctrl, entry in mapping.keys.items()
            },
            "encoders": [_serialize_encoder(enc) for enc in mapping.encoders],
            "screen_encoders": {
                str(slot): num for slot, num in mapping.screen_encoders.items()
            },
            "playbacks": {
                ctrl: _serialize_playback(entry)
                for ctrl, entry in mapping.playbacks.items()
            },
            "device_banks": device_banks_out,
            "encoder_acceleration": {
                "curve": acc.curve,
                "window": acc.window,
                "max_multiplier": acc.max_multiplier,
            },
            "value_acceleration": {
                "curve": vacc.curve,
                "window": vacc.window,
                "slow_rate": vacc.slow_rate,
                "fast_rate": vacc.fast_rate,
                "max_multiplier": vacc.max_multiplier,
            },
            "encoder_resolution": {
                "wheel": {
                    "normal": res.wheel.normal,
                    "fine": res.wheel.fine,
                    "ultra": res.wheel.ultra,
                },
                "attribute": {
                    "normal": res.attribute.normal,
                    "fine": res.attribute.fine,
                    "ultra": res.attribute.ultra,
                },
                "modifiers": res_mods,
            },
        },
        "hardkeys": {
            name: {"code": hc.code, "verified": hc.verified}
            for name, hc in config.hardkeys.items()
        },
        "layouts": layouts_out,
        "reconnect": {
            "initial_delay": config.reconnect.initial_delay,
            "max_delay": config.reconnect.max_delay,
            "jitter": config.reconnect.jitter,
            "login_failure_delay": config.reconnect.login_failure_delay,
        },
        "rate_limit": {
            "messages_per_second": config.rate_limit.messages_per_second,
            "burst": config.rate_limit.burst,
            "encoder_base_interval": config.rate_limit.encoder_base_interval,
            "encoder_stream_penalty": config.rate_limit.encoder_stream_penalty,
            "encoder_idle_base": config.rate_limit.encoder_idle_base,
            "encoder_idle_penalty": config.rate_limit.encoder_idle_penalty,
            "max_pending_delta": config.rate_limit.max_pending_delta,
        },
        "logging": {"level": config.logging.level},
        "web": {
            "bind": config.web.bind,
            "port": config.web.port,
            "pin_enabled": config.web.pin_enabled,
            "pin_set": bool(config.web.pin),
        },
        "led": led_out,
        "feedback": {
            "enabled": config.feedback.enabled,
            "interval_ms": config.feedback.interval_ms,
            "off_state": config.feedback.off_state,
            "fallback_color": config.feedback.fallback_color,
        },
        "screen_helper": {
            "enabled": config.screen_helper.enabled,
            "host": config.screen_helper.host,
            "port": config.screen_helper.port,
        },
    }
