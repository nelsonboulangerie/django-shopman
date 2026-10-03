"""O detalhe do pedido é UM contrato — o Gestor e o PDV são telas irmãs.

Decisão do dono (28/09/2026): o detalhe do pedido no Gestor e o da encomenda no
PDV mostram a MESMA estrutura e o mesmo conteúdo (resumo, cliente, nota fiscal,
itens, observação do cliente, nota da cozinha, histórico); o que muda entre os
dois é só a barra de ações, e quem decide as ações é o servidor pelo contexto.

Estes testes prendem o contrato: as seções de leitura são as mesmas nas duas
rotas, e cada contexto só oferece o que a tela dele executa.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.order_queue import DETAIL_CONTEXTS, build_operator_order

pytestmark = pytest.mark.django_db

#: As seções que as duas telas leem — o conteúdo comum do detalhe.
COMMON_SECTIONS = (
    "ref", "status", "status_label", "customer_name", "customer_phone", "channel_ref",
    "fulfillment_type", "fulfillment_label", "delivery_address", "total_display",
    "items", "timeline", "kitchen_note", "customer_note", "payment_method_label",
    "payment_status_label", "fiscal_status", "fiscal_status_label", "fiscal_links",
    "customer_profile", "schedule_label", "is_gift", "managers",
)


def _user(username: str, *codenames: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _order(ref: str = "DET-CTX", *, status: str = "accepted", channel_ref: str = "web", **data_extra) -> Order:
    data = {
        "customer": {"name": "Ana Souza", "phone": "+5543999887766"},
        "fulfillment_type": "pickup",
        "delivery_date": timezone.localdate().isoformat(),
        "delivery_time_slot": "slot-09",
        "order_notes": "Sem açúcar por cima",
        "kitchen_note": "Caprichar na casca",
        "payment": {"method": "cash"},
    }
    data.update(data_extra)
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=status, total_q=3600, data=data)
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão de fermentação natural",
                             qty=2, unit_price_q=1800, line_total_q=3600)
    return order


@pytest.fixture
def gestor(client):
    user = _user("gestora", "manage_orders")
    client.force_login(user)
    return client


@pytest.fixture
def caixa_user():
    return _user("caixa", "operate_pos", "manage_orders")


def test_as_duas_rotas_leem_o_mesmo_conteudo_e_so_o_contexto_muda(client, caixa_user):
    _order()
    client.force_login(caixa_user)

    no_gestor = client.get("/api/v1/backstage/orders/DET-CTX/").json()["order"]
    no_balcao = client.get("/api/v1/backstage/pos/preorders/DET-CTX/").json()["order"]

    assert {key: no_balcao[key] for key in COMMON_SECTIONS} == {key: no_gestor[key] for key in COMMON_SECTIONS}
    assert (no_gestor["context"], no_balcao["context"]) == ("orders", "pos")
    # O balcão passa a ver o que só o Gestor mostrava.
    assert no_balcao["kitchen_note"] == "Caprichar na casca"
    assert no_balcao["schedule_label"].startswith("Hoje · ")


def test_no_gestor_o_fluxo_inteiro_e_nenhum_bloco_de_balcao(gestor):
    _order(status="new")

    order = gestor.get("/api/v1/backstage/orders/DET-CTX/").json()["order"]

    assert order["counter"] is None
    refs = {action["ref"] for action in order["actions"]}
    assert {"confirm", "reject", "notes", "comment", "cancel"} <= refs


def test_no_balcao_so_os_gestos_do_balcao(client, caixa_user):
    _order(status="new")
    client.force_login(caixa_user)

    order = client.get("/api/v1/backstage/pos/preorders/DET-CTX/").json()["order"]

    # Das ações do fluxo, o balcão executa daqui só o comentário no histórico:
    # aceitar, avançar, nota da cozinha, atender e cancelar pelo Gestor não são dele.
    assert [action["ref"] for action in order["actions"]] == ["comment"]
    assert order["actions"][0]["enabled"] is True
    assert not any(order[flag] for flag in (
        "can_confirm", "can_advance", "can_cancel", "can_settle_delivery_cash", "can_resend_payment_link",
    ))
    assert order["courier"] is None and order["ifood_negotiations"] == []
    # Os gestos do balcão, com a régua de cada um.
    counter = order["counter"]
    assert counter["card"]["ref"] == "DET-CTX"
    assert set(counter) >= {"hand_over", "cancel", "reschedule", "edit", "revision", "actor_id", "ticket_printed"}
    assert counter["actor_id"] == caixa_user.pk


def test_o_balcao_comenta_no_historico_pela_rota_do_gestor(client, caixa_user):
    _order()
    client.force_login(caixa_user)
    comment = client.get("/api/v1/backstage/pos/preorders/DET-CTX/").json()["order"]["actions"][0]

    response = client.post(
        "/api/v1/backstage/orders/DET-CTX/comment/",
        {"note": "Cliente ligou: passa às 9h30.", **comment["payload_schema"], "idempotency_key": str(uuid4())},
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    timeline = client.get("/api/v1/backstage/pos/preorders/DET-CTX/").json()["order"]["timeline"]
    assert any("Cliente ligou" in (event["label"] + event["detail"]) for event in timeline)


def test_pedido_sem_data_combinada_nao_tem_previsao():
    order = _order(delivery_date=None, delivery_time_slot=None)

    assert build_operator_order(order).schedule_label == ""


def test_contexto_desconhecido_e_erro_e_nao_um_detalhe_silencioso():
    order = _order()

    assert DETAIL_CONTEXTS == ("orders", "pos")
    with pytest.raises(ValueError, match="Contexto de detalhe desconhecido"):
        build_operator_order(order, context="kds")


def test_o_cancelar_do_balcao_le_os_mesmos_motivos_prontos_do_gestor(client, caixa_user):
    """P7 do redesenho das Encomendas: no balcão, os motivos prontos são os do Gestor."""
    from django.core.cache import cache

    from shopman.shop.models import Shop

    Shop.objects.create(
        name="Loja Teste",
        cancellation_presets=[
            {"label": "Cliente desistiu", "group": "Cliente"},
            "Pedido em duplicidade",
        ],
    )
    cache.clear()  # Shop.load() memoriza o singleton
    _order()
    client.force_login(caixa_user)

    no_gestor = client.get("/api/v1/backstage/orders/DET-CTX/").json()["order"]
    no_balcao = client.get("/api/v1/backstage/pos/preorders/DET-CTX/").json()["order"]

    assert no_balcao["cancellation_presets"] == [
        {"label": "Cliente", "presets": ["Cliente desistiu"]},
        {"label": "", "presets": ["Pedido em duplicidade"]},
    ]
    assert no_balcao["cancellation_presets"] == no_gestor["cancellation_presets"]
