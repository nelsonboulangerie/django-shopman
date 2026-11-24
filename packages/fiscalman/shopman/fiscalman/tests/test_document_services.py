"""O ciclo do FiscalDocument no serviço do fiscalman (D-037, #3428)."""

from __future__ import annotations

import pytest
from shopman.fiscalman import services
from shopman.fiscalman.contracts import FiscalCancellationResult, FiscalDocumentResult
from shopman.fiscalman.models import FiscalDocument

pytestmark = pytest.mark.django_db

KEY = "4" * 44


def _authorized(access_key=KEY, protocol="P-AUT"):
    return FiscalDocumentResult(
        success=True, access_key=access_key, document_number=7, document_series=1,
        protocol_number=protocol, authorization_date="2026-11-23T10:00:00-03:00", status="authorized",
    )


def test_open_pending_e_idempotente():
    first = services.open_pending("REF-1")
    again = services.open_pending("REF-1")

    assert first.pk == again.pk
    assert again.status == FiscalDocument.Status.PENDING
    assert FiscalDocument.objects.count() == 1


def test_autorizacao_completa_a_linha_pendente():
    pending = services.open_pending("REF-1")

    document = services.record_authorized("REF-1", _authorized())

    assert document.pk == pending.pk
    assert document.status == FiscalDocument.Status.AUTHORIZED
    assert document.access_key == KEY
    assert document.protocol_number == "P-AUT"
    assert document.number == 7
    assert document.authorized_at is not None


def test_mesma_chave_de_novo_nao_reescreve_nada():
    services.record_authorized("REF-1", _authorized())

    document = services.record_authorized("REF-1", _authorized(protocol="OUTRO"))

    assert document.protocol_number == "P-AUT"


def test_outra_chave_para_a_mesma_referencia_e_conflito():
    services.record_authorized("REF-1", _authorized())

    with pytest.raises(services.FiscalDocumentConflict):
        services.record_authorized("REF-1", _authorized(access_key="5" * 44))

    assert FiscalDocument.objects.get(reference="REF-1").access_key == KEY


def test_autorizacao_sem_chave_e_conflito():
    with pytest.raises(services.FiscalDocumentConflict):
        services.record_authorized("REF-1", FiscalDocumentResult(success=True, status="authorized"))


def test_cancelamento_preserva_chave_e_protocolo():
    authorized = services.record_authorized("REF-1", _authorized())

    cancelled = services.record_cancelled(
        "REF-1", FiscalCancellationResult(success=True, protocol_number="P-CAN", cancellation_date="2026-11-23T10:05:00-03:00"),
    )

    assert cancelled.pk == authorized.pk
    assert cancelled.status == FiscalDocument.Status.CANCELLED
    assert cancelled.access_key == KEY
    assert cancelled.protocol_number == "P-AUT"
    assert cancelled.cancellation_protocol == "P-CAN"
    assert cancelled.cancelled_at is not None


def test_cancelamento_e_idempotente():
    services.record_authorized("REF-1", _authorized())
    services.record_cancelled("REF-1", FiscalCancellationResult(success=True, protocol_number="P-CAN"))

    again = services.record_cancelled("REF-1", FiscalCancellationResult(success=True, protocol_number="OUTRO"))

    assert again.cancellation_protocol == "P-CAN"


def test_cancelamento_sem_nota_autorizada_e_conflito():
    services.open_pending("REF-1")

    with pytest.raises(services.FiscalDocumentConflict):
        services.record_cancelled("REF-1", FiscalCancellationResult(success=True, protocol_number="P-CAN"))


def test_recusa_nunca_rebaixa_documento_autorizado():
    services.record_authorized("REF-1", _authorized())

    document = services.record_denied("REF-1")

    assert document.status == FiscalDocument.Status.AUTHORIZED


def test_recusado_volta_a_pendente_no_reenvio():
    services.open_pending("REF-1")
    services.record_denied("REF-1")

    document = services.open_pending("REF-1")

    assert document.status == FiscalDocument.Status.PENDING


def test_data_ilegivel_do_provedor_fica_vazia():
    result = _authorized()
    result.authorization_date = "ontem à tarde"

    document = services.record_authorized("REF-1", result)

    assert document.authorized_at is None
    assert document.access_key == KEY
