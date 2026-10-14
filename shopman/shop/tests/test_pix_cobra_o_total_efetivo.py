"""O Pix cobra o total que vale AGORA, não o selado (P0-6).

Pedido remoto editado enquanto novo (a concierge acrescenta itens em ``new``,
``storefront/concierge/order_addition.py``) grava o total novo no ajuste
(``order_composition``), e o ``Order.total_q`` fica selado com o valor de
nascimento. ``payment.initiate`` cobrava o selado: o cliente recebia um Pix
com o total antigo, pagava, e o pedido ficava com saldo que ninguém cobrou
(docs/reference/cenarios-de-pedido.md, P0-6).

A regra: o Pix sai com ``order_composition.effective_total_q``. E um Pix que
já tinha saído com o valor velho é cancelado no provedor e refeito com o novo,
para o cliente nunca ter na mão um QR com o valor errado.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent

from shopman.shop.models import Channel
from shopman.shop.services import order_composition
from shopman.shop.services import payment as payment_service

pytestmark = pytest.mark.django_db

MOCK_PIX = {
    "DEBUG": False,
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS": True,
    "SHOPMAN_PAYMENT_ADAPTERS": {
        "pix": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    },
}


def _pedido_remoto(ref: str) -> Order:
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=4200,
        data={"fulfillment_type": "pickup", "payment": {"method": "pix"}},
    )


def _editado_para(order: Order, total_q: int) -> Order:
    """O que ``order_edit.apply_final_items`` grava: o ajuste com a lista final e o total novo."""
    data = dict(order.data or {})
    data[order_composition.KEY] = order_composition.record(
        order,
        items=[{"line_id": "L1", "sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": total_q, "line_total_q": total_q}],
        total_q=total_q,
        source="concierge",
        event_id=f"test:{order.ref}",
    )
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return order


@override_settings(**MOCK_PIX)
def test_pix_de_pedido_editado_cobra_o_total_novo():
    order = _editado_para(_pedido_remoto("ORD-P06-1"), 5400)

    payment_service.initiate(order)

    order.refresh_from_db()
    intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
    assert intent.amount_q == 5400
    assert order.data["payment"]["amount_q"] == 5400


@override_settings(**MOCK_PIX)
def test_pix_ja_gerado_com_o_valor_velho_e_cancelado_e_refeito():
    order = _pedido_remoto("ORD-P06-2")
    payment_service.initiate(order)
    order.refresh_from_db()
    old_ref = order.data["payment"]["intent_ref"]
    assert PaymentIntent.objects.get(ref=old_ref).amount_q == 4200

    _editado_para(order, 5400)
    payment_service.initiate(order)

    order.refresh_from_db()
    new_ref = order.data["payment"]["intent_ref"]
    assert new_ref != old_ref
    assert PaymentIntent.objects.get(ref=new_ref).amount_q == 5400
    assert order.data["payment"]["amount_q"] == 5400
    # O QR velho não fica pagável: o cliente nunca tem dois valores na mão.
    assert PaymentIntent.objects.get(ref=old_ref).status == "cancelled"


@override_settings(**MOCK_PIX)
def test_pix_sem_edicao_segue_reaproveitado():
    # Controle: sem ajuste, a mesma cobrança é devolvida (idempotência intacta).
    order = _pedido_remoto("ORD-P06-3")
    payment_service.initiate(order)
    order.refresh_from_db()
    first = order.data["payment"]["intent_ref"]

    payment_service.initiate(order)

    order.refresh_from_db()
    assert order.data["payment"]["intent_ref"] == first
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
