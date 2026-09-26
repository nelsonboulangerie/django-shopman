"""Encomenda paga antes: Via Recibo no pagamento, NFC-e na saída da mercadoria.

Decisão do dono (26/09/2026). A NFC-e acompanha a SAÍDA da mercadoria, não o
pagamento: na retirada, quando o pedido é entregue ao cliente (``COMPLETED``);
na entrega, com a sacola pronta (``READY``) e o despacho como rede, porque a
DANFE vai dentro da sacola. A venda de balcão (leva agora) segue emitindo no
fechamento. O iFood tem regra própria e não muda.

O porquê é o prazo: no PR a NFC-e só cancela em 30 min e com a mercadoria na
casa (``fiscal.cancellation_path``). Emitida no pagamento de uma encomenda de
outro dia, "cancelar e refazer" virava quase sempre nota de estorno.

Estes testes passam pelo fechamento REAL do PDV e pelos callbacks reais do
lifecycle (``transaction=True``).
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.backstage.services.receipt_escpos import sale_receipt
from shopman.backstage.tests.test_pos_gateway_handoff_boundary import close_counter, fiscal_rows  # noqa: F401
from shopman.shop.directives import FISCAL_CANCEL_NFCE
from shopman.shop.services import fiscal as fiscal_service

pytestmark = pytest.mark.django_db(transaction=True)

ENDERECO = {
    "formatted_address": "Rua Pará, 86", "route": "Rua Pará", "street_number": "86",
    "neighborhood": "Centro", "postal_code": "86010000", "city": "Londrina", "state_code": "PR",
}


def _walk(order: Order, *statuses: str) -> Order:
    """Leva o pedido pelos degraus pedidos, pelas transições reais (e seus callbacks)."""
    for status in statuses:
        order.refresh_from_db()
        if order.status != status and order.can_transition_to(status):
            order.transition_status(status, actor="test")
    order.refresh_from_db()
    return order


def _encomenda(close, *, days_ahead: int = 2, ref: str, **overrides) -> Order:
    date = (timezone.localdate() + timedelta(days=days_ahead)).isoformat()
    order, _ = close(
        "cash",
        client_request_id=ref,
        delivery_date=date,
        customer_name="Ana",
        customer_phone="43999990000",
        **overrides,
    )
    return order


# ── Retirada ──────────────────────────────────────────────────────────────


def test_encomenda_paga_hoje_para_daqui_a_dois_dias_emite_so_na_retirada(close_counter):  # noqa: F811
    order = _encomenda(close_counter, ref="saida-retirada-2d")

    # No pagamento: Via Recibo, e nenhuma nota.
    assert not fiscal_rows(order).exists()
    assert fiscal_service.fiscal_state(order) == fiscal_service.FISCAL_STATE_AWAITING_PICKUP
    recibo = sale_receipt(order).decode("cp860", errors="replace")
    assert "Recibo não fiscal" in recibo
    assert "A nota fiscal sai na retirada." in recibo

    order = _walk(order, "accepted", "ready", "completed")

    assert order.status == Order.Status.COMPLETED
    assert fiscal_rows(order).get().payload["customer"]["tax_id"] == "52998224725"
    # Depois da saída, o recibo não repete uma promessa já cumprida.
    assert "A nota fiscal sai" not in sale_receipt(order, reprint=True).decode("cp860", errors="replace")


def test_encomenda_para_hoje_com_retirada_tambem_emite_na_retirada(close_counter):  # noqa: F811
    from shopman.guestman.models import Customer

    customer = Customer.objects.create(ref="ana-encomenda", first_name="Ana")
    order, _ = close_counter(
        "cash", client_request_id="saida-retirada-hoje", sales_mode="order",
        customer_ref=customer.ref, delivery_date=timezone.localdate().isoformat(),
        # Nota pedida pelo papel (``on_requested_receipt``), sem CPF: o CPF de
        # cliente cadastrado abre a pergunta "salvar no cadastro?".
        fiscal_tax_id="",
    )

    assert not fiscal_rows(order).exists()
    assert fiscal_service.fiscal_state(order) == fiscal_service.FISCAL_STATE_AWAITING_PICKUP

    order = _walk(order, "accepted", "ready", "completed")
    assert fiscal_rows(order).count() == 1


# ── Balcão ────────────────────────────────────────────────────────────────


def test_venda_de_balcao_emite_no_fechamento_como_sempre(close_counter):  # noqa: F811
    order, _ = close_counter("cash", client_request_id="saida-balcao")

    assert order.status == Order.Status.COMPLETED
    assert fiscal_rows(order).count() == 1
    assert "A nota fiscal sai" not in sale_receipt(order).decode("cp860", errors="replace")


# ── Entrega ───────────────────────────────────────────────────────────────


def test_entrega_emite_com_a_sacola_pronta_e_a_danfe_sai_no_despacho(close_counter):  # noqa: F811
    order = _encomenda(
        close_counter, ref="saida-entrega", days_ahead=0,
        fulfillment_type="delivery", delivery_address="Rua Pará, 86",
        delivery_address_structured=ENDERECO,
    )
    assert not fiscal_rows(order).exists()
    assert fiscal_service.fiscal_state(order) == fiscal_service.FISCAL_STATE_AWAITING_DELIVERY
    assert "A nota fiscal sai na entrega." in sale_receipt(order).decode("cp860", errors="replace")

    order = _walk(order, "accepted", "ready")
    assert order.status == Order.Status.READY
    assert fiscal_rows(order).count() == 1, "a nota nasce antes de o entregador sair"

    # A nota autorizou enquanto a sacola esperava: no despacho, a DANFE sai
    # na hora (``order_danfe.on_order_changed``), e o despacho não emite outra.
    order.data = {**order.data, "nfce_access_key": "4" * 44}
    order.save(update_fields=["data"])
    with patch("shopman.backstage.services.order_danfe.enqueue_auto_print") as auto_print:
        order = _walk(order, "dispatched")
    assert order.status == Order.Status.DISPATCHED
    auto_print.assert_called_once_with(order.ref)
    assert fiscal_rows(order).count() == 1


def test_entrega_que_pulou_a_sacola_pronta_emite_no_despacho(close_counter):  # noqa: F811
    order = _encomenda(
        close_counter, ref="saida-entrega-rede", days_ahead=0,
        fulfillment_type="delivery", delivery_address="Rua Pará, 86",
        delivery_address_structured=ENDERECO,
    )
    order = _walk(order, "accepted")
    # O pedido chega ao despacho sem ter passado pela emissão do READY.
    Order.objects.filter(pk=order.pk).update(status=Order.Status.READY)
    order.refresh_from_db()
    assert not fiscal_rows(order).exists()

    order = _walk(order, "dispatched")
    assert fiscal_rows(order).count() == 1


# ── Cancelamento antes da saída ──────────────────────────────────────────


def test_cancelar_encomenda_paga_antes_da_saida_nao_toca_o_fiscal(close_counter):  # noqa: F811
    order = _encomenda(close_counter, ref="saida-cancela")

    order = _walk(order, "cancelled")

    assert order.status == Order.Status.CANCELLED
    assert not fiscal_rows(order).exists()
    assert not Directive.objects.filter(topic=FISCAL_CANCEL_NFCE, payload__order_ref=order.ref).exists()


# ── Emissão tardia conta do dia da saída ─────────────────────────────────


def test_emissao_avulsa_conta_o_dia_da_saida_nao_o_do_pagamento(close_counter, settings):  # noqa: F811
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    order, _ = close_counter(
        "cash", client_request_id="saida-avulsa", fiscal_tax_id="", receipt_channels=[],
        delivery_date=(timezone.localdate() + timedelta(days=2)).isoformat(),
        customer_name="Ana", customer_phone="43999990000",
    )
    assert fiscal_service.fiscal_state(order) == fiscal_service.FISCAL_STATE_NOT_EXPECTED

    # Antes da saída a avulsa espera o momento da nota.
    assert "sai na retirada" in fiscal_service.issue_override_refusal(order)

    # Pago há três dias, retirado hoje: a venda fiscal é de hoje.
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(days=3))
    order = _walk(order, "accepted", "ready", "completed")
    assert order.status == Order.Status.COMPLETED
    assert fiscal_service.fiscal_sale_day(order) == timezone.localdate()
    assert fiscal_service.issue_override_refusal(order) == ""


# ── iFood inalterado ─────────────────────────────────────────────────────


def test_ifood_nao_entra_na_regra_da_saida():
    from shopman.shop.services.ifood_ingest import IFOOD_CHANNEL_REF

    order = Order(
        ref="IFOOD-SAIDA", channel_ref=IFOOD_CHANNEL_REF, status="ready", total_q=1000,
        data={"fulfillment_type": "delivery", "payment": {"method": "external"}},
    )
    assert fiscal_service.emission_waits_for_handoff(order) is False
    with patch.object(fiscal_service, "emit") as emit:
        fiscal_service.emit_for_delivery_handoff(order)
    emit.assert_not_called()
