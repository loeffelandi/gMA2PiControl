"""Structured logging with secret redaction.

Frame logs are one line per frame and always carry direction, frame type and
session id.  Both a filter and formatter scrub passwords, PINs, PSKs, tokens
and 32-character MD5 hashes across plain text, Python dicts, JSON strings and
exception tracebacks.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_SECRET_KEYS = re.compile(
    r"""(?i)(?P<prefix>["']?(?:password|passwd|pwd|password_hash|md5|pin|psk|wifi-sec\.psk|token|ma2pi_pin)["']?\s*[=:]\s*)(?:'[^']*'|\"[^\"]*\"|[^\s,;\}\]]+)"""
)
_MD5 = re.compile(r"\b[0-9a-fA-F]{32}\b")


def redact_text(text: str) -> str:
    """Replace secret values and 32-hex MD5 digests in ``text`` with ``***``."""

    redacted = _SECRET_KEYS.sub(lambda match: f"{match.group('prefix')}***", text)
    return _MD5.sub("***", redacted)


class RedactionFilter(logging.Filter):
    """Redact secrets from log messages before handlers inspect ``record``."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """Format records (including ``exc_info`` tracebacks) and scrub secrets."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def setup_logging(level: str = "INFO", stream: Any = None) -> None:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        RedactingFormatter(
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
