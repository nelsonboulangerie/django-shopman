"""Não retirado no Gestor (WP-G11): a prévia, a rota e a ação do detalhe.

O Gerente lê, antes de assinar, o destino de cada linha, quanto volta ao cliente e
quanto fica com a loja. O comando é ``no_show.mark_not_picked_up``; a rota só confere
quem age, a base que a tela leu e a assinatura.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import IdempotencyKey, Order

from shopman.backstage.projections.order_queue import build_operator_order
from shopman.shop.services import no_show
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv", "ifood")]

SIGN = "shopman.backstage.api.operations.pos_tabs_service.validate_manager_override"


@pytest.fixture
def operador(client, django_user_model):
    world.make_shop()
    world.product("CROIS", price_q=935)
    world.product("BOLO", price_q=3000)
    world.lot("CROIS")
    world.lot("BOLO")
    # A casa produz os dois (ficha ativa): a perda deles tem retenção (DEV-2026-089).
    world.produced("CROIS")
    world.produced("BOLO")
    user = django_user_model.objects.create_user(username="gestor-nao-retirado", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    return user


@pytest.fixture
def relogio(monkeypatch):
    def set_now(hour: int, minute: int = 0):
        moment = world.at(hour, minute)
        monkeypatch.setattr(timezone, "now", lambda: moment)
        return moment

    return set_now


def _order(ref: str = "NS-API", **kwargs) -> Order:
    """Croissant com estoque baixado (volta à venda) e bolo sem estoque baixado (perda)."""
    order = world.ready_order(ref, [("CROIS", 2, 935), ("BOLO", 1, 3000)], held=False, ready_at=world.at(9), **kwargs)
    order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref=ref)]
    order.save(update_fields=["data", "updated_at"])
    return order


def _preview(client, order):
    return client.get(reverse("api-backstage-order-no-show-preview", args=[order.ref]))


def _no_show(client, user, order, *, key=None, base=None, **body):
    payload = {"expected_actor_id": user.pk, "base_revision": base or no_show.revision(order), **body}
    return client.post(
        reverse("api-backstage-order-no-show", args=[order.ref]), payload,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
    )


# ── Prévia ───────────────────────────────────────────────────────────────────


def test_preview_says_the_destiny_of_each_line_and_of_the_money(client, operador, relogio):
    relogio(10)
    order = _order()
    world.pay(order, "pix")

    relogio(19)
    body = _preview(client, order).json()

    assert body["allowed"] is True
    assert body["block_reason"] == ""
    lines = {line["sku"]: line for line in body["lines"]}
    assert (lines["CROIS"]["destiny"], lines["CROIS"]["destiny_label"], lines["CROIS"]["value_q"]) == ("restock", "Volta à venda", 1870)
    assert (lines["BOLO"]["destiny"], lines["BOLO"]["destiny_label"], lines["BOLO"]["reason"]) == ("loss", "Perda", "no_stock")
    assert lines["BOLO"]["reason_label"] == "Sem estoque baixado: não há o que devolver ao balcão."
    assert (body["paid_q"], body["refund_q"], body["retained_q"]) == (4870, 3670, 1200)
    assert (body["refund_display"], body["retained_display"]) == ("R$ 36,70", "R$ 12,00")
    assert body["money_sentence"] == (
        "R$ 36,70 serão estornados ao Pix do cliente. R$ 12,00 ficam com a loja, conforme os Termos do serviço."
    )
    assert body["customer_text"].startswith("O pedido ficou pronto e não foi retirado. Vamos devolver R$ 36,70")
    assert body["action"]["ref"] == "no-show"
    assert body["action"]["enabled"] is True
    assert body["action"]["confirmation"] == {"required": True, "manager_approval": True}
    assert body["action"]["payload_schema"]["base_revision"] == no_show.revision(order)
    assert "—" not in str(body)


def test_preview_before_the_time_is_not_allowed_and_says_when(client, operador, relogio):
    relogio(10)
    order = _order()
    world.pay(order, "pix")

    relogio(15)
    body = _preview(client, order).json()

    assert body["allowed"] is False
    assert body["block_reason"] == "Pedido pago: o não retirado libera no corte do dia, às 19h."
    assert body["releases_at"] == world.at(19).isoformat()
    assert body["action"]["enabled"] is False
    assert body["action"]["reason"] == body["block_reason"]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"channel_ref": "ifood"}, "Pedido do iFood: o que não foi retirado é resolvido no portal do iFood."),
        ({"data": {"fulfillment_type": "delivery"}}, "Este pedido é de entrega: não retirado é só para retirada."),
        (
            {"channel_ref": "pdv", "data": {"origin_channel": "pos", "pos": {"sales_mode": "counter"}}},
            "Venda de balcão não tem retirada a esperar.",
        ),
    ],
)
def test_preview_says_why_the_order_is_not_eligible(client, operador, relogio, kwargs, expected):
    relogio(19)
    order = _order(**kwargs)

    body = _preview(client, order).json()

    assert body["allowed"] is False
    assert body["block_reason"] == expected
    assert body["action"]["enabled"] is False


def test_preview_of_an_unknown_order_is_404(client, operador):
    assert client.get(reverse("api-backstage-order-no-show-preview", args=["NAO-EXISTE"])).status_code == 404


# ── A rota ───────────────────────────────────────────────────────────────────


def test_no_show_asks_for_the_manager_and_writes_nothing_without_the_signature(client, operador, relogio):
    relogio(19)
    order = _order()
    key = str(uuid.uuid4())

    resp = _no_show(client, operador, order, key=key)

    assert resp.status_code == 422, resp.content
    assert resp.json()["error"]["code"] == "manager_approval_required"
    assert resp.json()["detail"] == "Não retirado pede a autorização de um gerente."
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_signed_no_show_cancels_and_records_who_signed(client, operador, relogio):
    relogio(10)
    order = _order()
    world.pay(order, "pix")
    key = str(uuid.uuid4())

    relogio(19)
    with patch(SIGN, return_value=operador) as signature:
        resp = _no_show(client, operador, order, key=key, manager_approval={"username": "gerente", "pin": "SYNTHETIC-NOT-A-PIN"})

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["outcome"] == "applied"
    assert (body["refund_q"], body["retained_q"]) == (3670, 1200)
    assert signature.call_args.kwargs["action"] == "order_no_show"
    assert signature.call_args.kwargs["message"] == "Não retirado pede a autorização de um gerente."
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert order.data["cancellation_reason_key"] == "not_picked_up"
    block = order.data["no_show"]
    assert block["approved_by"] == operador.get_username()
    assert (block["paid_q"], block["refund_q"], block["retained_q"]) == (4870, 3670, 1200)
    assert body["order"]["status"] == "cancelled"
    assert "SYNTHETIC-NOT-A-PIN" not in str(IdempotencyKey.objects.get(key=key).response_body)


def test_detail_of_a_closed_no_show_says_what_went_back_what_stayed_and_who_signed(
    client, operador, relogio, django_capture_on_commit_callbacks,
):
    """O detalhe dizia "Reembolsado" num pedido em que só parte do valor voltou."""
    relogio(10)
    order = _order()
    world.pay(order, "pix")
    operador.first_name = "Joyce"
    operador.save(update_fields=["first_name"])

    relogio(19)
    with patch(SIGN, return_value=operador), django_capture_on_commit_callbacks(execute=True):
        resp = _no_show(client, operador, order, manager_approval={"username": "gerente", "pin": "SYNTHETIC-NOT-A-PIN"})
    assert resp.status_code == 200, resp.content
    order.refresh_from_db()

    detail = build_operator_order(order, user=operador)

    assert detail.payment_status_label == "R$ 36,70 devolvidos, R$ 12,00 com a loja"
    cancelled = next(event for event in detail.timeline if event.label == "Cancelado")
    assert cancelled.detail == "Não retirado · autorizado por Joyce"


def test_payment_label_says_to_be_returned_while_the_money_has_not_left(operador, relogio):
    """Dinheiro e maquininha esperam o gesto no PDV: ainda não voltou."""
    from shopman.backstage.projections.order_no_show import payment_outcome_label

    relogio(19)
    order = _order("NS-A-DEVOLVER")
    world.pay(order, "cash")
    order.data["no_show"] = {"paid_q": 4870, "refund_q": 1870, "retained_q": 3000}

    assert payment_outcome_label(order) == "R$ 18,70 a devolver, R$ 30,00 com a loja"

    order.data["no_show"] = {"paid_q": 3000, "refund_q": 0, "retained_q": 3000}
    assert payment_outcome_label(order) == "R$ 30,00 ficaram com a loja"

    # Nada ficou com a loja: o rótulo comum do pagamento já diz a verdade.
    order.data["no_show"] = {"paid_q": 1870, "refund_q": 1870, "retained_q": 0}
    assert payment_outcome_label(order) == ""


def test_repeating_the_same_intention_does_not_run_twice(client, operador, relogio):
    relogio(19)
    order = _order()
    key = str(uuid.uuid4())
    base = no_show.revision(order)

    with patch(SIGN, return_value=operador):
        first = _no_show(client, operador, order, key=key, base=base)
        second = _no_show(client, operador, order, key=key, base=base)

    assert first.status_code == 200, first.content
    assert second.status_code == 200, second.content
    assert second.json()["replayed"] is True
    assert order.events.filter(type="status_changed").count() == 1


def test_stale_screen_is_refused_before_writing(client, operador, relogio):
    relogio(10)
    order = _order()
    stale = no_show.revision(order)
    # A tela leu a prévia; depois o pagamento chegou e o dinheiro do gesto mudou.
    world.pay(order, "pix")

    relogio(19)
    with patch(SIGN, return_value=operador):
        resp = _no_show(client, operador, order, base=stale)

    assert resp.status_code == 409, resp.content
    assert resp.json()["outcome"] == "not_applied"
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data


def test_no_show_before_the_time_is_refused_without_asking_for_the_pin(client, operador, relogio):
    relogio(10)
    order = _order(data={"delivery_date": timezone.localdate().isoformat(), "delivery_time_slot": "15:00-15:30"})

    relogio(15)
    with patch(SIGN, return_value=operador) as signature:
        resp = _no_show(client, operador, order)

    assert resp.status_code == 409, resp.content
    assert resp.json()["error"]["code"] == "no_show_not_allowed"
    assert resp.json()["detail"] == "A retirada foi combinada para as 15h: o não retirado libera às 16h."
    assert signature.call_count == 0
    order.refresh_from_db()
    assert order.status == Order.Status.READY


@pytest.mark.parametrize(
    "kwargs",
    [{"channel_ref": "ifood"}, {"data": {"fulfillment_type": "delivery"}}],
)
def test_ineligible_order_is_refused(client, operador, relogio, kwargs):
    relogio(19)
    order = _order(**kwargs)

    with patch(SIGN, return_value=operador):
        resp = _no_show(client, operador, order)

    assert resp.status_code == 409, resp.content
    assert resp.json()["error"]["code"] == "no_show_not_allowed"
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert "no_show" not in order.data


def test_no_show_needs_the_permission_to_manage_orders(client, django_user_model, relogio):
    world.make_shop()
    world.product("CROIS", price_q=935)
    world.product("BOLO", price_q=3000)
    world.lot("CROIS")
    world.lot("BOLO")
    # A casa produz os dois (ficha ativa): a perda deles tem retenção (DEV-2026-089).
    world.produced("CROIS")
    world.produced("BOLO")
    user = django_user_model.objects.create_user(username="sem-permissao", is_staff=True)
    client.force_login(user)
    relogio(19)
    order = _order()

    assert _preview(client, order).status_code == 403
    assert _no_show(client, user, order).status_code == 403


# ── A ação no detalhe do pedido ──────────────────────────────────────────────


def _detail_action(order, user):
    actions = [action for action in build_operator_order(order, user=user).actions if action.ref == "no-show"]
    return actions[0] if actions else None


def test_detail_offers_the_action_enabled_once_the_time_comes(operador, relogio):
    relogio(10)
    order = _order()
    world.pay(order, "pix")

    relogio(15)
    early = _detail_action(order, operador)
    assert (early.label, early.priority, early.kind, early.method) == ("Não retirado", "menu", "mutation", "POST")
    assert early.enabled is False
    assert early.reason == "Pedido pago: o não retirado libera no corte do dia, às 19h."
    assert early.confirmation == {"required": True, "manager_approval": True}

    relogio(19)
    released = _detail_action(order, operador)
    assert released.enabled is True
    assert released.reason == ""
    assert released.payload_schema == {"base_revision": no_show.revision(order), "expected_actor_id": operador.pk}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"channel_ref": "ifood"},
        {"data": {"fulfillment_type": "delivery"}},
        {"channel_ref": "pdv", "data": {"origin_channel": "pos", "pos": {"sales_mode": "counter"}}},
    ],
)
def test_detail_does_not_offer_the_action_to_an_ineligible_order(operador, relogio, kwargs):
    relogio(19)
    order = _order(**kwargs)

    assert _detail_action(order, operador) is None


def test_detail_does_not_offer_the_action_before_the_order_is_ready(operador, relogio):
    relogio(19)
    order = _order()
    Order.objects.filter(pk=order.pk).update(status=Order.Status.PREPARING)
    order.refresh_from_db()

    assert _detail_action(order, operador) is None
