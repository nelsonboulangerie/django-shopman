"""Logging helpers for production-safe structured logs."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from shopman.shop.telemetry_redaction import redact_observability_value

_RESERVED_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonLogFormatter(logging.Formatter):
    """Format LogRecord objects as compact JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_observability_value(record.getMessage(), key="message"),
        }

        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            payload[key] = _json_safe(redact_observability_value(value, key=key))

        if record.exc_info:
            payload["exception"] = redact_observability_value(
                self.formatException(record.exc_info),
                key="exception",
            )
        if record.stack_info:
            payload["stack"] = redact_observability_value(
                self.formatStack(record.stack_info),
                key="stack",
            )

        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)
