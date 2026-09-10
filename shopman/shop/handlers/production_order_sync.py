"""Visual sync between orders and production work orders.

The link is intentionally contextual and denormalized: orders keep
``data["awaiting_wo_refs"]`` and work orders keep
``meta["committed_order_refs"]``. The production and order cores remain
unchanged; Backstage uses these refs to explain operational dependencies.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from shopman.shop.handlers._resilient import resilient_receiver

logger = logging.getLogger(__name__)

ACTIVE_ORDER_STATUSES = ("accepted", "preparing", "ready")
ORDER_AWAITING_WO_REFS_KEY = "awaiting_wo_refs"
WORK_ORDER_COMMITTED_ORDER_REFS_KEY = "committed_order_refs"
ORDER_PRODUCTION_WO_REFS_KEY = "production_wo_refs"


def connect() -> None:
    """Wire order and production lifecycle receivers."""
    from shopman.craftsman.signals import production_changed
    from shopman.orderman.signals import order_changed

    order_changed.connect(
        queue_order_to_work_order_sync,
        dispatch_uid="shopman.shop.handlers.production_order_sync.link_order_to_work_orders",
        weak=False,
    )
    production_changed.connect(
        queue_work_order_to_order_sync,
        dispatch_uid="shopman.shop.handlers.production_order_sync.link_work_order_to_orders",
        weak=False,
    )
    logger.info("shopman.handlers: connected production/order sync receivers.")


def queue_order_to_work_order_sync(
    sender=None,
    order=None,
    event_type: str = "",
    actor: str = "",
    **kwargs,
) -> None:
    """Run cross-aggregate reconciliation only after the Order lock commits."""
    if order is None:
        return
    order_pk = order.pk

    def reconcile() -> None:
        from shopman.orderman.models import Order

        try:
            current = Order.objects.get(pk=order_pk)
            link_order_to_work_orders(
                order=current,
                event_type=event_type,
                actor=actor,
            )
        except Exception:
            logger.exception("production_order_sync.order_failed order_pk=%s", order_pk)

    transaction.on_commit(reconcile)


def queue_work_order_to_order_sync(
    sender=None,
    action: str = "",
    work_order=None,
    **kwargs,
) -> None:
    """Run cross-aggregate reconciliation after the WorkOrder lock commits."""
    if work_order is None:
        return
    work_order_pk = work_order.pk

    def reconcile() -> None:
        from shopman.craftsman.models import WorkOrder

        try:
            current = WorkOrder.objects.get(pk=work_order_pk)
            link_work_order_to_orders(action=action, work_order=current)
        except Exception:
            logger.exception(
                "production_order_sync.work_order_failed work_order_pk=%s action=%s",
                work_order_pk,
                action,
            )

    transaction.on_commit(reconcile)


def link_order_to_work_orders(sender=None, order=None, event_type: str = "", actor: str = "", **kwargs) -> None:
    """Attach a confirmed order to suitable planned/started work orders."""
    if order is None:
        return
    if event_type and event_type not in {"created", "status_changed"}:
        return

    from shopman.orderman.models import Order

    snapshot = Order.objects.prefetch_related("items").get(pk=order.pk)
    _reconcile_pending_links(
        output_skus=_order_skus(snapshot),
        order_ids=(snapshot.pk,),
    )


@resilient_receiver
def link_work_order_to_orders(sender=None, action: str = "", work_order=None, **kwargs) -> None:
    """Attach or detach orders when a work order changes state.

    BLINDADO: um erro aqui não pode derrubar o ``finish`` da fornada. Para o
    ``finished``, a rede de segurança é ``_ensure_order_links_closed`` no caminho
    guardado do finish (irmã de ``_ensure_stock_ledger_closed``): ela reconstrói
    o vínculo — idempotente — no MESMO finish caso este receiver estoure, e no
    replay do operador (que não reemite o sinal). Blindar sem a rede deixaria o
    vínculo órfão; a rede sem blindar deixaria o cosmético derrubar a fornada.
    """
    if work_order is None:
        return

    if action == "voided":
        _unlink_voided_work_order(work_order)
        _reconcile_pending_links(output_skus=(work_order.output_sku,))
        return

    if action == "finished":
        _resolve_finished_work_order(work_order)
        _reconcile_pending_links(output_skus=(work_order.output_sku,))
        return

    if action not in {"planned", "adjusted", "started"}:
        return

    _reconcile_pending_links(output_skus=(work_order.output_sku,))


def link_active_orders_to_work_order(work_order) -> None:
    """Reconcile links for the guarded finish path, idempotently.

    O nome é mantido para a rede de segurança recente do finish. A implementação
    usa o reconciliador canônico incoming e, para uma WO já concluída, move os
    vínculos pendentes para a linhagem antes de recalcular a fila.
    """
    from shopman.craftsman.models import WorkOrder

    if work_order.status == WorkOrder.Status.FINISHED:
        _resolve_finished_work_order(work_order)
    _reconcile_pending_links(output_skus=(work_order.output_sku,))


def _reconcile_pending_links(*, output_skus, order_ids=None) -> None:
    """Recompute affected pending pairs under the WorkOrder → Order lock order."""
    from shopman.craftsman.models import WorkOrder
    from shopman.orderman.models import Order

    skus = tuple(sorted({str(sku) for sku in output_skus if str(sku)}))
    if not skus:
        return

    with transaction.atomic():
        work_orders = list(
            WorkOrder.objects.select_for_update().filter(output_sku__in=skus).prefetch_related("events").order_by("pk")
        )
        pending_work_orders = [
            work_order
            for work_order in work_orders
            if work_order.status in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED)
        ]
        active_order_ids = set(
            Order.objects.filter(
                status__in=ACTIVE_ORDER_STATUSES,
                items__sku__in=skus,
            )
            .values_list("pk", flat=True)
            .distinct()
        )
        relevant_order_ids = active_order_ids | set(order_ids or ())
        orders = list(
            Order.objects.select_for_update().filter(pk__in=relevant_order_ids).prefetch_related("items").order_by("pk")
        )
        work_order_refs = {work_order.ref for work_order in work_orders}
        strategy = _match_strategy()
        active_orders = [order for order in orders if order.status in ACTIVE_ORDER_STATUSES]
        _, desired_work_orders_by_order = _allocate_pending_links(
            orders=active_orders,
            pending_work_orders=pending_work_orders,
            all_work_orders=work_orders,
            strategy=strategy,
        )

        for order in orders:
            current_work_order_refs = list((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or ())
            data = {**(order.data or {})}
            selected_refs = desired_work_orders_by_order.get(order.ref, [])

            for candidate in work_orders:
                if candidate.status == WorkOrder.Status.FINISHED:
                    if candidate.ref in current_work_order_refs and order.ref in _finished_order_refs(candidate):
                        history = list(data.get(ORDER_PRODUCTION_WO_REFS_KEY) or ())
                        if candidate.ref not in history:
                            data[ORDER_PRODUCTION_WO_REFS_KEY] = [
                                *history,
                                candidate.ref,
                            ]
                    continue
                meta = {**(candidate.meta or {})}
                current_order_refs = list(meta.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or ())
                should_link = candidate.ref in selected_refs
                if should_link:
                    updated_order_refs = list(dict.fromkeys([*current_order_refs, order.ref]))
                else:
                    updated_order_refs = [ref for ref in current_order_refs if ref != order.ref]
                if updated_order_refs == current_order_refs:
                    continue
                if updated_order_refs:
                    meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] = updated_order_refs
                else:
                    meta.pop(WORK_ORDER_COMMITTED_ORDER_REFS_KEY, None)
                candidate.meta = meta
                candidate.save(update_fields=["meta", "updated_at"])

            if order.status in ACTIVE_ORDER_STATUSES:
                updated_work_order_refs = [ref for ref in current_work_order_refs if ref not in work_order_refs]
            else:
                updated_work_order_refs = []
            updated_work_order_refs = list(dict.fromkeys([*updated_work_order_refs, *selected_refs]))
            if updated_work_order_refs == current_work_order_refs:
                continue
            if updated_work_order_refs:
                data[ORDER_AWAITING_WO_REFS_KEY] = updated_work_order_refs
            else:
                data.pop(ORDER_AWAITING_WO_REFS_KEY, None)
            order.data = data
            order.save(update_fields=["data", "updated_at"])


def order_requirement_for_work_order(work_order) -> Decimal:
    """Return the total ordered quantity for refs linked to ``work_order``."""
    from shopman.orderman.models import Order

    refs = linked_order_refs(work_order)
    if not refs:
        return Decimal("0")
    total = Decimal("0")
    for order in Order.objects.filter(
        ref__in=refs,
        status__in=ACTIVE_ORDER_STATUSES,
    ).prefetch_related("items"):
        for item in order.items.all():
            if item.sku == work_order.output_sku:
                total += item.qty
    return total


def reconcile_production_order_links(*, apply: bool = False) -> dict[str, Any]:
    """Audit and optionally repair denormalized Order ↔ WorkOrder links.

    Pending links are derived from current active orders and compatible
    planned/started work orders.  Completed production is retained as lineage;
    voided or missing work orders cannot remain in an order's pending queue.
    The write path observes the integration's global WorkOrder → Order lock
    order and is idempotent, making it safe after an ``on_commit`` receiver
    failure.
    """
    from shopman.craftsman.models import WorkOrder
    from shopman.orderman.models import Order

    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "work_orders_scanned": 0,
        "orders_scanned": 0,
        "work_orders_changed": 0,
        "orders_changed": 0,
        "pending_links_added": 0,
        "pending_links_removed": 0,
        "history_links_added": 0,
        "orphan_refs_found": 0,
        "historical_orphans_preserved": 0,
        "ambiguous_finished_pending_refs": 0,
    }

    with transaction.atomic():
        work_order_qs = WorkOrder.objects.prefetch_related("events").order_by("pk")
        order_qs = Order.objects.prefetch_related("items").order_by("pk")
        if apply:
            work_order_qs = work_order_qs.select_for_update()
            order_qs = order_qs.select_for_update()

        # Materialize in the declared global lock order.
        work_orders = list(work_order_qs)
        orders = list(order_qs)
        report["work_orders_scanned"] = len(work_orders)
        report["orders_scanned"] = len(orders)

        work_orders_by_ref = {work_order.ref: work_order for work_order in work_orders}
        orders_by_ref = {order.ref: order for order in orders}
        pending_work_orders = [
            work_order
            for work_order in work_orders
            if work_order.status in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED)
        ]
        active_orders = [order for order in orders if order.status in ACTIVE_ORDER_STATUSES]

        work_order_pending_edges = {
            (work_order.ref, order_ref)
            for work_order in work_orders
            if work_order.status != WorkOrder.Status.FINISHED
            for order_ref in linked_order_refs(work_order)
        }
        order_pending_edges = {
            (work_order_ref, order.ref)
            for order in orders
            for work_order_ref in ((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or ())
        }
        pending_orphans = {
            edge
            for edge in work_order_pending_edges | order_pending_edges
            if edge[0] not in work_orders_by_ref or edge[1] not in orders_by_ref
        }
        report["orphan_refs_found"] = len(pending_orphans)

        strategy = _match_strategy()
        desired_orders_by_work_order, desired_work_orders_by_order = _allocate_pending_links(
            orders=active_orders,
            pending_work_orders=pending_work_orders,
            all_work_orders=work_orders,
            strategy=strategy,
        )

        desired_pending_edges = {
            (work_order_ref, order_ref)
            for work_order_ref, order_refs in desired_orders_by_work_order.items()
            for order_ref in order_refs
        }
        complete_pending_edges = work_order_pending_edges & order_pending_edges
        report["pending_links_added"] = len(desired_pending_edges - complete_pending_edges)
        report["pending_links_removed"] = len((work_order_pending_edges | order_pending_edges) - desired_pending_edges)

        work_order_history_edges = {
            (work_order.ref, order_ref)
            for work_order in work_orders
            if work_order.status == WorkOrder.Status.FINISHED
            for order_ref in _finished_order_refs(work_order)
        }
        order_history_edges = {
            (work_order_ref, order.ref)
            for order in orders
            for work_order_ref in ((order.data or {}).get(ORDER_PRODUCTION_WO_REFS_KEY) or ())
        }
        ambiguous_finished_pending_edges = {
            edge
            for edge in order_pending_edges
            if edge[0] in work_orders_by_ref
            and work_orders_by_ref[edge[0]].status == WorkOrder.Status.FINISHED
            and edge not in work_order_history_edges
        }
        report["ambiguous_finished_pending_refs"] = len(ambiguous_finished_pending_edges)
        valid_history_edges = {
            edge
            for edge in (work_order_history_edges | order_history_edges)
            if edge[0] in work_orders_by_ref
            and edge[1] in orders_by_ref
            and work_orders_by_ref[edge[0]].status == WorkOrder.Status.FINISHED
        }
        report["history_links_added"] = len(valid_history_edges - (work_order_history_edges & order_history_edges))
        report["historical_orphans_preserved"] = len(
            (work_order_history_edges | order_history_edges) - valid_history_edges
        )

        historical_orders_by_work_order: dict[str, list[str]] = {}
        historical_work_orders_by_order: dict[str, list[str]] = {}
        for work_order_ref, order_ref in sorted(valid_history_edges):
            historical_orders_by_work_order.setdefault(work_order_ref, []).append(order_ref)
            historical_work_orders_by_order.setdefault(order_ref, []).append(work_order_ref)

        for work_order in work_orders:
            meta = {**(work_order.meta or {})}
            current_refs = list(meta.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or ())

            if work_order.status in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED):
                desired_refs = desired_orders_by_work_order.get(work_order.ref, [])
            elif work_order.status == WorkOrder.Status.VOID:
                desired_refs = []
            else:
                # Finished lineage is append-only.  Preserve even an unresolved
                # historical ref, report it, and repair the opposite side when
                # the referenced record still exists.
                desired_refs = [
                    *current_refs,
                    *historical_orders_by_work_order.get(work_order.ref, []),
                ]

            desired_refs = list(dict.fromkeys(desired_refs))
            if desired_refs == current_refs:
                continue
            report["work_orders_changed"] += 1
            if apply:
                if desired_refs:
                    meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] = desired_refs
                else:
                    meta.pop(WORK_ORDER_COMMITTED_ORDER_REFS_KEY, None)
                work_order.meta = meta
                work_order.save(update_fields=["meta", "updated_at"])

        for order in orders:
            data = {**(order.data or {})}
            current_pending = list(data.get(ORDER_AWAITING_WO_REFS_KEY) or ())
            desired_pending = desired_work_orders_by_order.get(order.ref, [])
            desired_pending = list(dict.fromkeys(desired_pending))

            current_history = list(data.get(ORDER_PRODUCTION_WO_REFS_KEY) or ())
            completed_refs = historical_work_orders_by_order.get(order.ref, [])
            desired_history = list(dict.fromkeys([*current_history, *completed_refs]))

            if desired_pending == current_pending and desired_history == current_history:
                continue
            report["orders_changed"] += 1
            if apply:
                if desired_pending:
                    data[ORDER_AWAITING_WO_REFS_KEY] = desired_pending
                else:
                    data.pop(ORDER_AWAITING_WO_REFS_KEY, None)
                if desired_history:
                    data[ORDER_PRODUCTION_WO_REFS_KEY] = desired_history
                order.data = data
                order.save(update_fields=["data", "updated_at"])

    return report


def linked_order_refs(work_order) -> tuple[str, ...]:
    return tuple(dict.fromkeys((work_order.meta or {}).get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or ()))


def _finished_order_refs(work_order) -> tuple[str, ...]:
    """Return append-only order lineage frozen when the work order finished."""
    from shopman.craftsman.models import WorkOrderEvent

    refs = list(linked_order_refs(work_order))
    cached = getattr(work_order, "_prefetched_objects_cache", {}).get("events")
    events = cached if cached is not None else work_order.events.all()
    finished = max(
        (event for event in events if event.kind == WorkOrderEvent.Kind.FINISHED),
        key=lambda event: event.seq,
        default=None,
    )
    if finished is not None:
        context = finished.payload.get("context") or {}
        refs.extend(context.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or ())
    return tuple(dict.fromkeys(refs))


def _fulfilled_order_skus(order, work_orders) -> set[str]:
    """Return SKUs with finished lineage for this order.

    Only append-only lineage is accepted as evidence. A pending reference alone
    cannot retroactively claim output from an already-finished work order.
    """
    from shopman.craftsman.models import WorkOrder

    data = order.data or {}
    order_lineage_refs = set(data.get(ORDER_PRODUCTION_WO_REFS_KEY) or ())
    return {
        work_order.output_sku
        for work_order in work_orders
        if work_order.status == WorkOrder.Status.FINISHED
        and (work_order.ref in order_lineage_refs or order.ref in _finished_order_refs(work_order))
    }


def _allocate_pending_links(
    *,
    orders,
    pending_work_orders,
    all_work_orders,
    strategy: str,
    operational_quantities: dict[str, Decimal] | None = None,
    preserve_existing: bool = False,
    preferred_work_order_ref: str = "",
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Allocate each active order/SKU to one WO without overcommitting it."""
    desired_orders_by_work_order: dict[str, list[str]] = {work_order.ref: [] for work_order in pending_work_orders}
    desired_work_orders_by_order: dict[str, list[str]] = {order.ref: [] for order in orders}
    fulfilled_order_skus = {
        (order.ref, sku) for order in orders for sku in _fulfilled_order_skus(order, all_work_orders)
    }

    if strategy == "manual":
        for work_order in pending_work_orders:
            work_order_refs = set(linked_order_refs(work_order))
            for order in orders:
                if (order.ref, work_order.output_sku) in fulfilled_order_skus:
                    continue
                order_refs = set((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or ())
                if order.ref not in work_order_refs and work_order.ref not in order_refs:
                    continue
                if not _compatible_order_work_order(order, work_order):
                    continue
                desired_orders_by_work_order[work_order.ref].append(order.ref)
                desired_work_orders_by_order[order.ref].append(work_order.ref)
        return desired_orders_by_work_order, desired_work_orders_by_order

    pending_by_sku: dict[str, list] = {}
    remaining: dict[int, Decimal] = {}
    quantity_overrides = operational_quantities or {}
    for work_order in pending_work_orders:
        pending_by_sku.setdefault(work_order.output_sku, []).append(work_order)
        if work_order.ref in quantity_overrides:
            operational_quantity = quantity_overrides[work_order.ref]
        else:
            operational_quantity = _work_order_operational_quantity(work_order)
        remaining[work_order.pk] = Decimal(str(operational_quantity))

    for order in sorted(
        orders,
        key=lambda candidate: (
            _target_date(candidate),
            candidate.created_at,
            candidate.pk,
        ),
    ):
        for sku in _order_skus(order):
            if (order.ref, sku) in fulfilled_order_skus:
                continue
            required = _order_sku_quantity(order, sku)
            if required <= 0:
                continue
            candidates = _ordered_candidate_work_orders(
                pending_by_sku.get(sku, []),
                target_date=_target_date(order),
                strategy=strategy,
            )
            if preserve_existing:
                order_refs = set((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or ())
                explicit = [
                    candidate
                    for candidate in candidates
                    if candidate.ref in order_refs or order.ref in linked_order_refs(candidate)
                ]
                if preferred_work_order_ref:
                    explicit.sort(key=lambda candidate: candidate.ref != preferred_work_order_ref)
                if explicit:
                    candidate = explicit[0]
                    desired_orders_by_work_order[candidate.ref].append(order.ref)
                    desired_work_orders_by_order[order.ref].append(candidate.ref)
                    remaining[candidate.pk] -= required
                    continue
            for candidate in candidates:
                if remaining[candidate.pk] < required:
                    continue
                desired_orders_by_work_order[candidate.ref].append(order.ref)
                desired_work_orders_by_order[order.ref].append(candidate.ref)
                remaining[candidate.pk] -= required
                break

    return desired_orders_by_work_order, desired_work_orders_by_order


def _order_sku_quantity(order, sku: str) -> Decimal:
    return sum(
        (item.qty for item in order.items.all() if item.sku == sku),
        Decimal("0"),
    )


def _work_order_operational_quantity(work_order) -> Decimal:
    from shopman.craftsman.models import WorkOrderEvent

    if work_order.status == work_order.Status.PLANNED:
        return Decimal(str(work_order.quantity))
    cached = getattr(work_order, "_prefetched_objects_cache", {}).get("events")
    events = cached if cached is not None else work_order.events.all()
    started = max(
        (event for event in events if event.kind == WorkOrderEvent.Kind.STARTED),
        key=lambda event: event.seq,
        default=None,
    )
    if started is None:
        return Decimal(str(work_order.quantity))
    return Decimal(str(started.payload.get("quantity") or "0"))


def _append_order_work_order_link(order, work_order) -> bool:
    order_refs = list((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or [])
    wo_refs = list((work_order.meta or {}).get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or [])
    changed = False

    if work_order.ref not in order_refs:
        order.data = {**(order.data or {}), ORDER_AWAITING_WO_REFS_KEY: [*order_refs, work_order.ref]}
        changed = True
    if order.ref not in wo_refs:
        work_order.meta = {**(work_order.meta or {}), WORK_ORDER_COMMITTED_ORDER_REFS_KEY: [*wo_refs, order.ref]}
        work_order.save(update_fields=["meta", "updated_at"])
        changed = True
    return changed


def _unlink_voided_work_order(work_order) -> None:
    from shopman.craftsman.models import WorkOrder
    from shopman.orderman.models import Order

    with transaction.atomic():
        work_order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
        refs = linked_order_refs(work_order)
        if not refs:
            return
        for order in Order.objects.select_for_update().filter(ref__in=refs).order_by("pk"):
            if _remove_ref(order.data, ORDER_AWAITING_WO_REFS_KEY, work_order.ref):
                order.save(update_fields=["data", "updated_at"])
        meta = {**(work_order.meta or {})}
        meta.pop(WORK_ORDER_COMMITTED_ORDER_REFS_KEY, None)
        work_order.meta = meta
        work_order.save(update_fields=["meta", "updated_at"])


def _unlink_inactive_order(order) -> None:
    """Remove stale demand links when an order leaves production statuses."""
    from shopman.craftsman.models import WorkOrder
    from shopman.orderman.models import Order

    refs = tuple((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or ())
    with transaction.atomic():
        work_orders = list(WorkOrder.objects.select_for_update().filter(ref__in=refs).order_by("pk"))
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status in ACTIVE_ORDER_STATUSES:
            return
        for work_order in work_orders:
            if _remove_ref(
                work_order.meta,
                WORK_ORDER_COMMITTED_ORDER_REFS_KEY,
                order.ref,
            ):
                work_order.save(update_fields=["meta", "updated_at"])
        data = {**(order.data or {})}
        data.pop(ORDER_AWAITING_WO_REFS_KEY, None)
        if data != (order.data or {}):
            order.data = data
            order.save(update_fields=["data", "updated_at"])


def _resolve_finished_work_order(work_order) -> None:
    """Move a finished WO out of each order's pending queue, preserving lineage."""
    from shopman.craftsman.models import WorkOrder
    from shopman.orderman.models import Order

    with transaction.atomic():
        work_order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
        refs = linked_order_refs(work_order)
        for order in Order.objects.select_for_update().filter(ref__in=refs).order_by("pk"):
            data = {**(order.data or {})}
            awaiting = list(data.get(ORDER_AWAITING_WO_REFS_KEY) or ())
            history = list(data.get(ORDER_PRODUCTION_WO_REFS_KEY) or ())
            updated_awaiting = [ref for ref in awaiting if ref != work_order.ref]
            updated_history = list(dict.fromkeys([*history, work_order.ref]))
            if updated_awaiting:
                data[ORDER_AWAITING_WO_REFS_KEY] = updated_awaiting
            else:
                data.pop(ORDER_AWAITING_WO_REFS_KEY, None)
            data[ORDER_PRODUCTION_WO_REFS_KEY] = updated_history
            if data != (order.data or {}):
                order.data = data
                order.save(update_fields=["data", "updated_at"])


def _remove_ref(container, key: str, ref: str) -> bool:
    original = {**(container or {})}
    existing = list(original.get(key) or ())
    updated = [value for value in existing if value != ref]
    if updated == existing:
        return False
    if updated:
        original[key] = updated
    else:
        original.pop(key, None)
    container.clear()
    container.update(original)
    return True


def _candidate_work_order(sku: str, *, target_date: date, lock: bool = False):
    from shopman.craftsman.models import WorkOrder

    qs = WorkOrder.objects.filter(
        output_sku=sku,
        status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED),
        target_date__lte=target_date,
    )
    if lock:
        qs = qs.select_for_update()
    strategy = _match_strategy()
    if strategy == "earliest_target":
        return qs.order_by("target_date", "created_at", "pk").first()
    if strategy == "manual":
        return None
    return qs.order_by("created_at", "pk").first()


def _candidate_from_work_orders(work_orders, *, target_date: date, strategy: str):
    ordered = _ordered_candidate_work_orders(
        work_orders,
        target_date=target_date,
        strategy=strategy,
    )
    return ordered[0] if ordered else None


def _ordered_candidate_work_orders(
    work_orders,
    *,
    target_date: date,
    strategy: str,
):
    eligible = [
        work_order for work_order in work_orders if (work_order.target_date or timezone.localdate()) <= target_date
    ]
    if not eligible or strategy == "manual":
        return []
    if strategy == "earliest_target":
        return sorted(
            eligible,
            key=lambda work_order: (
                work_order.target_date or timezone.localdate(),
                work_order.created_at,
                work_order.pk,
            ),
        )
    return sorted(
        eligible,
        key=lambda work_order: (work_order.created_at, work_order.pk),
    )


def _compatible_order_work_order(order, work_order) -> bool:
    return work_order.output_sku in _order_skus(order) and (
        work_order.target_date or timezone.localdate()
    ) <= _target_date(order)


def _match_strategy() -> str:
    try:
        from shopman.shop.production_config import ProductionConfig

        return ProductionConfig.load().order_match
    except Exception:
        logger.warning("production_order_sync.strategy_failed", exc_info=True)
    return "first_planned"


def _order_skus(order) -> tuple[str, ...]:
    return tuple(sorted({item.sku for item in order.items.all() if item.sku}))


def _target_date(order) -> date:
    from shopman.shop.services.order_helpers import get_commitment_date

    commitment = get_commitment_date(order)
    if commitment is not None:
        return commitment
    raw = (order.data or {}).get("target_date") or (order.data or {}).get("production_target_date")
    if raw:
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            logger.warning(
                "production_order_sync.invalid_target_date order=%s value=%r",
                order.ref,
                raw,
            )
    return timezone.localdate(order.created_at) if order.created_at else timezone.localdate()
