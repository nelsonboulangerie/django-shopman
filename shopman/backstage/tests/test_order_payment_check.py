"""O detalhe do pedido só LÊ; perguntar ao gateway do cartão é comando (A8-1).

O Gestor e o detalhe da encomenda no PDV perguntavam ao gateway dentro do GET:
toda releitura da tela era uma chance de chamada ao provedor e de carimbo
``gateway_checked_at`` no pedido. Agora a leitura diz ``payment_check_due`` e a
tela pede o comando ``POST .../payment/check/`` quando ele é verdadeiro. O que
se prova aqui:

* o GET do detalhe não chama o gateway nem grava nada no pedido, nos dois
  contextos (Gestor e PDV);
* ``payment_check_due`` é verdadeiro só para cartão em aberto sem captura;
* o POST pergunta ao gateway, liquida o webhook perdido e respeita o intervalo
  mínimo (``GATEWAY_RECHECK_SECONDS``);
* a porta do POST é a mesma do detalhe (permissão e corte das encomendas).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.cashman.models import Terminal
from shopman.orderman.models import Order, OrderItem
from shopman.payman import PaymentService

from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.adapters import payment_stripe
from shopman.shop.models import Channel, Shop

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("stripe_card"),
]


@pytest.fixture
def stripe_card():
    with override_settings(
        SHOPMAN_STRIPE={
            "secret_key": "sk_test_fake",
            "webhook_secret": "whsec_test_fake",
            "capture_method": "manual",
            "domain": "https://shop.example.com",
        },
        SHOPMAN_PAYMENT_ADAPTERS={
            "pix": "shopman.shop.adapters.payment_mock",
            "card": "shopman.shop.adapters.payment_stripe",
        },
    ):
        yield


@pytest.fixture
def gestor(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={})
    user = User.objects.create_user("gestor-cartao", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"
        )
    )
    return user


@pytest.fixture
def balcao(gestor):
    user = User.objects.create_user("caixa-cartao", password="pw", is_staff=True)
    for codename in ("operate_pos", "manage_orders"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _card_order(ref: str, *, status=Order.Status.NEW, method="card") -> tuple[Order, object]:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=status,
        total_q=1500,
        data={
            "customer": {"name": "Ana"},
            "fulfillment_type": "pickup",
            "delivery_date": timezone.localdate().isoformat(),
        },
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
    intent = PaymentService.create_intent(
        order_ref=order.ref, amount_q=order.total_q, method=method, gateway="stripe", gateway_data={}
    )
    intent.gateway_id = f"pi_{ref.lower()}"
    intent.save(update_fields=["gateway_id"])
    order.data["payment"] = {"method": method, "intent_ref": intent.ref}
    order.save(update_fields=["data", "updated_at"])
    return order, intent


def _gestor_client(client, gestor):
    client.force_login(gestor)
    return client


def _balcao_client(client, balcao):
    client.force_login(balcao)
    bind_station(client, Terminal.default().ref)
    return client


ROUTES = {
    "gestor": ("api-backstage-order-detail", "api-backstage-order-payment-check", _gestor_client, "gestor"),
    "pdv": ("api-backstage-pos-preorder-detail", "api-backstage-pos-preorder-payment-check", _balcao_client, "balcao"),
}


@pytest.mark.parametrize("context", sorted(ROUTES))
def test_o_GET_do_detalhe_nao_pergunta_ao_gateway_nem_grava(client, request, context):
    detail_route, _check, login, user_fixture = ROUTES[context]
    logged = login(client, request.getfixturevalue(user_fixture))
    order, _intent = _card_order(f"GET-{context.upper()}")
    before = Order.objects.get(pk=order.pk)

    with patch.object(payment_stripe, "check_gateway_status") as asked:
        first = logged.get(reverse(detail_route, args=[order.ref]))
        second = logged.get(reverse(detail_route, args=[order.ref]))

    assert first.status_code == 200, first.content
    assert second.status_code == 200
    asked.assert_not_called()
    assert first.json()["payment_check_due"] is True
    after = Order.objects.get(pk=order.pk)
    assert after.data == before.data
    assert "gateway_checked_at" not in after.data["payment"]
    assert after.updated_at == before.updated_at


@pytest.mark.parametrize("context", sorted(ROUTES))
def test_o_POST_pergunta_ao_gateway_e_liquida_o_webhook_perdido(client, request, context):
    detail_route, check_route, login, user_fixture = ROUTES[context]
    logged = login(client, request.getfixturevalue(user_fixture))
    order, intent = _card_order(f"POST-{context.upper()}")

    with patch.object(payment_stripe, "check_gateway_status", return_value="authorized") as asked:
        response = logged.post(reverse(check_route, args=[order.ref]))

    assert response.status_code == 200, response.content
    assert response.json()["changed"] is True
    asked.assert_called_once()
    intent.refresh_from_db()
    assert intent.status == "authorized"
    # Autorizar não é capturar: quem captura é o lifecycle, no aceite.
    assert PaymentService.captured_total(intent.ref) == 0


def test_o_POST_respeita_o_intervalo_minimo_entre_perguntas(client, gestor):
    logged = _gestor_client(client, gestor)
    order, _intent = _card_order("POST-THROTTLE")
    url = reverse("api-backstage-order-payment-check", args=[order.ref])

    with patch.object(payment_stripe, "check_gateway_status", return_value="pending") as asked:
        first = logged.post(url)
        second = logged.post(url)

    assert first.json() == {"ok": True, "changed": False, "payment_check_due": True}
    assert second.json()["changed"] is False
    assert asked.call_count == 1


def test_o_gateway_fora_do_ar_nao_derruba_o_gesto(client, gestor):
    logged = _gestor_client(client, gestor)
    order, _intent = _card_order("POST-DOWN")

    with patch.object(payment_stripe, "check_gateway_status", side_effect=RuntimeError("stripe caiu")):
        response = logged.post(reverse("api-backstage-order-payment-check", args=[order.ref]))

    assert response.status_code == 200
    assert response.json()["changed"] is False


@pytest.mark.parametrize(
    ("ref", "kwargs"),
    [
        ("DUE-PIX", {"method": "pix"}),
        ("DUE-DONE", {"status": Order.Status.COMPLETED}),
    ],
)
def test_payment_check_due_so_para_cartao_em_aberto(client, gestor, ref, kwargs):
    logged = _gestor_client(client, gestor)
    order, _intent = _card_order(ref, **kwargs)

    body = logged.get(reverse("api-backstage-order-detail", args=[order.ref])).json()

    assert body["payment_check_due"] is False


def test_payment_check_due_cai_quando_o_cartao_foi_capturado(client, gestor):
    logged = _gestor_client(client, gestor)
    order, intent = _card_order("DUE-PAID", status=Order.Status.ACCEPTED)
    PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
    PaymentService.capture(intent.ref, gateway_id=intent.gateway_id)

    body = logged.get(reverse("api-backstage-order-detail", args=[order.ref])).json()

    assert body["payment_check_due"] is False


def test_o_POST_tem_a_porta_do_detalhe(client, db, gestor):
    order, _intent = _card_order("PORTA")
    estranho = User.objects.create_user("sem-permissao", password="pw", is_staff=True)
    client.force_login(estranho)

    with patch.object(payment_stripe, "check_gateway_status") as asked:
        gestor_resp = client.post(reverse("api-backstage-order-payment-check", args=[order.ref]))
        pdv_resp = client.post(reverse("api-backstage-pos-preorder-payment-check", args=[order.ref]))

    assert gestor_resp.status_code in (401, 403)
    assert pdv_resp.status_code in (401, 403)
    asked.assert_not_called()


def test_o_POST_do_pdv_fica_no_corte_das_encomendas(client, balcao):
    logged = _balcao_client(client, balcao)
    order, _intent = _card_order("CORTE", status=Order.Status.CANCELLED)

    with patch.object(payment_stripe, "check_gateway_status") as asked:
        response = logged.post(reverse("api-backstage-pos-preorder-payment-check", args=[order.ref]))

    assert response.status_code == 404
    asked.assert_not_called()


def test_pedido_inexistente_e_404(client, gestor):
    logged = _gestor_client(client, gestor)
    assert logged.post(reverse("api-backstage-order-payment-check", args=["NAO-EXISTE"])).status_code == 404
