"""Structured logging with secret redaction.

Frame logs are one line per frame and always carry direction, frame type and
session id.  A filter removes password values and 32 character MD5 hashes as a
defence in depth; the normal code paths never pass secrets to the logger.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_SECRET_KEYS = re.compile(
    r"(?i)(password|passwd|pwd|password_hash|md5)\s*[=:]\s*('([^']*)'|\"([^\"]*)\"|[^\s,;]+)"
)
_MD5 = re.compile(r"\b[0-9a-fA-F]{32}\b")


class RedactionFilter(logging.Filter):
    """Redact passwords and MD5-like values from formatted records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = _SECRET_KEYS.sub(lambda match: f"{match.group(1)}=***", message)
        redacted = _MD5.sub("***", redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(level: str = "INFO", stream: Any = None) -> None:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def log_frame(
    logger: logging.Logger,
    direction: str,
    frame_type: str,
    session: int | None = None,
    **fields: Any,
) -> None:
    """Log one frame in a stable, greppable one-line format."""

    parts = [f"frame direction={direction}", f"type={frame_type}"]
    if session is not None:
        parts.append(f"session={session}")
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).replace("\n", "\\n")
        if any(ch.isspace() for ch in text) or "'" in text:
            text = "'" + text.replace("'", "\\'") + "'"
        parts.append(f"{key}={text}")
    logger.info(" ".join(parts))
