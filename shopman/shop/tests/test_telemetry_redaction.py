from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from shopman.shop.logging import JsonLogFormatter, PrivacySafeFormatter
from shopman.shop.telemetry_redaction import REDACTED, redact_observability_value


def test_recursive_redaction_keeps_safe_technical_refs_only():
    cleaned = redact_observability_value({
        "request_id": "request-safe-123",
        "receipt_ref": "receipt-safe-456",
        "recipient": "+55 43 99999-8888",
        "provider_response": {"raw": "customer@example.test"},
        "context": {
            "url": "https://provider.test/customer/pablo@example.test/send?token=secret#fragment",
            "error_code": "provider_timeout",
        },
    })

    assert cleaned["request_id"] == "request-safe-123"
    assert cleaned["receipt_ref"] == "receipt-safe-456"
    assert cleaned["recipient"] == REDACTED
    assert cleaned["provider_response"] == REDACTED
    assert cleaned["context"]["url"] == "https://provider.test"
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


def test_personal_aliases_and_documents_are_redacted_but_technical_refs_remain():
    cleaned = redact_observability_value({
        "customer_ref": "CUS-123",
        "subscriber_id": "998877",
        "session_key": "session-private",
        "client_ip": "192.0.2.10",
        "actor_ref": "operator-private",
        "user_id": "user-private",
        "subject_id": "subject-private",
        "address_id": "address-private",
        "delivery_address": "Rua das Flores, 123",
        "latitude": -23.3101,
        "order_ref": "ORD-TECHNICAL-1",
        "message": (
            "customer=CUS-PRIVATE; user_id=user-private; "
            "cpf=123.456.789-10 cnpj 12.345.678/0001-90"
        ),
    })

    assert cleaned["customer_ref"] == REDACTED
    assert cleaned["subscriber_id"] == REDACTED
    assert cleaned["session_key"] == REDACTED
    assert cleaned["client_ip"] == REDACTED
    assert cleaned["actor_ref"] == REDACTED
    assert cleaned["user_id"] == REDACTED
    assert cleaned["subject_id"] == REDACTED
    assert cleaned["address_id"] == REDACTED
    assert cleaned["delivery_address"] == REDACTED
    assert cleaned["latitude"] == REDACTED
    assert cleaned["order_ref"] == "ORD-TECHNICAL-1"
    assert "123.456.789-10" not in cleaned["message"]
    assert "12.345.678/0001-90" not in cleaned["message"]
    assert "CUS-PRIVATE" not in cleaned["message"]


def test_url_boundary_drops_userinfo_and_every_free_form_path():
    values = (
        "https://user:password@example.test/pos/customer/CUS-PRIVATE/profile/",
        "https://example.test/account/passkeys/cred-private/",
        "https://example.test/customer/pablo%40example.test/",
        "https://example.test/device/550e8400-e29b-41d4-a716-446655440000/",
    )

    assert [redact_observability_value(value, key="url") for value in values] == [
        "https://example.test",
        "https://example.test",
        "https://example.test",
        "https://example.test",
    ]


def test_human_formatter_uses_the_same_redaction_boundary():
    formatter = PrivacySafeFormatter(
        "{levelname} {asctime} {name} {message}",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    record = logging.LogRecord(
        name="shopman.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=(
            "falha customer_ref=CUS-PRIVATE; session_key=session-private; "
            "endereço=Rua das Flores 123; cpf=123.456.789-10"
        ),
        args=(),
        exc_info=None,
    )
    formatter.converter = time.gmtime
    record.created = datetime(2026, 9, 14, 22, 24, 36, tzinfo=UTC).timestamp()

    rendered = formatter.format(record)

    assert rendered.startswith("ERROR 2026-09-14 22:24:36 shopman.test ")
    assert "[phone]" not in rendered.split("shopman.test", 1)[0]
    assert "CUS-PRIVATE" not in rendered
    assert "session-private" not in rendered
    assert "Rua das Flores" not in rendered
    assert "123.456.789-10" not in rendered


def test_human_formatter_redacts_extra_and_exception_without_mutating_record():
    formatter = PrivacySafeFormatter("{message} {customer_ref}", style="{")
    try:
        raise RuntimeError("cpf=123.456.789-10")
    except RuntimeError:
        import sys

        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="shopman.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="pedido %s",
        args=("customer_ref=CUS-PRIVATE",),
        exc_info=exc_info,
    )
    record.customer_ref = "CUS-PRIVATE"

    rendered = formatter.format(record)

    assert "CUS-PRIVATE" not in rendered
    assert "123.456.789-10" not in rendered
    assert record.args == ("customer_ref=CUS-PRIVATE",)
