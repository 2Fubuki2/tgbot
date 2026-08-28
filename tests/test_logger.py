"""Тесты модуля логирования."""
import io
import json
import logging
import sys
from unittest.mock import patch

import pytest

from src.config.logger import JsonFormatter, setup_logging


class _FakeSettings:
    log_level = "DEBUG"
    use_webhook = False
    webhook_domain = ""


def test_json_formatter_structure():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname="", lineno=0,
        msg="Test message", args=(), exc_info=None,
    )
    record.created = 1700000000.0  # fixed timestamp

    output = formatter.format(record)
    obj = json.loads(output)

    assert obj["level"] == "INFO"
    assert obj["logger"] == "test.logger"
    assert obj["message"] == "Test message"
    assert "timestamp" in obj


def test_json_formatter_with_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("test error")
    except ValueError:
        import traceback
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test.logger", level=logging.ERROR, pathname="", lineno=0,
        msg="Something went wrong", args=(), exc_info=exc_info,
    )
    output = formatter.format(record)
    obj = json.loads(output)

    assert obj["level"] == "ERROR"
    assert "exception" in obj
    assert "test error" in obj["exception"]


def test_setup_logging_local_mode():
    """In local mode (no webhook), should set up stdout + file handler."""
    with patch("src.config.logger.settings", _FakeSettings()):
        with patch("src.config.logger.logging.StreamHandler") as mock_stream:
            mock_stream.return_value = logging.StreamHandler(io.StringIO())
            setup_logging()

    root = logging.getLogger()
    # Should have at least the stdout handler
    assert len(root.handlers) >= 1
    # aiogram should be suppressed
    assert logging.getLogger("aiogram").level == logging.WARNING


def test_setup_logging_production_mode():
    """In webhook mode, should use JSON formatter."""
    class ProdSettings:
        log_level = "INFO"
        use_webhook = True
        webhook_domain = "https://example.com"
        webhook_path = "/webhook"

    with patch("src.config.logger.settings", ProdSettings()):
        with patch("src.config.logger.logging.StreamHandler") as mock_handler:
            mock_handler.return_value = logging.StreamHandler(io.StringIO())
            setup_logging()

    root = logging.getLogger()
    # Check that JSON formatter is used
    json_used = False
    for h in root.handlers:
        if isinstance(h.formatter, JsonFormatter):
            json_used = True
            break
    assert json_used, "JSON formatter should be active in production mode"
