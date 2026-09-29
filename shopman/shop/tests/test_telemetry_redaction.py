from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from shopman.shop.logging import JsonLogFormatter, PrivacySafeFormatter
from shopman.shop.telemetry_redaction import REDACTED, redact_observability_value, redact_text


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
    # A ROTA fica (`/customer/.../send`) — é ela que diz qual chamada falhou.
    # O que sai é a query (`?token=`), o fragmento e o e-mail dentro do caminho.
    assert cleaned["context"]["url"] == "https://provider.test/customer/[email]/send"
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


def test_url_boundary_drops_userinfo_and_secrets_but_keeps_the_route():
    """O corte de URL tira credencial; a rota fica, porque é o diagnóstico.

    Amputar o caminho transformaria "o webhook do Pix da Efí quebrou" em "alguma
    coisa no servidor quebrou". O que a barreira tira é o que é segredo por
    contrato — userinfo, query, fragmento — e o que os regex de PII reconhecem
    DENTRO do caminho.
    """

    values = (
        "https://user:password@example.test/pos/customer/CUS-PRIVATE/profile/",
        "https://example.test/account/passkeys/cred-private/?token=abc#x",
        "https://example.test/customer/pablo@example.test/",
    )

    assert [redact_observability_value(value, key="url") for value in values] == [
        # `user:password@` sai: credencial no userinfo nunca é diagnóstico.
        "https://example.test/pos/customer/CUS-PRIVATE/profile/",
        # `?token=` e `#x` saem; a rota do passkey fica.
        "https://example.test/account/passkeys/cred-private/",
        # e-mail no caminho é redigido no lugar, sem derrubar a rota.
        "https://example.test/customer/[email]/",
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


def test_referencia_do_edge_sobrevive_a_redacao():
    """O timestamp Unix da referência do Akamai tem forma de telefone.

    Ele é o que o suporte do iFood usa para achar a regra que bloqueou o
    polling; redigido, o chamado volta sem resposta. Ver `ifood_http`.
    """
    texto = "ifood_http.poll: recusa=edge referencia=Reference #18.1f9ab259.1758275496.3d4e5f6a"
    saida = redact_text(texto)
    assert "18.1f9ab259.1758275496.3d4e5f6a" in saida
    assert "[phone]" not in saida


def test_a_excecao_da_referencia_nao_abre_passagem_para_telefone():
    """A guarda é da referência, não de qualquer corrida de dígitos."""
    assert "[phone]" in redact_text("contato 11 98765-4321")
    assert "[phone]" in redact_text("Reference #18.abc concluída; ligar para 11987654321")
    # A forma protegida é a da referência inteira; um trecho parecido não passa.
    assert "[phone]" in redact_text("pedido 18.1f9ab259 e telefone 11987654321")


def test_data_iso_sobrevive_a_redacao():
    """Data ISO tem oito dígitos com hífen — forma de telefone para o regex.

    A mensagem da reconciliação financeira chegava ao Sentry como
    "Reconciliação financeira de [phone]"; a data é o que diz qual dia divergiu.
    """
    casos = [
        "Reconciliação financeira de 2026-09-21 encontrou divergências.",
        "janela 2026-09-21T14:30:00Z até 2026-09-22T02:00:00.123456+00:00",
        "fechamento 2026-09-21 14:30:00 e 2026-09-21 14:30",
        "de 2026-12-31 a 2027-01-01",
    ]
    for texto in casos:
        saida = redact_text(texto)
        assert saida == texto, saida


def test_a_excecao_da_data_nao_abre_passagem_para_telefone():
    """A guarda é da data válida, não de qualquer corrida de dígitos com hífen."""
    assert redact_text("dia 2026-09-21, ligar para 11 98765-4321") == (
        "dia 2026-09-21, ligar para [phone]"
    )
    assert "[phone]" in redact_text("telefone +55 43 99999-8888")
    assert "[phone]" in redact_text("telefone (43) 3025-1234")
    assert "[phone]" in redact_text("telefone 43999998888")
    # Mês 13 / dia 32 não é data: segue sendo tratado como telefone.
    assert "[phone]" in redact_text("código 4399-13-12")
    assert "[phone]" in redact_text("código 4399-12-32")
    # Data grudada em mais dígitos não é data isolada.
    assert "[phone]" in redact_text("número 2026-09-21-4321")
