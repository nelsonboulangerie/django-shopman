"""Perfis de consumo do balcão — A/B/C, piso e teto (BI-CONSUMPTION-PROFILES).

O que estes testes guardam:

- as três leituras da classe ambígua saem da MESMA regra, por remapeamento;
- linha sem SKU se etiqueta pelo NOME (os combos do Yooga deixam de ser invisíveis);
- bebida é fato à parte da leitura: reetiquetar café como "bebida preparada"
  não muda perfil nenhum, só a conta de bebida;
- **conciliação**: A + B + C + sem etiqueta + entrega = faturamento do período
  pela leitura atual do ``bi_sales`` — em qualquer leitura;
- filtros de dia da semana e faixa recortam sem inventar balde;
- RevPASH divide pela conta declarada (assentos × horas da faixa × dias).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.models import (
    Beverage,
    ConsumptionRole,
    DayClosing,
    HistoricalSale,
    HistoricalSaleItem,
    ProductConsumptionTag,
    Reading,
)
from shopman.backstage.projections.bi_profiles import (
    PROFILE_A,
    PROFILE_B,
    PROFILE_C,
    PROFILE_UNCLASSIFIED,
    REVPASH_SEATS,
    build_bi_consumption_profiles,
)
from shopman.backstage.projections.bi_sales import build_bi_sales
from shopman.backstage.services import consumption as rule
from shopman.backstage.services.hour_bands import HOUR_BANDS, band_for


@pytest.fixture
def roles(db):
    return {
        ref: ConsumptionRole.objects.create(
            ref=ref, label=ref, reading=reading, beverage=bev, eat_in_weight=weight
        )
        for ref, reading, bev, weight in [
            ("bebida-preparada", Reading.ANCHOR, Beverage.PREPARED, 95),
            ("bebida-pronta", Reading.ANCHOR, Beverage.READY, 95),
            ("consome-aqui", Reading.ANCHOR, Beverage.NONE, 95),
            ("leva", Reading.TAKEAWAY, Beverage.NONE, 5),
            ("hibrido", Reading.HYBRID, Beverage.NONE, 50),
        ]
    }


@pytest.fixture
def tagged(roles):
    for sku, role in {
        "CAFE": "bebida-preparada",
        "AGUA": "bebida-pronta",
        "CROQUE": "consome-aqui",
        "PAO": "leva",
        "CROISSANT": "hibrido",
        "nome:Combo Cola + Hotdog": "consome-aqui",
    }.items():
        ProductConsumptionTag.objects.create(sku=sku, role=roles[role])
    return rule.sku_facts()


def _local(day_offset: int, hour: int, minute: int = 0) -> datetime:
    """Um instante local em dia passado (nunca hoje: o dia nativo vence)."""
    tz = timezone.get_current_timezone()
    day = timezone.localdate() - timedelta(days=day_offset)
    return datetime.combine(day, datetime.min.time(), tzinfo=tz).replace(hour=hour, minute=minute)


_seq = iter(range(1, 10_000))


def _sale(when: datetime, lines, *, is_delivery=False, total_q=None):
    """Venda histórica com linhas ``(sku, name, category, qty, line_total_q)``."""
    lines = list(lines)
    sale = HistoricalSale.objects.create(
        source="yooga", external_id=next(_seq), occurred_at=when,
        total_q=total_q if total_q is not None else sum(line[4] for line in lines),
        is_delivery=is_delivery,
    )
    for seq, (sku, name, category, qty, line_total_q) in enumerate(lines, start=1):
        HistoricalSaleItem.objects.create(
            sale=sale, seq=seq, product_name=name, sku=sku, category=category,
            qty=Decimal(qty), unit_price_q=line_total_q // max(qty, 1), line_total_q=line_total_q,
        )
    return sale


def _basket(lines, *, is_delivery=False):
    """Uma cesta em memória, para testar a regra sem banco."""
    facts = rule.sku_facts()
    readings = {k: f.reading for k, f in facts.items()}
    beverages = {k: f.beverage for k, f in facts.items()}
    weights = {k: f.weight for k, f in facts.items()}
    return rule.Basket(
        source="yooga", sale_id=0, local=_local(1, 10), total_q=0, is_delivery=is_delivery,
        channel="", lines=tuple(
            rule.BasketLine(
                key=rule.line_key(sku, name), sku=sku, name=name, category=category,
                reading=rule.reading_for(sku, category, readings, name=name),
                beverage=rule.beverage_for(sku, category, beverages, name=name),
                qty=Decimal(1), line_total_q=100,
                weight=rule.weight_for(sku, category, weights, name=name),
            )
            for sku, name, category in lines
        ),
    )


# ── As três leituras ─────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lines, floor, current, ceiling",
    [
        # só híbrido: piso diz levou, vigente diz levou, teto diz consumiu aqui
        ([("CROISSANT", "Croissant", "")], rule.TAKEAWAY, rule.TAKEAWAY, rule.DINE_IN),
        # âncora + híbrido: no piso o croissant foi levado; nas outras, comeu junto
        ([("CAFE", "Café", ""), ("CROISSANT", "Croissant", "")],
         rule.DINE_IN_TAKEAWAY, rule.DINE_IN, rule.DINE_IN),
        # leva + híbrido: só o teto enxerga alguém sentado
        ([("PAO", "Pão", ""), ("CROISSANT", "Croissant", "")],
         rule.TAKEAWAY, rule.TAKEAWAY, rule.DINE_IN_TAKEAWAY),
        # âncora + leva: B em qualquer leitura — o híbrido não está na cesta
        ([("CAFE", "Café", ""), ("PAO", "Pão", "")],
         rule.DINE_IN_TAKEAWAY, rule.DINE_IN_TAKEAWAY, rule.DINE_IN_TAKEAWAY),
        # só âncora: C sempre
        ([("CROQUE", "Croque", "")], rule.DINE_IN, rule.DINE_IN, rule.DINE_IN),
    ],
)
def test_the_three_readings_come_from_the_same_rule(tagged, lines, floor, current, ceiling):
    basket = _basket(lines)
    assert basket.mode(rule.READING_FLOOR) == floor
    assert basket.mode(rule.READING_CURRENT) == current
    assert basket.mode(rule.READING_CEILING) == ceiling


@pytest.mark.django_db
def test_delivery_and_untagged_ignore_the_reading(tagged):
    assert {_basket([("CAFE", "Café", "")], is_delivery=True).mode(v) for v in rule.READING_VARIANTS} == {rule.DELIVERY}
    assert {_basket([("XPTO", "Novo", "")]).mode(v) for v in rule.READING_VARIANTS} == {rule.UNCLASSIFIED}


# ── Chave por nome e bebida ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_a_line_without_sku_finds_its_tag_by_name(tagged):
    """Os combos do Yooga: sem SKU e sem categoria, invisíveis até a chave por nome."""
    basket = _basket([("", "Combo Cola + Hotdog", "")])
    line = basket.lines[0]
    assert line.key == "nome:Combo Cola + Hotdog"
    assert line.reading == rule.ANCHOR
    # O combo inteiro não é bebida: contar a linha como refrigerante jogaria o
    # hotdog na receita de bebida pronta.
    assert line.beverage == rule.BEVERAGE_NONE
    assert basket.mode() == rule.DINE_IN
    # Nome que ninguém etiquetou continua sem etiqueta — nada é inventado.
    assert _basket([("", "Combo Que Não Existe", "")]).mode() == rule.UNCLASSIFIED


@pytest.mark.django_db
def test_category_is_the_fallback_for_beverage_too(tagged):
    """15 mil linhas de bebida sem SKU: 'Cafés' é preparada, 'Bebidas' é pronta."""
    lines = _basket([("", "Espresso Duplo", "Cafés"), ("", "Coca-Cola 350ml", "Bebidas"),
                     ("", "Baguete", "Pães Rústicos")]).lines
    assert [line.beverage for line in lines] == [rule.BEVERAGE_PREPARED, rule.BEVERAGE_READY, ""]
    assert [line.reading for line in lines] == [rule.ANCHOR, rule.ANCHOR, rule.TAKEAWAY_ITEM]


@pytest.mark.django_db
def test_beverage_role_reads_like_consome_aqui(roles):
    """Trocar um SKU entre 'consome aqui' e 'bebida' não muda perfil nenhum."""
    tag = ProductConsumptionTag.objects.create(sku="CAFE", role=roles["consome-aqui"])
    before = _basket([("CAFE", "Café", ""), ("PAO", "Pão", "")]).mode()
    tag.role = roles["bebida-preparada"]
    tag.save()
    after = _basket([("CAFE", "Café", ""), ("PAO", "Pão", "")]).mode()
    assert before == after == rule.DINE_IN  # PAO sem etiqueta neste teste


# ── A leitura em graus: o peso ───────────────────────────────────────────────


@pytest.mark.django_db
def test_the_biggest_weight_in_the_basket_decides(tagged):
    """P(sentou) é o MAIOR peso, não o produto: café + croissant é o café falando."""
    assert _basket([("CAFE", "Café", "")]).eat_in_probability() == 0.95
    assert _basket([("PAO", "Pão", "")]).eat_in_probability() == 0.05
    assert _basket([("CROISSANT", "Croissant", "")]).eat_in_probability() == 0.5
    assert _basket([("CAFE", "Café", ""), ("CROISSANT", "Croissant", "")]).eat_in_probability() == 0.95
    assert _basket([("PAO", "Pão", ""), ("CROISSANT", "Croissant", "")]).eat_in_probability() == 0.5
    # três croissants não são mais "sentado" do que um: contagem não é evidência
    assert _basket([("CROISSANT", "Croissant", "")] * 3).eat_in_probability() == 0.5


@pytest.mark.django_db
def test_delivery_is_zero_and_unweighted_is_unknown(tagged):
    assert _basket([("CAFE", "Café", "")], is_delivery=True).eat_in_probability() == 0.0
    assert _basket([("XPTO", "Novo", "")]).eat_in_probability() is None
    assert _basket([]).eat_in_probability() is None


@pytest.mark.django_db
def test_sku_weight_overrides_the_role_weight(roles):
    """O papel dá o peso de partida; o SKU pode dizer o seu."""
    tag = ProductConsumptionTag.objects.create(sku="CROISSANT", role=roles["hibrido"])
    assert _basket([("CROISSANT", "Croissant", "")]).eat_in_probability() == 0.5
    tag.eat_in_weight = 35
    tag.save()
    assert _basket([("CROISSANT", "Croissant", "")]).eat_in_probability() == 0.35
    # e mudar o peso do papel move todos os que herdam dele
    roles["hibrido"].eat_in_weight = 60
    roles["hibrido"].save()
    ProductConsumptionTag.objects.create(sku="MADELEINE", role=roles["hibrido"])
    assert _basket([("MADELEINE", "Madeleine", "")]).eat_in_probability() == 0.6
    assert _basket([("CROISSANT", "Croissant", "")]).eat_in_probability() == 0.35  # o SKU vence


@pytest.mark.django_db
def test_category_gives_a_starting_weight_to_lines_without_tag(tagged):
    lines = _basket([("", "Espresso Duplo", "Cafés"), ("", "Baguete", "Pães Rústicos"),
                     ("", "Chausson", "Pães Finos"), ("", "Coisa", "")]).lines
    assert [line.weight for line in lines] == [95, 5, 50, None]


@pytest.mark.django_db
def test_sku_signal_tells_what_history_knows(week):
    signal = rule.sku_signal("PAO")
    # PAO em duas vendas de balcão (a entrega fica fora): café+pão e pão sozinho
    assert signal.sales == 2 and signal.with_beverage_pct == 50
    assert signal.alone_pct == 50 and signal.bulk_pct == 0
    combo = rule.sku_signal("nome:Combo Cola + Hotdog")
    assert combo.sales == 1 and combo.alone_pct == 100 and combo.with_beverage_pct == 0
    assert rule.sku_signal("NUNCA-VENDIDO") is None


# ── O relatório ──────────────────────────────────────────────────────────────


@pytest.fixture
def week(tagged):
    """Uma semana de balcão + entrega, com hora e dia da semana controlados."""
    # dia 3 dias atrás, 10h: café + pão (B em todas), R$ 15
    _sale(_local(3, 10), [("CAFE", "Café", "Cafés", 1, 700), ("PAO", "Pão", "Pães Rústicos", 2, 800)])
    # mesmo dia, 12h30: só croissant (A no piso/vigente, C no teto), R$ 9
    _sale(_local(3, 12, 30), [("CROISSANT", "Croissant", "Pães Finos", 1, 900)])
    # 4 dias atrás, 15h: croque + água (C sempre), R$ 30 — total de cabeçalho R$ 31 (acréscimo)
    _sale(_local(4, 15), [("CROQUE", "Croque", "Sanduíches", 1, 2500),
                          ("AGUA", "Água", "Bebidas", 1, 500)], total_q=3100)
    # 4 dias atrás, 16h: só pão (A sempre), R$ 8
    _sale(_local(4, 16), [("PAO", "Pão", "Pães Rústicos", 1, 800)])
    # 5 dias atrás, 17h: combo por nome (C, não é bebida), R$ 26
    _sale(_local(5, 17), [("", "Combo Cola + Hotdog", "", 1, 2600)])
    # 5 dias atrás, 11h: sem etiqueta, R$ 12
    _sale(_local(5, 11), [("XPTO", "Novidade", "", 1, 1200)])
    # entrega, 6 dias atrás: fora da pergunta, dentro da conciliação, R$ 40
    _sale(_local(6, 12), [("PAO", "Pão", "Pães Rústicos", 4, 4000)], is_delivery=True)
    return build_bi_consumption_profiles(
        date_from=timezone.localdate() - timedelta(days=7), date_to=timezone.localdate()
    )


def _rows(report, reading):
    return {row.profile: row for row in report.profiles if row.reading == reading}


@pytest.mark.django_db
def test_profiles_by_reading(week):
    current = _rows(week, rule.READING_CURRENT)
    assert {p: r.orders for p, r in current.items()} == {
        PROFILE_A: 2, PROFILE_B: 1, PROFILE_C: 2, PROFILE_UNCLASSIFIED: 1,
    }
    floor = _rows(week, rule.READING_FLOOR)
    ceiling = _rows(week, rule.READING_CEILING)
    # o croissant sozinho é a única cesta que muda: A no piso, C no teto
    assert floor[PROFILE_A].orders == 2 and floor[PROFILE_C].orders == 2
    assert ceiling[PROFILE_A].orders == 1 and ceiling[PROFILE_C].orders == 3
    assert week.sensitivity.orders_changed == 1
    assert week.sensitivity.share_changed == round(100 / 6, 1)
    a_range = next(r for r in week.sensitivity.ranges if r.profile == PROFILE_A)
    assert (a_range.min_orders, a_range.max_orders) == (1, 2)


@pytest.mark.django_db
def test_revenue_reconciles_with_bi_sales_in_every_reading(week):
    """Não bateu = errado = não serve."""
    sales = build_bi_sales(
        date_from=timezone.localdate() - timedelta(days=7), date_to=timezone.localdate()
    )
    assert week.revenue_total_q == sales.revenue_total_q == 1500 + 900 + 3100 + 800 + 2600 + 1200 + 4000
    for reading in rule.READING_VARIANTS:
        rows = _rows(week, reading)
        assert sum(r.revenue_q for r in rows.values()) + week.delivery_revenue_q == week.revenue_total_q
        assert sum(r.orders for r in rows.values()) == week.counter_orders == 6
    assert week.delivery_orders == 1 and week.delivery_revenue_q == 4000


@pytest.mark.django_db
def test_row_metrics(week):
    b = _rows(week, rule.READING_CURRENT)[PROFILE_B]
    assert b.revenue_q == 1500 and b.average_ticket_q == 1500
    assert b.units_per_order == "3.0" and b.distinct_per_order == "2.0"
    assert b.orders_share == round(100 / 6, 1)
    # distribuição por faixa: o café + pão foi às 10h → manhã (índice 0)
    assert b.orders_by_band == (1, 0, 0, 0, 0)
    assert b.revenue_by_band_q == (1500, 0, 0, 0, 0)
    assert week.coverage == round(500 / 6, 1)


@pytest.mark.django_db
def test_weighted_estimate(week):
    """A esperança sob os pesos: quantos comeram aqui, quantos só buscaram."""
    est = week.estimate
    # café+pão .95 · croissant .5 · croque+água .95 · pão .05 · combo .95 · novidade sem peso
    assert est.weighted_orders == 5 and est.unweighted_orders == 1
    assert est.seated_orders == 3.4 and est.seated_share == 68.0
    assert est.takeaway_orders == 1.6 and est.takeaway_share == 32.0
    assert est.seated_revenue_q == 7330 and est.seated_revenue_share == round(7330 * 100 / 8900, 1)
    assert est.seated_by_band == (0.95, 0.5, 1.0, 0.95, 0.0)
    assert est.orders_by_band == (1, 1, 2, 1, 0)
    assert week.previous.estimate.weighted_orders == 0


@pytest.mark.django_db
def test_categories_and_header_gap(week):
    by = {row.category: row for row in week.categories}
    assert by["Pães Rústicos"].revenue_q == 800 + 800  # a entrega fica fora
    assert by["Bebidas"].ready_beverage_q == 500
    assert by["(sem categoria)"].revenue_q == 2600 + 1200  # combo + novidade, sem bebida pronta
    assert by["(sem categoria)"].ready_beverage_q == 0
    assert week.category_header_gap_q == 100  # o acréscimo de cabeçalho da venda do croque


@pytest.mark.django_db
def test_beverage_measures(week):
    bev = week.beverage
    # café+pão, croque+água → 2 de 6 pedidos com bebida (o combo não conta)
    assert bev.orders_with_beverage == 2 and bev.strike_rate == round(200 / 6, 1)
    assert bev.prepared_rate == round(100 / 6, 1)
    assert bev.ready_revenue_q == 500
    # pedidos com item local (âncora): café+pão, croque+água, combo → 2 bebidas em 3 → 0,7
    assert bev.local_orders == 3 and bev.per_local_order == "0.7"
    afternoon = next(c for c in bev.by_band if c.band == "afternoon")
    assert (afternoon.orders, afternoon.with_beverage, afternoon.rate) == (2, 1, 50.0)
    assert len(bev.by_weekday_band) == 7 * len(HOUR_BANDS)


@pytest.mark.django_db
def test_beverage_only_is_measured_not_estimated(week):
    """'Só veio tomar um café': todas as linhas são bebida. Nenhuma na semana base…"""
    assert week.beverage.beverage_only_orders == 0
    # …até aparecerem: um espresso sozinho (9h) e café + água (15h); café + pão não conta
    _sale(_local(2, 9), [("CAFE", "Café", "Cafés", 1, 700)])
    _sale(_local(2, 15), [("CAFE", "Café", "Cafés", 1, 700), ("AGUA", "Água", "Bebidas", 1, 500)])
    report = build_bi_consumption_profiles(
        date_from=timezone.localdate() - timedelta(days=7), date_to=timezone.localdate()
    )
    bev = report.beverage
    assert bev.beverage_only_orders == 2
    assert bev.beverage_only_share == round(200 / 8, 1)
    assert bev.beverage_only_ticket_q == (700 + 1200) // 2
    assert bev.beverage_only_by_band == (1, 0, 1, 0, 0)


@pytest.mark.django_db
def test_revpash_uses_the_declared_denominator(week):
    assert week.seats == REVPASH_SEATS == 24
    assert week.days_with_sales == 3  # três dias de balcão com venda
    afternoon = next(r for r in week.revpash if r.band == "afternoon")
    # receita dos pedidos com item local às 14–17h: só o croque + água (R$ 31)
    assert afternoon.revenue_local_q == 3100
    assert afternoon.revpash_q == 3100 // (24 * 3 * 3)


@pytest.mark.django_db
def test_filters_cut_without_inventing(week):
    day = (timezone.localdate() - timedelta(days=4)).weekday()
    report = build_bi_consumption_profiles(
        date_from=timezone.localdate() - timedelta(days=7), date_to=timezone.localdate(),
        weekday=day, hour_band="afternoon",
    )
    assert report.weekday == day and report.hour_band == "afternoon"
    assert report.counter_orders == 2  # croque+água (15h) e pão (16h)
    current = _rows(report, rule.READING_CURRENT)
    assert current[PROFILE_A].orders == 1 and current[PROFILE_C].orders == 1
    # valores fora do vocabulário caem em "todos", declarado no contrato
    loose = build_bi_consumption_profiles(weekday=9, hour_band="brunch")
    assert loose.weekday is None and loose.hour_band == ""


@pytest.mark.django_db
def test_previous_period_uses_the_same_rule(week):
    assert week.previous.counter_orders == 0
    assert {r.reading for r in week.previous.rows} == {rule.READING_CURRENT}


@pytest.mark.django_db
def test_native_day_wins_over_history(week):
    """Um pedido Shopman no dia apaga o histórico daquele dia — como no bi_sales."""
    from shopman.orderman.models import Order, OrderItem

    order = Order.objects.create(ref="NAT-1", channel_ref="pdv",
                                 status=Order.Status.COMPLETED, total_q=700)
    OrderItem.objects.create(order=order, line_id="L1", sku="CAFE", name="Café",
                             qty=Decimal("1"), unit_price_q=700, line_total_q=700)
    Order.objects.filter(pk=order.pk).update(created_at=_local(3, 9))
    report = build_bi_consumption_profiles(
        date_from=timezone.localdate() - timedelta(days=7), date_to=timezone.localdate()
    )
    sales = build_bi_sales(
        date_from=timezone.localdate() - timedelta(days=7), date_to=timezone.localdate()
    )
    assert report.revenue_total_q == sales.revenue_total_q
    assert report.counter_orders == 5  # as 2 vendas históricas de 3 dias atrás saíram, 1 nativa entrou


# ── Faixas ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("hour, key", [(9, "morning"), (10, "morning"), (11, "lunch"),
                                        (13, "lunch"), (14, "afternoon"), (16, "afternoon"),
                                        (17, "late"), (18, "late"), (8, "outside"), (19, "outside")])
def test_hour_bands_by_occasion(hour, key):
    assert band_for(hour).key == key


def test_band_title_carries_the_hours():
    assert band_for(12).title == "Almoço · 11–14h"


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_endpoint_requires_view_bi(client):
    bare = User.objects.create_user("bare-profiles", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-bi-consumption-profiles")).status_code == 403


@pytest.mark.django_db
def test_endpoint_responds(client, week):
    user = User.objects.create_user("bi-profiles", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi",
    ))
    client.force_login(user)
    response = client.get(
        reverse("api-backstage-bi-consumption-profiles"),
        {"weekday": "4", "hour_band": "lunch", "date_from": "2020-01-01"},
    )
    assert response.status_code == 200
    body = response.json()["bi"]
    assert body["weekday"] == 4 and body["hour_band"] == "lunch"
    assert len(body["profiles"]) == 12
    assert [b["key"] for b in body["bands"]] == ["morning", "lunch", "afternoon", "late", "outside"]
