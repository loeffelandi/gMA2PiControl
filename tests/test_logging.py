from __future__ import annotations

import io
import logging

from ma2pi.logging_setup import log_frame, setup_logging


def test_frame_log_format():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    logger = logging.getLogger("ma2pi.test")
    log_frame(logger, "tx", "hardkeyPress", 7, hardkey=41, value=1.0)
    output = stream.getvalue()
    assert "direction=tx" in output
    assert "type=hardkeyPress" in output
    assert "session=7" in output
    assert "hardkey=41" in output


def test_secrets_are_redacted():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    logger = logging.getLogger("ma2pi.test")
    md5 = "5ebe2294ecd0e0f08eab7690d2a6ee69"
    logger.info("login password=%s", md5)
    logger.info("password_hash=%s", md5)
    output = stream.getvalue()
    assert md5 not in output
    assert "***" in output


def test_password_keyword_is_redacted():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    logging.getLogger("ma2pi.test").info("password='hunter2'")
    output = stream.getvalue()
    assert "hunter2" not in output
