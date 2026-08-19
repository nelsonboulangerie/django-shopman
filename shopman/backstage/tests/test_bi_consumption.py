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
    Reading,
)
from shopman.backstage.projections.bi_explore import ExploreError, build_bi_explore, validate_config
from shopman.backstage.services.consumption import (
    DINE_IN,
    DINE_IN_TAKEAWAY,
    TAKEAWAY,
    UNCLASSIFIED,
    classify_basket,
    sku_readings,
)
from shopman.backstage.tests.support import historical_batch


@pytest.fixture
def roles(db):
    """As três leituras do seed — três, porque são três os comportamentos."""
    return {
        ref: ConsumptionRole.objects.create(ref=ref, label=label, reading=reading)
        for ref, label, reading in [
            ("consome-aqui", "Consome aqui", Reading.ANCHOR),
            ("leva", "Leva", Reading.TAKEAWAY),
            ("hibrido", "Híbrido", Reading.HYBRID),
        ]
    }


@pytest.fixture
def tagged(roles):
    tags = {
        "CAFE": "consome-aqui",
        "SUCO": "consome-aqui",
        "PAO-FRANCES": "leva",
        # Os dois que o nome engana: são PÃES, não lanches (correção do dono).
        "BAGUETE-LANCHE": "leva",
        "HAMBURGUER-100G": "leva",
        "CROISSANT": "hibrido",
    }
    for sku, role_ref in tags.items():
        ProductConsumptionTag.objects.create(sku=sku, role=roles[role_ref])
    return sku_readings()


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


def test_quantity_does_not_change_any_verdict(tagged):
    """Houve um corte de "compra de estoque" que não decidia nada, e saiu.

    Com estes quatro modos, cesta sem âncora já é "levou" — com uma unidade ou
    com uma dúzia. E quatro cafés são uma mesa de quatro, não uma despensa.
    """
    assert classify_basket([("PAO-FRANCES", 1)], tagged) == TAKEAWAY
    assert classify_basket([("PAO-FRANCES", 10)], tagged) == TAKEAWAY
    assert classify_basket([("CAFE", 4)], tagged) == DINE_IN


def test_the_second_reading_is_what_separates_what_she_took_from_what_she_ate(tagged):
    """Por que "leva" não pode ser um booleano de âncora só.

    Com um bit apenas, estas duas cestas seriam idênticas — âncora mais
    não-âncora — e o quarto modo que o dono pediu ("consumir no local e levar")
    ou some, ou passa a incluir todo croissant que acompanha um café.
    """
    assert classify_basket([("CAFE", 1), ("PAO-FRANCES", 1)], tagged) == DINE_IN_TAKEAWAY
    assert classify_basket([("CAFE", 1), ("CROISSANT", 1)], tagged) == DINE_IN


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
        batch=historical_batch("yooga"), source="yooga", external_id=1,
        occurred_at=timezone.now() - timedelta(days=2), total_q=900,
    )
    HistoricalSaleItem.objects.create(sale=sale, seq=1, product_name="Café", sku="CAFE",
                                      qty=Decimal("1"), unit_price_q=900, line_total_q=900)

    report = build_bi_explore(metric="revenue", by="consumption_mode")
    assert {row.key: row.value for row in report.rows} == {DINE_IN: 900.0}


@pytest.mark.django_db
def test_historical_delivery_is_delivery_whatever_the_basket(tagged):
    sale = HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga", external_id=2, is_delivery=True,
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
def test_readings_ignore_inactive_roles(roles):
    ProductConsumptionTag.objects.create(sku="CAFE", role=roles["consome-aqui"])
    assert "CAFE" in sku_readings()
    ConsumptionRole.objects.filter(ref="consome-aqui").update(is_active=False)
    # Papel desativado sai de circulação: o produto volta a não ter veredito, em
    # vez de continuar ancorando com uma regra que o gestor tirou do ar.
    assert "CAFE" not in sku_readings()


@pytest.mark.django_db
def test_the_vocabulary_has_exactly_three_readings():
    """Nome novo é bem-vindo; comportamento novo muda com teste, não cadastro."""
    assert {choice.value for choice in Reading} == {"anchor", "takeaway", "hybrid"}
