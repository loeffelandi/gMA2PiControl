"""Device and logical-control descriptions for the configuration UI."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from ..config import AppConfig, DeviceConfig, ProfileConfig
from ..hid_input import DeviceInfo, device_matches, list_devices
from ..midi_input import list_midi_devices

LOGGER = logging.getLogger("ma2pi.web.devices")


def _controls(profile: ProfileConfig) -> dict[str, Any]:
    keys = [
        {"code": code, "control": control}
        for code, control in sorted(profile.keys.items())
    ]
    notes = [
        {"note": note, "control": control}
        for note, control in sorted(profile.notes.items())
    ]
    encoders = [
        {
            "id": encoder.id,
            "control": f"encoder.{encoder.id}",
            "axis": encoder.control,
            "detents_per_revolution": encoder.detents_per_revolution,
            "direction": encoder.direction,
            "threshold": encoder.threshold,
        }
        for encoder in profile.encoders
    ]
    midi_encoders = [
        {
            "id": encoder.id,
            "control": f"encoder.{encoder.id}",
            "note": encoder.note,
            "cw_velocity": encoder.cw_velocity,
            "ccw_velocity": encoder.ccw_velocity,
            "direction": encoder.direction,
        }
        for encoder in profile.midi_encoders
    ]
    logical = sorted(
        {entry["control"] for entry in keys}
        | {entry["control"] for entry in notes}
        | {entry["control"] for entry in encoders}
        | {entry["control"] for entry in midi_encoders}
    )
    return {
        "keys": keys,
        "notes": notes,
        "encoders": encoders,
        "midi_encoders": midi_encoders,
        "logical": logical,
    }


def _detected(info: DeviceInfo) -> dict[str, Any]:
    return {
        "path": info.path,
        "name": info.name,
        "vendor_id": info.vendor_id,
        "product_id": info.product_id,
        "vendor_product": f"{info.vendor_id:04x}:{info.product_id:04x}",
        "readable": info.readable,
        "backend": info.backend,
        "phys": info.phys,
        "error": info.error,
    }


def _entry(
    name: str,
    device: DeviceConfig,
    profile: ProfileConfig,
    match: DeviceInfo | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "backend": device.backend,
        "profile": device.profile,
        "vendor_id": device.vendor_id,
        "product_id": device.product_id,
        "vendor_product": f"{device.vendor_id:04x}:{device.product_id:04x}",
        "name_contains": device.name_contains,
        "detected": _detected(match) if match is not None else None,
        "controls": _controls(profile),
    }


def device_summary(
    config: AppConfig,
    detected: Iterable[DeviceInfo] | None = None,
) -> list[dict[str, Any]]:
    """Describe every configured device, optionally matched to live hardware."""

    pool = list(detected or [])
    result: list[dict[str, Any]] = []
    for name, device in config.devices.items():
        match = next(
            (
                info
                for info in pool
                if info.backend == device.backend and device_matches(device, info)
            ),
            None,
        )
        profile = config.profiles[device.profile]
        result.append(_entry(name, device, profile, match))
    return result


def detect_devices(config: AppConfig) -> list[dict[str, Any]]:
    """Enumerate hardware and merge it into the configured device list."""

    pool: list[DeviceInfo] = []
    try:
        pool.extend(list_devices())
    except Exception as exc:  # pragma: no cover - platform dependent
        LOGGER.info("evdev-Enumeration nicht verfügbar: %s", exc)
    try:
        pool.extend(list_midi_devices())
    except Exception as exc:  # pragma: no cover - platform dependent
        LOGGER.info("MIDI-Enumeration nicht verfügbar: %s", exc)
    return device_summary(config, pool)
