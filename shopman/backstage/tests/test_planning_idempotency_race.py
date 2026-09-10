"""PostgreSQL proof for globally unique production planning attempts."""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import close_old_connections, connection
from shopman.craftsman import craft
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.orderman.models import IdempotencyKey

from shopman.backstage.models import OvenRun
from shopman.backstage.services.exceptions import ProductionConflict
from shopman.backstage.services.production import apply_oven_arm, apply_oven_conclude
from shopman.shop.services.production import (
    PLANNING_RECEIPT_SCOPE,
    set_planned_quantity,
)

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="SELECT FOR UPDATE and unique-insert contention require PostgreSQL",
)


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_same_attempt_key_cannot_mutate_two_recipes_concurrently():
    recipes = [
        Recipe.objects.create(
            ref=f"pg-planning-race-{slot}",
            name=f"Race {slot}",
            output_sku=f"PG-RACE-{slot}",
            batch_size=Decimal("10"),
        )
        for slot in (1, 2)
    ]
    attempt_key = "production.plan:pg-cross-recipe-race"
    barrier = threading.Barrier(2, timeout=10)
    outcomes: list[tuple[str, str]] = []

    def plan(recipe_id: int, quantity: str) -> None:
        close_old_connections()
        try:
            barrier.wait()
            result = set_planned_quantity(
                recipe_id=recipe_id,
                quantity=quantity,
                target_date_value=date.today().isoformat(),
                position_ref="production",
                actor="production:race",
                expected_rev=None,
                idempotency_key=attempt_key,
            )
            outcomes.append(("accepted", result[1]))
        except CraftError as exc:
            outcomes.append(("rejected", exc.code))
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=plan, args=(recipes[0].pk, "10")),
        threading.Thread(target=plan, args=(recipes[1].pk, "20")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(kind for kind, _ in outcomes) == ["accepted", "rejected"]
    assert next(value for kind, value in outcomes if kind == "rejected") == ("IDEMPOTENCY_CONFLICT")
    assert WorkOrder.objects.filter(recipe__in=recipes).count() == 1
    receipt = IdempotencyKey.objects.get(
        scope=PLANNING_RECEIPT_SCOPE,
        key=attempt_key,
    )
    assert receipt.status == "done"


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_two_initial_edits_of_the_same_cell_create_only_one_work_order():
    recipe = Recipe.objects.create(
        ref="pg-planning-cell-race",
        name="Cell race",
        output_sku="PG-CELL-RACE",
        batch_size=Decimal("10"),
    )
    barrier = threading.Barrier(2, timeout=10)
    outcomes: list[tuple[str, str]] = []

    def plan(slot: int, quantity: str) -> None:
        close_old_connections()
        try:
            barrier.wait()
            result = set_planned_quantity(
                recipe_id=recipe.pk,
                quantity=quantity,
                target_date_value=date.today().isoformat(),
                position_ref="production",
                actor=f"production:tablet-{slot}",
                expected_rev=None,
                idempotency_key=f"production.plan:pg-cell-race-{slot}",
            )
            outcomes.append(("accepted", result[1]))
        except CraftError as exc:
            outcomes.append(("rejected", exc.code))
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=plan, args=(1, "10")),
        threading.Thread(target=plan, args=(2, "20")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(kind for kind, _ in outcomes) == ["accepted", "rejected"]
    assert next(value for kind, value in outcomes if kind == "rejected") == ("STALE_REVISION")
    work_order = WorkOrder.objects.get(recipe=recipe)
    assert work_order.quantity in (Decimal("10"), Decimal("20"))
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.PLANNED,
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
@requires_postgres
def test_two_tablets_cannot_duplicate_oven_arm_or_conclude():
    recipe = Recipe.objects.create(
        ref="pg-oven-fact-race",
        name="Oven fact race",
        output_sku="PG-OVEN-RACE",
        batch_size=Decimal("10"),
    )
    work_order = craft.start(
        craft.plan(
            recipe,
            Decimal("10"),
            date=date.today(),
            position_ref="pg-oven",
        ),
        quantity=Decimal("10"),
        position_ref="pg-oven",
    )

    def race(operation, *, expected_rev: int, key_prefix: str):
        barrier = threading.Barrier(2, timeout=10)
        outcomes: list[tuple[str, str]] = []

        def mutate(slot: int) -> None:
            close_old_connections()
            try:
                barrier.wait()
                operation(
                    work_order_id=work_order.pk,
                    actor=f"production:tablet-{slot}",
                    expected_rev=expected_rev,
                    idempotency_key=f"{key_prefix}-{slot}",
                )
                outcomes.append(("accepted", str(slot)))
            except ProductionConflict as exc:
                outcomes.append(("rejected", str(exc.data.get("cause") or "")))
            finally:
                close_old_connections()

        threads = [threading.Thread(target=mutate, args=(slot,)) for slot in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert all(not thread.is_alive() for thread in threads)
        return outcomes

    arm_outcomes = race(
        lambda **kwargs: apply_oven_arm(planned_seconds=600, **kwargs),
        expected_rev=work_order.rev,
        key_prefix="pg-arm",
    )
    assert sorted(kind for kind, _ in arm_outcomes) == ["accepted", "rejected"]
    assert next(value for kind, value in arm_outcomes if kind == "rejected") == ("stale_revision")
    assert OvenRun.objects.filter(work_order_ref=work_order.ref, status="open").count() == 1
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.OVEN_ARMED,
        ).count()
        == 1
    )

    work_order.refresh_from_db()
    conclude_outcomes = race(
        apply_oven_conclude,
        expected_rev=work_order.rev,
        key_prefix="pg-conclude",
    )
    assert sorted(kind for kind, _ in conclude_outcomes) == ["accepted", "rejected"]
    assert next(value for kind, value in conclude_outcomes if kind == "rejected") == "stale_revision"
    assert (
        OvenRun.objects.filter(
            work_order_ref=work_order.ref,
            status="concluded",
        ).count()
        == 1
    )
    assert (
        WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
        ).count()
        == 1
    )
