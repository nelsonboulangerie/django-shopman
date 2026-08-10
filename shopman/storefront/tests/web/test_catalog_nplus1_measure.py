"""Measurement + golden-snapshot harness for the catalog N+1 plan.

Not a normal assertion test: it seeds a rich catalog (many products across
collections, tags, a bundle, active promotions targeting sku/collection/segment,
happy-hour disabled for storefront) then:

  - measures the query count of a *steady-state* ``build_catalog`` call with
    ``CaptureQueriesContext`` (warms caches first, like a long-lived worker), and
  - serializes the full projection (items + prices + badges + sections) to JSON
    at ``$CATALOG_SNAPSHOT_PATH`` so before/after runs can be diffed byte-for-byte.

Run before and after the fix:

    CATALOG_SNAPSHOT_PATH=/tmp/before.json \
      .venv/bin/python -m pytest shopman/storefront/tests/web/test_catalog_nplus1_measure.py -s

The ``-s`` surfaces the printed query count.
"""
from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Listing,
    ListingItem,
    Product,
    ProductComponent,
)

from shopman.shop.models import Promotion
from shopman.storefront.presentation import build_catalog

pytestmark = pytest.mark.django_db


COLLECTIONS = [
    ("paes", "Pães", 1),
    ("doces", "Doces", 2),
    ("bebidas", "Bebidas", 3),
]

# 15 merchandise products spread across the 3 collections + 1 bundle = 16 SKUs.
PRODUCTS = [
    # (sku, name, price_q, collection_ref, tags, sellable)
    ("PAO-FRANCES", "Pão Francês", 80, "paes", ["salgado", "classico"], True),
    ("PAO-INTEGRAL", "Pão Integral", 120, "paes", ["salgado", "fit"], True),
    ("PAO-QUEIJO", "Pão de Queijo", 90, "paes", ["salgado", "sem-gluten"], True),
    ("BAGUETE", "Baguete", 150, "paes", ["salgado", "classico"], True),
    ("CIABATTA", "Ciabatta", 160, "paes", ["salgado"], True),
    ("CROISSANT", "Croissant", 800, "doces", ["amanteigado", "classico"], True),
    ("PAO-CHOCOLATE", "Pain au Chocolat", 900, "doces", ["amanteigado", "chocolate"], True),
    ("BOLO-CENOURA", "Bolo de Cenoura", 1200, "doces", ["chocolate"], True),
    ("BRIGADEIRO", "Brigadeiro", 350, "doces", ["chocolate", "doce"], True),
    ("SONHO", "Sonho", 600, "doces", ["doce"], False),  # not sellable → paused
    ("CAFE", "Café Coado", 500, "bebidas", ["quente"], True),
    ("CAPPUCCINO", "Cappuccino", 900, "bebidas", ["quente", "leite"], True),
    ("SUCO-LARANJA", "Suco de Laranja", 700, "bebidas", ["gelado", "fruta"], True),
    ("AGUA", "Água Mineral", 300, "bebidas", ["gelado"], True),
    ("CHA", "Chá", 400, "bebidas", ["quente"], True),
]

BUNDLE_SKU = "COMBO-CAFE-PAO"


def _seed_catalog() -> None:
    from shopman.shop.models import Channel, Shop

    if not Shop.objects.exists():
        Shop.objects.create(name="Demo", brand_name="Demo", short_name="Demo")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja Online"})

    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    collections = {}
    for ref, name, order in COLLECTIONS:
        collections[ref] = Collection.objects.create(
            name=name, ref=ref, is_active=True, sort_order=order
        )

    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )

    for idx, (sku, name, price_q, col_ref, tags, sellable) in enumerate(PRODUCTS):
        p = Product.objects.create(
            sku=sku,
            name=name,
            base_price_q=price_q,
            is_published=True,
            is_sellable=sellable,
            short_description=f"{name} fresquinho",
        )
        p.keywords.add(*tags)
        CollectionItem.objects.create(collection=collections[col_ref], product=p, sort_order=idx)
        ListingItem.objects.create(
            listing=listing, product=p, price_q=price_q, is_published=True, is_sellable=True
        )
        # Varying stock: some low, some plenty, one zero (sold out).
        qty = Decimal("3") if idx % 5 == 0 else Decimal("50")
        if sku == "AGUA":
            qty = Decimal("0")
        if qty > 0:
            stock.receive(
                quantity=qty, sku=sku, position=position, target_date=date.today(),
                reason="nplus1 seed",
            )

    # Bundle: café + pão francês.
    bundle = Product.objects.create(
        sku=BUNDLE_SKU,
        name="Combo Café + Pão",
        base_price_q=550,
        is_published=True,
        is_sellable=True,
        short_description="Café coado com pão francês",
    )
    bundle.keywords.add("combo", "promo")
    CollectionItem.objects.create(collection=collections["bebidas"], product=bundle, sort_order=99)
    ListingItem.objects.create(
        listing=listing, product=bundle, price_q=550, is_published=True, is_sellable=True
    )
    ProductComponent.objects.create(
        parent=bundle, component=Product.objects.get(sku="CAFE"), qty=Decimal("1")
    )
    ProductComponent.objects.create(
        parent=bundle, component=Product.objects.get(sku="PAO-FRANCES"), qty=Decimal("1")
    )

    now = timezone.now()
    # Global percent promo (all SKUs).
    Promotion.objects.create(
        ref="semana-do-pao",
        name="Semana do Pão",
        type=Promotion.PERCENT,
        value=10,
        is_active=True,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    # Collection-targeted percent promo (doces).
    Promotion.objects.create(
        ref="doces-em-oferta",
        name="Doces em Oferta",
        type=Promotion.PERCENT,
        value=20,
        is_active=True,
        collections=["doces"],
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    # SKU-targeted fixed promo.
    Promotion.objects.create(
        ref="cafe-barato",
        name="Café Barato",
        type=Promotion.FIXED,
        value=100,
        is_active=True,
        skus=["CAFE"],
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )


def _serialize(proj) -> dict:
    def item_dict(it):
        d = dataclasses.asdict(it)
        # tuples → lists for stable JSON; sort where order is set-derived.
        return d

    return {
        "items": [item_dict(i) for i in proj.items],
        "sections": [
            {
                "ref": s.ref,
                "label": s.label,
                "icon": s.icon,
                "is_dynamic": s.is_dynamic,
                "dynamic_ref": s.dynamic_ref,
                "item_skus": [i.sku for i in s.items],
            }
            for s in proj.sections
        ],
        "featured_skus": [i.sku for i in proj.featured],
        "categories": [{"ref": c.ref, "name": c.name} for c in proj.categories],
        "active_category_ref": proj.active_category_ref,
        "happy_hour": dataclasses.asdict(proj.happy_hour) if proj.happy_hour else None,
    }


def test_measure_catalog_queries():
    _seed_catalog()

    # Warm caches (rules engine, ChannelConfig, boot) so we measure steady state,
    # not one-off boot queries — production workers are long-lived.
    build_catalog(channel_ref="web")

    with CaptureQueriesContext(connection) as ctx:
        proj = build_catalog(channel_ref="web")

    n = len(ctx.captured_queries)
    print(f"\n[CATALOG-NPLUS1] build_catalog queries (steady state): {n}")
    print(f"[CATALOG-NPLUS1] items: {len(proj.items)} sections: {len(proj.sections)}")

    snapshot = _serialize(proj)
    path = os.environ.get("CATALOG_SNAPSHOT_PATH")
    if path:
        with open(path, "w") as fh:
            json.dump(snapshot, fh, indent=2, ensure_ascii=False, sort_keys=True, default=str)
        print(f"[CATALOG-NPLUS1] snapshot written to {path}")

    # Also dump the raw SQL for cold-path analysis when asked.
    if os.environ.get("CATALOG_SQL_DUMP"):
        with open(os.environ["CATALOG_SQL_DUMP"], "w") as fh:
            for q in ctx.captured_queries:
                fh.write(q["sql"] + "\n")

    assert len(proj.items) == len(PRODUCTS) + 1  # +bundle
    # Regression ceiling: before the N+1 fix this fixture cost 111 queries. The
    # count is now bounded by collection count + fixed availability passes, not
    # per-SKU. Generous headroom; the strong guard is the scaling test below.
    assert n <= 55, n


def _extra_products(listing, collections, position, n: int, start: int) -> None:
    from shopman.stockman import stock

    col_refs = list(collections)
    for i in range(n):
        idx = start + i
        col_ref = col_refs[i % len(col_refs)]
        sku = f"FILLER-{idx}"
        p = Product.objects.create(
            sku=sku, name=f"Filler {idx}", base_price_q=100 + idx,
            is_published=True, is_sellable=True, short_description="filler",
        )
        p.keywords.add("filler", f"lote-{idx % 3}")
        CollectionItem.objects.create(collection=collections[col_ref], product=p, sort_order=1000 + idx)
        ListingItem.objects.create(
            listing=listing, product=p, price_q=100 + idx, is_published=True, is_sellable=True
        )
        stock.receive(quantity=Decimal("20"), sku=sku, position=position,
                      target_date=date.today(), reason="filler")


def test_query_count_does_not_scale_with_product_count():
    """The N+1 is dead when adding products does NOT add queries.

    Seeds the same 3 collections with a small vs large product count and asserts
    the query count is (nearly) flat — remaining queries scale with collection
    count and the fixed availability passes, never per product.
    """
    from shopman.offerman.models import Listing
    from shopman.stockman.models import Position, PositionKind

    from shopman.shop.models import Channel, Shop

    if not Shop.objects.exists():
        Shop.objects.create(name="Demo", brand_name="Demo", short_name="Demo")
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja Online"})
    listing = Listing.objects.create(ref="web", name="Web", is_active=True, priority=10)
    collections = {}
    for ref, name, order in COLLECTIONS:
        collections[ref] = Collection.objects.create(name=name, ref=ref, is_active=True, sort_order=order)
    position, _ = Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )

    _extra_products(listing, collections, position, n=6, start=0)
    build_catalog(channel_ref="web")  # warm
    with CaptureQueriesContext(connection) as small_ctx:
        small = build_catalog(channel_ref="web")
    n_small = len(small_ctx.captured_queries)

    _extra_products(listing, collections, position, n=60, start=100)
    build_catalog(channel_ref="web")  # warm
    with CaptureQueriesContext(connection) as big_ctx:
        big = build_catalog(channel_ref="web")
    n_big = len(big_ctx.captured_queries)

    print(f"\n[CATALOG-NPLUS1] {len(small.items)} products -> {n_small} queries; "
          f"{len(big.items)} products -> {n_big} queries")
    # 10x the products must not meaningfully move the query count. Allow a tiny
    # slop for prefetch/grouping variation; a per-product N+1 would add ~54.
    assert n_big - n_small <= 3, (n_small, n_big)
