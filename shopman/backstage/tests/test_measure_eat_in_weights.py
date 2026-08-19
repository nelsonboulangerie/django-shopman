"""`measure_eat_in_weights` — o dado inclina os híbridos (BI-CONSUMPTION-PROFILES §8.1).

O peso de um SKU híbrido é o quanto ele puxa gente para sentar ALÉM da média
da casa: (P(bebida | SKU) − P(bebida)) / (1 − P(bebida)). Na média → piso;
100% com bebida → teto. Âncoras e "leva" não são tocados; variante "M"+SKU e
gêmeo do cardápio 2027 herdam; base pequena fica no peso do papel, declarada.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.backstage.management.commands.measure_eat_in_weights import _lift
from shopman.backstage.models import (
    Beverage,
    ConsumptionRole,
    HistoricalSale,
    HistoricalSaleItem,
    ProductConsumptionTag,
    Reading,
)
from shopman.backstage.services.consumption import beverage_rate
from shopman.backstage.tests.support import historical_batch


def test_lift_is_the_pull_above_the_house_average():
    assert _lift(35, 35) == 5  # na média: não inclina (piso)
    assert _lift(20, 35) == 5  # abaixo: piso
    assert _lift(100, 35) == 95  # sempre com bebida: teto
    assert _lift(59, 35) == 37  # (59−35)/65 = 36,9
    assert _lift(50, 35) == 23
    assert _lift(41, 35) == 9
    assert _lift(50, 100) == 5  # casa sem bebida nenhuma: nada a medir


_seq = iter(range(1, 100_000))


def _sale(lines, *, delivery=False, days_ago=3):
    sale = HistoricalSale.objects.create(
        batch=historical_batch("yooga"), source="yooga", external_id=next(_seq), is_delivery=delivery,
        occurred_at=timezone.now() - timedelta(days=days_ago), total_q=1000,
    )
    for seq, (sku, name, category) in enumerate(lines, start=1):
        HistoricalSaleItem.objects.create(
            sale=sale, seq=seq, sku=sku, product_name=name, category=category,
            qty=Decimal(1), unit_price_q=500, line_total_q=500,
        )


@pytest.fixture
def world(db):
    hib = ConsumptionRole.objects.create(ref="hibrido", label="Híbrido", reading=Reading.HYBRID, eat_in_weight=50)
    bev = ConsumptionRole.objects.create(ref="bebida-preparada", label="Bebida", reading=Reading.ANCHOR,
                                         beverage=Beverage.PREPARED, eat_in_weight=95)
    leva = ConsumptionRole.objects.create(ref="leva", label="Leva", reading=Reading.TAKEAWAY, eat_in_weight=5)
    for sku, role in [("CT", hib), ("MCT", hib), ("TB", hib), ("RARO", hib),
                      ("CAFE", bev), ("PAO", leva)]:
        ProductConsumptionTag.objects.create(sku=sku, role=role)
    # 10 vendas de balcão: 4 com café → média da casa 40%
    for _ in range(4):
        _sale([("CAFE", "Café", "Cafés"), ("CT", "Croissant", "Pães Finos")])  # CT com bebida ×4
    for _ in range(2):
        _sale([("CT", "Croissant", "Pães Finos")])  # CT sem bebida ×2 → CT: 4/6 = 67%
    for _ in range(4):
        _sale([("TB", "Tabatière", "Pães Finos"), ("PAO", "Pão", "Pães Rústicos")])  # TB 0%
    _sale([("RARO", "Raro", "Pães Finos")])  # 1 venda: sem base
    _sale([("CAFE", "Café", "Cafés"), ("CT", "Croissant", "Pães Finos")], delivery=True)  # entrega: fora
    return {"hib": hib}


@pytest.mark.django_db
def test_house_average_counts_counter_sales_only(world):
    assert beverage_rate() == 36  # 4 de 11 vendas de balcão (a entrega fica fora)


@pytest.mark.django_db
def test_dry_run_prints_and_writes_nothing(world):
    out = StringIO()
    call_command("measure_eat_in_weights", "--min-sales", "2", stdout=out)
    text = out.getvalue()
    assert "Média da casa: 36%" in text
    assert "CT " in text and "herdado do gêmeo CT" in text
    assert "sem --apply" in text
    assert ProductConsumptionTag.objects.filter(eat_in_weight__isnull=False).count() == 0


@pytest.mark.django_db
def test_apply_sets_measured_inherited_and_leaves_the_rest(world):
    call_command("measure_eat_in_weights", "--apply", "--min-sales", "2", stdout=StringIO())
    by = {t.sku: t for t in ProductConsumptionTag.objects.all()}
    # CT: 67% com bebida contra 36% da casa → (67−36)/64 = 48
    assert by["CT"].eat_in_weight == 48 and "peso pelo histórico" in by["CT"].note
    # TB: 0% → piso
    assert by["TB"].eat_in_weight == 5
    # A herança que sobra é a do meio-preço: MCT é o mesmo croissant, sem base
    # própria. Havia aqui um caso "CROISSANT herda de CT", do tempo em que o
    # cardápio e o Yooga usavam códigos diferentes para o mesmo pão — o
    # catálogo passou a usar os códigos da casa, e o gêmeo virou o próprio SKU.
    assert by["MCT"].eat_in_weight == 48 and "herdado do gêmeo CT" in by["MCT"].note
    # base pequena fica no peso do papel; âncora e leva não são tocados
    assert by["RARO"].eat_in_weight is None
    assert by["CAFE"].eat_in_weight is None and by["PAO"].eat_in_weight is None
