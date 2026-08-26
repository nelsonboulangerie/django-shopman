"""Contrato de projection COMPARTILHADO BE↔FE — o artefato único.

O furo que isto fecha (auditoria de 26/08): o BE travava o que emite em
asserts escritos à mão, e o vitest do Nuxt consumia fixtures TAMBÉM escritas
à mão. Um rename de chave feito "completo" (BE + teste BE + fixture FE, tudo
junto, tudo verde) passava por todos os gates e quebrava só na tela.

O mecanismo: estes testes constroem um cenário canônico determinístico,
serializam a projection real e comparam byte a byte com o snapshot commitado
em ``contracts/projections/*.json``. O MESMO arquivo é importado pelo vitest
do storefront-nuxt (``tests/projectionContracts.test.ts``), que o atribui aos
tipos TS e o atravessa pelas funções de presentation — então mudar o contrato
exige regenerar UM artefato, cujo diff grita no PR, e o FE nunca testa contra
uma forma que o BE não produz mais.

Para regenerar após uma mudança DELIBERADA de contrato:

    SHOPMAN_UPDATE_CONTRACTS=1 pytest shopman/storefront/tests/test_shared_projection_contracts.py

e commite o diff de ``contracts/projections/`` junto com a mudança.

Valores voláteis (datas, horários) são normalizados relativo ao dia do run
(``<today>``/``<tomorrow>``/``<datetime>``) — o contrato trava ESTRUTURA e
valores estáveis, nunca o relógio (uma âncora só, como manda a memória do
dia semeado).
"""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts" / "projections"

_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _scrub(value, *, today: str, tomorrow: str):
    """Normaliza valores presos ao relógio, preservando a estrutura."""
    if isinstance(value, dict):
        return {k: _scrub(v, today=today, tomorrow=tomorrow) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub(v, today=today, tomorrow=tomorrow) for v in value]
    if isinstance(value, str):
        if _DATETIME_RE.match(value):
            return "<datetime>"
        if _DATE_RE.match(value):
            if value == today:
                return "<today>"
            if value == tomorrow:
                return "<tomorrow>"
            return "<date>"
    return value


def _assert_matches_contract(payload, name: str) -> None:
    today = timezone.localdate()
    scrubbed = _scrub(
        payload, today=str(today), tomorrow=str(today + timedelta(days=1))
    )
    rendered = json.dumps(scrubbed, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    path = CONTRACTS_DIR / f"{name}.json"

    if os.environ.get("SHOPMAN_UPDATE_CONTRACTS") == "1":
        CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        pytest.fail(
            f"Contrato {name} regenerado em {path}. Revise o diff, commite junto "
            "com a mudança de contrato, e rode de novo SEM SHOPMAN_UPDATE_CONTRACTS."
        )

    assert path.exists(), (
        f"Contrato {path} não existe. Gere com SHOPMAN_UPDATE_CONTRACTS=1 e commite."
    )
    assert rendered == path.read_text(encoding="utf-8"), (
        f"A projection diverge do contrato compartilhado {name}.json. Se a mudança "
        "de contrato é deliberada, regenere com SHOPMAN_UPDATE_CONTRACTS=1, revise "
        "o diff (o FE consome ESTE arquivo) e commite os dois lados juntos."
    )


@pytest.fixture
def canonical_catalog(db):
    """O cardápio canônico: um produto por estado de disponibilidade."""
    from shopman.offerman.models import (
        Collection,
        CollectionItem,
        Listing,
        ListingItem,
        Product,
    )
    from shopman.stockman.models import Position, PositionKind, Quant

    from shopman.shop.models import Shop

    Shop.load() or Shop.objects.create(name="Padaria Contrato")
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={
            "name": "Vitrine",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    collection = Collection.objects.create(ref="paes", name="Pães", is_active=True)
    listing = Listing.objects.create(ref="web", name="Loja", is_active=True)

    def add_product(sku: str, name: str, price_q: int, *, qty: Decimal | None):
        product = Product.objects.create(sku=sku, name=name, base_price_q=price_q)
        CollectionItem.objects.create(collection=collection, product=product, is_primary=True)
        ListingItem.objects.create(listing=listing, product=product, price_q=price_q)
        if qty is not None:
            Quant.objects.create(sku=sku, position=vitrine, _quantity=qty)
        return product

    add_product("PAO-CONTRATO", "Pão do Contrato", 900, qty=Decimal("12"))
    add_product("CROISSANT-CONTRATO", "Croissant do Contrato", 1200, qty=Decimal("2"))
    add_product("BOLO-CONTRATO", "Bolo do Contrato", 2400, qty=None)

    # Planejado para amanhã: o estado "encomendável" (planned) do cardápio.
    sonho = add_product("SONHO-CONTRATO", "Sonho do Contrato", 800, qty=None)
    Quant.objects.create(
        sku=sonho.sku,
        position=None,
        target_date=timezone.localdate() + timedelta(days=1),
        _quantity=Decimal("30"),
    )
    return collection


def test_storefront_catalog_matches_shared_contract(canonical_catalog):
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.catalog import build_catalog

    payload = projection_data(build_catalog(channel_ref="web"))
    _assert_matches_contract(payload, "storefront_catalog")


def test_storefront_product_detail_matches_shared_contract(canonical_catalog):
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.product_detail import build_product_detail

    payload = projection_data(
        build_product_detail(sku="CROISSANT-CONTRATO", channel_ref="web")
    )
    _assert_matches_contract(payload, "storefront_product_detail")
