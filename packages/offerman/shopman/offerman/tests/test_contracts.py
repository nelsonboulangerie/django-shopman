"""
Contratos públicos do Offerman: o Protocol declara o que a impl oferece.

Duas travas por contrato:

- **paridade de assinatura**: cada verbo do Protocol existe na impl com os
  mesmos parâmetros (nome, tipo de passagem e default). ``runtime_checkable``
  só confere que o nome existe; um ``get_price(sku, qty)`` posicional passaria
  num contrato só de palavra-chave;
- **contrato fechado**: a impl do pacote não oferece verbo público que o
  Protocol não declara. Verbo fora do contrato é o consumidor chamando por
  ``hasattr`` ou por delegação implícita — o contrato aberto que estas travas
  fecham.

E os verbos públicos do ``CatalogService`` que decidem preço respondem pela
mesma régua: ``unit_prices`` é o único algoritmo de faixa; ``unit_price``,
``price``, ``get_price`` e a projeção externa leem dele.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest
from shopman.offerman import protocols
from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend
from shopman.offerman.adapters.noop import (
    NoopCatalogProjectionBackend,
    NoopCostBackend,
    NoopPricingBackend,
)
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.offerman.protocols import (
    CatalogBackend,
    CatalogProjectionBackend,
    CostBackend,
    PricingBackend,
)
from shopman.offerman.service import CatalogService


def protocol_verbs(protocol: type) -> dict[str, inspect.Signature]:
    """Os verbos declarados pelo Protocol (herança incluída), sem ``self``."""
    verbs = {}
    for klass in reversed(protocol.__mro__):
        if klass is object or not getattr(klass, "_is_protocol", False):
            continue
        for name, member in vars(klass).items():
            if name.startswith("_") or not callable(member):
                continue
            verbs[name] = inspect.signature(member)
    return verbs


def public_verbs(impl: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(impl, callable)
        if not name.startswith("_")
    }


def shape(signature: inspect.Signature) -> list[tuple[str, inspect._ParameterKind, object]]:
    return [
        (param.name, param.kind, param.default)
        for param in signature.parameters.values()
        if param.name != "self"
    ]


def assert_honours(impl: type, protocol: type, *, closed: bool = True) -> None:
    declared = protocol_verbs(protocol)
    assert declared, f"{protocol.__name__} não declara verbo nenhum"
    for name, expected in declared.items():
        assert hasattr(impl, name), f"{impl.__name__} não implementa {protocol.__name__}.{name}"
        actual = inspect.signature(getattr(impl, name))
        assert shape(actual) == shape(expected), (
            f"{impl.__name__}.{name}{actual} diverge de {protocol.__name__}.{name}{expected}"
        )
    if closed:
        extra = public_verbs(impl) - set(declared)
        assert not extra, f"{impl.__name__} oferece verbos fora de {protocol.__name__}: {sorted(extra)}"


@pytest.mark.parametrize(
    ("impl", "protocol"),
    [
        (OffermanCatalogBackend, CatalogBackend),
        (NoopPricingBackend, PricingBackend),
        (NoopCatalogProjectionBackend, CatalogProjectionBackend),
        (NoopCostBackend, CostBackend),
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_in_package_impls_honour_their_protocol(impl, protocol):
    assert_honours(impl, protocol)


def test_every_exported_protocol_is_runtime_checkable():
    exported = [getattr(protocols, name) for name in protocols.__all__]
    contracts = [obj for obj in exported if getattr(obj, "_is_protocol", False)]
    assert contracts
    for contract in contracts:
        assert getattr(contract, "_is_runtime_protocol", False), contract.__name__
        assert protocol_verbs(contract), f"{contract.__name__} é um port vazio"


def test_catalog_backend_carries_no_price_verb():
    """Preço tem um dono: ``CatalogService``. O port de catálogo não cota."""
    assert set(protocol_verbs(CatalogBackend)) == {"get_product"}


def test_incremental_projection_extends_the_base_contract():
    verbs = set(protocol_verbs(protocols.IncrementalCatalogProjectionBackend))
    assert verbs == {"project", "retract", "update_price", "set_availability"}
    assert not isinstance(NoopCatalogProjectionBackend(), protocols.IncrementalCatalogProjectionBackend)


def test_label_attributes_provider_contract():
    assert set(protocol_verbs(protocols.LabelAttributesProvider)) == {"get", "set"}


# ── Verbos públicos de preço: uma régua só ────────────────────────────────────


@pytest.fixture
def tiers(db):
    """Um produto com faixas na vitrine e outro cuja primeira faixa começa em 6."""
    listing = Listing.objects.create(ref="contract", name="Contract", is_active=True)
    pao = Product.objects.create(sku="CT-PAO", name="Pão", base_price_q=500)
    caixa = Product.objects.create(sku="CT-CAIXA", name="Caixa", base_price_q=900)
    ListingItem.objects.create(listing=listing, product=pao, price_q=450, min_qty=Decimal("1"))
    ListingItem.objects.create(listing=listing, product=pao, price_q=400, min_qty=Decimal("10"))
    ListingItem.objects.create(listing=listing, product=caixa, price_q=700, min_qty=Decimal("6"))
    return listing


@pytest.mark.parametrize("qty", [Decimal("0.5"), Decimal("1"), Decimal("9"), Decimal("10"), Decimal("25")])
@pytest.mark.parametrize("sku", ["CT-PAO", "CT-CAIXA"])
def test_price_verbs_read_the_single_tier_algorithm(tiers, sku, qty):
    [expected_unit] = CatalogService.unit_prices([(sku, qty)], listings=(tiers.ref,))
    assert CatalogService.unit_price(sku, qty=qty, listing=tiers.ref) == expected_unit

    quote = CatalogService.get_price(sku, qty=qty, listing=tiers.ref)
    assert quote.list_unit_price_q == expected_unit
    assert quote.list_line_total_q == CatalogService.price(sku, qty=qty, listing=tiers.ref)
    # Sem PricingBackend configurado, a cotação contextual é a de lista.
    assert quote.final_unit_price_q == expected_unit
    assert quote.adjustments == []


def test_projection_publishes_the_unit_price_of_the_same_algorithm(tiers):
    """A faixa que começa em 6 caixas não é o preço de UMA caixa."""
    projected = {item.sku: item.price_q for item in CatalogService.get_projection_items(tiers.ref)}
    assert projected == {
        "CT-PAO": CatalogService.unit_price("CT-PAO", listing=tiers.ref),
        "CT-CAIXA": CatalogService.unit_price("CT-CAIXA", listing=tiers.ref),
    }
    assert projected["CT-CAIXA"] == 900
