"""Modo de consumo inferido pela cesta (BI-QUESTION-CATALOG §3.1/F3).

A decisão do dono foi inferir em vez de capturar. O que isso compra — e o que
estes testes guardam:

- a MESMA regra vale para o nativo e para os dois anos do histórico, senão a
  série deixa de ser comparável consigo mesma, que era o motivo de inferir;
- produto sem etiqueta **não vira "levar" por omissão**;
- a âncora vence o corte de estoque: quatro cafés são uma mesa de quatro, não
  uma despensa;
- "consumiu e levou" sai da composição da cesta, sem botão nenhum;
- **pão é pão**: Baguete Lanche e Hambúrguer 100g não ancoram consumo local.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from shopman.backstage.models import (
    ConsumptionRole,
    HistoricalSale,
    HistoricalSaleItem,
    ProductConsumptionTag,
)
from shopman.backstage.projections.bi_explore import ExploreError, build_bi_explore, validate_config
from shopman.backstage.services.consumption import (
    DINE_IN,
    DINE_IN_TAKEAWAY,
    TAKEAWAY,
    UNCLASSIFIED,
    classify_basket,
    role_flags,
)


@pytest.fixture
def roles(db):
    """O vocabulário do seed, no mínimo que a regra precisa."""
    made = {}
    for ref, label, anchors, travels in [
        ("bebida-preparada", "Bebida preparada", True, False),
        ("bebida-pronta", "Bebida pronta", True, False),
        ("pao-de-levar", "Pão de levar", False, True),
        ("fino-individual", "Doce / viennoiserie", False, False),
    ]:
        made[ref] = ConsumptionRole.objects.create(
            ref=ref, label=label, anchors_dine_in=anchors, travels=travels
        )
    return made


@pytest.fixture
def tagged(roles):
    tags = {
        "CAFE": "bebida-preparada",
        "SUCO": "bebida-pronta",
        "PAO-FRANCES": "pao-de-levar",
        # Os dois que o nome engana: são PÃES, não lanches (correção do dono).
        "BAGUETE-LANCHE": "pao-de-levar",
        "HAMBURGUER-100G": "pao-de-levar",
        "CROISSANT": "fino-individual",
    }
    for sku, role_ref in tags.items():
        ProductConsumptionTag.objects.create(sku=sku, role=roles[role_ref])
    return role_flags()


# ── A regra ──────────────────────────────────────────────────────────────────


def test_drink_anchors_dine_in(tagged):
    assert classify_basket([("CAFE", 1)], tagged) == DINE_IN


def test_ready_drink_anchors_alone(tagged):
    """Refinamento do dono: levar bebida é desprezível, então ancora sozinha."""
    assert classify_basket([("SUCO", 1)], tagged) == DINE_IN


def test_bread_alone_is_takeaway(tagged):
    assert classify_basket([("PAO-FRANCES", 1)], tagged) == TAKEAWAY


def test_pastry_alone_is_takeaway_not_dine_in(tagged):
    """A variante permissiva (doce sozinho = local) foi descartada: inflava o salão."""
    assert classify_basket([("CROISSANT", 1)], tagged) == TAKEAWAY


def test_drink_with_bread_is_ate_here_and_took_some(tagged):
    """O terceiro estado que o dono pediu — sem botão, só a cesta."""
    assert classify_basket([("CAFE", 1), ("PAO-FRANCES", 2)], tagged) == DINE_IN_TAKEAWAY


def test_bread_by_the_dozen_is_a_stock_purchase(tagged):
    assert classify_basket([("PAO-FRANCES", 10)], tagged) == TAKEAWAY


def test_four_coffees_are_a_table_of_four_not_a_pantry(tagged):
    """O corte de estoque só olha item de levar — senão lê o sábado ao contrário."""
    assert classify_basket([("CAFE", 4)], tagged) == DINE_IN


def test_the_two_breads_whose_name_lies_do_not_anchor(tagged):
    """'Hambúrguer 100g' é o PÃO. Etiquetar pelo nome inflaria o salão no churrasco."""
    assert classify_basket([("HAMBURGUER-100G", Decimal("6"))], tagged) == TAKEAWAY
    assert classify_basket([("BAGUETE-LANCHE", 1)], tagged) == TAKEAWAY
    # E junto de um café continuam sendo o que são: pão que a pessoa levou.
    assert classify_basket([("CAFE", 1), ("BAGUETE-LANCHE", 1)], tagged) == DINE_IN_TAKEAWAY


def test_delivery_precedes_the_basket(tagged):
    assert classify_basket([("CAFE", 1)], tagged, is_delivery=True) == "delivery"


def test_untagged_basket_has_no_verdict(tagged):
    """Sem etiqueta, a venda não cai no balde mais provável — ela se declara."""
    assert classify_basket([("SKU-NOVO", 1)], tagged) == UNCLASSIFIED
    assert classify_basket([], tagged) == UNCLASSIFIED


def test_partially_tagged_basket_decides_on_what_it_knows(tagged):
    assert classify_basket([("SKU-NOVO", 1), ("CAFE", 1)], tagged) == DINE_IN


# ── No explorador, nas duas fontes ───────────────────────────────────────────


@pytest.mark.django_db
def test_native_sale_gets_its_mode(tagged):
    from shopman.orderman.models import Order, OrderItem

    order = Order.objects.create(ref="CM-1", channel_ref="pdv",
                                 status=Order.Status.COMPLETED, total_q=1800)
    OrderItem.objects.create(order=order, line_id="L1", sku="CAFE", name="Café",
                             qty=Decimal("1"), unit_price_q=800, line_total_q=800)
    OrderItem.objects.create(order=order, line_id="L2", sku="PAO-FRANCES", name="Pão",
                             qty=Decimal("2"), unit_price_q=500, line_total_q=1000)

    report = build_bi_explore(metric="revenue", by="consumption_mode")
    assert {row.key: row.value for row in report.rows} == {DINE_IN_TAKEAWAY: 1800.0}
    assert report.rows[0].label == "Consumiu e levou"


@pytest.mark.django_db
def test_historical_sale_gets_the_same_rule(tagged):
    """É isto que faz os dois anos comparáveis com o presente."""
    sale = HistoricalSale.objects.create(
        source="yooga", external_id=1,
        occurred_at=timezone.now() - timedelta(days=2), total_q=900,
    )
    HistoricalSaleItem.objects.create(sale=sale, seq=1, product_name="Café", sku="CAFE",
                                      qty=Decimal("1"), unit_price_q=900, line_total_q=900)

    report = build_bi_explore(metric="revenue", by="consumption_mode")
    assert {row.key: row.value for row in report.rows} == {DINE_IN: 900.0}


@pytest.mark.django_db
def test_historical_delivery_is_delivery_whatever_the_basket(tagged):
    sale = HistoricalSale.objects.create(
        source="yooga", external_id=2, is_delivery=True,
        occurred_at=timezone.now() - timedelta(days=2), total_q=900,
    )
    HistoricalSaleItem.objects.create(sale=sale, seq=1, product_name="Café", sku="CAFE",
                                      qty=Decimal("1"), unit_price_q=900, line_total_q=900)
    report = build_bi_explore(metric="revenue", by="consumption_mode")
    assert {row.key for row in report.rows} == {"delivery"}


@pytest.mark.django_db
def test_native_delivery_reads_the_fulfillment_type(tagged):
    from shopman.orderman.models import Order, OrderItem

    order = Order.objects.create(ref="CM-D", channel_ref="web", status=Order.Status.COMPLETED,
                                 total_q=900, data={"fulfillment_type": "delivery"})
    OrderItem.objects.create(order=order, line_id="L1", sku="CAFE", name="Café",
                             qty=Decimal("1"), unit_price_q=900, line_total_q=900)
    report = build_bi_explore(metric="revenue", by="consumption_mode")
    assert {row.key for row in report.rows} == {"delivery"}


@pytest.mark.django_db
def test_unclassified_shows_up_as_its_own_row_instead_of_hiding(tagged):
    """A cobertura tem de ser visível: venda sem etiqueta não some nem vira levar."""
    from shopman.orderman.models import Order, OrderItem

    order = Order.objects.create(ref="CM-U", channel_ref="pdv",
                                 status=Order.Status.COMPLETED, total_q=500)
    OrderItem.objects.create(order=order, line_id="L1", sku="SKU-SEM-ETIQUETA",
                             name="Novidade", qty=Decimal("1"), unit_price_q=500,
                             line_total_q=500)
    report = build_bi_explore(metric="revenue", by="consumption_mode")
    assert {row.key: row.label for row in report.rows} == {UNCLASSIFIED: "(sem etiqueta)"}


@pytest.mark.django_db
def test_what_the_room_eats_crosses_mode_with_product(tagged):
    """A pergunta V4: o que o salão come e o que o balcão leva."""
    from shopman.orderman.models import Order, OrderItem

    sat = Order.objects.create(ref="CM-S", channel_ref="pdv",
                               status=Order.Status.COMPLETED, total_q=800)
    OrderItem.objects.create(order=sat, line_id="L1", sku="CAFE", name="Café",
                             qty=Decimal("2"), unit_price_q=400, line_total_q=800)
    took = Order.objects.create(ref="CM-T", channel_ref="pdv",
                                status=Order.Status.COMPLETED, total_q=500)
    OrderItem.objects.create(order=took, line_id="L1", sku="PAO-FRANCES", name="Pão",
                             qty=Decimal("5"), unit_price_q=100, line_total_q=500)

    report = build_bi_explore(metric="qty_sold", by="consumption_mode", by2="sku")
    cells = {(row.key, row.key2): row.value for row in report.rows}
    assert cells == {(DINE_IN, "CAFE"): 2.0, (TAKEAWAY, "PAO-FRANCES"): 5.0}


@pytest.mark.django_db
def test_ticket_by_mode_is_the_question_about_who_spends_more(tagged):
    from shopman.orderman.models import Order, OrderItem

    for ref, sku, total in [("CM-A", "CAFE", 6000), ("CM-B", "PAO-FRANCES", 2000)]:
        order = Order.objects.create(ref=ref, channel_ref="pdv",
                                     status=Order.Status.COMPLETED, total_q=total)
        OrderItem.objects.create(order=order, line_id="L1", sku=sku, name=sku,
                                 qty=Decimal("1"), unit_price_q=total, line_total_q=total)
    report = build_bi_explore(metric="average_ticket", by="consumption_mode")
    assert {row.key: row.value for row in report.rows} == {DINE_IN: 6000.0, TAKEAWAY: 2000.0}


# ── Gramática ────────────────────────────────────────────────────────────────


def test_consumption_mode_is_in_the_grammar_where_it_belongs():
    assert validate_config("revenue", "consumption_mode", "hour")
    assert validate_config("qty_sold", "consumption_mode", "sku")
    # Fornada não é função do modo de consumo do cliente.
    with pytest.raises(ExploreError, match="não vale para Quantidade produzida"):
        validate_config("qty_produced", "consumption_mode", "")


@pytest.mark.django_db
def test_role_flags_ignores_inactive_roles(roles):
    ProductConsumptionTag.objects.create(sku="CAFE", role=roles["bebida-preparada"])
    assert "CAFE" in role_flags()
    ConsumptionRole.objects.filter(ref="bebida-preparada").update(is_active=False)
    # Papel desativado sai de circulação: o produto volta a não ter veredito, em
    # vez de continuar ancorando com uma regra que o gestor tirou do ar.
    assert "CAFE" not in role_flags()
