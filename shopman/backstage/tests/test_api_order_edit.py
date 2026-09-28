"""POST /api/v1/backstage/orders/<ref>/edit/ (+ /preview/) e o estorno da maquininha.

A regra mora em ``shop.services.order_edit`` (``shop/tests/test_order_edit.py``);
aqui só as portas: permissão ``shop.manage_orders``, prévia que não grava e
devolve a revisão, intenção idempotente como as outras ações de pedido, revisão
``edit`` lida (409 quando velha), recusa no dialeto ``{detail, field, errors}``
com ``error.code``, PIN de gerente na redução paga — e a pendência da
maquininha fechada pelo PDV.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Terminal
from shopman.doorman.models import PinCredential
from shopman.offerman.models import Product
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.projections.preorders import build_preorder_detail
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services import order_composition
from shopman.shop.services import payment as payment_service
from shopman.shop.services.operator_orders import operational_revision

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, app_label: str, model: str, codename: str) -> None:
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get(app_label=app_label, model=model), codename=codename)
    )


@pytest.fixture
def shop(db):
    Channel.objects.create(ref="web", name="Loja", config={"payment": {"timing": "external", "method": "cash"}})
    # SKUs fora do Stockman: sem reserva — a porta é o que está em teste.
    Product.objects.create(sku="SKU", name="Produto", base_price_q=1500, is_published=True, is_sellable=True)
    Product.objects.create(sku="NOVO", name="Novo", base_price_q=500, is_published=True, is_sellable=True)
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(shop):
    user = User.objects.create_user("edit-op", password="pw", is_staff=True)
    _grant(user, "shop", "shop", "manage_orders")
    _grant(user, "cashman", "shift", "operate_pos")
    return user


@pytest.fixture
def manager(shop):
    user = User.objects.create_user("edit-gerente", password="pw", is_staff=True)
    _grant(user, "cashman", "shift", "adjust_shift")
    PinCredential.set_for(user, MANAGER_PIN)
    return user


@pytest.fixture
def plain_staff(shop):
    return User.objects.create_user("edit-plain", password="pw", is_staff=True)


def _day(offset: int):
    return timezone.localdate() + timedelta(days=offset)


def _order(ref: str, *, qty: int = 2, method: str = "cash", paid: bool = False) -> Order:
    total = 1500 * qty
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="accepted", total_q=total,
        data={"customer": {"name": "Ana"}, "payment": {"method": method}, "fulfillment_type": "pickup",
              "delivery_date": _day(3).isoformat(), "delivery_time_slot": "slot-09", "is_preorder": True},
    )
    OrderItem.objects.create(order=order, line_id="L1", sku="SKU", name="Produto", qty=qty, unit_price_q=1500, line_total_q=total)
    if paid:
        intent = PaymentService.settle(order.ref, total, method, idempotency_key=f"t:{ref}")
        order.data["payment"]["intent_ref"] = intent.ref
        order.save(update_fields=["data", "updated_at"])
    return order


def _body(operator, order, **inputs):
    return {
        "expected_actor_id": operator.pk,
        "base_revision": operational_revision(order, field="edit"),
        "idempotency_key": str(uuid4()),
        **inputs,
    }


def test_sem_permissao_e_403(client, plain_staff, shop):
    order = _order("ED-API-0")
    client.force_login(plain_staff)
    for name in ("api-backstage-order-edit", "api-backstage-order-edit-preview"):
        response = client.post(reverse(name, args=[order.ref]), data={"items": []}, content_type="application/json")
        assert response.status_code == 403


def test_previa_nao_grava_e_devolve_a_revisao(client, operator):
    order = _order("ED-API-1")
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-order-edit-preview", args=[order.ref]),
        data={"items": [{"line_id": "L1", "sku": "SKU", "qty": 2}, {"sku": "NOVO", "qty": 1}]},
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["base_revision"] == operational_revision(order, field="edit")
    preview = body["preview"]
    assert preview["previous_total_q"] == 3000 and preview["total_q"] == 3500 and preview["difference_q"] == 500
    assert preview["settlement"] == {"kind": "collect", "amount_q": 3500, "method": ""}
    assert [item["is_new"] for item in preview["items"]] == [False, True]
    assert preview["customer_note"] == "Entrou 1 Novo. Novo total R$ 35,00, a pagar na retirada"
    order.refresh_from_db()
    assert not order_composition.is_adjusted(order)


def test_edita_e_aparece_no_historico(client, operator):
    order = _order("ED-API-2")
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-order-edit", args=[order.ref]),
        data=_body(operator, order, items=[{"line_id": "L1", "sku": "SKU", "qty": 3}], notes="sem açúcar"),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["outcome"] == "applied" and body["changed"] is True and body["revision"] == 1
    order.refresh_from_db()
    assert order_composition.effective_total_q(order) == 4500
    assert order.data["order_notes"] == "sem açúcar"
    assert "edit" in body["order"]["revisions"]
    (event,) = [e for e in body["order"]["timeline"] if e["event_type"] == "order_edited"]
    assert event["label"] == "Encomenda editada"
    assert event["detail"].startswith("Produto passou de 2 para 3. Anotamos a sua observação.")


def test_revisao_velha_e_conflito(client, operator):
    order = _order("ED-API-3")
    client.force_login(operator)
    stale = _body(operator, order, notes="primeira")
    order.data = {**order.data, "order_notes": "mudou em outra tela"}
    order.save(update_fields=["data", "updated_at"])

    response = client.post(reverse("api-backstage-order-edit", args=[order.ref]), data=stale, content_type="application/json")

    assert response.status_code == 409
    order.refresh_from_db()
    assert order.data["order_notes"] == "mudou em outra tela"


def test_recusa_sai_no_dialeto_de_campo(client, operator):
    order = _order("ED-API-4")
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-order-edit", args=[order.ref]),
        data=_body(operator, order, items=[{"sku": "NAO-EXISTE", "qty": 1}]),
        content_type="application/json",
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "items.0"
    assert body["errors"] == {"items.0": [body["detail"]]}
    assert body["error"]["code"] == "unknown_sku"
    assert body["outcome"] == "not_applied"


def test_reducao_paga_pede_gerente_e_com_pin_aplica(client, operator, manager):
    order = _order("ED-API-5", qty=3, paid=True)
    client.force_login(operator)
    url = reverse("api-backstage-order-edit", args=[order.ref])
    items = [{"line_id": "L1", "sku": "SKU", "qty": 1}]

    response = client.post(url, data=_body(operator, order, items=items), content_type="application/json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"
    assert response.json()["outcome"] == "not_applied"

    response = client.post(
        url,
        data=_body(operator, order, items=items, manager_approval={"username": manager.username, "pin": MANAGER_PIN}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    assert response.json()["preview"]["settlement"] == {"kind": "refund_cash", "amount_q": 3000, "method": "cash"}
    (pending,) = payment_service.pending_cash_refunds()
    assert pending.order_ref == order.ref and pending.amount_q == 3000 and pending.reason == "reduced"
    order.refresh_from_db()
    assert order.events.get(type="order_edited").payload["approved_by"] == manager.username


def test_estorno_da_maquininha_fecha_a_pendencia_pelo_pdv(client, operator, manager):
    order = _order("ED-API-6", qty=2, method="credit", paid=True)
    client.force_login(operator)
    response = client.post(
        reverse("api-backstage-order-edit", args=[order.ref]),
        data=_body(
            operator, order, items=[{"line_id": "L1", "sku": "SKU", "qty": 1}],
            manager_approval={"username": manager.username, "pin": MANAGER_PIN},
        ),
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    (pending,) = payment_service.pending_card_machine_refunds()
    assert pending.amount_q == 1500

    bind_station(client, Terminal.default().ref)
    url = reverse("api-backstage-pos-card-machine-refund", args=[order.ref])
    response = client.post(url, data={"client_request_id": "t-cm-1"}, content_type="application/json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"

    response = client.post(
        url,
        data={"client_request_id": "t-cm-2", "manager_approval": {"username": manager.username, "pin": MANAGER_PIN}},
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    assert response.json() == {"ok": True, "refunded_q": 1500}
    assert payment_service.pending_card_machine_refunds() == []


def test_detalhe_da_encomenda_oferece_editar_com_a_revisao_certa(operator):
    order = _order("ED-API-7")

    detail = build_preorder_detail(order.ref, user=operator)

    assert detail.edit.allowed is True and detail.edit.cancel_and_redo is False
    assert detail.edit.revision == operational_revision(order, field="edit")
    # Reagendar confere a revisão DA DATA: é ela que o detalhe precisa entregar.
    assert detail.reschedule.revision == operational_revision(order, field="schedule")

    order.data = {**order.data, "nfce_access_key": "4126" + "0" * 40}
    order.save(update_fields=["data", "updated_at"])
    detail = build_preorder_detail(order.ref, user=operator)
    assert detail.edit.allowed is False and detail.edit.cancel_and_redo is True
    assert "cancele e refaça" in detail.edit.block_reason


def test_reagendar_pelo_pdv_com_a_revisao_do_detalhe_aplica(client, operator):
    """Regressão: o PDV mandava a revisão geral e todo reagendamento voltava 409."""
    order = _order("ED-API-8")
    detail = build_preorder_detail(order.ref, user=operator)
    client.force_login(operator)

    response = client.post(
        reverse("api-backstage-order-reschedule", args=[order.ref]),
        data={
            "date": _day(5).isoformat(), "slot": "slot-12", "expected_actor_id": operator.pk,
            "base_revision": detail.reschedule.revision, "idempotency_key": str(uuid4()),
        },
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    assert response.json()["changed"] is True
