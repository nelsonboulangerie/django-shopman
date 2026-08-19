"""Cancelar não é devolver: o dinheiro de venda cancelada sai pela gaveta de quem devolve.

Às 22h o gestor cancela; ninguém abriu gaveta. O pedido morre, o intent em
dinheiro fica capturado, e a devolução aparece PENDENTE na antesala até alguém
com turno aberto entregar as notas ("Devolver", com PIN de gerente). Só então
Payman e livro-caixa registram, juntos. No balcão, dentro da janela, cliente na
frente: cancelar e devolver são o mesmo gesto.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift
from shopman.doorman.models import PinCredential
from shopman.offerman.models import Product
from shopman.orderman.models import Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.backstage.projections.pos import build_pos
from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSError
from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders
from shopman.shop.services import pos as shop_pos

pytestmark = pytest.mark.django_db

MANAGER_PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def counter():
    Shop.objects.create(name="Loja", brand_name="Loja")
    Channel.objects.create(
        ref="pdv", name="PDV", is_active=True,
        config={"confirmation": {"mode": "immediate"}, "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False}},
    )
    Product.objects.create(sku="PAO", name="Pão", base_price_q=1200, is_published=True, is_sellable=True)
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    _grant(operator, "operate_pos")
    manager = get_user_model().objects.create_user(username="pablo", password="x", is_staff=True)
    _grant(manager, "adjust_shift")
    PinCredential.set_for(manager, MANAGER_PIN)
    shift = cash.open_shift(operator=operator, float_q=10000)
    return {"operator": operator, "manager": manager, "shift": shift}


def _sell(counter, ref: str) -> Order:
    result = shop_pos.close_sale(
        channel_ref="pdv",
        payload={
            "items": [{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1200}],
            "customer_name": "Cliente",
            "payment_method": "cash",
            "tendered_amount_q": 1200,
            "client_request_id": ref,
            "cash_shift_id": counter["shift"].pk,
        },
        actor="pos:marina",
        operator_username="marina",
    )
    return Order.objects.get(ref=result.order_ref)


def _approval() -> dict:
    return {"username": "pablo", "pin": MANAGER_PIN}


# ── Cancelar pelo gestor deixa a devolução pendente ───────────────────────


def test_cancelar_pelo_gestor_nao_devolve_o_dinheiro(counter, django_capture_on_commit_callbacks):
    order = _sell(counter, "r1")
    intent_ref = order.data["payment"]["intent_ref"]

    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")

    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert PaymentService.get(intent_ref).status == PaymentIntent.Status.CAPTURED
    assert not Entry.objects.filter(kind=Entry.Kind.REFUND).exists()
    assert cash.balance(counter["shift"]) == 11200  # o dinheiro continua na gaveta

    runtime = build_pos(operator=counter["operator"]).cash_runtime
    (pending,) = runtime.pending_cash_refunds
    assert pending.order_ref == order.ref
    assert pending.amount_q == 1200
    assert pending.amount_display == "R$ 12,00"
    assert "refund_cash" in {a.ref for a in build_pos(operator=counter["operator"]).actions}


def test_a_pendencia_aparece_para_quem_abrir_o_caixa_depois(counter, django_capture_on_commit_callbacks):
    """O turno da venda fechou; quem abre a gaveta amanhã vê a devolução a fazer."""
    order = _sell(counter, "r2")
    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")
    cash.close_shift(counter["shift"], counted_q=11200, actor=counter["operator"])

    tomorrow = cash.open_shift(operator=counter["operator"], float_q=5000)
    runtime = build_pos(operator=counter["operator"]).cash_runtime
    assert [p.order_ref for p in runtime.pending_cash_refunds] == [order.ref]
    assert runtime.shift_id == tomorrow.pk


# ── Devolver: turno aberto, PIN, os dois livros ───────────────────────────


def test_devolver_grava_payman_e_livro_na_gaveta_de_quem_devolve(counter, django_capture_on_commit_callbacks):
    order = _sell(counter, "r3")
    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")

    refunded = pos_service.refund_cash(operator=counter["operator"], order_ref=order.ref, manager_approval=_approval())

    assert refunded == 1200
    line = Entry.objects.get(kind=Entry.Kind.REFUND)
    assert line.shift == counter["shift"]
    assert line.amount_q == -1200
    assert line.approved_by == counter["manager"]
    assert line.parent.kind == Entry.Kind.SALE and line.parent.order_ref == order.ref
    assert PaymentService.get(order.data["payment"]["intent_ref"]).status == PaymentIntent.Status.REFUNDED
    assert cash.balance(counter["shift"]) == 10000
    assert build_pos(operator=counter["operator"]).cash_runtime.pending_cash_refunds == ()


def test_devolver_exige_pin_de_gerente_e_venda_cancelada(counter):
    order = _sell(counter, "r4")
    from shopman.shop.services.pos_intent import PosIntentError

    with pytest.raises(PosIntentError) as exc:
        pos_service.refund_cash(operator=counter["operator"], order_ref=order.ref)
    assert exc.value.code == "manager_approval_required"
    with pytest.raises(POSError, match="cancelada"):
        pos_service.refund_cash(operator=counter["operator"], order_ref=order.ref, manager_approval=_approval())


def test_devolver_duas_vezes_diz_que_nao_ha_pendencia(counter, django_capture_on_commit_callbacks):
    order = _sell(counter, "r5")
    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")
    pos_service.refund_cash(operator=counter["operator"], order_ref=order.ref, manager_approval=_approval())
    with pytest.raises(POSError, match="pendente"):
        pos_service.refund_cash(operator=counter["operator"], order_ref=order.ref, manager_approval=_approval())
    assert Entry.objects.filter(kind=Entry.Kind.REFUND).count() == 1


def test_endpoint_de_devolucao(client, counter, django_capture_on_commit_callbacks):
    order = _sell(counter, "r6")
    with django_capture_on_commit_callbacks(execute=True):
        operator_orders.cancel_order(order, reason="customer_requested", actor="gestor:pablo")
    client.force_login(counter["operator"])

    response = client.post(
        reverse("api-backstage-pos-cash-refund", args=[order.ref]), data={}, content_type="application/json"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"

    response = client.post(
        reverse("api-backstage-pos-cash-refund", args=[order.ref]),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "refunded_q": 1200}


def test_endpoint_exige_permissao_de_operar_pdv(client, counter):
    curious = get_user_model().objects.create_user(username="curioso", password="x")
    client.force_login(curious)
    response = client.post(
        reverse("api-backstage-pos-cash-refund", args=["X"]),
        data={"manager_approval": _approval()},
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


# ── No balcão, dentro da janela, cancelar e devolver são o mesmo gesto ────


def test_cancel_no_pdv_devolve_na_hora_e_assina_o_gerente(client, counter, django_capture_on_commit_callbacks):
    order = _sell(counter, "r7")
    client.force_login(counter["operator"])

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("api-backstage-pos-cancel-recent-sale"),
            data={"order_ref": order.ref, "manager_approval": _approval()},
            content_type="application/json",
        )

    assert response.status_code == 200, response.content
    line = Entry.objects.get(kind=Entry.Kind.REFUND)
    assert line.amount_q == -1200
    assert line.approved_by == counter["manager"]
    assert PaymentService.get(order.data["payment"]["intent_ref"]).status == PaymentIntent.Status.REFUNDED
    assert build_pos(operator=counter["operator"]).cash_runtime.pending_cash_refunds == ()
