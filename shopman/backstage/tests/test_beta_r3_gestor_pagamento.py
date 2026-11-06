"""Beta 06/11 (3ª rodada): o pagamento visto pelo operador no Gestor.

- F4: autorizar não é cobrar, e o histórico diz os dois em português;
- PIXEXP-03: o Pix que entrou numa cobrança encerrada e voltou aparece no pedido;
- PIXEXP-05: o pedido novo esperando o Pix diz até quando, e que cancela sozinho;
- F5: cancelar diz antes o que acontece com o dinheiro;
- W3: o histórico e os avisos sem chave de máquina na tela.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.projections import order_queue
from shopman.backstage.projections.order_queue import build_operator_order, build_order_card

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

REPO = Path(__file__).resolve().parents[3]


def _order(ref: str, status: str, *, payment: dict, total_q: int = 2200) -> Order:
    data = {
        "customer": {"name": f"Cliente {ref}"},
        "fulfillment_type": "pickup",
        "payment": payment,
        "availability_decision": {"approved": True, "decisions": []},
    }
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"s-{ref}", status=status, total_q=total_q, data=data,
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q, line_total_q=total_q,
    )
    return order


# ── F4: o histórico do dinheiro ─────────────────────────────────────────────


def test_autorizar_nao_e_cobrar_e_o_historico_fala_portugues():
    order = _order("R3-F4", "accepted", payment={"method": "card", "intent_ref": "INT-R3-F4"})
    order.emit_event("payment.authorized", actor="payment.gateway_reconcile", payload={"intent_ref": "INT-R3-F4"})
    order.emit_event("payment.captured", actor="payment.capture", payload={"method": "card", "amount_q": 510})
    order.emit_event("payment.refunded", actor="payment.refund", payload={"method": "card", "amount_q": 510})

    timeline = {e.event_type: e for e in build_operator_order(order).timeline}

    authorized = timeline["payment.authorized"]
    assert authorized.label == "Cartão autorizado (ainda não cobrado)"
    assert authorized.actor != "Pagamento confirmado"
    assert timeline["payment.captured"].label == "Pagamento recebido"
    assert timeline["payment.captured"].detail == "Cartão · R$ 5,10"
    assert timeline["payment.refunded"].label == "Pagamento estornado"
    for event in timeline.values():
        assert "payment." not in event.label.lower()
        assert "intent" not in event.detail.lower()


def test_todo_evento_de_dinheiro_gravado_pelo_codigo_tem_rotulo():
    """Trava: o fallback ``.capitalize()`` punha "Payment.captured" na tela."""
    pattern = re.compile(r"""(?:event_type=|emit_event\(\s*)["'](payment\.[a-z_.]+)["']""")
    emitted: set[str] = set()
    for root in ("shopman", "packages"):
        for path in (REPO / root).rglob("*.py"):
            if "/tests/" in str(path) or "/migrations/" in str(path):
                continue
            emitted.update(pattern.findall(path.read_text(encoding="utf-8")))
    assert {"payment.authorized", "payment.captured", "payment.refunded"} <= emitted
    assert not emitted - set(order_queue._EVENT_LABELS)


def test_a_captura_no_aceite_entra_no_historico():
    from shopman.shop.services import payment as payment_service

    order = _order("R3-F4-CAP", "accepted", payment={"method": "card", "intent_ref": "INT-R3-F4-CAP"})
    PaymentService.create_intent(order.ref, 2200, "card", gateway="stripe", ref="INT-R3-F4-CAP")
    adapter = SimpleNamespace(
        capture=lambda intent_ref: SimpleNamespace(success=True, transaction_id="ch_1", amount_q=2200),
    )
    with patch.object(payment_service, "_adapter_for_persisted_intent", return_value=adapter):
        payment_service.capture(order)

    event = order.events.get(type="payment.captured")
    assert event.payload["amount_q"] == 2200
    assert event.payload["method"] == "card"


# ── PIXEXP-03: o Pix fora da cobrança, recebido e estornado ─────────────────


def test_pix_recebido_e_estornado_fora_da_cobranca_aparece_no_detalhe():
    order = _order("R3-PIX03", "cancelled", payment={"method": "pix", "intent_ref": "INT-R3-PIX03"})
    PaymentService.create_intent(order.ref, 2200, "pix", gateway="efi", gateway_id="tx-dead", ref="INT-R3-PIX03")
    PaymentService.cancel("INT-R3-PIX03", reason="payment_timeout")
    booked = PaymentService.create_intent(
        order.ref, 2200, "pix", gateway="", gateway_id="tx-dead",
        gateway_data={"booked_by": "pix_confirmation", "superseded_intent_ref": "INT-R3-PIX03"},
        ref="INT-R3-PIX03-BOOKED",
    )
    PaymentService.authorize(booked.ref)
    PaymentService.capture(booked.ref)
    PaymentService.refund(booked.ref, reason="order_cancelled")

    detail = build_operator_order(order)

    assert detail.payment_status == "cancelled"
    assert detail.payment_status_label == "R$ 22,00 recebido e estornado"


def test_cobranca_paga_continua_dizendo_o_rotulo_de_sempre():
    order = _order("R3-PIX03-OK", "accepted", payment={"method": "pix", "intent_ref": "INT-R3-PIX03-OK"})
    PaymentService.create_intent(order.ref, 2200, "pix", gateway="efi", ref="INT-R3-PIX03-OK")
    PaymentService.authorize("INT-R3-PIX03-OK")
    PaymentService.capture("INT-R3-PIX03-OK")

    assert "recebido" not in build_operator_order(order).payment_status_label


# ── PIXEXP-05: o pedido novo esperando o Pix ────────────────────────────────


def _pending_pix(order: Order, *, created_minutes_ago: int, window: int = 10) -> None:
    from shopman.payman.models import PaymentIntent

    created = timezone.now() - timedelta(minutes=created_minutes_ago)
    intent = PaymentIntent.objects.create(
        ref=order.data["payment"]["intent_ref"], order_ref=order.ref, method="pix", amount_q=2200,
        status="pending", expires_at=created + timedelta(minutes=window),
    )
    PaymentIntent.objects.filter(pk=intent.pk).update(created_at=created)


def test_pedido_novo_esperando_pix_diz_ate_quando_e_que_cancela_sozinho():
    order = _order("R3-PIX05", "new", payment={"method": "pix", "intent_ref": "INT-R3-PIX05"})
    _pending_pix(order, created_minutes_ago=2)
    order = Order.objects.get(pk=order.pk)

    card = build_order_card(order)
    detail = build_operator_order(order)

    assert card.advance_block_label == "Aguardando Pix"
    assert "expira às" in card.advance_block_reason
    assert card.advance_block_reason.endswith("sem pagamento até lá, cancela sozinho")
    assert detail.advance_block_reason == card.advance_block_reason


def test_pedido_novo_com_pix_vencido_nao_promete_nada():
    order = _order("R3-PIX05-OLD", "new", payment={"method": "pix", "intent_ref": "INT-R3-PIX05-OLD"})
    _pending_pix(order, created_minutes_ago=30)

    card = build_order_card(Order.objects.get(pk=order.pk))

    assert card.advance_block_label == "Pix expirado"
    assert "cancela sozinho" not in card.advance_block_reason


# ── F5: o dinheiro antes de cancelar ────────────────────────────────────────


def test_cancelar_pix_pago_diz_que_o_valor_volta_ao_pix():
    order = _order("R3-F5-PIX", "accepted", payment={"method": "pix", "intent_ref": "INT-R3-F5-PIX"})
    PaymentService.create_intent(order.ref, 2200, "pix", gateway="efi", ref="INT-R3-F5-PIX")
    PaymentService.authorize("INT-R3-F5-PIX")
    PaymentService.capture("INT-R3-F5-PIX")

    detail = build_operator_order(order)

    assert detail.cancel_money_effect == "R$ 22,00 serão estornados ao Pix do cliente."
    assert detail.cancel_waits_for_gateway is True


def test_cancelar_cartao_so_autorizado_diz_que_nada_foi_cobrado():
    order = _order("R3-F5-CARD", "new", payment={"method": "card", "intent_ref": "INT-R3-F5-CARD"}, total_q=510)
    PaymentService.create_intent(order.ref, 510, "card", gateway="stripe", ref="INT-R3-F5-CARD")
    PaymentService.authorize("INT-R3-F5-CARD")

    detail = build_operator_order(order)

    assert detail.cancel_money_effect == "A reserva de R$ 5,10 no cartão do cliente será desfeita. Nada foi cobrado."
    assert detail.cancel_waits_for_gateway is True


def test_cancelar_pix_ainda_nao_pago_diz_que_nada_foi_cobrado():
    order = _order("R3-F5-PEND", "new", payment={"method": "pix", "intent_ref": "INT-R3-F5-PEND"})
    _pending_pix(order, created_minutes_ago=1)

    detail = build_operator_order(Order.objects.get(pk=order.pk))

    assert detail.cancel_money_effect == "Nada foi cobrado do cliente."
    assert detail.cancel_waits_for_gateway is False


# ── W3: o aviso genérico tem nome ───────────────────────────────────────────


def test_aviso_generico_tem_nome_em_portugues():
    from shopman.backstage.projections.notification_receipts import _template_label

    assert _template_label("order_ready") == "Pedido pronto"
    assert _template_label("order_ready_pickup") == "Pedido pronto para retirada"
