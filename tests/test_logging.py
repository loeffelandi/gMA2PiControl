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


def test_dict_json_pin_psk_and_traceback_secrets_are_redacted():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    logger = logging.getLogger("ma2pi.test")
    logger.info("payload=%r", {"password": "dict-secret", "pin": "9876", "psk": "wlan-geheim"})
    logger.info('json={"password": "json-secret", "token": "tok-abc123"}')
    try:
        raise RuntimeError('{"password": "trace-secret", "wifi-sec.psk": "ap-pass"}')
    except RuntimeError:
        logger.exception("fehler beim anwenden")
    output = stream.getvalue()
    for leaked in ("dict-secret", "9876", "wlan-geheim", "json-secret", "tok-abc123", "trace-secret", "ap-pass"):
        assert leaked not in output
    assert "***" in output


def test_escaped_quotes_inside_secret_are_fully_redacted():
    stream = io.StringIO()
    setup_logging("INFO", stream)
    logger = logging.getLogger("ma2pi.test")
    logger.info(r'json={"password": "ab\"cd", "psk": "ef\\gh\"ij"}')
    logger.info(r"repr={'password': 'xy\'zw'}")
    output = stream.getvalue()
    assert "cd" not in output
    assert "ij" not in output
    assert "zw" not in output
