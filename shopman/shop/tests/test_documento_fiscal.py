"""O FiscalDocument é a autoridade da nota (D-037, #3428).

O aceite da issue: o processo morre depois que o provedor AUTORIZOU a nota e
antes da gravação local. O reenvio recupera o MESMO documento (nenhum segundo
POST, nenhuma segunda linha), e o cancelamento preserva a chave e o protocolo.
"""

from __future__ import annotations

from unittest import mock

import pytest
from shopman.fiscalman import services as fiscal_documents
from shopman.fiscalman.contracts import FiscalCancellationResult, FiscalDocumentResult
from shopman.fiscalman.models import FiscalDocument
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler
from shopman.shop.models import Channel
from shopman.shop.services import fiscal_mirror

pytestmark = pytest.mark.django_db

ACCESS_KEY = "41261199999999000191650010000012341876543210"
PROTOCOL = "141260000012345"


class ProviderWithMemory:
    """Provedor falso que guarda a nota que autorizou, como a Focus guarda."""

    def __init__(self):
        self.notes: dict[str, FiscalDocumentResult] = {}
        self.emit_calls = 0
        self.query_calls = 0
        self.cancel_calls = 0

    def emit(self, *, reference, **kwargs):
        self.emit_calls += 1
        note = FiscalDocumentResult(
            success=True, access_key=ACCESS_KEY, document_number=1234, document_series=1,
            protocol_number=PROTOCOL, authorization_date="2026-11-23T10:00:00-03:00",
            danfe_url=f"https://homologacao.focusnfe.com.br/danfe/{ACCESS_KEY}.pdf", status="authorized",
        )
        self.notes[reference] = note
        return note

    def query_status(self, *, reference):
        self.query_calls += 1
        return self.notes.get(reference) or FiscalDocumentResult(
            success=False, status="not_found", error_code="focus_nfe_http_404",
        )

    def cancel(self, *, reference, reason):
        self.cancel_calls += 1
        return FiscalCancellationResult(
            success=True, protocol_number="141260000099999", cancellation_date="2026-11-23T10:05:00-03:00",
        )


@pytest.fixture
def order(db):
    Channel.objects.create(ref="pdv", name="PDV")
    return Order.objects.create(
        ref="ORD-DOC-1", channel_ref="pdv", status=Order.Status.ACCEPTED, total_q=5000,
        data={"fiscal": {"issue_document": True}},
    )


def _emit_directive(order, attempts=1):
    return Directive.objects.create(
        topic="fiscal.emit_nfce",
        payload={"order_ref": order.ref, "items": [], "payment": {"method": "cash", "amount_q": 5000}},
        attempts=attempts,
    )


def _cancel_directive(order):
    return Directive.objects.create(
        topic="fiscal.cancel_nfce",
        payload={"order_ref": order.ref, "reason": "cancelamento de teste com justificativa"},
    )


def _assert_mirror_matches_document(order):
    """O espelho em ``Order.data`` diz exatamente o que o documento diz."""
    order.refresh_from_db()
    document = FiscalDocument.objects.get(reference=order.ref)
    expected = fiscal_mirror.mirror_values(document)
    assert {key: order.data.get(key) for key in expected} == expected


def test_interrupcao_depois_da_autorizacao_recupera_o_mesmo_documento_e_o_cancelamento_preserva_chave_e_protocolo(order):
    provider = ProviderWithMemory()

    # 1. O provedor autoriza e o processo morre antes da gravação local.
    with mock.patch.object(fiscal_documents, "record_authorized", side_effect=RuntimeError("o processo morreu")):
        with pytest.raises(RuntimeError):
            NFCeEmitHandler(provider).handle(message=_emit_directive(order), ctx={})

    assert provider.emit_calls == 1
    assert order.ref in provider.notes  # a nota existe no provedor
    pending = FiscalDocument.objects.get(reference=order.ref)
    assert pending.status == FiscalDocument.Status.PENDING
    assert pending.access_key == ""
    order.refresh_from_db()
    assert "nfce_access_key" not in order.data

    # 2. O reprocesso nasce com attempts=1: sem a linha pendente, re-POSTaria.
    #    A linha manda consultar, e a consulta completa o MESMO documento.
    NFCeEmitHandler(provider).handle(message=_emit_directive(order, attempts=1), ctx={})

    assert provider.emit_calls == 1
    assert provider.query_calls == 1
    assert FiscalDocument.objects.count() == 1
    document = FiscalDocument.objects.get(reference=order.ref)
    assert document.pk == pending.pk
    assert document.status == FiscalDocument.Status.AUTHORIZED
    assert document.access_key == ACCESS_KEY
    assert document.protocol_number == PROTOCOL
    assert document.number == 1234
    assert document.authorized_at is not None
    order.refresh_from_db()
    assert order.data["nfce_access_key"] == ACCESS_KEY
    assert order.data["nfce_protocol"] == PROTOCOL
    assert order.data["nfce_status"] == "authorized"
    _assert_mirror_matches_document(order)

    # 3. O cancelamento grava ao lado da autorização, que fica intacta.
    from shopman.shop.services import fiscal as fiscal_service

    with mock.patch.object(fiscal_service, "cancellation_path", return_value={"path": "cancel"}):
        NFCeCancelHandler(provider).handle(message=_cancel_directive(order), ctx={})

    document.refresh_from_db()
    assert document.pk == pending.pk
    assert document.status == FiscalDocument.Status.CANCELLED
    assert document.access_key == ACCESS_KEY
    assert document.protocol_number == PROTOCOL
    assert document.cancellation_protocol == "141260000099999"
    assert document.cancelled_at is not None
    order.refresh_from_db()
    assert order.data["nfce_cancelled"] is True
    assert order.data["nfce_access_key"] == ACCESS_KEY
    _assert_mirror_matches_document(order)

    # 4. Cancelar de novo não chama o provedor.
    with mock.patch.object(fiscal_service, "cancellation_path", return_value={"path": "cancel"}):
        NFCeCancelHandler(provider).handle(message=_cancel_directive(order), ctx={})
    assert provider.cancel_calls == 1


def test_a_linha_nasce_pendente_antes_do_pedido_ao_provedor(order):
    seen = {}

    class ProviderThatLooks(ProviderWithMemory):
        def emit(self, *, reference, **kwargs):
            seen["status"] = FiscalDocument.objects.get(reference=reference).status
            return super().emit(reference=reference, **kwargs)

    NFCeEmitHandler(ProviderThatLooks()).handle(message=_emit_directive(order), ctx={})

    assert seen["status"] == FiscalDocument.Status.PENDING


def test_recusa_do_provedor_deixa_o_documento_recusado_e_o_reprocesso_reenvia(order):
    class RefusingThenAuthorizing(ProviderWithMemory):
        def emit(self, *, reference, **kwargs):
            self.emit_calls += 1
            if self.emit_calls == 1:
                return FiscalDocumentResult(
                    success=False, status="denied", error_code="focus_nfe_http_400", error_message="Rejeição 778",
                )
            return super().emit(reference=reference, **kwargs)

    provider = RefusingThenAuthorizing()
    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(provider).handle(message=_emit_directive(order), ctx={})
    refused = FiscalDocument.objects.get(reference=order.ref)
    assert refused.status == FiscalDocument.Status.DENIED

    NFCeEmitHandler(provider).handle(message=_emit_directive(order), ctx={})

    document = FiscalDocument.objects.get(reference=order.ref)
    assert document.pk == refused.pk
    assert document.status == FiscalDocument.Status.AUTHORIZED
    assert provider.query_calls == 0


def test_provedor_com_outra_chave_para_a_mesma_referencia_falha_gritando(order):
    fiscal_documents.record_authorized(
        order.ref, FiscalDocumentResult(success=True, access_key="9" * 44, protocol_number="P0", status="authorized"),
    )

    with pytest.raises(DirectiveTerminalError, match="já tem a nota"):
        NFCeEmitHandler._record(order, FiscalDocumentResult(success=True, access_key=ACCESS_KEY, status="authorized"))

    document = FiscalDocument.objects.get(reference=order.ref)
    assert document.access_key == "9" * 44


def test_cancelamento_sem_documento_autorizado_nao_chama_o_provedor(order):
    provider = ProviderWithMemory()

    with pytest.raises(DirectiveTerminalError, match="nada a cancelar"):
        NFCeCancelHandler(provider).handle(message=_cancel_directive(order), ctx={})

    assert provider.cancel_calls == 0


def test_emissao_direta_deixa_o_espelho_igual_ao_documento(order):
    NFCeEmitHandler(ProviderWithMemory()).handle(message=_emit_directive(order), ctx={})

    _assert_mirror_matches_document(order)


# ── linha pendente: o reprocesso SEMPRE consulta antes de emitir ─────────────
#
# A linha ``pending`` é gravada e confirmada antes do POST, então ela sobrevive a
# processo morto e a deploy no meio: quem retoma é outro processo, com outro
# handler, e a única memória é a linha. Por isso os casos abaixo montam a linha
# direto no banco e usam directive nova com attempts=1 (o reprocesso).


def test_linha_pendente_com_nota_no_provedor_adota_sem_emitir(order):
    provider = ProviderWithMemory()
    provider.emit(reference=order.ref)  # a nota que o processo anterior autorizou
    provider.emit_calls = 0
    fiscal_documents.open_pending(order.ref)

    NFCeEmitHandler(provider).handle(message=_emit_directive(order, attempts=1), ctx={})

    assert provider.query_calls == 1
    assert provider.emit_calls == 0
    _assert_mirror_matches_document(order)


def test_linha_pendente_sem_nota_no_provedor_consulta_e_so_entao_emite(order):
    provider = ProviderWithMemory()
    fiscal_documents.open_pending(order.ref)

    NFCeEmitHandler(provider).handle(message=_emit_directive(order, attempts=1), ctx={})

    assert provider.query_calls == 1
    assert provider.emit_calls == 1
    assert FiscalDocument.objects.count() == 1
    _assert_mirror_matches_document(order)


def test_linha_pendente_com_provedor_sem_resposta_nao_emite(order):
    from shopman.orderman.exceptions import DirectiveTransientError

    class Unreachable(ProviderWithMemory):
        def query_status(self, *, reference):
            self.query_calls += 1
            return FiscalDocumentResult(success=False, status="denied", error_code="focus_nfe_http_error")

    provider = Unreachable()
    fiscal_documents.open_pending(order.ref)

    with pytest.raises(DirectiveTransientError):
        NFCeEmitHandler(provider).handle(message=_emit_directive(order, attempts=1), ctx={})

    assert provider.emit_calls == 0
    assert FiscalDocument.objects.get(reference=order.ref).status == FiscalDocument.Status.PENDING


def test_linha_pendente_de_pedido_desfeito_consulta_e_nunca_emite(order):
    provider = ProviderWithMemory()
    fiscal_documents.open_pending(order.ref)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)

    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(provider).handle(message=_emit_directive(order, attempts=1), ctx={})

    assert provider.query_calls == 1
    assert provider.emit_calls == 0
