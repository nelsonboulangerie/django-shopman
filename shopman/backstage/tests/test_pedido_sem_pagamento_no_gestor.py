"""O Gestor mostra o pedido como pendência só quando dá para agir (DEV-2026-091).

Fala do dono (25/11/2026): "Se um pedido ainda não pago nem pode ser Aceito, vale a
pena mostrá-lo no gestor??? Porque não mostrar no gestor apenas quando o operador
pode fazer algo a respeito??? Até porque, quando o pagamento é de fato realizado, o
gestor nem recebe um novo alerta."

- Pix ou cartão que ainda não caiu: o pedido não pede ninguém (``attention`` vazio),
  não conta no "para aceitar" da Central e não faz o Gestor tocar;
- no instante em que o dinheiro cai, o pedido passa a "confirm" pela primeira vez,
  e é esse o toque de pedido novo (o som do Gestor segue o ``attention``);
- quem paga na retirada nunca esperou nada: é acionável desde o início, como hoje.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.projections import hub
from shopman.backstage.projections.order_queue import build_two_zone_queue
from shopman.shop.models import Channel, Shop
from shopman.shop.policies import order_payment

pytestmark = pytest.mark.django_db

#: A loja online da casa: paga ao pedir (Pix ou cartão), aceite em 5 min ou cancela.
_WEB_PAYS_AT_ORDER = {
    "confirmation": {"mode": "auto_cancel", "timeout_minutes": 5, "preorder_timeout_minutes": 60},
    "payment": {"method": ["pix", "card", "cash"], "timing": "at_commit", "timeout_minutes": 10},
}


@pytest.fixture
def gestor(db):
    Shop.objects.create(name="Loja")
    Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "config": _WEB_PAYS_AT_ORDER})
    user = User.objects.create_user("gestor-sem-pagamento", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    ))
    return User.objects.get(pk=user.pk)


def _order(ref: str, method: str) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"sk-{ref}", status=Order.Status.NEW, total_q=1500,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup", "payment": {"method": method}},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _with_intent(order: Order, method: str):
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method=method)
    order.data["payment"] = {"method": method, "intent_ref": intent.ref}
    order.save(update_fields=["data", "updated_at"])
    return intent


def _card(user, ref: str):
    queue = build_two_zone_queue(user=user)
    cards = [*queue.intake, *queue.prep, *queue.expedition_pickup, *queue.expedition_delivery]
    return {card.ref: card for card in cards}[ref]


def _to_accept(user) -> list[str]:
    with override_settings(SHOPMAN_SURFACE_URLS={"gestor": "https://gestor.example.test/"}):
        return [
            item.title for item in hub.collect_operator_queue(user).items if item.kind == "order_to_accept"
        ]


def test_pix_que_nao_caiu_nao_pede_ninguem_nem_conta_na_central(gestor):
    order = _order("NB-PIX", "pix")
    _with_intent(order, "pix")

    card = _card(gestor, order.ref)

    assert order_payment.awaits_online_payment(Order.objects.get(pk=order.pk)) is True
    assert card.awaits_online_payment is True
    assert card.attention in (None, "")
    assert _to_accept(gestor) == []


def test_pix_que_caiu_vira_pedido_para_aceitar_pela_primeira_vez(gestor):
    order = _order("NB-PIX-PAGO", "pix")
    intent = _with_intent(order, "pix")
    assert _card(gestor, order.ref).attention in (None, "")

    PaymentService.authorize(intent.ref, gateway_id="pix-gw")
    PaymentService.capture(intent.ref)

    card = _card(gestor, order.ref)
    assert order_payment.awaits_online_payment(Order.objects.get(pk=order.pk)) is False
    assert (card.awaits_online_payment, card.attention) == (False, "confirm")
    assert _to_accept(gestor) == ["Pedido PAGO para aceitar"]


def test_cartao_autorizado_ja_e_para_aceitar(gestor):
    """Captura manual: a autorização reserva o dinheiro e o aceite é que cobra."""
    order = _order("NB-CARTAO", "card")
    intent = _with_intent(order, "card")
    assert _card(gestor, order.ref).attention in (None, "")

    PaymentService.authorize(intent.ref, gateway_id="card-gw")

    card = _card(gestor, order.ref)
    assert (card.awaits_online_payment, card.attention) == (False, "confirm")
    assert _to_accept(gestor) == ["Pedido CARTAO para aceitar"]


def test_quem_paga_na_retirada_e_acionavel_desde_o_inicio(gestor):
    order = _order("NB-DINHEIRO", "cash")

    card = _card(gestor, order.ref)

    assert order_payment.awaits_online_payment(order) is False
    assert (card.awaits_online_payment, card.attention) == (False, "confirm")
    assert _to_accept(gestor) == ["Pedido DINHEIRO para aceitar"]
