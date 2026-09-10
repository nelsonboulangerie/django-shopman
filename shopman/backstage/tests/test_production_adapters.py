from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from shopman.craftsman import craft
from shopman.craftsman.contrib.formula import accept_suggestion
from shopman.craftsman.contrib.stockman.production import CraftsmanProductionBackend
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Position
from shopman.stockman.protocols.production import ProductionPriority, ProductionRequest

from shopman.backstage.models import OvenRun


@pytest.fixture
def production_position(db):
    return Position.objects.create(
        ref="producao-adapter",
        name="Produção adapters",
        is_default=True,
    )


@pytest.fixture
def recipe(db, production_position):
    return Recipe.objects.create(
        ref="adapter-croissant-v1",
        name="Croissant adapters",
        output_sku="ADAPTER-CROISSANT",
        batch_size=Decimal("10"),
    )


def _formula_basis(recipe: Recipe, *, available: bool = True) -> dict:
    shortages = (
        []
        if available
        else [
            {
                "sku": "FARINHA",
                "needed": "5",
                "available": "1",
                "shortage": "4",
            }
        ]
    )
    return {
        "calculation_ref": "formula:2026-09-09:croissant",
        "recipe_ref": recipe.ref,
        "rounded_quantity": "10",
        "material_availability": {
            "all_available": available,
            "shortages": shortages,
            "status": "available" if available else "short",
        },
    }


@pytest.mark.django_db
def test_formula_accept_replays_and_persists_explicit_basis(recipe):
    request = {
        "recipe_ref": recipe.ref,
        "target_date": date.today(),
        "quantity": "10",
        "actor": "formula:ana",
        "basis": _formula_basis(recipe),
        "idempotency_key": "formula-accept-42",
    }

    first = accept_suggestion(**request)
    replay = accept_suggestion(**request)

    assert replay.pk == first.pk
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1
    first.refresh_from_db()
    assert first.source_ref == "formula:suggestion"
    assert first.meta["formula_basis"] == {
        **_formula_basis(recipe),
        "accepted_quantity": "10",
    }
    assert (
        WorkOrderEvent.objects.filter(
            work_order=first,
            idempotency_key="production.plan:formula:formula-accept-42",
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_formula_distinct_attempts_create_distinct_batches_in_the_same_cell(recipe):
    common = {
        "recipe_ref": recipe.ref,
        "target_date": date.today(),
        "quantity": "10",
        "actor": "formula:ana",
        "basis": _formula_basis(recipe),
    }

    first = accept_suggestion(**common, idempotency_key="formula-batch-a")
    second = accept_suggestion(**common, idempotency_key="formula-batch-b")

    assert first.pk != second.pk
    assert WorkOrder.objects.filter(recipe=recipe).count() == 2


@pytest.mark.django_db
def test_formula_accept_requires_an_origin_attempt_key(recipe):
    with pytest.raises(TypeError, match="idempotency_key"):
        accept_suggestion(
            recipe_ref=recipe.ref,
            target_date=date.today(),
            quantity="10",
            actor="formula:ana",
            basis=_formula_basis(recipe),
        )

    assert not WorkOrder.objects.filter(recipe=recipe).exists()


@pytest.mark.django_db
def test_formula_shortage_override_remains_blocked_until_d1_policy(recipe):
    request = {
        "recipe_ref": recipe.ref,
        "target_date": date.today(),
        "quantity": "10",
        "actor": "formula:supervisor",
        "basis": _formula_basis(recipe, available=False),
        "allow_shortage": True,
        "idempotency_key": "formula-shortage-gated",
    }

    with pytest.raises(CraftError) as missing_reason:
        accept_suggestion(**request)
    assert missing_reason.value.code == "FORMULA_OVERRIDE_REASON_REQUIRED"

    with pytest.raises(CraftError) as unauthorized:
        accept_suggestion(**request, override_reason="Compra emergencial confirmada")
    assert unauthorized.value.code == "FORMULA_OVERRIDE_POLICY_PENDING"

    with pytest.raises(CraftError) as self_declared:
        accept_suggestion(
            **request,
            override_reason="Compra emergencial confirmada",
            override_authorized=True,
        )
    assert self_declared.value.code == "FORMULA_OVERRIDE_POLICY_PENDING"
    assert not WorkOrder.objects.filter(recipe=recipe).exists()


def _stocking_request(
    recipe: Recipe,
    *,
    quantity: str = "12",
    reference: str | None = "REORDER-42",
) -> ProductionRequest:
    return ProductionRequest(
        sku=recipe.output_sku,
        quantity=Decimal(quantity),
        target_date=date.today(),
        priority=ProductionPriority.HIGH,
        reference=reference,
        metadata={"trigger": "reorder", "minimum": Decimal("2")},
    )


def test_production_request_rejects_legacy_positional_construction():
    with pytest.raises(TypeError):
        ProductionRequest(
            "SKU",
            Decimal("1"),
            date.today(),
            ProductionPriority.HIGH,
        )


@pytest.mark.django_db
def test_stocking_request_replays_and_cancel_uses_canonical_oven_guard(recipe):
    backend = CraftsmanProductionBackend()

    first = backend.request_production(_stocking_request(recipe))
    replay = backend.request_production(_stocking_request(recipe))

    assert first.success is replay.success is True
    assert replay.request_id == first.request_id
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1
    order = WorkOrder.objects.get(recipe=recipe)
    assert order.meta["stocking_request"] == {
        "sku": recipe.output_sku,
        "quantity": "12",
        "target_date": date.today().isoformat(),
        "priority": "high",
        "reference": "REORDER-42",
        "metadata": {"trigger": "reorder", "minimum": "2"},
    }

    craft.start(order, quantity=order.quantity, expected_rev=order.rev)
    order.refresh_from_db()
    oven_run = OvenRun.objects.create(
        work_order_ref=order.ref,
        oven_ref=order.position_ref,
        operator_ref="stocking:test",
        planned_seconds=600,
    )

    cancelled = backend.cancel_request(first.request_id, reason="Demanda cancelada")
    retried = backend.cancel_request(first.request_id, reason="Demanda cancelada")

    assert cancelled.success is retried.success is True
    order.refresh_from_db()
    oven_run.refresh_from_db()
    assert order.status == WorkOrder.Status.VOID
    assert oven_run.status == "abandoned"
    assert (
        WorkOrderEvent.objects.filter(
            work_order=order,
            kind=WorkOrderEvent.Kind.VOIDED,
        ).count()
        == 1
    )
    assert (
        WorkOrderEvent.objects.filter(
            work_order=order,
            kind=WorkOrderEvent.Kind.OVEN_ABANDONED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_distinct_stocking_references_create_distinct_batches_in_same_cell(recipe):
    backend = CraftsmanProductionBackend()

    first = backend.request_production(_stocking_request(recipe, reference="REORDER-A"))
    second = backend.request_production(_stocking_request(recipe, reference="REORDER-B"))

    assert first.success is second.success is True
    assert first.request_id != second.request_id
    assert WorkOrder.objects.filter(recipe=recipe).count() == 2


@pytest.mark.django_db
def test_stocking_request_without_origin_reference_fails_closed(recipe):
    result = CraftsmanProductionBackend().request_production(_stocking_request(recipe, reference=None))

    assert result.success is False
    assert "referência única" in result.message
    assert not WorkOrder.objects.filter(recipe=recipe).exists()


@pytest.mark.django_db
def test_stocking_simple_request_requires_and_uses_attempt_reference(recipe):
    result = CraftsmanProductionBackend().request_production_simple(
        recipe.output_sku,
        Decimal("12"),
        reference="SIMPLE-REORDER-1",
    )

    assert result.success is True
    assert WorkOrder.objects.filter(recipe=recipe).count() == 1


@pytest.mark.django_db
def test_stocking_request_cannot_bypass_linked_order_coverage(recipe):
    order = Order.objects.create(
        ref="STOCKING-LINKED-ORDER",
        channel_ref="web",
        status=Order.Status.ACCEPTED,
        total_q=1000,
        data={"target_date": date.today().isoformat()},
    )
    OrderItem.objects.create(
        order=order,
        line_id="linked-1",
        sku=recipe.output_sku,
        name=recipe.name,
        qty=Decimal("10"),
        unit_price_q=100,
        line_total_q=1000,
    )

    result = CraftsmanProductionBackend().request_production(_stocking_request(recipe, quantity="5"))

    assert result.success is False
    assert not WorkOrder.objects.filter(recipe=recipe).exists()


def test_stockman_public_adapter_has_no_alternate_writer(monkeypatch):
    from shopman.stockman.adapters import production as legacy

    source = Path(legacy.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"plan", "schedule", "void"}
    ]
    assert forbidden_calls == []

    sentinel = object()

    class Canonical:
        def request_production(self, request):
            assert request is sentinel
            return "delegated"

    monkeypatch.setattr(legacy, "_craftsman_available", lambda: True)
    monkeypatch.setattr(
        legacy.ProductionBackend,
        "_canonical_backend",
        staticmethod(lambda: Canonical()),
    )
    assert legacy.ProductionBackend().request_production(sentinel) == "delegated"
