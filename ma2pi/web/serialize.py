"""Safe JSON representation of the configuration for the UI."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..config import AppConfig


def redacted_config(config: AppConfig) -> dict[str, Any]:
    """Return the configuration as JSON without any password material.

    The password value, its file and its environment variable name never leave
    the daemon.  ``password_set`` tells the UI whether a source is configured.
    """

    data = asdict(config)
    data.pop("source_path", None)
    ma2 = data.get("ma2", {})
    ma2.pop("password_file", None)
    ma2.pop("password_env", None)
    ma2["password_set"] = bool(config.ma2.password_file or config.ma2.password_env)
    web = data.get("web", {})
    web.pop("pin", None)
    web["pin_set"] = bool(config.web.pin)
    return data
