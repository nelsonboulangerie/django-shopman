"""Contrato dos verbos públicos do Stockman (F4c da consolidação).

Três travas, uma por gate:

1. **Autoridade única da promessa.** A regra (pausa, política, rastreio) mora em
   ``services/availability.py`` — ``promise_for_sku`` e
   ``decision_from_availability``. Nenhum outro módulo do Stockman compara a
   política de oferta para aprovar ou recusar; o hold pede a decisão e só soma
   as duas autorizações que não são da oferta (insumo de WorkOrder e demanda
   autorizada pelo chamador).
2. **Sem número mágico.** SKU sem ledger é ``is_tracked=False`` com
   ``available_qty=None``; nenhum literal do tipo ``999999`` representa "sem
   limite" (o sentinela saiu em ``df5fe69ff``; esta trava impede que volte).
3. **Verbos públicos.** Promessa, hold (criar, confirmar, consumir, liberar,
   expirar) e consultas, pela fachada ``Stock``.
"""

from __future__ import annotations

import ast
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.stockman import StockError
from shopman.stockman.adapters.sku_validation import reset_sku_validator
from shopman.stockman.models import Hold, Quant
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.protocols.sku import PromiseDecision, PromiseReasonCode
from shopman.stockman.service import Stock
from shopman.stockman.services.availability import promise_for_sku

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
POLICY_LITERALS = {"demand_ok", "stock_only", "planned_ok"}

# (arquivo relativo, função) que podem COMPARAR a política de oferta.
# ``holds.py::hold`` compara só para a ALOCAÇÃO (hold flutuante sem quant),
# depois que a promessa já foi decidida por ``promise_for_sku``.
POLICY_COMPARISON_OWNERS = {
    ("services/availability.py", "_policy_promisable_qty"),
    ("services/availability.py", "decision_from_availability"),
    ("services/holds.py", "hold"),
}


def _source_files():
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        rel = path.relative_to(PACKAGE_ROOT).as_posix()
        if rel.startswith(("tests/", "migrations/")):
            continue
        yield rel, ast.parse(path.read_text(encoding="utf-8"), filename=rel)


def _enclosing_functions(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _function_of(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            return node.name
    return None


# ── Gate 1: autoridade única ──────────────────────────────────────────


def test_only_the_promise_module_compares_offer_policy():
    offenders = []
    for rel, tree in _source_files():
        parents = _enclosing_functions(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            if not any(isinstance(o, ast.Constant) and o.value in POLICY_LITERALS for o in operands):
                continue
            owner = (rel, _function_of(node, parents))
            if owner not in POLICY_COMPARISON_OWNERS:
                offenders.append(f"{rel}:{node.lineno} em {owner[1]}")
    assert offenders == [], (
        "Regra de promessa fora de services/availability.py; peça a decisão a "
        f"promise_for_sku em vez de comparar a política: {offenders}"
    )


def test_promise_symbols_are_defined_once():
    defined = {}
    for rel, tree in _source_files():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {
                "promise_for_sku",
                "decision_from_availability",
            }:
                defined.setdefault(node.name, []).append(rel)
    assert defined == {
        "promise_for_sku": ["services/availability.py"],
        "decision_from_availability": ["services/availability.py"],
    }


# ── Gate 2: sem sentinela ─────────────────────────────────────────────


def test_no_magic_unlimited_quantity_in_stockman_source():
    offenders = []
    for rel, tree in _source_files():
        for node in ast.walk(tree):
            value = None
            if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
                value = node.value
            elif (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "Decimal"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                try:
                    value = Decimal(node.args[0].value)
                except Exception:  # noqa: BLE001 - literal não numérico
                    value = None
            if value is not None and not isinstance(value, bool) and value >= 99999:
                offenders.append(f"{rel}:{node.lineno} ({value})")
    assert offenders == [], f"Quantidade mágica no Stockman: {offenders}"


@pytest.mark.django_db
def test_untracked_sku_has_no_quantity_not_a_big_one(today):
    decision = promise_for_sku("SEM-LEDGER", Decimal("1000000"), target_date=today)

    assert isinstance(decision, PromiseDecision)
    assert decision.is_tracked is False
    assert decision.available_qty is None
    assert decision.orderable_ceiling is None
    assert decision.approved is True


@pytest.mark.django_db
def test_tracked_sku_reports_factual_decimal(product, vitrine, today):
    Stock.receive(Decimal("4"), product.sku, vitrine)

    decision = promise_for_sku(product.sku, Decimal("5"), target_date=today)

    assert decision.is_tracked is True
    assert decision.available_qty == Decimal("4")
    assert isinstance(decision.available_qty, Decimal)
    assert decision.approved is False
    assert decision.reason_code == PromiseReasonCode.INSUFFICIENT_SUPPLY


# ── Gate 4: verbos públicos ───────────────────────────────────────────


@pytest.fixture
def stock_only(settings):
    settings.STOCKMAN = {**settings.STOCKMAN, "SKU_VALIDATOR": "shopman.stockman.tests.fakes.StockOnlySkuValidator"}
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture
def paused(settings):
    settings.STOCKMAN = {**settings.STOCKMAN, "SKU_VALIDATOR": "shopman.stockman.tests.fakes.PausedSkuValidator"}
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.mark.django_db
class TestPromiseVerb:
    def test_stock_promise_is_promise_for_sku(self, product, vitrine, today):
        Stock.receive(Decimal("3"), product.sku, vitrine)

        assert Stock.promise(product.sku, Decimal("2"), target_date=today) == promise_for_sku(
            product.sku, Decimal("2"), target_date=today
        )

    def test_hold_refusal_carries_the_promise_reason(self, product, vitrine, today):
        Stock.receive(Decimal("1"), product.sku, vitrine)
        decision = promise_for_sku(product.sku, Decimal("2"), target_date=today)

        with pytest.raises(StockError) as exc:
            Stock.hold(Decimal("2"), product.sku, today)

        assert exc.value.code == "INSUFFICIENT_AVAILABLE"
        assert exc.value.data["reason_code"] == decision.reason_code
        assert exc.value.data["available"] == decision.orderable_ceiling


@pytest.mark.django_db
class TestHoldVerbs:
    def test_create_reserves_against_a_quant(self, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)

        hold_id = Stock.hold(Decimal("2"), product.sku, today)

        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        assert hold_id.startswith("hold:")
        assert hold.status == HoldStatus.PENDING
        assert hold.quant is not None
        assert Stock.available(product.sku, today) == Decimal("3")

    def test_create_uses_the_policy_of_the_product_it_receives(self, demand_product, today):
        # O produto diz ``demand_ok``; o validador (Noop) diria ``planned_ok``.
        # A política entra na promessa, que aprova sem oferta; o hold flutua.
        hold_id = Stock.hold(Decimal("4"), demand_product, today)

        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        assert hold.quant is None
        assert promise_for_sku(
            demand_product.sku, Decimal("4"), target_date=today, availability_policy="demand_ok"
        ).approved

    def test_stock_only_refuses_planned_supply(self, stock_only, product, vitrine, tomorrow):
        Stock.plan(Decimal("10"), product, tomorrow, position=vitrine)

        with pytest.raises(StockError) as exc:
            Stock.hold(Decimal("1"), product.sku, tomorrow)

        assert exc.value.code == "INSUFFICIENT_AVAILABLE"
        assert exc.value.data["available"] == Decimal("0")

    def test_paused_refuses_even_when_caller_allows_demand(self, paused, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)

        with pytest.raises(StockError) as exc:
            Stock.hold(Decimal("1"), product.sku, today, allow_demand=True)

        assert exc.value.data["reason_code"] == PromiseReasonCode.PAUSED

    def test_workorder_reservation_ignores_the_sale_gate(self, paused, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)

        hold_id = Stock.hold(Decimal("1"), product.sku, today, purpose="workorder")

        assert hold_id.startswith("hold:")

    def test_confirm_then_fulfill_consumes_the_quant(self, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)
        hold_id = Stock.hold(Decimal("2"), product.sku, today)

        Stock.confirm(hold_id)
        move = Stock.fulfill(hold_id)

        hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
        assert hold.status == HoldStatus.FULFILLED
        assert move.delta == Decimal("-2")
        assert Quant.objects.get(sku=product.sku).quantity == Decimal("3")
        assert Stock.available(product.sku, today) == Decimal("3")

    def test_release_returns_the_reservation(self, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)
        hold_id = Stock.hold(Decimal("2"), product.sku, today)

        Stock.release(hold_id)

        assert Hold.objects.get(pk=int(hold_id.split(":")[1])).status == HoldStatus.RELEASED
        assert Stock.available(product.sku, today) == Decimal("5")

    def test_release_expired_frees_only_past_deadline(self, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)
        past = timezone.now() - timedelta(minutes=1)
        future = timezone.now() + timedelta(hours=1)
        expired_id = Stock.hold(Decimal("1"), product.sku, today, expires_at=past)
        live_id = Stock.hold(Decimal("1"), product.sku, today, expires_at=future)

        assert Stock.release_expired() == 1

        assert Hold.objects.get(pk=int(expired_id.split(":")[1])).status == HoldStatus.RELEASED
        assert Hold.objects.get(pk=int(live_id.split(":")[1])).status == HoldStatus.PENDING
        assert Stock.available(product.sku, today) == Decimal("4")

    def test_fulfill_requires_confirmation(self, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)
        hold_id = Stock.hold(Decimal("1"), product.sku, today)

        with pytest.raises(StockError) as exc:
            Stock.fulfill(hold_id)

        assert exc.value.code == "INVALID_STATUS"


@pytest.mark.django_db
class TestQueryVerbs:
    def test_available_demand_and_committed(self, demand_product, product, vitrine, today):
        Stock.receive(Decimal("5"), product.sku, vitrine)
        Stock.hold(Decimal("2"), product.sku, today)
        Stock.hold(Decimal("3"), demand_product, today)

        assert Stock.available(product.sku, today) == Decimal("3")
        assert Stock.committed(product.sku, today) == Decimal("2")
        assert Stock.demand(demand_product, today) == Decimal("3")

    def test_unknown_sku_reads_as_zero_not_as_unlimited(self, today):
        assert Stock.available(SimpleNamespace(sku="NINGUEM"), today) == Decimal("0")
