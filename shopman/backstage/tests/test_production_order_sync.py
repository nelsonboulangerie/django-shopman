from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from itertools import count

import pytest
from django.core.management import call_command
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Position

from shopman.backstage.projections.order_queue import build_operator_order
from shopman.backstage.projections.production import build_work_order_card
from shopman.backstage.services.exceptions import ProductionConflict
from shopman.backstage.services.production import (
    ProductionOrderShortError,
    production_shortage_snapshot,
)
from shopman.backstage.services.production import (
    apply_finish as _raw_apply_finish,
)
from shopman.backstage.services.production import (
    apply_planned as _raw_apply_planned,
)
from shopman.backstage.services.production import (
    apply_quick_finish as _raw_apply_quick_finish,
)
from shopman.backstage.services.production import (
    apply_start as _raw_apply_start,
)
from shopman.shop.handlers import production_order_sync
from shopman.shop.handlers.production_order_sync import (
    ORDER_PRODUCTION_WO_REFS_KEY,
    WORK_ORDER_COMMITTED_ORDER_REFS_KEY,
    link_order_to_work_orders,
    link_work_order_to_orders,
    order_requirement_for_work_order,
    reconcile_production_order_links,
)
from shopman.shop.models import Shop

_attempts = count(1)


def _work_order_attempt(work_order_id, kwargs, action: str):
    enriched = dict(kwargs)
    if "expected_rev" not in enriched:
        enriched["expected_rev"] = WorkOrder.objects.values_list("rev", flat=True).get(pk=work_order_id)
    enriched.setdefault("idempotency_key", f"test-sync-{action}-{next(_attempts)}")
    return enriched


def apply_start(*, work_order_id, **kwargs):
    return _raw_apply_start(
        work_order_id=work_order_id,
        **_work_order_attempt(work_order_id, kwargs, "start"),
    )


def apply_finish(*, work_order_id, **kwargs):
    return _raw_apply_finish(
        work_order_id=work_order_id,
        **_work_order_attempt(work_order_id, kwargs, "finish"),
    )


def apply_planned(**kwargs):
    body = dict(kwargs)
    body.setdefault("idempotency_key", f"test-sync-plan-{next(_attempts)}")
    return _raw_apply_planned(**body)


def apply_quick_finish(**kwargs):
    body = dict(kwargs)
    body.setdefault("idempotency_key", f"test-sync-quick-{next(_attempts)}")
    return _raw_apply_quick_finish(**body)


def _five_saleable_and_five_lost() -> list[dict[str, object]]:
    """QC KISS: total da fornada, uma saída vendável e um único déficit explicado."""
    return [
        {"quantity": "5", "quality_grade_ref": "standard"},
        {
            "quantity": "5",
            "quality_defect_ref": "overbaked",
            "loss": True,
        },
    ]


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="sync-croissant",
        name="Croissant",
        output_sku="CROISSANT",
        batch_size=Decimal("10"),
    )


def _order(ref: str, sku: str = "CROISSANT", qty: int = 2, status: str = "accepted") -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=1000, data={"target_date": date.today().isoformat()}
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku=sku, name=sku, qty=qty, unit_price_q=500, line_total_q=1000
    )
    return order


@pytest.mark.django_db
def test_confirmed_order_links_existing_planned_work_order(recipe):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="")
    order = _order("SYNC-ORD-1")

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    wo.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [wo.ref]
    assert wo.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]


@pytest.mark.django_db
def test_operator_order_projects_gift_recipient():
    """GIFT-UX: o operador vê o destinatário do presente (entrega a terceiro)."""
    order = _order("GIFT-OP-1")
    order.data = {
        **order.data,
        "is_gift": True,
        "recipient": {"name": "Maria Silva", "phone": "+5543988887777"},
        "gift_message": "Feliz aniversário!",
        "gift_hide_values": True,
    }
    order.save(update_fields=["data", "updated_at"])

    detail = build_operator_order(order)

    assert detail.is_gift is True
    assert detail.gift_recipient_name == "Maria Silva"
    assert detail.gift_recipient_phone == "+5543988887777"
    assert detail.gift_message == "Feliz aniversário!"
    assert detail.gift_hide_values is True


@pytest.mark.django_db
def test_operator_order_non_gift_has_empty_gift_fields():
    detail = build_operator_order(_order("GIFT-OP-2"))
    assert detail.is_gift is False
    assert detail.gift_recipient_name == ""
    assert detail.gift_hide_values is False


@pytest.mark.django_db
def test_order_without_produced_recipe_does_not_link(recipe):
    order = _order("SYNC-ORD-2", sku="AGUA")

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data


@pytest.mark.django_db
def test_finished_work_order_progress_is_projected_for_order(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    craft.start(wo, quantity=10, expected_rev=0)
    craft.finish(wo, finished=8, actor="test")
    order = _order("SYNC-ORD-3")
    order.data = {"awaiting_wo_refs": [wo.ref]}
    order.save(update_fields=["data", "updated_at"])

    detail = build_operator_order(order)

    assert detail.awaiting_work_orders[0].ref == wo.ref
    assert detail.awaiting_work_orders[0].progress_pct == 80


@pytest.mark.django_db
def test_work_order_card_projects_committed_item_quantity(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    first = _order("SYNC-ORD-4", qty=3)
    second = _order("SYNC-ORD-4B", qty=10)
    wo.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [first.ref, second.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    card = build_work_order_card(wo.ref)

    assert card.committed_qty == "13"
    assert [item.ref for item in card.order_commitments] == [first.ref, second.ref]
    assert [item.qty_required for item in card.order_commitments] == ["3", "10"]


@pytest.mark.django_db
def test_work_order_void_removes_bidirectional_refs(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-ORD-5")
    order.data = {"awaiting_wo_refs": [wo.ref]}
    order.save(update_fields=["data", "updated_at"])
    wo.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    craft.void(wo, reason="sem demanda", expected_rev=wo.rev)
    link_work_order_to_orders(action="voided", work_order=wo)

    order.refresh_from_db()
    wo.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in wo.meta


@pytest.mark.django_db
def test_earliest_target_strategy_prefers_older_work_order(recipe):
    Shop.objects.create(name="Loja", defaults={"production": {"order_match": "earliest_target"}})
    newer = craft.plan(recipe, 10, date=date.today())
    older = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
    order = _order("SYNC-ORD-6")

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [older.ref]
    assert newer.ref not in order.data["awaiting_wo_refs"]


@pytest.mark.django_db
def test_order_requirement_sums_linked_order_items(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    first = _order("SYNC-ORD-7", qty=2)
    second = _order("SYNC-ORD-8", qty=4)
    wo.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [first.ref, second.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    assert order_requirement_for_work_order(wo) == Decimal("6")


@pytest.mark.django_db
def test_inactive_order_is_unlinked_and_no_longer_counts_as_requirement(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-CANCELLED", qty=8)
    order.data = {**order.data, "awaiting_wo_refs": [wo.ref, "WO-MISSING"]}
    order.save(update_fields=["data", "updated_at"])
    wo.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    wo.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in wo.meta
    assert order_requirement_for_work_order(wo) == Decimal("0")


@pytest.mark.django_db
def test_finished_work_order_leaves_pending_queue_but_preserves_lineage(recipe):
    wo = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-FINISHED", qty=8)
    order.data = {**order.data, "awaiting_wo_refs": [wo.ref]}
    order.save(update_fields=["data", "updated_at"])
    wo.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    craft.start(wo, quantity=10, expected_rev=wo.rev)
    craft.finish(wo, finished=10, actor="test")
    link_work_order_to_orders(action="finished", work_order=wo)

    order.refresh_from_db()
    wo.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data
    assert order.data[ORDER_PRODUCTION_WO_REFS_KEY] == [wo.ref]
    assert wo.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]


@pytest.mark.django_db
def test_finished_work_order_does_not_requeue_fulfilled_order_on_fallback(recipe):
    fulfilled = craft.plan(recipe, 10, date=date.today())
    fallback = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-FINISHED-NO-FALLBACK", qty=8)
    link_order_to_work_orders(order=order, event_type="status_changed")
    order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [fulfilled.ref]

    craft.start(fulfilled, quantity=10, expected_rev=fulfilled.rev)
    craft.finish(fulfilled, finished=10, actor="test")
    link_work_order_to_orders(action="finished", work_order=fulfilled)

    order.refresh_from_db()
    fallback.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data
    assert order.data[ORDER_PRODUCTION_WO_REFS_KEY] == [fulfilled.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in fallback.meta


@pytest.mark.django_db
def test_finish_fails_closed_when_saleable_output_does_not_cover_orders(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    fallback = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-FINISH-PARTIAL", qty=8)
    link_order_to_work_orders(order=order, event_type="status_changed")
    work_order.refresh_from_db()
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    work_order.refresh_from_db()

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_finish(
            work_order_id=work_order.pk,
            quantity="10",
            partition=_five_saleable_and_five_lost(),
            actor="production:test",
            force=True,
            override_reason="quebra acima do esperado",
            expected_rev=work_order.rev,
            idempotency_key="finish-partial-output",
        )

    assert exc_info.value.allow_override is False
    assert exc_info.value.required == Decimal("8")
    assert exc_info.value.requested == Decimal("5")
    work_order.refresh_from_db()
    fallback.refresh_from_db()
    order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED
    assert fallback.status == WorkOrder.Status.PLANNED
    assert order.data["awaiting_wo_refs"] == [work_order.ref]
    assert ORDER_PRODUCTION_WO_REFS_KEY not in order.data
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in fallback.meta


@pytest.mark.django_db
def test_finish_guard_recovers_when_order_link_callback_was_lost(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    _order("SYNC-FINISH-LOST-LINK", qty=8)
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    work_order.refresh_from_db()
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in work_order.meta

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_finish(
            work_order_id=work_order.pk,
            quantity="10",
            partition=_five_saleable_and_five_lost(),
            actor="production:test",
            expected_rev=work_order.rev,
            idempotency_key="finish-lost-order-link",
        )

    assert exc_info.value.order_refs == ("SYNC-FINISH-LOST-LINK",)
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


@pytest.mark.django_db
def test_finish_guard_accepts_order_side_only_link(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-FINISH-ORDER-SIDE", qty=8)
    order.data = {**order.data, "awaiting_wo_refs": [work_order.ref]}
    order.save(update_fields=["data", "updated_at"])
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    work_order.refresh_from_db()

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_finish(
            work_order_id=work_order.pk,
            quantity="10",
            partition=_five_saleable_and_five_lost(),
            actor="production:test",
            expected_rev=work_order.rev,
            idempotency_key="finish-order-side-link",
        )

    assert exc_info.value.order_refs == (order.ref,)
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.STARTED


@pytest.mark.django_db
def test_start_fails_closed_below_allocated_order_demand(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-START-PARTIAL", qty=8)
    link_order_to_work_orders(order=order, event_type="status_changed")
    work_order.refresh_from_db()

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_start(
            work_order_id=work_order.pk,
            quantity="5",
            actor="production:test",
            expected_rev=work_order.rev,
            idempotency_key="start-partial-demand",
        )

    assert exc_info.value.required == Decimal("8")
    assert exc_info.value.allow_override is False
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_start_normalizes_duplicate_order_ownership_across_work_orders(recipe):
    first = craft.plan(recipe, 10, date=date.today(), position_ref="linha-a")
    second = craft.plan(recipe, 10, date=date.today(), position_ref="linha-b")
    order = _order("SYNC-DUPLICATE-START-OWNER", qty=8)
    order.data = {**order.data, "awaiting_wo_refs": [first.ref, second.ref]}
    order.save(update_fields=["data", "updated_at"])
    for work_order in (first, second):
        work_order.meta = {
            **(work_order.meta or {}),
            WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref],
        }
        work_order.save(update_fields=["meta", "updated_at"])

    apply_start(
        work_order_id=first.pk,
        quantity="10",
        actor="production:test",
        expected_rev=first.rev,
        idempotency_key="normalize-owner-first",
    )
    second.refresh_from_db()
    apply_start(
        work_order_id=second.pk,
        quantity="10",
        actor="production:test",
        expected_rev=second.rev,
        idempotency_key="normalize-owner-second",
    )

    first.refresh_from_db()
    second.refresh_from_db()
    order.refresh_from_db()
    assert first.status == WorkOrder.Status.STARTED
    assert second.status == WorkOrder.Status.STARTED
    assert order.data["awaiting_wo_refs"] == [first.ref]
    assert first.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in second.meta


@pytest.mark.django_db
def test_late_order_uses_fallback_capacity_without_blocking_started_work(recipe):
    Position.objects.create(ref="vitrine-capacity", name="Vitrine", is_saleable=True)
    started = craft.plan(recipe, 10, date=date.today())
    fallback = craft.plan(recipe, 10, date=date.today())
    first = _order("SYNC-CAPACITY-FIRST", qty=8)
    link_order_to_work_orders(order=first, event_type="status_changed")
    started.refresh_from_db()
    apply_start(
        work_order_id=started.pk,
        quantity="10",
        actor="production:test",
        expected_rev=started.rev,
        idempotency_key="start-capacity-first",
    )

    second = _order("SYNC-CAPACITY-SECOND", qty=8)
    link_order_to_work_orders(order=second, event_type="status_changed")

    first.refresh_from_db()
    second.refresh_from_db()
    started.refresh_from_db()
    fallback.refresh_from_db()
    assert first.data["awaiting_wo_refs"] == [started.ref]
    assert second.data["awaiting_wo_refs"] == [fallback.ref]
    assert started.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [first.ref]
    assert fallback.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [second.ref]

    apply_finish(
        work_order_id=started.pk,
        quantity="10",
        actor="production:test",
        expected_rev=started.rev,
        idempotency_key="finish-capacity-first",
    )

    started.refresh_from_db()
    fallback.refresh_from_db()
    second.refresh_from_db()
    assert started.status == WorkOrder.Status.FINISHED
    assert second.data["awaiting_wo_refs"] == [fallback.ref]
    assert fallback.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [second.ref]


@pytest.mark.django_db
def test_finish_persists_lineage_when_post_commit_callback_fails(
    recipe,
    monkeypatch,
):
    Position.objects.create(ref="vitrine-lineage", name="Vitrine", is_saleable=True)
    work_order = craft.plan(recipe, 10, date=date.today())
    fallback = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-FINISH-CALLBACK-FAIL", qty=8)
    apply_start(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="start-before-finish-callback-failure",
    )
    work_order.refresh_from_db()

    def fail_callback(*args, **kwargs):
        raise RuntimeError("injected callback failure")

    monkeypatch.setattr(
        production_order_sync,
        "link_work_order_to_orders",
        fail_callback,
    )
    apply_finish(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="finish-with-callback-failure",
    )

    work_order.refresh_from_db()
    order.refresh_from_db()
    assert work_order.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]
    assert "awaiting_wo_refs" not in order.data
    assert order.data[ORDER_PRODUCTION_WO_REFS_KEY] == [work_order.ref]
    finished = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.FINISHED,
    )
    assert finished.payload["context"]["committed_order_refs"] == [order.ref]

    reconcile_production_order_links(apply=True)

    order.refresh_from_db()
    fallback.refresh_from_db()
    assert "awaiting_wo_refs" not in order.data
    assert order.data[ORDER_PRODUCTION_WO_REFS_KEY] == [work_order.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in fallback.meta


@pytest.mark.django_db
def test_finish_drops_cancelled_order_left_by_a_missed_callback(recipe):
    Position.objects.create(ref="vitrine-cancelled", name="Vitrine", is_saleable=True)
    work_order = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-CANCELLED-CALLBACK-FAIL", qty=8)
    reconcile_production_order_links(apply=True)
    work_order.refresh_from_db()
    order.refresh_from_db()
    assert work_order.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]
    assert order.data["awaiting_wo_refs"] == [work_order.ref]

    apply_start(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="start-before-cancelled-order",
    )
    work_order.refresh_from_db()
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)

    apply_finish(
        work_order_id=work_order.pk,
        quantity="10",
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key="finish-after-cancelled-order",
    )

    work_order.refresh_from_db()
    order.refresh_from_db()
    finished = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.FINISHED,
    )
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in work_order.meta
    assert finished.payload["context"]["committed_order_refs"] == []
    assert ORDER_PRODUCTION_WO_REFS_KEY not in order.data


@pytest.mark.django_db
def test_quick_finish_preserves_the_typed_order_shortage(recipe):
    Position.objects.create(ref="vitrine-quick-order", name="Vitrine", is_saleable=True)
    order = _order("SYNC-QUICK-ORDER-SHORTAGE", qty=10)

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_quick_finish(
            recipe_id=recipe.pk,
            quantity="5",
            position_id=None,
            actor="production:test",
            idempotency_key="quick-order-shortage",
        )

    work_order = WorkOrder.objects.get(recipe=recipe)
    assert exc_info.value.work_order_ref == work_order.ref
    assert exc_info.value.order_refs == (order.ref,)
    assert exc_info.value.required == Decimal("10")
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_reducing_planned_below_linked_orders_requires_force(recipe):
    wo = craft.plan(recipe, 10, date=date.today(), position_ref="", operator_ref="")
    order = _order("SYNC-ORD-9", qty=8)
    wo.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    wo.save(update_fields=["meta", "updated_at"])

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_planned(
            recipe_id=recipe.pk,
            quantity="5",
            target_date_value=date.today().isoformat(),
            position_ref="",
            operator_ref="",
            actor="test",
            idempotency_key="plan-order-shortage-attempt",
        )
    assert "8 un. comprometidas" in str(exc_info.value)
    assert "pedido(s)" not in str(exc_info.value)

    apply_planned(
        recipe_id=recipe.pk,
        quantity="5",
        target_date_value=date.today().isoformat(),
        position_ref="",
        operator_ref="",
        actor="test",
        force=True,
        reason="Manter compromisso parcial autorizado",
        expected_rev=wo.rev,
        idempotency_key="plan-order-shortage-attempt",
        approved_shortage=production_shortage_snapshot(exc_info.value),
    )
    wo.refresh_from_db()
    assert wo.quantity == Decimal("5")
    override = WorkOrderEvent.objects.get(
        work_order=wo,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    )
    assert override.payload["impact"]["order_refs"] == [order.ref]
    assert override.payload["impact"]["required"] == "8"


@pytest.mark.django_db
def test_initial_plan_must_cover_active_orders_or_record_force(recipe):
    order = _order("SYNC-BEFORE-FIRST-WO", qty=10)
    request = {
        "recipe_id": recipe.pk,
        "quantity": "5",
        "target_date_value": date.today().isoformat(),
        "position_ref": "",
        "operator_ref": "",
        "actor": "test",
        "expected_rev": None,
    }

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_planned(**request, idempotency_key="initial-shortage-blocked")
    assert exc_info.value.required == Decimal("10")
    assert not WorkOrder.objects.filter(recipe=recipe).exists()

    _, wo_ref, _, _ = apply_planned(
        **request,
        force=True,
        reason="Primeira fornada parcial autorizada",
        idempotency_key="initial-shortage-blocked",
        approved_shortage=production_shortage_snapshot(exc_info.value),
    )

    work_order = WorkOrder.objects.get(ref=wo_ref)
    override = WorkOrderEvent.objects.get(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    )
    assert override.payload["impact"]["order_refs"] == [order.ref]
    assert override.payload["impact"]["required"] == "10"


@pytest.mark.django_db
def test_multiple_planned_work_orders_require_an_explicit_target(recipe):
    primary = craft.plan(recipe, 10, date=date.today(), position_ref="")
    duplicate = craft.plan(recipe, 10, date=date.today(), position_ref="")
    first = _order("SYNC-CONSOLIDATE-A", qty=8)
    second = _order("SYNC-CONSOLIDATE-B", qty=8)
    primary.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [first.ref]}
    duplicate.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [second.ref]}
    primary.save(update_fields=["meta", "updated_at"])
    duplicate.save(update_fields=["meta", "updated_at"])
    first.data = {**first.data, "awaiting_wo_refs": [primary.ref]}
    second.data = {**second.data, "awaiting_wo_refs": [duplicate.ref]}
    first.save(update_fields=["data", "updated_at"])
    second.save(update_fields=["data", "updated_at"])

    with pytest.raises(ProductionConflict) as exc_info:
        apply_planned(
            recipe_id=recipe.pk,
            quantity="16",
            target_date_value=date.today().isoformat(),
            position_ref="",
            operator_ref="",
            actor="test",
            expected_rev=primary.rev,
            idempotency_key="ambiguous-without-target",
        )
    assert exc_info.value.data["cause"] == "ambiguous_work_order"

    _, kept_ref, _, result = apply_planned(
        recipe_id=recipe.pk,
        quantity="16",
        target_date_value=date.today().isoformat(),
        position_ref="",
        operator_ref="",
        actor="test",
        work_order_id=primary.pk,
        expected_rev=primary.rev,
        idempotency_key="adjust-explicit-primary",
    )

    assert kept_ref == primary.ref
    assert result == "adjusted"
    primary.refresh_from_db()
    duplicate.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert duplicate.status == WorkOrder.Status.PLANNED
    assert primary.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [first.ref]
    assert duplicate.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [second.ref]
    assert first.data["awaiting_wo_refs"] == [primary.ref]
    assert second.data["awaiting_wo_refs"] == [duplicate.ref]


@pytest.mark.django_db
def test_reducing_second_capacity_allocated_work_order_requires_force(recipe):
    primary = craft.plan(recipe, 10, date=date.today(), position_ref="")
    secondary = craft.plan(recipe, 10, date=date.today(), position_ref="")
    first = _order("SYNC-CAPACITY-PLAN-A", qty=8)
    second = _order("SYNC-CAPACITY-PLAN-B", qty=8)
    reconcile_production_order_links(apply=True)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.data["awaiting_wo_refs"] == [primary.ref]
    assert second.data["awaiting_wo_refs"] == [secondary.ref]

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_planned(
            recipe_id=recipe.pk,
            work_order_id=secondary.pk,
            quantity="7",
            target_date_value=date.today().isoformat(),
            actor="production:test",
            expected_rev=secondary.rev,
            idempotency_key="reduce-secondary-without-force",
        )

    assert exc_info.value.order_refs == (second.ref,)
    assert exc_info.value.required == Decimal("8")
    secondary.refresh_from_db()
    assert secondary.quantity == Decimal("10")

    _, work_order_ref, quantity, result = apply_planned(
        recipe_id=recipe.pk,
        work_order_id=secondary.pk,
        quantity="7",
        target_date_value=date.today().isoformat(),
        actor="production:test",
        force=True,
        reason="Produção complementar confirmada",
        expected_rev=secondary.rev,
        idempotency_key="reduce-secondary-without-force",
        approved_shortage=production_shortage_snapshot(exc_info.value),
    )

    assert (work_order_ref, quantity, result) == (
        secondary.ref,
        Decimal("7"),
        "adjusted",
    )
    override = WorkOrderEvent.objects.get(
        work_order=secondary,
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
    )
    assert override.payload["impact"]["order_refs"] == [second.ref]


@pytest.mark.django_db
def test_order_link_reconciler_is_dry_run_by_default_and_idempotent(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-RECONCILE", qty=4)
    order.data = {**order.data, "awaiting_wo_refs": ["WO-MISSING"]}
    order.save(update_fields=["data", "updated_at"])

    dry_run = reconcile_production_order_links()

    assert dry_run["mode"] == "dry-run"
    assert dry_run["work_orders_changed"] == 1
    assert dry_run["orders_changed"] == 1
    assert dry_run["orphan_refs_found"] == 1
    assert dry_run["pending_links_added"] == 1
    assert dry_run["pending_links_removed"] == 1
    order.refresh_from_db()
    work_order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == ["WO-MISSING"]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in work_order.meta

    output = StringIO()
    call_command("reconcile_production_order_links", "--apply", "--all", stdout=output)
    applied = json.loads(output.getvalue())
    assert applied["mode"] == "apply"
    assert applied["work_orders_changed"] == 1
    assert applied["orders_changed"] == 1

    order.refresh_from_db()
    work_order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [work_order.ref]
    assert work_order.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]

    repeated = reconcile_production_order_links(apply=True)
    assert repeated["work_orders_changed"] == 0
    assert repeated["orders_changed"] == 0


@pytest.mark.django_db
def test_reconciler_rejects_one_sided_finished_pending_ref_as_lineage(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    craft.start(work_order, quantity=10, expected_rev=work_order.rev)
    craft.finish(work_order, finished=10, actor="test")
    fallback = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-FINISHED-ASYMMETRIC", qty=4)
    order.data = {**order.data, "awaiting_wo_refs": [work_order.ref]}
    order.save(update_fields=["data", "updated_at"])

    dry_run = reconcile_production_order_links()
    assert dry_run["history_links_added"] == 0
    assert dry_run["ambiguous_finished_pending_refs"] == 1

    reconcile_production_order_links(apply=True)

    order.refresh_from_db()
    work_order.refresh_from_db()
    fallback.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [fallback.ref]
    assert ORDER_PRODUCTION_WO_REFS_KEY not in order.data
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in work_order.meta
    assert fallback.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]


@pytest.mark.django_db
def test_reconciler_does_not_requeue_order_with_finished_lineage(recipe):
    fulfilled = craft.plan(recipe, 10, date=date.today())
    fallback = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-RECONCILE-NO-REQUEUE", qty=4)
    order.data = {
        **order.data,
        ORDER_PRODUCTION_WO_REFS_KEY: [fulfilled.ref],
        "awaiting_wo_refs": [fallback.ref],
    }
    order.save(update_fields=["data", "updated_at"])
    fulfilled.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    fulfilled.save(update_fields=["meta", "updated_at"])
    fallback.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    fallback.save(update_fields=["meta", "updated_at"])
    craft.start(fulfilled, quantity=10, expected_rev=fulfilled.rev)
    craft.finish(fulfilled, finished=10, actor="test")

    report = reconcile_production_order_links(apply=True)

    order.refresh_from_db()
    fallback.refresh_from_db()
    assert report["pending_links_removed"] == 1
    assert "awaiting_wo_refs" not in order.data
    assert order.data[ORDER_PRODUCTION_WO_REFS_KEY] == [fulfilled.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in fallback.meta


@pytest.mark.django_db
def test_finished_lineage_does_not_block_adjusting_uncommitted_open_work(recipe):
    fulfilled = craft.plan(recipe, 10, date=date.today())
    open_work_order = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-PLAN-FINISHED-LINEAGE", qty=8)
    order.data = {
        **order.data,
        ORDER_PRODUCTION_WO_REFS_KEY: [fulfilled.ref],
    }
    order.save(update_fields=["data", "updated_at"])
    fulfilled.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    fulfilled.save(update_fields=["meta", "updated_at"])
    craft.start(fulfilled, quantity=10, expected_rev=fulfilled.rev)
    craft.finish(fulfilled, finished=10, actor="production:test")

    _, work_order_ref, quantity, result = apply_planned(
        recipe_id=recipe.pk,
        work_order_id=open_work_order.pk,
        quantity="1",
        target_date_value=date.today().isoformat(),
        actor="production:test",
        expected_rev=open_work_order.rev,
        idempotency_key="adjust-after-finished-lineage",
    )

    assert (work_order_ref, quantity, result) == (
        open_work_order.ref,
        Decimal("1"),
        "adjusted",
    )


@pytest.mark.django_db
def test_order_link_reconciler_uses_one_eligible_work_order_per_order(recipe):
    future = craft.plan(recipe, 10, date=date.today() + timedelta(days=2))
    earliest = craft.plan(recipe, 10, date=date.today() - timedelta(days=2))
    later = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
    order = _order("SYNC-RECONCILE-DATES", qty=4)

    reconcile_production_order_links(apply=True)

    order.refresh_from_db()
    earliest.refresh_from_db()
    later.refresh_from_db()
    future.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [earliest.ref]
    assert earliest.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in later.meta
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in future.meta


@pytest.mark.django_db
def test_manual_reconciler_repairs_only_existing_explicit_pair(recipe):
    Shop.objects.create(name="Loja", defaults={"production": {"order_match": "manual"}})
    linked = craft.plan(recipe, 10, date=date.today())
    untouched = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-RECONCILE-MANUAL", qty=4)
    linked.meta = {WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [order.ref]}
    linked.save(update_fields=["meta", "updated_at"])

    reconcile_production_order_links(apply=True)

    order.refresh_from_db()
    linked.refresh_from_db()
    untouched.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [linked.ref]
    assert linked.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in untouched.meta


@pytest.mark.django_db
def test_voided_selected_work_order_relinks_order_to_fallback(recipe):
    selected = craft.plan(recipe, 10, date=date.today())
    fallback = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-VOID-FALLBACK", qty=4)
    link_order_to_work_orders(order=order, event_type="status_changed")
    order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [selected.ref]

    craft.void(selected, reason="sem capacidade", expected_rev=selected.rev)
    link_work_order_to_orders(action="voided", work_order=selected)

    order.refresh_from_db()
    fallback.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [fallback.ref]
    assert fallback.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]


@pytest.mark.django_db
def test_retroactive_earliest_work_order_replaces_previous_link(recipe):
    Shop.objects.create(name="Loja", defaults={"production": {"order_match": "earliest_target"}})
    previous = craft.plan(recipe, 10, date=date.today())
    order = _order("SYNC-RETROACTIVE", qty=4)
    order.data = {**order.data, "target_date": (date.today() + timedelta(days=1)).isoformat()}
    order.save(update_fields=["data", "updated_at"])
    link_order_to_work_orders(order=order, event_type="status_changed")

    retroactive = craft.plan(recipe, 10, date=date.today() - timedelta(days=1))
    link_work_order_to_orders(action="planned", work_order=retroactive)

    order.refresh_from_db()
    previous.refresh_from_db()
    retroactive.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [retroactive.ref]
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in previous.meta
    assert retroactive.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]


@pytest.mark.django_db
def test_open_work_order_remains_linkable_after_recipe_deactivation(recipe):
    work_order = craft.plan(recipe, 10, date=date.today())
    recipe.is_active = False
    recipe.save(update_fields=["is_active", "updated_at"])
    order = _order("SYNC-INACTIVE-RECIPE", qty=4)

    link_order_to_work_orders(order=order, event_type="status_changed")

    order.refresh_from_db()
    work_order.refresh_from_db()
    assert order.data["awaiting_wo_refs"] == [work_order.ref]
    assert work_order.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] == [order.ref]


@pytest.mark.django_db
def test_order_shortage_guard_applies_only_to_the_selected_cell(recipe):
    Position.objects.get_or_create(ref="linha-a", defaults={"name": "Linha A"})
    Position.objects.get_or_create(ref="linha-b", defaults={"name": "Linha B"})
    _order("SYNC-CELL-OWNER", qty=8)
    apply_planned(
        recipe_id=recipe.pk,
        quantity="8",
        target_date_value=date.today().isoformat(),
        position_ref="linha-a",
        actor="test",
        expected_rev=None,
        idempotency_key="selected-cell-primary",
    )

    _, second_ref, _, result = apply_planned(
        recipe_id=recipe.pk,
        quantity="1",
        target_date_value=date.today().isoformat(),
        position_ref="linha-b",
        actor="test",
        expected_rev=None,
        idempotency_key="selected-cell-secondary",
    )

    assert second_ref
    assert result == "created"


@pytest.mark.django_db
def test_manual_order_matching_does_not_claim_unlinked_demand(recipe):
    Shop.objects.create(name="Loja", defaults={"production": {"order_match": "manual"}})
    _order("SYNC-MANUAL-UNLINKED", qty=8)

    _, work_order_ref, quantity, result = apply_planned(
        recipe_id=recipe.pk,
        quantity="1",
        target_date_value=date.today().isoformat(),
        actor="test",
        expected_rev=None,
        idempotency_key="manual-unlinked-demand",
    )

    assert work_order_ref
    assert quantity == Decimal("1")
    assert result == "created"


@pytest.mark.django_db
def test_today_work_order_must_cover_order_due_tomorrow(recipe):
    order = _order("SYNC-FUTURE-DEMAND", qty=8)
    order.data = {
        **order.data,
        "delivery_date": (date.today() + timedelta(days=1)).isoformat(),
    }
    order.save(update_fields=["data", "updated_at"])

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_planned(
            recipe_id=recipe.pk,
            quantity="1",
            target_date_value=date.today().isoformat(),
            actor="test",
            expected_rev=None,
            idempotency_key="future-demand-shortage",
        )

    assert exc_info.value.order_refs == (order.ref,)
    assert exc_info.value.required == Decimal("8")


@pytest.mark.django_db
def test_explicit_target_fails_closed_when_order_link_callback_was_lost(recipe):
    work_order = craft.plan(recipe, 10, date=date.today(), position_ref="")
    order = _order("SYNC-LOST-CALLBACK", qty=8)
    assert "awaiting_wo_refs" not in order.data
    assert WORK_ORDER_COMMITTED_ORDER_REFS_KEY not in work_order.meta

    with pytest.raises(ProductionOrderShortError) as exc_info:
        apply_planned(
            recipe_id=recipe.pk,
            work_order_id=work_order.pk,
            quantity="1",
            target_date_value=date.today().isoformat(),
            actor="test",
            expected_rev=work_order.rev,
            idempotency_key="lost-order-link",
        )

    assert exc_info.value.order_refs == (order.ref,)
    work_order.refresh_from_db()
    assert work_order.quantity == Decimal("10")
