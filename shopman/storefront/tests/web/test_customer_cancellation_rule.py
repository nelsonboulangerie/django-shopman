"""A régua do cliente que quer cancelar (decisão do dono, 06/11/2026).

"Se for antes [do preparo], cancelamos e reembolsamos. Se for depois, o pedido não
pode mais ser cancelado, e no máximo é encaminhado para falar com gerente."
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.order_queue import build_operator_order
from shopman.shop.services import customer_contact, customer_orders
from shopman.shop.services import payment as payment_service
from shopman.storefront.presentation.order_tracking import build_order_tracking

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)


def _paid_pix(order: Order) -> Order:
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="pix", gateway="mock")
    PaymentService.authorize(intent.ref, gateway_id=f"gw-{intent.ref}")
    PaymentService.capture(intent.ref)
    data = {**(order.data or {}), "payment": {"method": "pix", "intent_ref": intent.ref}}
    Order.objects.filter(pk=order.pk).update(data=data)
    order.refresh_from_db()
    return order


def _cancel(client, order):
    return client.post(
        f"/api/v1/orders/{order.ref}/cancel/",
        data={},
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=f"cancel-{order.ref}",
    )


def _contact(client, order, origin="cancellation"):
    return client.post(
        f"/api/v1/orders/{order.ref}/contact-request/",
        data={"origin": origin},
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=f"contact-{origin}-{order.ref}",
    )


# ── 1. Antes do preparo: cancela na hora, pago ou não, e devolve ──────────────


@_MOCK_ADAPTERS
def test_paid_pix_before_preparation_offers_cancel_with_the_refund_in_the_dialog(order_paid):
    _paid_pix(order_paid)

    proj = build_order_tracking(order_paid)

    refs = [action.ref for action in proj.actions]
    assert "cancel_order" in refs
    assert "request_cancellation_contact" not in refs
    assert proj.cancel_dialog_money_line == (
        "O preparo ainda não começou. Cancelamos agora e devolvemos os R$ 25,00 do seu Pix para a mesma conta."
    )


@_MOCK_ADAPTERS
def test_paid_pix_before_preparation_cancels_refunds_and_tells_orders(
    client, order_paid, django_capture_on_commit_callbacks
):
    _paid_pix(order_paid)

    with django_capture_on_commit_callbacks(execute=True):
        response = _cancel(client, order_paid)

    assert response.status_code == 200, response.content
    order_paid.refresh_from_db()
    assert order_paid.status == "cancelled"
    assert order_paid.data["cancellation_reason_key"] == "customer_request"
    money = payment_service.cancelled_money(order_paid)
    assert money is not None and money.outcome == "refunded" and money.amount_q == 2500
    # A resposta do cancelar sai antes do estorno (que roda no commit); a tela relê.
    assert response.json()["cancellation_money_line"] == "Estamos devolvendo os R$ 25,00 do seu Pix para a mesma conta."
    assert build_order_tracking(order_paid).cancellation_money_line == (
        "Devolvemos os R$ 25,00 do seu Pix para a mesma conta."
    )

    alert = OperatorAlert.objects.get(type=customer_orders.SELF_CANCELLED_ALERT_TYPE, order_ref=order_paid.ref)
    assert alert.severity == "info"
    assert alert.audience == "orders"
    assert alert.message == (
        f"O cliente cancelou o pedido {order_paid.ref} antes do preparo. Devolução de R$ 25,00 feita no Pix."
    )


def test_unpaid_order_still_cancels_and_says_nothing_was_charged(client, order, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = _cancel(client, order)

    assert response.status_code == 200, response.content
    order.refresh_from_db()
    assert order.status == "cancelled"
    alert = OperatorAlert.objects.get(type=customer_orders.SELF_CANCELLED_ALERT_TYPE, order_ref=order.ref)
    assert alert.message == f"O cliente cancelou o pedido {order.ref} antes do preparo."


def test_unreadable_payment_does_not_self_cancel(order_paid):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(payment_service, "get_payment_status", lambda order, **_: "unknown")
        assert payment_service.can_cancel(order_paid) is False


# ── 2. Depois do preparo: não cancela; fala com o responsável ─────────────────


def test_after_preparation_there_is_no_cancel_only_the_manager(order_paid):
    Order.objects.filter(pk=order_paid.pk).update(status="preparing")
    order_paid.refresh_from_db()

    proj = build_order_tracking(order_paid)

    refs = [action.ref for action in proj.actions]
    assert "cancel_order" not in refs
    assert "request_cancellation_contact" in refs
    action = next(action for action in proj.actions if action.ref == "request_cancellation_contact")
    assert action.label == "Pedir contato sobre cancelamento"
    assert proj.cancellation_contact is not None and proj.cancellation_contact.requested is False
    assert proj.copy.cancellation_contact_message == (
        "O preparo já começou e o pedido é feito para você, então ele não pode mais ser cancelado. "
        "Se algo não está certo, fale com o responsável."
    )


def test_contact_after_preparation_opens_the_ombudsman_without_cancelling(client, order_paid):
    Order.objects.filter(pk=order_paid.pk).update(status="preparing")
    order_paid.refresh_from_db()

    response = _contact(client, order_paid)

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["cancellation_contact"] == {"requested": True}
    assert "request_cancellation_contact" not in [action["ref"] for action in body["actions"]]
    order_paid.refresh_from_db()
    assert order_paid.status == "preparing"
    alert = OperatorAlert.objects.get(type=customer_contact.ALERT_TYPE, order_ref=order_paid.ref)
    assert "queria cancelar, mas o preparo já começou" in alert.message
    gestor = build_operator_order(order_paid).contact_request
    assert gestor is not None and gestor.origin == "cancellation" and gestor.rating == 0


def test_contact_for_cancellation_before_preparation_is_refused(client, order_paid):
    response = _contact(client, order_paid)

    assert response.status_code == 409
    assert not OperatorAlert.objects.filter(type=customer_contact.ALERT_TYPE, order_ref=order_paid.ref).exists()


def test_unknown_contact_origin_is_a_400(client, order_paid):
    assert _contact(client, order_paid, origin="other").status_code == 400


# ── 3. Corrida: a cozinha começou no mesmo instante ───────────────────────────


@_MOCK_ADAPTERS
def test_preparation_started_in_the_same_instant_refuses_without_charging_or_half_cancelling(
    client, order_paid, django_capture_on_commit_callbacks
):
    _paid_pix(order_paid)
    stale = Order.objects.get(pk=order_paid.pk)
    assert customer_orders.can_cancel(stale)
    # A cozinha avança depois de a tela ler o pedido e antes de o cancelar chegar.
    Order.objects.filter(pk=order_paid.pk).update(status="preparing")

    with django_capture_on_commit_callbacks(execute=True):
        assert customer_orders.cancel(stale) is False
        response = _cancel(client, order_paid)

    assert response.status_code == 409
    assert response.json()["error_code"] == "order_not_cancellable"
    assert "não pode mais ser cancelado" in response.json()["detail"]
    order_paid.refresh_from_db()
    assert order_paid.status == "preparing"
    assert "cancellation_reason" not in order_paid.data
    intent_ref = order_paid.data["payment"]["intent_ref"]
    assert PaymentService.refunded_total(intent_ref) == 0
    assert PaymentService.captured_total(intent_ref) == 2500
    assert not OperatorAlert.objects.filter(
        type=customer_orders.SELF_CANCELLED_ALERT_TYPE, order_ref=order_paid.ref
    ).exists()
    # De volta ao caminho 2: a tela oferece falar com o responsável.
    assert "request_cancellation_contact" in [action.ref for action in build_order_tracking(order_paid).actions]
