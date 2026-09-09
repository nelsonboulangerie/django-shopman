"""
Execution service — finish and void operations.

All methods are @classmethod (mixin pattern).
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.services.scheduling import _check_rev, _next_seq

logger = logging.getLogger(__name__)


def _positive_decimal(value, *, field: str = "quantity") -> Decimal:
    try:
        quantity = Decimal(str(value))
    except Exception as exc:
        raise CraftError("INVALID_QUANTITY", field=field, quantity=value) from exc
    # `Decimal` aceita "NaN"/"Infinity" como números legítimos: o NaN estoura na
    # comparação `<= 0` (InvalidOperation, que não é CraftError e vaza como 500),
    # e o infinito passa reto e vira quantidade produzida. Não-finito é inválido.
    if not quantity.is_finite() or quantity <= 0:
        raise CraftError("INVALID_QUANTITY", field=field, quantity=str(quantity))
    return quantity


def _required_ref(value, *, field: str) -> str:
    ref = str(value or "").strip()
    if not ref:
        raise CraftError("INVALID_REF", field=field)
    return ref


def _mapping_item(value, *, field: str) -> dict:
    if not isinstance(value, dict):
        raise CraftError("INVALID_PAYLOAD", field=field)
    return value


def _decimal_wire(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _canonical_attempt_value(value):
    if isinstance(value, Decimal):
        return _decimal_wire(value)
    if isinstance(value, dict):
        return {
            str(key): _canonical_attempt_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_attempt_value(item) for item in value]
    return value


def _canonical_attempt_rows(values, *, field: str) -> list[dict]:
    rows: list[dict] = []
    for raw in values:
        row = dict(_mapping_item(raw, field=field))
        row["quantity"] = _decimal_wire(_positive_decimal(row.get("quantity"), field=f"{field}.quantity"))
        rows.append(_canonical_attempt_value(row))
    return rows


def _finish_attempt(*, finished, finished_decimal, consumed, wasted, note, context) -> dict:
    if isinstance(finished, (int, float, Decimal, str)):
        finished_attempt = {
            "mode": "scalar",
            "quantity": _decimal_wire(finished_decimal),
        }
    else:
        finished_attempt = {
            "mode": "partition",
            "items": _canonical_attempt_rows(finished, field="finished"),
        }

    if consumed is None:
        consumed_attempt = {"mode": "automatic"}
    else:
        consumed_attempt = {
            "mode": "explicit",
            "items": _canonical_attempt_rows(consumed, field="consumed"),
        }

    if wasted is None:
        wasted_attempt = {"mode": "automatic"}
    elif isinstance(wasted, (int, float, Decimal, str)):
        wasted_attempt = {
            "mode": "scalar",
            "quantity": _decimal_wire(_positive_decimal(wasted, field="wasted")),
        }
    else:
        wasted_attempt = {
            "mode": "explicit",
            "items": _canonical_attempt_rows(wasted, field="wasted"),
        }

    return {
        "finished": finished_attempt,
        "consumed": consumed_attempt,
        "wasted": wasted_attempt,
        "note": str(note or ""),
        "context": _canonical_attempt_value(dict(context or {})),
    }


class CraftExecution:
    """Finish and void operations."""

    @classmethod
    def advance_step(
        cls,
        order,
        *,
        step_index,
        step_name="",
        expected_rev=None,
        actor=None,
        idempotency_key=None,
    ):
        """Persist a manual recipe-step advance with revision and audit event.

        The caller resolves the next valid index from the frozen/current recipe
        presentation.  Craftsman owns the material mutation: row lock, optimistic
        revision and the append-only witness all commit together.
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent

        try:
            normalized_index = int(step_index)
        except (TypeError, ValueError) as exc:
            raise CraftError("INVALID_PAYLOAD", field="step_index") from exc
        if normalized_index <= 0:
            raise CraftError("INVALID_PAYLOAD", field="step_index")
        attempt = {
            "step_index": normalized_index,
            "step_name": str(step_name or ""),
        }

        with transaction.atomic():
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            if idempotency_key:
                existing = (
                    WorkOrderEvent.objects.filter(idempotency_key=idempotency_key).select_related("work_order").first()
                )
                if existing:
                    if (
                        existing.work_order_id != order.pk
                        or existing.kind != WorkOrderEvent.Kind.STEP_ADVANCED
                        or existing.actor != str(actor or "")
                        or (
                            existing.payload.get(
                                "attempt",
                                {
                                    "step_index": existing.payload.get("step_index"),
                                    "step_name": existing.payload.get("step_name", ""),
                                },
                            )
                            != attempt
                        )
                    ):
                        raise CraftError(
                            "IDEMPOTENCY_CONFLICT",
                            idempotency_key=idempotency_key,
                            work_order=order.ref,
                            existing_work_order=existing.work_order.ref,
                        )
                    return existing.work_order

            if order.status != WorkOrder.Status.STARTED:
                raise CraftError(
                    "INVALID_STATUS",
                    current=order.status,
                    expected=WorkOrder.Status.STARTED,
                )

            _check_rev(order, expected_rev)
            meta = dict(order.meta or {})
            meta["steps_progress"] = normalized_index
            meta["steps_progress_actor"] = actor or ""
            meta["steps_progress_updated_at"] = timezone.now().isoformat()
            order.meta = meta
            order.save(update_fields=["meta", "updated_at"])

            WorkOrderEvent.objects.create(
                work_order=order,
                seq=_next_seq(order),
                kind=WorkOrderEvent.Kind.STEP_ADVANCED,
                payload={
                    "step_index": normalized_index,
                    "step_name": str(step_name or ""),
                    "attempt": attempt,
                },
                actor=actor or "",
                idempotency_key=idempotency_key,
            )

        return order

    @classmethod
    def finish(
        cls,
        order,
        finished,
        *,
        consumed=None,
        wasted=None,
        expected_rev=None,
        actor=None,
        note=None,
        idempotency_key=None,
        fail_closed=False,
        event_context=None,
        _idempotent_summary_replay=False,
    ):
        """
        Finish a WorkOrder with final production results.
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        # Normalize finished quantity (pure computation, safe outside transaction)
        if isinstance(finished, (int, float, Decimal, str)):
            finished_decimal = _positive_decimal(finished, field="finished")
            finished_items = None
        else:
            finished_items = finished
            if not finished_items:
                raise CraftError("INVALID_QUANTITY", field="finished")
            finished_decimal = Decimal("0")
            for p in finished_items:
                p = _mapping_item(p, field="finished")
                finished_decimal += _positive_decimal(p.get("quantity"), field="finished.quantity")
        attempt = _finish_attempt(
            finished=finished,
            finished_decimal=finished_decimal,
            consumed=consumed,
            wasted=wasted,
            note=note,
            context=event_context,
        )

        with transaction.atomic():
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            if idempotency_key:
                existing = (
                    WorkOrderEvent.objects.filter(
                        idempotency_key=idempotency_key,
                    )
                    .select_related("work_order")
                    .first()
                )
                if existing:
                    existing_attempt = existing.payload.get("attempt")
                    if existing_attempt is None:
                        existing_attempt_matches = (
                            attempt["finished"]["mode"] == "scalar"
                            and _decimal_wire(Decimal(str(existing.payload.get("finished_qty"))))
                            == attempt["finished"]["quantity"]
                            and attempt["consumed"]["mode"] == "automatic"
                            and attempt["wasted"]["mode"] == "automatic"
                            and not attempt["note"]
                            and not attempt["context"]
                        )
                    else:
                        existing_attempt_matches = existing_attempt == attempt
                    if _idempotent_summary_replay:
                        existing_attempt_matches = _decimal_wire(
                            Decimal(str(existing.payload.get("finished_qty")))
                        ) == _decimal_wire(finished_decimal)
                    if (
                        existing.work_order_id != order.pk
                        or existing.kind != WorkOrderEvent.Kind.FINISHED
                        or existing.actor != str(actor or "")
                        or not existing_attempt_matches
                    ):
                        raise CraftError(
                            "IDEMPOTENCY_CONFLICT",
                            idempotency_key=idempotency_key,
                            work_order=order.ref,
                            existing_work_order=existing.work_order.ref,
                        )
                    return existing.work_order

            if order.status == WorkOrder.Status.FINISHED:
                raise CraftError("TERMINAL_STATUS", status=order.status)
            if order.status == WorkOrder.Status.VOID:
                raise CraftError("TERMINAL_STATUS", status=order.status)

            _check_rev(order, expected_rev)

            now = timezone.now()
            if order.started_at is None:
                order.started_at = now

            if order.status == WorkOrder.Status.PLANNED:
                implicit_started_qty = order.quantity
                next_seq = _next_seq(order)
                WorkOrderEvent.objects.create(
                    work_order=order,
                    seq=next_seq,
                    kind=WorkOrderEvent.Kind.STARTED,
                    payload={
                        "quantity": str(implicit_started_qty),
                        "operator_ref": order.operator_ref,
                        "position_ref": order.position_ref,
                        "note": note or "",
                        "implicit": True,
                    },
                    actor=actor or "",
                )
                order.status = WorkOrder.Status.STARTED
                order.save(update_fields=["started_at", "status", "updated_at"])

            recipe = order.recipe
            started_qty = order.started_qty or order.quantity

            snapshot = order.meta.get("_recipe_snapshot") if order.meta else None
            if snapshot:
                batch_size = Decimal(snapshot["batch_size"])
                coefficient = started_qty / batch_size
                recipe_item_data = snapshot["items"]
            else:
                coefficient = started_qty / recipe.batch_size
                recipe_item_data = [
                    {"input_sku": ri.input_sku, "quantity": str(ri.quantity), "unit": ri.unit}
                    for ri in recipe.items.filter(is_optional=False).order_by("sort_order")
                ]

            from shopman.craftsman.models import WorkOrderItem

            all_items = []
            requirements = []

            for item_data in recipe_item_data:
                req_qty = Decimal(item_data["quantity"]) * coefficient
                requirements.append(
                    {
                        "item_ref": item_data["input_sku"],
                        "quantity": req_qty,
                        "unit": item_data["unit"],
                    }
                )
                all_items.append(
                    WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.REQUIREMENT,
                        item_ref=item_data["input_sku"],
                        quantity=req_qty,
                        unit=item_data["unit"],
                        recorded_at=now,
                        recorded_by=actor or "",
                    )
                )

            if consumed is not None:
                recipe_refs = {r["item_ref"] for r in requirements}
                for c in consumed:
                    if c["item_ref"] not in recipe_refs:
                        logger.warning(
                            "WorkOrder %s: consumed item_ref '%s' not in recipe (substitution?)",
                            order.ref,
                            c["item_ref"],
                        )

            if consumed is None:
                for req in requirements:
                    all_items.append(
                        WorkOrderItem(
                            work_order=order,
                            kind=WorkOrderItem.Kind.CONSUMPTION,
                            item_ref=req["item_ref"],
                            quantity=req["quantity"],
                            unit=req["unit"],
                            recorded_at=now,
                            recorded_by=actor or "",
                        )
                    )
            else:
                for c in consumed:
                    c = _mapping_item(c, field="consumed")
                    consumed_ref = _required_ref(c.get("item_ref"), field="consumed.item_ref")
                    consumed_quantity = _positive_decimal(c.get("quantity"), field="consumed.quantity")
                    all_items.append(
                        WorkOrderItem(
                            work_order=order,
                            kind=WorkOrderItem.Kind.CONSUMPTION,
                            item_ref=consumed_ref,
                            quantity=consumed_quantity,
                            unit=c.get("unit", ""),
                            recorded_at=now,
                            recorded_by=actor or "",
                            meta=c.get("meta", {}),
                        )
                    )

            if finished_items is None:
                all_items.append(
                    WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.OUTPUT,
                        item_ref=order.output_sku,
                        quantity=finished_decimal,
                        unit="",
                        recorded_at=now,
                        recorded_by=actor or "",
                    )
                )
            else:
                for p in finished_items:
                    p = _mapping_item(p, field="finished")
                    output_ref = _required_ref(p.get("item_ref"), field="finished.item_ref")
                    output_quantity = _positive_decimal(p.get("quantity"), field="finished.quantity")
                    # `meta` também aqui (era só no ramo de wasted) — a assimetria
                    # impedia a partição de carregar informação (ADR-017). As refs
                    # de partição são opacas para o core: repassa, não interpreta.
                    all_items.append(
                        WorkOrderItem(
                            work_order=order,
                            kind=WorkOrderItem.Kind.OUTPUT,
                            item_ref=output_ref,
                            quantity=output_quantity,
                            unit=p.get("unit", ""),
                            recorded_at=now,
                            recorded_by=actor or "",
                            meta=p.get("meta", {}),
                            quality_grade_ref=p.get("quality_grade_ref", ""),
                            quality_defect_ref=p.get("quality_defect_ref", ""),
                            batch_ref=p.get("batch_ref", ""),
                        )
                    )

            if wasted is None:
                auto_waste = started_qty - finished_decimal
                if auto_waste > 0:
                    all_items.append(
                        WorkOrderItem(
                            work_order=order,
                            kind=WorkOrderItem.Kind.WASTE,
                            item_ref=order.output_sku,
                            quantity=auto_waste,
                            unit="",
                            recorded_at=now,
                            recorded_by=actor or "",
                        )
                    )
            elif isinstance(wasted, (int, float, Decimal, str)):
                waste_decimal = _positive_decimal(wasted, field="wasted")
                all_items.append(
                    WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.WASTE,
                        item_ref=order.output_sku,
                        quantity=waste_decimal,
                        unit="",
                        recorded_at=now,
                        recorded_by=actor or "",
                    )
                )
            else:
                for w in wasted:
                    w = _mapping_item(w, field="wasted")
                    waste_ref = _required_ref(w.get("item_ref"), field="wasted.item_ref")
                    waste_quantity = _positive_decimal(w.get("quantity"), field="wasted.quantity")
                    # Perda também carrega o defeito (unidades vetadas chegam aqui
                    # com o motivo); `batch_ref` não — perda não vira lote.
                    all_items.append(
                        WorkOrderItem(
                            work_order=order,
                            kind=WorkOrderItem.Kind.WASTE,
                            item_ref=waste_ref,
                            quantity=waste_quantity,
                            unit=w.get("unit", ""),
                            recorded_at=now,
                            recorded_by=actor or "",
                            meta=w.get("meta", {}),
                            quality_grade_ref=w.get("quality_grade_ref", ""),
                            quality_defect_ref=w.get("quality_defect_ref", ""),
                        )
                    )

            waste_total = sum(item.quantity for item in all_items if item.kind == WorkOrderItem.Kind.WASTE)
            WorkOrderItem.objects.bulk_create(all_items)

            order.finished = finished_decimal
            order.status = WorkOrder.Status.FINISHED
            order.finished_at = now
            order.save(
                update_fields=[
                    "finished",
                    "status",
                    "finished_at",
                    "started_at",
                    "updated_at",
                ]
            )

            # O ledger imutável carrega a partição (ADR-017 §7): o fato de que a
            # fornada saiu em grupos não pode viver só em linhas mutáveis por
            # admin — o evento é a testemunha. O core grava o que recebeu, opaco.
            partition_payload = [
                {
                    "item_ref": item.item_ref,
                    "quantity": str(item.quantity),
                    "quality_grade_ref": item.quality_grade_ref,
                    "quality_defect_ref": item.quality_defect_ref,
                    "batch_ref": item.batch_ref,
                    **({"meta": item.meta} if item.meta else {}),
                }
                for item in all_items
                if item.kind in (WorkOrderItem.Kind.OUTPUT, WorkOrderItem.Kind.WASTE)
                and (item.quality_grade_ref or item.quality_defect_ref or item.batch_ref)
            ]

            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.FINISHED,
                payload={
                    "finished_qty": str(finished_decimal),
                    "planned_qty": str(order.quantity),
                    "started_qty": str(started_qty),
                    "loss_qty": str(waste_total),
                    "output_sku": order.output_sku,
                    "target_date": str(order.target_date) if order.target_date else None,
                    "source_ref": order.source_ref,
                    "position_ref": order.position_ref,
                    "operator_ref": order.operator_ref,
                    **({"partition": partition_payload} if partition_payload else {}),
                    **({"context": dict(event_context)} if event_context else {}),
                    "attempt": attempt,
                },
                actor=actor or "",
                idempotency_key=idempotency_key,
            )

        # Stock ledger (consume insumos + receive output) is realized by the
        # `production_changed` signal handlers in contrib/stockman — the single
        # canonical craftsman→stockman write path. See _handle_finished.
        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_sku,
            date=order.target_date,
            action="finished",
            work_order=order,
            fail_closed=fail_closed,
        )

        logger.info("WorkOrder %s finished: finished_qty=%s", order.ref, finished_decimal)
        return order

    @classmethod
    def void(
        cls,
        order,
        reason,
        expected_rev=None,
        actor=None,
        idempotency_key=None,
        fail_closed=False,
        attempt_payload=None,
        attempt_result=None,
    ):
        """Void (cancel) a non-finished WorkOrder."""
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        with transaction.atomic():
            # Acquire row lock, then refresh caller's object in-place
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            if idempotency_key:
                existing = (
                    WorkOrderEvent.objects.filter(idempotency_key=idempotency_key).select_related("work_order").first()
                )
                if existing:
                    if (
                        existing.work_order_id != order.pk
                        or existing.kind != WorkOrderEvent.Kind.VOIDED
                        or existing.actor != str(actor or "")
                        or existing.payload.get("reason") != reason
                        or (attempt_payload and existing.payload.get("attempt") != attempt_payload)
                    ):
                        raise CraftError(
                            "IDEMPOTENCY_CONFLICT",
                            idempotency_key=idempotency_key,
                            work_order=order.ref,
                            existing_work_order=existing.work_order.ref,
                        )
                    return existing.work_order

            # Status check (inside transaction, fresh from DB)
            if order.status == WorkOrder.Status.FINISHED:
                raise CraftError("VOID_FROM_DONE", work_order=order.ref)
            if order.status == WorkOrder.Status.VOID:
                raise CraftError("TERMINAL_STATUS", status=order.status)

            _check_rev(order, expected_rev)

            order.status = WorkOrder.Status.VOID
            order.save(update_fields=["status", "updated_at"])

            # Atomic seq via row lock
            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.VOIDED,
                payload={
                    "reason": reason,
                    "result": str(attempt_result or "cleared"),
                    **({"attempt": dict(attempt_payload)} if attempt_payload else {}),
                },
                actor=actor or "",
                idempotency_key=idempotency_key,
            )

        # Voiding planned/started production cancels its planned/started quants
        # via the `production_changed` (action=voided) signal handler.
        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_sku,
            date=order.target_date,
            action="voided",
            work_order=order,
            fail_closed=fail_closed,
        )

        logger.info("WorkOrder %s voided: %s", order.ref, reason)
        return order
