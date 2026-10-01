from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.offerman.models import Product

from shopman.shop import dynamic_collections


@pytest.mark.django_db
def test_fresh_from_oven_uses_current_craftsman_work_order_contract():
    Product.objects.create(
        sku="CROISSANT-FRESH",
        name="Croissant",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    recipe = Recipe.objects.create(
        ref="croissant-fresh",
        name="Croissant",
        output_sku="CROISSANT-FRESH",
        batch_size=Decimal("12"),
    )
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku="CROISSANT-FRESH",
        quantity=Decimal("12"),
        finished=Decimal("12"),
        status=WorkOrder.Status.FINISHED,
        finished_at=timezone.now(),
    )

    section = dynamic_collections.resolve("fresh_from_oven", channel_ref="web")

    assert section is not None
    assert section.skus == ("CROISSANT-FRESH",)


def _published(sku: str) -> Product:
    return Product.objects.create(
        sku=sku, name=sku, base_price_q=1000, is_published=True, is_sellable=True,
    )


def _sell(sku: str, times: int) -> None:
    from shopman.orderman.models import Order, OrderItem

    for _ in range(times):
        order = Order.objects.create(
            ref=f"DYN-{Order.objects.count() + 1}", channel_ref="web", status="new", total_q=1000,
        )
        OrderItem.objects.create(
            order=order, line_id="L1", sku=sku, name=sku, qty=Decimal("1"),
            unit_price_q=1000, line_total_q=1000,
        )


def _featured() -> tuple[str, ...]:
    section = dynamic_collections.resolve("featured", channel_ref="web")
    return section.skus if section else ()


@pytest.mark.django_db
def test_featured_ranking_is_read_once_per_window():
    """O agregado de vendas sai do cache curto: pedido novo espera a janela."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    _published("PAO-A")
    _published("PAO-B")
    _sell("PAO-B", 2)
    _sell("PAO-A", 1)
    assert _featured() == ("PAO-B", "PAO-A")

    _sell("PAO-A", 3)
    with CaptureQueriesContext(connection) as ctx:
        assert _featured() == ("PAO-B", "PAO-A")
    assert not any("orderman_orderitem" in q["sql"] for q in ctx.captured_queries)

    dynamic_collections.invalidate_featured_ranking()
    assert _featured() == ("PAO-A", "PAO-B")
    assert dynamic_collections.FEATURED_RANKING_TTL_SECONDS == 300


@pytest.mark.django_db
def test_featured_reads_publication_and_pause_live():
    """Só o ranking fica guardado: pausar o produto tira dos Destaques na hora."""
    _published("PAO-A")
    pausado = _published("PAO-B")
    _sell("PAO-B", 2)
    _sell("PAO-A", 1)
    assert _featured() == ("PAO-B", "PAO-A")

    pausado.is_sellable = False
    pausado.save(update_fields=["is_sellable"])
    assert _featured() == ("PAO-A",)


@pytest.mark.django_db
def test_featured_survives_cache_outage(monkeypatch):
    """Cache fora do ar não derruba a seção: o ranking vem do banco."""
    from django.core.cache import cache

    def down(*args, **kwargs):
        raise ConnectionError("cache fora do ar")

    _published("PAO-A")
    _sell("PAO-A", 1)
    monkeypatch.setattr(cache, "get", down)
    monkeypatch.setattr(cache, "set", down)
    assert _featured() == ("PAO-A",)
