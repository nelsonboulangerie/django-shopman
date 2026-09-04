"""A tabela de afinidade: lift acima de contagem, suporte contra ruído, cadência.

O teste que dá nome ao WP está no fim: a **água não pode ganhar por
popularidade**. Ela aparece em quase toda cesta, e é exatamente por isso que o
lift a rejeita — aparecer com tudo não é combinar com nada.
"""

from __future__ import annotations

import itertools
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import ProductAffinity

pytestmark = pytest.mark.django_db


_seq = itertools.count(1)


def _order(*skus, days_ago=1, status=Order.Status.COMPLETED):
    order = Order.objects.create(
        ref=f"ORD-{next(_seq):05d}", status=status, total_q=1000,
    )
    for i, sku in enumerate(skus):
        # `line_id` é único por pedido: a linha do PDV tem identidade própria.
        OrderItem.objects.create(
            order=order, line_id=f"L{i}", sku=sku, name=sku,
            qty=1, unit_price_q=500, line_total_q=500,
        )
    # `created_at` é auto_now_add: só um update direto envelhece a cesta.
    when = timezone.now() - timedelta(days=days_ago)
    Order.objects.filter(pk=order.pk).update(created_at=when)
    return order


def _run(**kwargs):
    call_command(
        "compute_product_affinity",
        min_support=kwargs.pop("min_support", 2),
        min_interval_hours=kwargs.pop("min_interval_hours", 0),
        verbosity=0,
        **kwargs,
    )


def _lift(a, b) -> float | None:
    row = ProductAffinity.objects.filter(sku_a=a, sku_b=b).first()
    return row.lift if row else None


# --- o básico ---------------------------------------------------------------


def test_a_pair_that_repeats_becomes_a_row():
    for _ in range(3):
        _order("PAO", "CAFE")
    _run()

    assert _lift("PAO", "CAFE") is not None


def test_the_pair_is_written_both_ways():
    # A leitura pergunta sempre por `sku_a`; sem os dois sentidos ela precisaria
    # de um OR sobre duas colunas em toda sugestão.
    for _ in range(3):
        _order("PAO", "CAFE")
    _run()

    assert _lift("PAO", "CAFE") == _lift("CAFE", "PAO")


def test_a_single_item_basket_teaches_nothing():
    for _ in range(5):
        _order("PAO")
    _run()

    assert ProductAffinity.objects.count() == 0


def test_cancelled_orders_do_not_teach():
    for _ in range(5):
        _order("PAO", "CAFE", status=Order.Status.CANCELLED)
    _run()

    assert ProductAffinity.objects.count() == 0


# --- ruído ------------------------------------------------------------------


def test_a_pair_below_the_support_floor_is_not_a_row():
    # Duas cestas com o mesmo par dariam um lift enorme e sem sentido.
    _order("PAO", "CAVIAR")
    _order("PAO", "CAFE")
    _order("PAO", "CAFE")
    _order("PAO", "CAFE")
    _run(min_support=3)

    assert _lift("PAO", "CAFE") is not None
    assert _lift("PAO", "CAVIAR") is None


def test_recompute_drops_pairs_that_fell_below_support():
    for _ in range(3):
        _order("PAO", "CAFE")
    _run(min_support=2)
    assert _lift("PAO", "CAFE") is not None

    _run(min_support=10)
    assert _lift("PAO", "CAFE") is None


# --- peso decrescente -------------------------------------------------------


def test_a_recent_basket_weighs_more_than_an_old_one():
    for _ in range(3):
        _order("PAO", "CAFE", days_ago=1)
    for _ in range(3):
        _order("PAO", "SUCO", days_ago=300)
    _run(half_life_days=60)

    recent = ProductAffinity.objects.get(sku_a="PAO", sku_b="CAFE")
    old = ProductAffinity.objects.get(sku_a="PAO", sku_b="SUCO")
    assert recent.score > old.score
    # A contagem crua não tem peso — é o piso de suporte, não a força.
    assert recent.together_count == old.together_count


def test_baskets_outside_the_window_are_not_read():
    for _ in range(5):
        _order("PAO", "CAFE", days_ago=400)
    _run(window_days=365)

    assert ProductAffinity.objects.count() == 0


# --- cadência ---------------------------------------------------------------


def test_a_fresh_table_is_not_recomputed():
    for _ in range(3):
        _order("PAO", "CAFE")
    _run()
    stamp = ProductAffinity.objects.first().computed_at

    for _ in range(3):
        _order("PAO", "SUCO")
    call_command("compute_product_affinity", min_support=2, verbosity=0)  # 20h por padrão

    assert ProductAffinity.objects.first().computed_at == stamp
    assert _lift("PAO", "SUCO") is None


def test_force_recomputes_a_fresh_table():
    for _ in range(3):
        _order("PAO", "CAFE")
    _run()

    for _ in range(3):
        _order("PAO", "SUCO")
    call_command("compute_product_affinity", min_support=2, force=True, verbosity=0)

    assert _lift("PAO", "SUCO") is not None


# --- o teste que dá nome ao WP ---------------------------------------------


def test_water_does_not_win_by_being_popular():
    """A regra antiga ofereceu Água a quem levava pão. O lift não oferece.

    A água entra em quase toda cesta desta casa — com pão, com doce, com
    sanduíche. Aparecer com tudo é o oposto de combinar com algo: o lift dela
    fica na vizinhança de 1 (o acaso), enquanto o par que de fato anda junto
    sobe bem acima.
    """
    # Água acompanha tudo: 12 cestas, um item diferente em cada.
    for i in range(12):
        _order("AGUA", f"ITEM{i % 6}")
    # Pão e café andam juntos, e só entre si.
    for _ in range(6):
        _order("PAO", "CAFE")
    # Pão também sai com água, na mesma proporção em que a água sai com tudo.
    for _ in range(2):
        _order("PAO", "AGUA")

    _run(min_support=2)

    pao_cafe = _lift("PAO", "CAFE")
    pao_agua = _lift("PAO", "AGUA")

    assert pao_cafe is not None
    assert pao_agua is not None
    assert pao_cafe > pao_agua, (
        f"café ({pao_cafe:.2f}) tem de combinar mais com pão que a água ({pao_agua:.2f})"
    )

    # E o mais forte para PAO é o café, não a água — que é a sugestão que sai.
    top = ProductAffinity.objects.filter(sku_a="PAO").order_by("-lift").first()
    assert top.sku_b == "CAFE"


# --- a fronteira com o backstage -------------------------------------------


def test_the_external_history_teaches_too():
    """Os dois anos do Yooga são a maior parte do que a casa sabe sobre cestas.

    O ``shop`` não alcança o ``backstage`` — a regra de dependência só abre
    exceção em ``adapters/``. Este teste existe para provar que a exceção está
    de pé: sem ela, a afinidade nasceria sabendo só dos pedidos nativos, que são
    poucos.
    """
    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem, ImportBatch

    batch = ImportBatch.objects.create(source="yooga", file_name="teste.csv")
    for n in range(4):
        sale = HistoricalSale.objects.create(
            source="yooga", external_id=n, occurred_at=timezone.now() - timedelta(days=30),
            total_q=1000, batch=batch,
        )
        for seq, sku in enumerate(("CROISSANT", "CAPPUCCINO")):
            HistoricalSaleItem.objects.create(
                sale=sale, seq=seq, product_name=sku, sku=sku,
                qty=1, unit_price_q=500, line_total_q=500,
            )

    _run(min_support=2)

    assert _lift("CROISSANT", "CAPPUCCINO") is not None


def test_history_lines_without_a_resolved_sku_are_not_products():
    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem, ImportBatch

    batch = ImportBatch.objects.create(source="yooga", file_name="teste.csv")
    for n in range(4):
        sale = HistoricalSale.objects.create(
            source="yooga", external_id=n, occurred_at=timezone.now() - timedelta(days=30),
            total_q=1000, batch=batch,
        )
        # Nome solto do sistema antigo, sem de-para: é uma string, não um produto.
        HistoricalSaleItem.objects.create(
            sale=sale, seq=0, product_name="Pão sem cadastro", sku="",
            qty=1, unit_price_q=500, line_total_q=500,
        )
        HistoricalSaleItem.objects.create(
            sale=sale, seq=1, product_name="Café", sku="CAFE",
            qty=1, unit_price_q=500, line_total_q=500,
        )

    _run(min_support=2)

    assert ProductAffinity.objects.count() == 0
