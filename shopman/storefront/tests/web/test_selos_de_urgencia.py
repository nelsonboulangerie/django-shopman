"""Os selos de urgência no card do cardápio e na página do produto (#2807).

O servidor já derivava os selos (``presentation/fomo``) e os servia por SKU, mas
nenhuma tela os desenhava. Agora o item do cardápio e o produto levam
``fomo_badges``, da mesma derivação, com os fatos em lote: a fornada de todos os
SKUs numa query, o estoque e as promoções que o cardápio já tinha em mão.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.offerman.models import ListingItem

from shopman.shop.models import Promotion
from shopman.storefront.presentation import build_catalog
from shopman.storefront.presentation.fomo import showcase_badges

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


def _publish(listing, product) -> None:
    ListingItem.objects.get_or_create(
        listing=listing, product=product,
        defaults={"price_q": product.base_price_q, "is_published": True, "is_sellable": True},
    )


def _finished(sku: str, minutes_ago: int) -> WorkOrder:
    recipe, _ = Recipe.objects.get_or_create(ref=f"r-{sku.lower()}", defaults={"name": sku, "output_sku": sku, "batch_size": 1})
    work_order = WorkOrder.objects.create(recipe=recipe, output_sku=sku, quantity=10, status="finished")
    WorkOrder.objects.filter(pk=work_order.pk).update(finished_at=timezone.now() - timedelta(minutes=minutes_ago))
    return work_order


def _item(sku: str):
    return next(item for item in build_catalog(channel_ref="web").items if item.sku == sku)


def test_fornada_pronta_ha_pouco_vira_selo_no_card(listing, collection_item, product):
    _publish(listing, product)
    _finished(product.sku, minutes_ago=12)

    badges = _item(product.sku).fomo_badges

    assert [(b.type, b.label) for b in badges] == [("fresh", "Fornada pronta há 12 min")]
    # A tela refaz o "há N min" pelo relógio dela: o cardápio passa por cache de borda.
    assert badges[0].meta["finished_at"]
    assert badges[0].expires_at


def test_fornada_de_mais_de_uma_hora_nao_e_noticia(listing, collection_item, product):
    _publish(listing, product)
    _finished(product.sku, minutes_ago=90)

    assert _item(product.sku).fomo_badges == ()


def test_promocao_acabando_vira_contagem_no_card(listing, collection_item, product):
    _publish(listing, product)
    now = timezone.now()
    Promotion.objects.create(
        ref="relampago", name="Relâmpago", type=Promotion.PERCENT, value=10,
        valid_from=now - timedelta(hours=1), valid_until=now + timedelta(minutes=150), is_active=True,
    )

    badges = _item(product.sku).fomo_badges

    assert [(b.type, b.label) for b in badges] == [("promo_countdown", "Promoção acaba em 2h")]


def test_os_selos_sao_os_da_vitrine_sem_prova_social():
    """Últimas unidades com o número; no máximo dois, do mais urgente."""
    now = timezone.now()
    badges = showcase_badges(
        "CRO",
        available_qty=3,
        finished_at=now - timedelta(minutes=5),
        promotions=[],
        sku_collections=(),
        low_stock_threshold=Decimal("5"),
        now=now,
    )

    assert [(b.type, b.label) for b in badges] == [
        ("fresh", "Fornada pronta há 5 min"),
        ("low_stock", "Últimas 3 unidades"),
    ]


def test_sem_estoque_conhecido_nao_ha_ultimas_unidades():
    assert showcase_badges(
        "CRO", available_qty=None, finished_at=None, promotions=[], sku_collections=(),
        low_stock_threshold=Decimal("5"),
    ) == ()


def test_a_pagina_do_produto_leva_os_mesmos_selos(listing, collection_item, product):
    from shopman.storefront.presentation.product_detail import build_product_detail

    _publish(listing, product)
    _finished(product.sku, minutes_ago=12)

    detail = build_product_detail(sku=product.sku, channel_ref="web")

    assert [(b.type, b.label) for b in detail.fomo_badges] == [("fresh", "Fornada pronta há 12 min")]
