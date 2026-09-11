from __future__ import annotations

import json
import logging

from shopman.shop.logging import JsonLogFormatter
from shopman.shop.telemetry_redaction import REDACTED, redact_observability_value


def test_recursive_redaction_keeps_safe_technical_refs_only():
    cleaned = redact_observability_value({
        "request_id": "request-safe-123",
        "receipt_ref": "receipt-safe-456",
        "recipient": "+55 43 99999-8888",
        "provider_response": {"raw": "customer@example.test"},
        "context": {
            "url": "https://provider.test/send?token=secret#fragment",
            "error_code": "provider_timeout",
        },
    })

    assert cleaned["request_id"] == "request-safe-123"
    assert cleaned["receipt_ref"] == "receipt-safe-456"
    assert cleaned["recipient"] == REDACTED
    assert cleaned["provider_response"] == REDACTED
    assert cleaned["context"]["url"] == "https://provider.test/send"
    assert cleaned["context"]["error_code"] == "provider_timeout"


def test_json_log_formatter_redacts_message_extra_and_exception():
    formatter = JsonLogFormatter()
    try:
        raise RuntimeError("falha para customer@example.test token=top-secret")
    except RuntimeError:
        record = logging.LogRecord(
            name="shopman.marketing",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="envio para +55 43 99999-8888 falhou",
            args=(),
            exc_info=__import__("sys").exc_info(),
        )
    record.provider_response = {"body": "customer@example.test"}
    record.request_id = "request-safe-123"

    payload = json.loads(formatter.format(record))
    serialized = json.dumps(payload)

    assert "customer@example.test" not in serialized
    assert "99999-8888" not in serialized
    assert "top-secret" not in serialized
    assert payload["provider_response"] == REDACTED
    assert payload["request_id"] == "request-safe-123"
