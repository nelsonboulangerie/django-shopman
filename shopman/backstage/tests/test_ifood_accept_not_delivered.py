"""P1-3 no Gestor: o card e o detalhe dizem que o aceite não chegou ao iFood.

Antes, o card perdia o prazo do iFood assim que o pedido saía de ``new`` e o
operador só via o alerta genérico de tarefas. Agora, com o ``confirm`` falhando:

- o card e o detalhe trazem ``ifood_accept_failed`` e a frase do aviso;
- o prazo do iFood continua contando (``confirmation_deadline_iso``, ``cancel``);
- a ação ``ifood-accept-retry`` existe, com permissão, e o endpoint reabre o envio
  uma vez por intenção.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections.order_queue import build_operator_order, build_two_zone_queue
from shopman.shop.directives import IFOOD_STATUS_CALLBACK
from shopman.shop.services import ifood_accept_sync

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(django_user_model):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Laboratório do aceite iFood")
    user = django_user_model.objects.create_user(username="gestor-aceite", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    return user


@pytest.fixture
def order():
    confirm_by = timezone.now() + timedelta(minutes=5)
    return Order.objects.create(
        ref="IFD-SEM-ACEITE", channel_ref="ifood", external_ref="remote-order", status="preparing",
        data={
            "fulfillment_type": "delivery",
            "payment": {"method": "external", "gateway": "ifood", "status": "paid"},
            "ifood": {"delivered_by": "IFOOD", "confirm_by": confirm_by.isoformat()},
        },
    )


def _failed_accept(order, **fields):
    defaults = {"status": "failed", "attempts": 5, "last_error": "iFood 503", "error_code": "terminal"}
    return Directive.objects.create(
        topic=IFOOD_STATUS_CALLBACK,
        dedupe_key=ifood_accept_sync.dedupe_key(order.ref),
        payload={"order_ref": order.ref, "ifood_order_id": order.external_ref, "status": "accepted"},
        **{**defaults, **fields},
    )


def _card(user, ref):
    queue = build_two_zone_queue(user=user)
    cards = [*queue.intake, *queue.prep, *queue.expedition_pickup, *queue.expedition_delivery, *queue.expedition_delivery_transit]
    return next(card for card in cards if card.ref == ref)


def test_card_says_accept_did_not_reach_ifood_and_keeps_the_ifood_clock(operator, order):
    _failed_accept(order)
    card = _card(operator, order.ref)

    assert card.ifood_accept_failed is True
    assert card.ifood_accept_notice.startswith("O iFood ainda não recebeu o aceite do pedido IFD-SEM-ACEITE")
    # O prazo do iFood não some quando o pedido sai de "novo": ele ainda cancela.
    assert card.confirmation_deadline_iso == order.data["ifood"]["confirm_by"]
    assert card.confirmation_action == "cancel"
    retry = next(action for action in card.actions if action.ref == "ifood-accept-retry")
    assert retry.enabled
    assert retry.label == "Tentar de novo"
    assert retry.payload_schema["base_revision"] == ifood_accept_sync.state_for(order).revision


@pytest.mark.parametrize("directive", [
    {"status": "done", "attempts": 1, "last_error": "", "error_code": ""},
    {"status": "queued", "attempts": 0, "last_error": "", "error_code": ""},
])
def test_card_stays_quiet_while_the_accept_is_fine(operator, order, directive):
    _failed_accept(order, **directive)
    card = _card(operator, order.ref)
    assert card.ifood_accept_failed is False
    assert card.ifood_accept_notice == ""
    assert card.confirmation_deadline_iso == ""
    assert not any(action.ref == "ifood-accept-retry" for action in card.actions)


def test_ifood_confirmation_silences_the_card(operator, order):
    _failed_accept(order)
    order.data["ifood"]["remote_confirmed"] = {"event_id": "evt-cfm"}
    order.save(update_fields=["data"])
    card = _card(operator, order.ref)
    assert card.ifood_accept_failed is False
    assert card.confirmation_deadline_iso == ""


def test_detail_carries_the_same_notice_clock_and_action(operator, order):
    _failed_accept(order)
    detail = build_operator_order(order, user=operator)
    assert detail.ifood_accept_failed is True
    assert "Tentar de novo" in detail.ifood_accept_notice
    assert detail.confirmation_deadline_iso == order.data["ifood"]["confirm_by"]
    assert detail.confirmation_action == "cancel"
    assert any(action.ref == "ifood-accept-retry" and action.enabled for action in detail.actions)


def test_retry_without_permission_is_offered_disabled_and_refused(client, django_user_model, order):
    _failed_accept(order)
    clerk = django_user_model.objects.create_user(username="sem-permissao", is_staff=True)
    card_action = next(a for a in build_operator_order(order, user=clerk).actions if a.ref == "ifood-accept-retry")
    assert not card_action.enabled
    client.force_login(clerk)
    response = client.post(reverse("api-backstage-order-ifood-accept-retry", args=[order.ref]))
    assert response.status_code == 403


def test_retry_endpoint_reopens_once_per_intention(client, operator, order):
    directive = _failed_accept(order)
    client.force_login(operator)
    url = reverse("api-backstage-order-ifood-accept-retry", args=[order.ref])
    body = {"expected_actor_id": operator.pk, "base_revision": ifood_accept_sync.state_for(order).revision}

    with patch("shopman.orderman.dispatch._process_directive"):
        first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="aceite-1")
        replay = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="aceite-1")
        stale = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="aceite-2")

    assert first.status_code == 200, first.content
    assert first.json()["effect_status"] == "queued"
    assert first.json()["directive_id"] == directive.pk
    assert replay.status_code == 200 and replay.json()["replayed"]
    # A mesma leitura numa intenção nova: o estado já mudou, nada é reaberto de novo.
    assert stale.status_code == 409, stale.content
    directive.refresh_from_db()
    assert (directive.status, directive.attempts) == ("queued", 0)
    assert order.events.filter(type=ifood_accept_sync.EVENT_RETRIED).count() == 1


def test_retry_endpoint_refuses_when_ifood_already_has_the_accept(client, operator, order):
    _failed_accept(order, status="done", attempts=1, last_error="", error_code="")
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-order-ifood-accept-retry", args=[order.ref]),
        {"expected_actor_id": operator.pk, "base_revision": ifood_accept_sync.state_for(order).revision},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY="aceite-ja-foi",
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "O iFood já recebeu o aceite deste pedido."


def test_fila_puts_the_order_in_needs_you_with_the_ifood_clock(operator, order):
    """Em preparo a Fila dizia "nada pede você"; com o aceite sem chegar, pede."""
    _failed_accept(order)
    card = _card(operator, order.ref)
    deadline = ifood_accept_sync.deadline(order)
    assert card.attention == "ifood_accept"
    assert card.attention_since_iso == order.created_at.isoformat()
    assert card.goal_label == f"aceite até {timezone.localtime(deadline):%H:%M}"


def test_fila_leaves_the_order_alone_once_ifood_has_the_accept(operator, order):
    _failed_accept(order, status="done", attempts=1, last_error="", error_code="")
    assert _card(operator, order.ref).attention != "ifood_accept"
