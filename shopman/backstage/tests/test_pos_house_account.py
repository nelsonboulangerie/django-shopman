"""Conta do cliente no PDV, pela API crua (WP-10 do CASHMAN-PLAN).

- O lookup do cliente diz se ele tem conta e quanto deve (só para quem tem).
- A venda "em conta" passa pela API de venda só para cliente elegível.
- A antesala lista as contas em aberto (``cash_runtime.account_balances``).
- O acerto em dinheiro entra no turno aberto de quem recebeu; pix é atestado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.payman.models import PaymentIntent

from shopman.backstage.projections.pos import build_pos, build_pos_customer_lookup
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as shop_pos

pytestmark = pytest.mark.django_db


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
    ct = ContentType.objects.get_for_model(Shift)
    operator.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))
    shift = cash.open_shift(operator=operator, float_q=10000)
    ana = Customer.objects.create(ref="CLI-ANA", first_name="Ana", phone="+5543999990001", metadata={"house_account": True})
    bia = Customer.objects.create(ref="CLI-BIA", first_name="Bia", phone="+5543999990002")
    return {"operator": operator, "shift": shift, "ana": ana, "bia": bia}


def _sell_on_account(counter, *, customer_ref: str, ref: str, qty: int = 1):
    return shop_pos.close_sale(
        channel_ref="pdv",
        payload={
            "items": [{"sku": "PAO", "name": "Pão", "qty": qty, "unit_price_q": 1200}],
            "customer_ref": customer_ref,
            "payment_method": "account",
            "client_request_id": ref,
            "cash_shift_id": counter["shift"].pk,
        },
        actor="pos:marina",
        operator_username="marina",
    )


def test_o_lookup_diz_quem_tem_conta_e_quanto_deve(counter):
    ana = build_pos_customer_lookup("+5543999990001")
    bia = build_pos_customer_lookup("+5543999990002")
    assert (ana.house_account, ana.account_balance_q) == (True, 0)
    assert (bia.house_account, bia.account_balance_q) == (False, 0)

    _sell_on_account(counter, customer_ref="CLI-ANA", ref="c-1", qty=2)
    assert build_pos_customer_lookup("+5543999990001").account_balance_q == 2400


def test_acerto_pela_api_em_dinheiro_e_em_pix(client, counter):
    client.force_login(counter["operator"])
    _sell_on_account(counter, customer_ref="CLI-ANA", ref="c-1", qty=1)   # 12
    _sell_on_account(counter, customer_ref="CLI-ANA", ref="c-2", qty=2)   # 24

    body = client.get(reverse("api-backstage-pos-accounts")).json()
    assert body["accounts"] == [{
        "customer_ref": "CLI-ANA", "customer_name": "Ana", "balance_q": 3600, "balance_display": "R$ 36,00",
        "intents": 2, "oldest_at": body["accounts"][0]["oldest_at"],
    }]
    assert body["accounts"][0]["oldest_at"]

    # A antesala também lista.
    runtime = build_pos(operator=counter["operator"]).cash_runtime
    assert [a.customer_ref for a in runtime.account_balances] == ["CLI-ANA"]

    # R$ 12 em dinheiro: captura a venda mais antiga; entra na gaveta.
    response = client.post(
        reverse("api-backstage-pos-account-settle", args=["CLI-ANA"]),
        {"amount": "12,00", "method": "cash"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.json()
    assert (response.json()["settled_q"], response.json()["remaining_q"]) == (1200, 2400)
    (line,) = Entry.objects.filter(kind=Entry.Kind.ACCOUNT_SETTLED)
    assert (line.amount_q, line.shift_id, line.payload["customer_ref"]) == (1200, counter["shift"].pk, "CLI-ANA")
    assert cash.balance(counter["shift"]) == 11200

    # Valor que não cobre a próxima venda inteira: recusa e nada muda.
    response = client.post(
        reverse("api-backstage-pos-account-settle", args=["CLI-ANA"]),
        {"amount": "10,00", "method": "cash"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "venda inteira" in response.json()["detail"]

    # O resto por pix, atestado no balcão: nada na gaveta, saldo zera.
    response = client.post(
        reverse("api-backstage-pos-account-settle", args=["CLI-ANA"]),
        {"amount": "24,00", "method": "pix"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["remaining_q"] == 0
    assert Entry.objects.filter(kind=Entry.Kind.ACCOUNT_SETTLED).count() == 1
    assert PaymentIntent.objects.filter(method="account", status="authorized").count() == 0
    assert client.get(reverse("api-backstage-pos-accounts")).json()["accounts"] == []


def test_acerto_em_dinheiro_exige_turno_aberto(client, counter):
    _sell_on_account(counter, customer_ref="CLI-ANA", ref="c-1")
    cash.close_shift(counter["shift"], counted_q=10000, actor=counter["operator"])
    client.force_login(counter["operator"])
    response = client.post(
        reverse("api-backstage-pos-account-settle", args=["CLI-ANA"]),
        {"amount": "12,00", "method": "cash"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "turno" in response.json()["detail"]
