"""Achados do beta test de 05/11/2026 na Cozinha (KDS), travados no servidor.

- KDS-03: o pacote de um componente só não aparece com o nome duplicado.
- KDS-04: o ticket diz quando o PEDIDO entrou, além de quando chegou à cozinha.
- KDS-05: o painel do cliente não diz "Em preparo" para pedido que nenhuma estação recebeu.
- KDS-07: o telefone do cliente não vira nome no ticket.
- PDV-09: o roteamento diz se a estação é de preparo, o que vai à cozinha no balcão.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product, ProductComponent
from shopman.orderman.models import Order, OrderItem, Session

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_customer_status, build_kds_ticket
from shopman.shop.models import Shop
from shopman.shop.services import kds

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja():
    Shop.objects.create(name="Loja")


# ── KDS-03: pacote de um componente ──────────────────────────────────────


def _bundle_ticket(*, components: list[tuple[str, str, int]], parent_name: str, qty: int = 1):
    KDSInstance.objects.create(ref="separa", name="Encomendas", type="picking")
    Session.objects.create(session_key="BUNDLE-1", channel_ref="web")
    order = Order.objects.create(ref="BUNDLE-1", session_key="BUNDLE-1", status="preparing")
    parent = Product.objects.create(sku="PACOTE", name=parent_name)
    for sku, name, comp_qty in components:
        child = Product.objects.create(sku=sku, name=name)
        ProductComponent.objects.create(parent=parent, component=child, qty=Decimal(comp_qty))
    OrderItem.objects.create(
        order=order, line_id="L1", sku=parent.sku, name=parent.name, qty=Decimal(qty), unit_price_q=1000, line_total_q=1000,
    )
    return kds.dispatch(order)[0]


def test_pacote_de_um_componente_le_uma_vez_so(loja):
    ticket = _bundle_ticket(
        components=[("BUN", "Brioche Burger Bun", 2)], parent_name="Brioche Burger Bun (pc. 2un.)",
    )
    item = ticket.items[0]
    assert item["name"] == "Brioche Burger Bun"
    assert item["qty"] == 2
    assert item["notes"] == "1 pacote de 2"


def test_combo_de_varios_componentes_sem_parenteses_aninhados(loja):
    ticket = _bundle_ticket(
        components=[("PAO", "Pão", 1), ("CAFE", "Café (coado)", 1)], parent_name="Café da manhã (M)",
    )
    names = sorted(item["name"] for item in ticket.items)
    assert names == ["Café (coado) · Café da manhã (M)", "Pão · Café da manhã (M)"]
    assert all(item["notes"] == "" for item in ticket.items)


# ── KDS-04 e KDS-07: o ticket fala do pedido ─────────────────────────────


def test_ticket_diz_quando_o_pedido_entrou_e_nao_mostra_telefone_como_nome(loja):
    prep = KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    order = Order.objects.create(
        ref="IFOOD-261105-E67", channel_ref="ifood", session_key="sk-e67", status="accepted",
        handle_ref="+5543993333333", data={"fulfillment_type": "pickup"},
    )
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(minutes=33))
    ticket = KDSTicket.objects.create(session_key="sk-e67", kds_instance=prep, items=[{"sku": "SP", "name": "Espresso", "qty": 1}])

    projection = build_kds_ticket(ticket.pk)

    assert projection.elapsed_seconds < 60  # o relógio da cozinha segue no ticket
    assert projection.order_elapsed_seconds >= 33 * 60
    assert projection.order_created_at_display
    assert projection.customer_name == ""


def test_nome_do_cliente_continua_quando_existe(loja):
    prep = KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    Order.objects.create(
        ref="WEB-1", channel_ref="web", session_key="sk-web-1", status="accepted",
        handle_ref="+5543993333333", data={"customer": {"name": "Ana"}},
    )
    ticket = KDSTicket.objects.create(session_key="sk-web-1", kds_instance=prep, items=[])
    assert build_kds_ticket(ticket.pk).customer_name == "Ana"


# ── KDS-05: "Em preparo" só com a cozinha tendo o pedido ─────────────────


def test_painel_do_cliente_nao_promete_preparo_sem_estacao(loja):
    prep = KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    Order.objects.create(
        ref="PDV-261105-K38", channel_ref="pos", session_key="sk-k38", status=Order.Status.ACCEPTED,
        data={"fulfillment_type": "pickup"},
    )
    Order.objects.create(
        ref="PDV-261105-R09", channel_ref="pos", session_key="sk-r09", status=Order.Status.ACCEPTED,
        data={"fulfillment_type": "pickup"},
    )
    KDSTicket.objects.create(
        session_key="sk-r09", kds_instance=prep, status="in_progress",
        items=[{"sku": "SP", "name": "Espresso", "qty": 1}],
    )
    # Desde 06/11 o ticket nasce no aceite e espera "Iniciar preparo" no posto:
    # ter ticket na tela não é estar sendo feito.
    Order.objects.create(
        ref="WEB-261106-W11", channel_ref="web", session_key="sk-w11", status=Order.Status.ACCEPTED,
        data={"fulfillment_type": "pickup"},
    )
    KDSTicket.objects.create(session_key="sk-w11", kds_instance=prep, items=[{"sku": "SP", "name": "Espresso", "qty": 1}])
    Order.objects.create(
        ref="PDV-261105-C02", channel_ref="pos", session_key="sk-c02", status=Order.Status.PREPARING,
        data={"fulfillment_type": "pickup"},
    )

    preparing = {p.ref for p in build_kds_customer_status().preparing}

    assert preparing == {"PDV-261105-R09", "PDV-261105-C02"}


# ── PDV-09: o roteamento diz se é preparo ────────────────────────────────


def test_rota_diz_se_a_estacao_e_de_preparo(loja, monkeypatch):
    KDSInstance.objects.create(ref="cafes", name="Cafés", type="prep")
    KDSInstance.objects.create(ref="separa", name="Encomendas", type="picking")
    Product.objects.create(sku="CAPU", name="Cappuccino")
    Product.objects.create(sku="CROI", name="Croissant")
    monkeypatch.setattr(kds, "_made_to_order_skus", lambda production, skus: {"CAPU"} & set(skus))

    routes = kds.kitchen_routes_for_skus(["CAPU", "CROI"])

    assert routes["CAPU"]["station"] == "Cafés" and routes["CAPU"]["prep"] is True
    assert routes["CROI"]["station"] == "Encomendas" and routes["CROI"]["prep"] is False
