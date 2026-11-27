"""Resolve ``[mapping.playbacks]`` targets per device, bank and control.

The router resolves one event at a time; the MIDI remote sync needs every
target the router could ever send.  Both use the functions here so a remote
always exists for the executor a press is routed to.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig, effective_transport


@dataclass(frozen=True, slots=True)
class PlaybackTarget:
    page: int | str
    executor: int
    kind: str
    button: int
    accelerated: bool
    transport: str = "web"


def bank_size(config: AppConfig, device: str) -> int:
    """Executor offset between two banks of ``device``."""

    settings = config.mapping.device_banks.get(device)
    if settings is not None and settings.bank_size is not None:
        return settings.bank_size
    device_config = config.devices.get(device)
    if device_config is None:
        return 1
    kinds = config.profiles[device_config.profile].control_kinds
    faders = sum(1 for kind in kinds.values() if kind == "fader")
    if faders:
        return faders
    buttons = sum(1 for kind in kinds.values() if kind == "button")
    return max(1, buttons)


def resolve_target(
    config: AppConfig, device: str, bank: int, control: str
) -> PlaybackTarget | None:
    """Merge the global target with the bank layer of ``device``."""

    base = config.mapping.playbacks.get(control)
    settings = config.mapping.device_banks.get(device)
    layer = settings.banks.get(bank) if settings is not None else None
    override = layer.playbacks.get(control) if layer is not None else None
    if base is None and override is None:
        return None

    def pick(name: str, default):
        if override is not None and getattr(override, name) is not None:
            return getattr(override, name)
        if base is not None:
            return getattr(base, name)
        return default

    page = pick("page", None)
    executor = pick("executor", None)
    if page is None or executor is None:
        return None
    if (
        settings is not None
        and bank > 1
        and (override is None or override.executor is None)
        and (layer is None or layer.ma_page is None)
    ):
        executor += (bank - 1) * bank_size(config, device)
    kind = pick("kind", "button")
    transport = effective_transport(
        kind, pick("transport", None), config.midi_remote.enabled
    )
    return PlaybackTarget(
        page=page,
        executor=executor,
        kind=kind,
        button=pick("button", 1),
        accelerated=pick("accelerated", False),
        transport=transport,
    )


def device_banks(config: AppConfig, device: str) -> tuple[int, ...]:
    profile = config.profiles[config.devices[device].profile]
    return tuple(sorted(bank.number for bank in profile.banks)) or (1,)


def midi_button_targets(config: AppConfig) -> set[tuple[int | str, int, int]]:
    """Every ``(page, executor, button)`` a press may send over MIDI."""

    targets: set[tuple[int | str, int, int]] = set()
    for device, device_config in config.devices.items():
        controls = config.profiles[device_config.profile].control_names
        for bank in device_banks(config, device):
            for control in sorted(controls):
                target = resolve_target(config, device, bank, control)
                if target is None or target.kind != "button":
                    continue
                if target.transport == "midi":
                    targets.add((target.page, target.executor, target.button))
    return targets
