"""Porteiro fiscal do catálogo: publicar vendável exige classificação completa.

Regressão do audit do Fiscalman (F1): a guarda de completude só existia na
emissão — assíncrona, horas depois da venda — e a validação do form do admin é
opt-in ("once any fiscal data is present"), então produto criado por seed, sync
de catálogo ou script entrava no ar sem NCM e só era descoberto quando a SEFAZ
recusasse a nota.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from shopman.offerman.models import Listing, ListingItem, Product

from shopman.shop.models import Channel
from shopman.shop.services import fiscal_catalog

pytestmark = pytest.mark.django_db

GATE_ON = override_settings(SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH=True)
COMPLETE = {"fiscal": {"profile": "own_production", "ncm": "19059010"}}


def _product(sku="PAO-1", *, metadata=None, published=True):
    return Product.objects.create(
        sku=sku,
        name=f"Produto {sku}",
        is_published=published,
        is_sellable=published,
        metadata=metadata or {},
    )


def _listing(ref="pdv", *, policy=Channel.CommercePolicy.ORDER, active=True):
    Channel.objects.create(ref=ref, name=ref.upper(), commerce_policy=policy, is_active=active)
    return Listing.objects.create(ref=ref, name=ref.upper())


def _publish(listing, product, **kwargs):
    return ListingItem.objects.create(
        listing=listing, product=product, price_q=1000, **kwargs
    )


# ── porteiro desligado (pré-go-live) ──────────────────────────────────────────


def test_gate_off_lets_unclassified_product_be_published():
    listing = _listing()
    product = _product()
    _publish(listing, product)  # não levanta: a chave está desligada

    assert ListingItem.objects.filter(product=product).exists()


# ── porteiro ligado ───────────────────────────────────────────────────────────


@GATE_ON
def test_publishing_unclassified_product_in_selling_channel_is_refused():
    listing = _listing()
    product = _product()

    with pytest.raises(ValidationError) as exc:
        _publish(listing, product)

    assert "Sem classificação fiscal" in str(exc.value)
    assert not ListingItem.objects.filter(product=product).exists()


@GATE_ON
def test_publishing_classified_product_passes():
    listing = _listing()
    product = _product(metadata=COMPLETE)

    _publish(listing, product)

    assert ListingItem.objects.filter(product=product).exists()


@GATE_ON
def test_resale_without_cest_is_refused_by_name():
    listing = _listing()
    product = _product(metadata={"fiscal": {"profile": "resale", "ncm": "22021000"}})

    with pytest.raises(ValidationError) as exc:
        _publish(listing, product)

    assert "CEST" in str(exc.value)


@GATE_ON
def test_display_only_channel_has_no_fiscal_gate():
    # Menuboard/catálogo do Google mostram preço e nunca transacionam: não
    # emitem nota, então não têm porteiro fiscal.
    listing = _listing(ref="display", policy=Channel.CommercePolicy.DISPLAY)
    product = _product()

    _publish(listing, product)

    assert ListingItem.objects.filter(product=product).exists()


@GATE_ON
def test_unpublished_listing_item_is_not_gated():
    listing = _listing()
    product = _product()

    _publish(listing, product, is_published=False)

    assert ListingItem.objects.filter(product=product).exists()


@GATE_ON
def test_unpublished_product_is_not_gated():
    listing = _listing()
    product = _product(published=False)

    _publish(listing, product)

    assert ListingItem.objects.filter(product=product).exists()


@GATE_ON
def test_publishing_the_product_of_a_live_listing_item_is_refused():
    # A outra ordem de operação: o item de vitrine já está publicado e quem liga
    # a última chave é o produto. O porteiro tem de estar nas DUAS portas.
    listing = _listing()
    product = _product(published=False)
    _publish(listing, product)

    product.is_published = True
    product.is_sellable = True
    with pytest.raises(ValidationError):
        product.save()


@GATE_ON
def test_clearing_the_classification_of_a_live_product_is_refused():
    listing = _listing()
    product = _product(metadata=COMPLETE)
    _publish(listing, product)

    product.metadata = {}
    with pytest.raises(ValidationError):
        product.save()


@GATE_ON
def test_product_without_publication_can_stay_unclassified():
    _listing()
    product = _product()  # nenhum ListingItem

    product.name = "Renomeado"
    product.save()

    product.refresh_from_db()
    assert product.name == "Renomeado"


# ── auditoria de catálogo (independe da chave) ────────────────────────────────


def test_audit_lists_incomplete_published_products_with_their_channels():
    listing = _listing()
    other = _listing(ref="whatsapp")
    complete = _product("PAO-OK", metadata=COMPLETE)
    incomplete = _product("PAO-X")
    _publish(listing, complete)
    _publish(listing, incomplete)
    _publish(other, incomplete)

    rows = fiscal_catalog.incomplete_published_products()

    assert [row.sku for row in rows] == ["PAO-X"]
    assert rows[0].listing_refs == ("pdv", "whatsapp")
    assert "Sem classificação fiscal" in rows[0].errors[0]


def test_audit_ignores_products_that_are_not_published():
    listing = _listing()
    hidden = _product("PAO-OFF", published=False)
    _publish(listing, hidden)

    assert fiscal_catalog.incomplete_published_products() == []
