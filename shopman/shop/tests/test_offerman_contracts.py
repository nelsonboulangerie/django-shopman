"""
Contratos do Offerman do lado do orquestrador, e a autoridade única de preço.

1. **Contratos fechados.** Cada impl que o orquestrador pluga num Protocol do
   Offerman (``OFFERMAN[...]``, ``CRAFTSMAN["CATALOG_BACKEND"]``) honra a
   assinatura declarada, e verbo opcional só existe declarado
   (``IncrementalCatalogProjectionBackend``), nunca por ``hasattr``.

2. **Autoridade única de preço** — a busca de símbolo, executável:

   - faixa por quantidade: só ``CatalogService.unit_prices`` (o
     ``test_offerman_is_the_only_list_tier_price_owner`` cobre os consumidores
     nomeados);
   - preço contextual: só ``CatalogService.get_price`` consulta o
     ``PricingBackend`` (``get_pricing_backend``) e chama o seu ``get_price``
     com ``list_unit_price_q``; ``ContextualPrice`` nasce no Offerman ou numa
     impl de ``PricingBackend``;
   - caminhos mortos que não voltam: ``shop/services/pricing.py::resolve``, o
     ``get_price`` do adapter interno de catálogo e o ``get_price`` do port de
     catálogo (``CatalogBackend``).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from shopman.offerman.protocols import (
    CatalogBackend,
    CatalogProjectionBackend,
    IncrementalCatalogProjectionBackend,
    LabelAttributesProvider,
    PricingBackend,
)

from shopman.shop.adapters.catalog_backend import ComposedCatalogBackend
from shopman.shop.adapters.catalog_projection_google import GoogleMerchantProjection
from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection
from shopman.shop.adapters.catalog_projection_meta import MetaCatalogProjection
from shopman.shop.adapters.pricing import PromotionPricingBackend
from shopman.shop.services.attributes import LabelAttributesProvider as ShopLabelAttributesProvider

REPO_ROOT = Path(__file__).resolve().parents[3]
CODE_ROOTS = (REPO_ROOT / "shopman", REPO_ROOT / "packages", REPO_ROOT / "config")
OFFERMAN_SERVICE = REPO_ROOT / "packages" / "offerman" / "shopman" / "offerman" / "service.py"
OFFERMAN_CONF = REPO_ROOT / "packages" / "offerman" / "shopman" / "offerman" / "conf.py"
OFFERMAN_NOOP = REPO_ROOT / "packages" / "offerman" / "shopman" / "offerman" / "adapters" / "noop.py"
SHOP_PRICING_BACKEND = REPO_ROOT / "shopman" / "shop" / "adapters" / "pricing.py"


def _protocol_verbs(protocol: type) -> dict[str, inspect.Signature]:
    verbs = {}
    for klass in reversed(protocol.__mro__):
        if klass is object or not getattr(klass, "_is_protocol", False):
            continue
        for name, member in vars(klass).items():
            if not name.startswith("_") and callable(member):
                verbs[name] = inspect.signature(member)
    return verbs


def _shape(signature: inspect.Signature) -> list[tuple]:
    return [(p.name, p.kind, p.default) for p in signature.parameters.values() if p.name != "self"]


def _public_verbs(impl: type) -> set[str]:
    return {name for name, _member in inspect.getmembers(impl, callable) if not name.startswith("_")}


@pytest.mark.parametrize(
    ("impl", "protocol"),
    [
        (PromotionPricingBackend, PricingBackend),
        (ComposedCatalogBackend, CatalogBackend),
        (GoogleMerchantProjection, CatalogProjectionBackend),
        (MetaCatalogProjection, CatalogProjectionBackend),
        (IFoodCatalogProjection, IncrementalCatalogProjectionBackend),
        (ShopLabelAttributesProvider, LabelAttributesProvider),
    ],
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_orchestrator_impls_honour_offerman_contracts(impl, protocol):
    declared = _protocol_verbs(protocol)
    for name, expected in declared.items():
        assert hasattr(impl, name), f"{impl.__name__} não implementa {protocol.__name__}.{name}"
        actual = inspect.signature(getattr(impl, name))
        assert _shape(actual) == _shape(expected), (
            f"{impl.__name__}.{name}{actual} diverge de {protocol.__name__}.{name}{expected}"
        )
    extra = _public_verbs(impl) - set(declared)
    assert not extra, f"{impl.__name__} oferece verbos fora de {protocol.__name__}: {sorted(extra)}"


def test_only_ifood_is_an_incremental_projection():
    """O verbo opcional se pergunta pelo contrato; Google e Meta não o têm."""
    assert isinstance(IFoodCatalogProjection(), IncrementalCatalogProjectionBackend)
    assert not isinstance(GoogleMerchantProjection(), IncrementalCatalogProjectionBackend)
    assert not isinstance(MetaCatalogProjection(), IncrementalCatalogProjectionBackend)


def test_projection_handler_asks_the_contract_not_hasattr():
    source = (REPO_ROOT / "shopman" / "shop" / "handlers" / "catalog_projection.py").read_text()
    assert 'hasattr(backend, "set_availability")' not in source
    assert 'hasattr(backend, "update_price")' not in source
    assert "isinstance(backend, IncrementalCatalogProjectionBackend)" in source


# ── Autoridade única de preço ────────────────────────────────────────────────


def _production_modules():
    for root in CODE_ROOTS:
        for path in root.rglob("*.py"):
            # ``build/`` e ``dist/`` são cópias de empacotamento (gitignored), não código.
            if set(path.parts) & {"tests", "migrations", "node_modules", "build", "dist", ".venv"}:
                continue
            yield path, ast.parse(path.read_text(), filename=str(path))


def _calls(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def _callee_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_only_catalog_service_consults_the_pricing_backend():
    readers, quoters = [], []
    for path, tree in _production_modules():
        for call in _calls(tree):
            name = _callee_name(call)
            if name == "get_pricing_backend" and path != OFFERMAN_SERVICE:
                readers.append(f"{path.relative_to(REPO_ROOT)}:{call.lineno}")
            if name == "get_price" and any(kw.arg == "list_unit_price_q" for kw in call.keywords):
                # ``CatalogService.get_price(...)`` é o verbo público (que recebe
                # a lista já resolvida por ``unit_prices`` em lote); o que não
                # pode é chamar o ``get_price`` do backend por fora dele.
                receiver = call.func.value if isinstance(call.func, ast.Attribute) else None
                if isinstance(receiver, ast.Name) and receiver.id == "CatalogService":
                    continue
                if path != OFFERMAN_SERVICE:
                    quoters.append(f"{path.relative_to(REPO_ROOT)}:{call.lineno}")
    assert not readers, "PricingBackend lido fora do CatalogService:\n" + "\n".join(readers)
    assert not quoters, "PricingBackend.get_price chamado fora do CatalogService:\n" + "\n".join(quoters)


def test_contextual_price_is_born_only_in_offerman_or_a_pricing_backend():
    allowed = {OFFERMAN_SERVICE, OFFERMAN_NOOP, SHOP_PRICING_BACKEND}
    violations = [
        f"{path.relative_to(REPO_ROOT)}:{call.lineno}"
        for path, tree in _production_modules()
        if path not in allowed
        for call in _calls(tree)
        if _callee_name(call) == "ContextualPrice"
    ]
    assert not violations, "Cotação contextual montada fora do dono:\n" + "\n".join(violations)


def test_dead_price_paths_stay_dead():
    from shopman.shop.adapters import catalog as catalog_adapter

    assert not (REPO_ROOT / "shopman" / "shop" / "services" / "pricing.py").exists()
    assert not hasattr(catalog_adapter, "get_price")
    assert set(_protocol_verbs(CatalogBackend)) == {"get_product"}
    for path, tree in _production_modules():
        if not path.stem.startswith("pricing"):
            continue
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert "resolve" not in names, f"{path.relative_to(REPO_ROOT)} voltou a ter um resolve de preço"


def test_get_pricing_backend_is_defined_once():
    definers = [
        path
        for path, tree in _production_modules()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "get_pricing_backend"
    ]
    assert definers == [OFFERMAN_CONF]
