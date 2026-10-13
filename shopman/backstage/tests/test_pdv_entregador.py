"""PDV: "Chamar entregador" (TaOn) na encomenda de entrega da casa (dono, 13/10/2026).

O balcão não tem régua própria: o detalhe da encomenda (contexto "pos") traz o
MESMO bloco ``courier`` e as MESMAS ações ``courier-dispatch`` /
``courier-dispatch-again`` do Gestor, e a linha da lista diz o estado da corrida
lido desse bloco. Adapter mock — nunca a TaOn de verdade.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.projections import preorders
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja", route="Rua da Loja", street_number="10", city="Londrina",
        state_code="PR", latitude=-23.34, longitude=-51.15)


def _operator(*codenames: str) -> User:
    user = User.objects.create_user(f"pdv-{'-'.join(codenames) or 'none'}", password="pw", is_staff=True)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.fixture
def caixa(client):
    """O grupo Caixa: operar o PDV e gerenciar pedidos (``setup_groups``)."""
    user = _operator("operate_pos", "manage_orders")
    client.force_login(user)
    return client, user


def _delivery(ref="PDV-ENT", *, status=Order.Status.READY, channel_ref="pdv", **extra) -> Order:
    data = {
        "fulfillment_type": "delivery",
        "origin_channel": "pos",
        "pos": {"sales_mode": "order"},
        "delivery_date": timezone.localdate().isoformat(),
        "customer": {"name": "Ana Souza", "phone": "5543999990000"},
        "payment": {"method": "cash"},
        "delivery_address_structured": {"route": "Rua das Flores", "street_number": "123", "city": "Londrina",
            "state_code": "PR", "formatted_address": "Rua das Flores 123", "latitude": -23.31, "longitude": -51.16},
    }
    data.update(extra)
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, session_key=f"S-{ref}", status=status,
        snapshot={"items": []}, total_q=1500, data=data)
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1,
        unit_price_q=1500, line_total_q=1500)
    return order


def _detail(client, ref):
    response = client.get(f"/api/v1/backstage/pos/preorders/{ref}/")
    assert response.status_code == 200, response.content
    return response.json()["order"]


def _row(client, ref):
    body = client.get("/api/v1/backstage/pos/preorders/").json()
    return next(card for day in body["days"] for card in day["orders"] if card["ref"] == ref)


def _action(detail, ref):
    return next((action for action in detail["actions"] if action["ref"] == ref), None)


# ── O detalhe: o bloco e as ações do Gestor ───────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_o_detalhe_da_encomenda_de_entrega_pronta_oferece_chamar(caixa, shop):
    client, _ = caixa
    _delivery()

    detail = _detail(client, "PDV-ENT")

    assert detail["courier"]["can_dispatch"] is True
    dispatch = _action(detail, "courier-dispatch")
    assert dispatch["enabled"] is True
    # A MESMA pergunta do Gestor, do servidor.
    assert dispatch["confirmation"]["description"].startswith("Chamar um entregador")
    assert "cobrada da casa" in dispatch["confirmation"]["description"]
    # O balcão chama e chama de novo; cancelar e cotar a corrida ficam no Gestor.
    assert _action(detail, "courier-cancel") is None
    assert _action(detail, "courier-quote") is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_o_balcao_e_o_gestor_leem_o_mesmo_bloco_e_a_mesma_acao(caixa, shop):
    client, user = caixa
    _delivery()

    pos = _detail(client, "PDV-ENT")
    gestor = client.get(reverse("api-backstage-order-detail", args=["PDV-ENT"])).json()["order"]

    assert pos["courier"] == gestor["courier"]
    assert _action(pos, "courier-dispatch") == _action(gestor, "courier-dispatch")
    assert _action(pos, "courier-dispatch-again") == _action(gestor, "courier-dispatch-again")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_o_caixa_chama_pela_mesma_rota_do_gestor(caixa, shop):
    client, _ = caixa
    _delivery()
    schema = _action(_detail(client, "PDV-ENT"), "courier-dispatch")["payload_schema"]

    response = client.post(reverse("api-backstage-order-courier-dispatch", args=["PDV-ENT"]), schema,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY="pdv-chamar")

    assert response.status_code == 200, response.content
    assert Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref="PDV-ENT").count() == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sem_resposta_da_taon_o_detalhe_oferece_chamar_de_novo(caixa, shop):
    client, _ = caixa
    order = _delivery()
    Directive.objects.create(topic=COURIER_DISPATCH, status="failed",
        payload={"order_ref": order.ref, "actor": "lab", "dispatch_attempt": {"state": "unknown"}})

    detail = _detail(client, order.ref)

    assert _action(detail, "courier-dispatch")["enabled"] is False
    assert _action(detail, "courier-dispatch-again")["enabled"] is True
    card = detail["counter"]["card"]
    assert (card["courier_label"], card["courier_tone"], card["courier_call"]) == ("Sem resposta da TaOn", "warning", True)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_retirada_e_entrega_do_marketplace_nao_tem_entregador_no_balcao(caixa, shop):
    client, _ = caixa
    _delivery("PDV-RET", fulfillment_type="pickup")
    _delivery("IF-ENT", channel_ref="ifood", origin_channel="ifood", pos={},
        ifood={"delivered_by": "IFOOD"})

    for ref in ("PDV-RET", "IF-ENT"):
        detail = _detail(client, ref)
        assert detail["courier"] is None
        assert _action(detail, "courier-dispatch") is None
        assert detail["counter"]["card"]["courier_label"] == ""


def test_sem_a_taon_ligada_o_balcao_nao_oferece_chamar(caixa, shop):
    client, _ = caixa
    _delivery()

    detail = _detail(client, "PDV-ENT")

    assert detail["courier"] is None
    assert _action(detail, "courier-dispatch") is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sem_gerenciar_pedidos_a_acao_vem_apagada_e_a_rota_recusa(client, shop):
    """O PDV inteiro já pede ``manage_orders`` nas Encomendas; a chamada, também."""
    user = _operator("operate_pos")
    client.force_login(user)
    _delivery()

    response = client.post(reverse("api-backstage-order-courier-dispatch", args=["PDV-ENT"]),
        {"expected_actor_id": user.pk, "base_revision": "x"}, content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="pdv-sem-permissao")

    assert response.status_code == 403
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


# ── A linha da lista ──────────────────────────────────────────────────────


@pytest.mark.parametrize(("status", "label", "tone"), [
    ("P", "Procurando entregador", "neutral"),
    ("A", "Entregador a caminho da loja", "info"),
    ("E", "Saiu para entrega", "info"),
    ("F", "Entregue", "success"),
    ("N", "Não atendida", "danger"),
])
@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_linha_diz_o_estado_da_corrida(caixa, shop, status, label, tone):
    client, _ = caixa
    _delivery(courier={"provider": "machine", "id_mch": "R1", "status": status},
        **({"status": Order.Status.DISPATCHED} if status == "E" else {"status": Order.Status.DELIVERED} if status == "F" else {}))

    card = _row(client, "PDV-ENT")

    assert (card["courier_label"], card["courier_tone"]) == (label, tone)
    # Ninguém aceitou: chamar outro está à mão; corrida em curso ou entregue, não.
    assert card["courier_call"] is (status == "N")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_entrega_pronta_sem_corrida_diz_que_o_entregador_nao_foi_chamado(caixa, shop):
    client, _ = caixa
    _delivery()
    _delivery("PDV-CEDO", status=Order.Status.NEW)

    pronta = _row(client, "PDV-ENT")
    cedo = _row(client, "PDV-CEDO")

    assert (pronta["courier_label"], pronta["courier_tone"], pronta["courier_call"]) == (
        preorders.COURIER_NOT_CALLED_LABEL, "warning", True)
    # Antes de poder chamar (a régua é do servidor: `courier.RIDE_ORDER_STATUSES`),
    # a linha não fala da corrida (zero não é informação).
    assert (cedo["courier_label"], cedo["courier_call"]) == ("", False)


# ── Seguimento: o canal pelo nome, o aviso que contradizia a tela ─────────


def test_o_detalhe_diz_o_canal_pelo_nome_nunca_pelo_ref_cru(caixa, shop):
    """Sem cadastro do canal, o rótulo humano das Encomendas ("PDV"), não o "pdv"."""
    client, _ = caixa
    _delivery()

    assert _detail(client, "PDV-ENT")["channel_name"] == "PDV"


def test_o_canal_cadastrado_fala_o_nome_do_cadastro(caixa, shop):
    from shopman.shop.models import Channel

    client, _ = caixa
    Channel.objects.create(ref="pdv", name="Balcão da loja")
    _delivery()

    assert _detail(client, "PDV-ENT")["channel_name"] == "Balcão da loja"
