from __future__ import annotations

import json
import logging

from src.core import context
from src.core.logging import CorrelationFilter, JsonFormatter


def _record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("test.logger", logging.INFO, __file__, 1, message, None, None)


def test_json_formatter_includes_correlation_id():
    token = context.correlation_id_ctx.set("abc123")
    try:
        record = _record("hello")
        CorrelationFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        context.correlation_id_ctx.reset(token)

    assert payload["correlation_id"] == "abc123"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["logger"] == "test.logger"


def test_json_formatter_defaults_correlation_to_dash():
    record = _record()
    CorrelationFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["correlation_id"] == "-"
