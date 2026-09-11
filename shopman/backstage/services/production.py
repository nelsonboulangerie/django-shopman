"""Production operator mutation facade.

Backstage views call this module for production mutations. Domain invariants
remain in ``shopman.shop.services.production`` and Craftsman; this layer is the
operator-surface boundary for form-oriented actions.
"""

from __future__ import annotations

import csv
import hashlib
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.utils import timezone
from shopman.utils.spreadsheet import escape_cell

from shopman.backstage.services.exceptions import (
    ProductionConflict,
    ProductionError,
    ProductionNotFound,
)
from shopman.shop.services import production as production_core

logger = logging.getLogger(__name__)

QUICK_FINISH_RECEIPT_SCOPE = "production:quick-finish-attempt"
PROJECTED_ACTION_CLAIM_SCOPE = "production:projected-action-claim"
QUICK_FINISH_EXECUTION_LEASE_SECONDS = 120


def _operator_error(exc: Exception) -> Exception:
    """Traduz um ``CraftError`` do kernel para a borda do operador.

    Sem isto, dois quiosques fechando a MESMA fornada davam 500 cru com
    mensagem em inglês (o ``CraftError`` não é DRF nem ``ProductionError``,
    então nenhuma view o capturava). Conflito de estado (fechada/estornada/
    alterada em outra tela) vira ``ProductionConflict`` → 409; o resto vira
    ``ProductionError`` → 400. Exceção que não é ``CraftError`` volta como
    veio (o chamador decide).

    ``StockError`` entra na mesma tradução. Na borda Backstage, o ``atomic``
    externo inclui os receivers e impede afirmar que a fornada foi fechada
    quando qualquer perna transacional falhou.
    """
    from django.core.exceptions import ObjectDoesNotExist
    from shopman.craftsman.exceptions import CraftError
    from shopman.stockman.exceptions import StockError

    if isinstance(exc, StockError):
        return ProductionError(
            f"A fornada não foi concluída porque o estoque falhou: {exc}. Atualize o painel e tente novamente."
        )
    if isinstance(exc, ObjectDoesNotExist):
        return ProductionNotFound(
            "Recurso de produção não encontrado.",
            resource="production_resource",
            identifier="",
        )
    if not isinstance(exc, CraftError):
        return exc
    code = getattr(exc, "code", "")
    data = getattr(exc, "data", {}) or {}
    if code in ("TERMINAL_STATUS", "VOID_FROM_DONE"):
        if str(data.get("status") or "") == "void":
            return ProductionConflict("Esta fornada foi estornada. Atualize o painel.", data=data)
        if code == "VOID_FROM_DONE":
            return ProductionConflict("Fornada concluída não pode ser estornada.", data=data)
        return ProductionConflict(
            "Esta fornada já foi fechada em outra tela. Atualize o painel.",
            data=data,
        )
    if code in (
        "INVALID_STATUS",
        "STALE_REVISION",
        "IDEMPOTENCY_CONFLICT",
        "AMBIGUOUS_WORK_ORDER",
    ):
        return ProductionConflict(
            "A fornada mudou em outra tela. Atualize o painel e tente de novo.",
            code="conflict",
            data={**data, "cause": code.lower()},
        )
    if code == "INVALID_QUANTITY":
        return ProductionError("Quantidade inválida.")
    return ProductionError(str(exc) or "Falha na produção.")


def _positive_quantity(value, *, allow_zero: bool = False) -> Decimal:
    """Normalize an operator quantity before fingerprints or domain arithmetic.

    Planning alone accepts zero because that is the explicit gesture that clears
    an existing matrix cell. Starting, finishing and every QC group remain
    strictly positive.
    """
    try:
        quantity = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise ProductionError("Quantidade inválida.") from exc
    if not quantity.is_finite() or quantity < 0 or (quantity == 0 and not allow_zero):
        raise ProductionError("Quantidade inválida.")
    return quantity


@dataclass(frozen=True)
class MissingMaterial:
    sku: str
    needed: Decimal
    available: Decimal

    @property
    def shortage(self) -> Decimal:
        return max(Decimal("0"), self.needed - self.available)


class ProductionStockShortError(ProductionError):
    """Raised when pre-finish material validation detects a shortage."""

    def __init__(self, *, work_order_ref: str, missing: list[MissingMaterial]):
        self.work_order_ref = work_order_ref
        self.missing = missing
        summary = ", ".join(f"{item.sku}: faltam {_qty(item.shortage)}" for item in missing)
        super().__init__(f"Insumos insuficientes para {work_order_ref}: {summary}")


class ProductionBatchTraceabilityError(ProductionError):
    """A finish cannot commit if its saleable batch facts cannot be written."""

    def __init__(self, *, work_order_ref: str, output_sku: str, cause: Exception):
        self.work_order_ref = work_order_ref
        self.output_sku = output_sku
        self.cause = cause
        super().__init__(
            "A fornada não foi concluída porque a rastreabilidade do lote falhou. Atualize o painel e tente novamente."
        )


class ProductionOrderShortError(ProductionError):
    """Raised when an operation no longer covers linked orders."""

    def __init__(
        self,
        *,
        work_order_ref: str,
        required: Decimal,
        requested: Decimal,
        order_refs: tuple[str, ...],
        allow_override: bool = True,
    ):
        self.work_order_ref = work_order_ref
        self.required = required
        self.requested = requested
        self.order_refs = order_refs
        self.allow_override = allow_override
        short = max(Decimal("0"), required - requested)
        super().__init__(
            f"{work_order_ref} tem {_qty(required)} un. comprometidas; "
            f"a nova quantidade deixa {_qty(short)} un. descobertas."
        )


def production_shortage_snapshot(exc: ProductionError) -> dict | None:
    """Canonical impact approved by the operator in a shortage continuation."""
    if isinstance(exc, ProductionStockShortError):
        return {
            "kind": "material_shortage",
            "work_order_ref": exc.work_order_ref,
            "missing": [
                {
                    "sku": item.sku,
                    "needed": _qty(item.needed),
                    "available": _qty(item.available),
                    "shortage": _qty(item.shortage),
                }
                for item in exc.missing
            ],
        }
    if isinstance(exc, ProductionOrderShortError):
        return {
            "kind": "order_shortage",
            "work_order_ref": exc.work_order_ref,
            "required": _qty(exc.required),
            "requested": _qty(exc.requested),
            "order_refs": list(exc.order_refs),
        }
    return None


def _require_approved_shortage_snapshot(
    approved: dict | None,
    current_error: ProductionError | None,
) -> None:
    current = production_shortage_snapshot(current_error) if current_error else None
    if current_error is not None and approved is None:
        # A reason/force bit is never an approval. The exact impact must have
        # come back from the signed shortage continuation offered by the API.
        raise current_error
    if approved is None:
        return
    if current == approved:
        return
    if current_error is not None:
        # Return the newly observed impact as a fresh 409/proof; do not apply an
        # approval that was granted for a smaller or otherwise different loss.
        raise current_error
    raise ProductionConflict(
        "A falta mudou desde a autorização. Atualize o painel e tente novamente.",
        data={"cause": "shortage_snapshot_changed"},
    )


def has_committed_mutation_attempt(
    *,
    action_kind: str,
    work_order_id,
    idempotency_key: str | None,
    body: dict,
) -> bool:
    """Identify only a durable commit for an exact client attempt.

    This supports response-loss recovery after the projection expires.  It is
    deliberately narrower than "an object with this status exists": the
    canonical service still receives the request and validates its frozen
    actor/payload before returning the replayed result.
    """
    client_key = str(idempotency_key or "").strip()
    if not client_key:
        return False

    from shopman.craftsman.models import WorkOrder, WorkOrderEvent

    event_specs = {
        "start": ("start", WorkOrderEvent.Kind.STARTED),
        "review_qc": ("quality-review", WorkOrderEvent.Kind.QUALITY_REVIEWED),
        "correct_qc": ("quality-correction", WorkOrderEvent.Kind.QUALITY_CORRECTED),
        "advance_step": ("advance-step", WorkOrderEvent.Kind.STEP_ADVANCED),
        "void": ("void", WorkOrderEvent.Kind.VOIDED),
        "oven_arm": ("oven-arm", WorkOrderEvent.Kind.OVEN_ARMED),
        "oven_conclude": ("oven-conclude", WorkOrderEvent.Kind.OVEN_CONCLUDED),
    }
    if action_kind == "plan":
        return WorkOrderEvent.objects.filter(
            idempotency_key=f"production.plan:{client_key}",
            kind__in=(
                WorkOrderEvent.Kind.PLANNED,
                WorkOrderEvent.Kind.PLANNING_CONFIRMED,
                WorkOrderEvent.Kind.ADJUSTED,
                WorkOrderEvent.Kind.VOIDED,
            ),
        ).exists()
    if action_kind in event_specs and work_order_id is not None:
        action, event_kind = event_specs[action_kind]
        return WorkOrderEvent.objects.filter(
            work_order_id=work_order_id,
            kind=event_kind,
            idempotency_key=_mutation_idempotency_key(
                action,
                work_order_id,
                client_key,
            ),
        ).exists()
    if action_kind == "finish" and work_order_id is not None:
        work_order = WorkOrder.objects.filter(pk=work_order_id).first()
        if work_order is None:
            return False
        finish_key = _finish_idempotency_key(
            work_order,
            quantity=body.get("quantity"),
            quality=body.get("quality", ""),
            partition=body.get("partition"),
            force=bool(body.get("force")),
            override_reason=body.get("reason", ""),
            yield_deviation_confirmed=bool(body.get("yield_deviation_confirmed")),
            yield_deviation_reason=body.get("yield_deviation_reason", ""),
            client_key=client_key,
        )
        return WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.FINISHED,
            idempotency_key=finish_key,
        ).exists()
    if action_kind == "quick_finish":
        from shopman.orderman.models import IdempotencyKey

        receipt = IdempotencyKey.objects.filter(
            scope=QUICK_FINISH_RECEIPT_SCOPE,
            key=client_key,
        ).first()
        if receipt is None:
            return False
        if receipt.status == "done":
            return True
        receipt_body = dict(receipt.response_body or {})
        work_order = WorkOrder.objects.filter(ref=str(receipt_body.get("work_order_ref") or "")).first()
        if work_order is None:
            return False
        finish_key = _finish_idempotency_key(
            work_order,
            quantity=body.get("quantity"),
            quality="",
            partition=body.get("partition"),
            force=bool(body.get("force")),
            override_reason=body.get("reason", ""),
            yield_deviation_confirmed=False,
            yield_deviation_reason="",
            client_key=client_key,
        )
        return WorkOrderEvent.objects.filter(
            work_order=work_order,
            kind=WorkOrderEvent.Kind.FINISHED,
            idempotency_key=finish_key,
        ).exists()
    return False


def _require_irreversible_attempt(
    *,
    actor: str,
    expected_rev: int | None,
    idempotency_key: str | None,
) -> None:
    """Fail closed before an irreversible service writer can inspect its target."""
    missing = []
    if not str(actor or "").strip():
        missing.append("actor")
    if expected_rev is None:
        missing.append("expected_rev")
    if not str(idempotency_key or "").strip():
        missing.append("idempotency_key")
    if missing:
        raise ProductionConflict(
            "A mutação exige operador, revisão e chave idempotente.",
            data={
                "cause": "missing_mutation_attempt",
                "missing": missing,
            },
        )


def _require_creation_attempt(*, actor: str, idempotency_key: str | None) -> None:
    """Require a durable identity before a writer can create a work order."""
    missing = []
    if not str(actor or "").strip():
        missing.append("actor")
    if not str(idempotency_key or "").strip():
        missing.append("idempotency_key")
    if missing:
        raise ProductionConflict(
            "A criação exige operador e chave idempotente.",
            data={
                "cause": "missing_mutation_attempt",
                "missing": missing,
            },
        )


def apply_void(
    work_order_id,
    *,
    actor: str,
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
    reason: str = "Estornado via produção rápida",
) -> str:
    """Void a work order from the operator surface."""
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    try:
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(pk=work_order_id)
            result = production_core.void_work_order(
                work_order_id,
                actor=actor,
                reason=reason,
                expected_rev=expected_rev,
                idempotency_key=_mutation_idempotency_key("void", work_order_id, idempotency_key),
            )
            _abandon_open_oven_run(
                work_order,
                actor=actor,
                transition="void",
                reason="work_order_voided",
            )
            return result
    except WorkOrder.DoesNotExist:
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None
    except Exception as exc:
        logger.debug("production_quick_finish_failed", exc_info=True)
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def _quick_finish_attempt(*, recipe_id, quantity, position_id, partition) -> dict:
    import json

    try:
        normalized_partition = json.loads(
            json.dumps(
                partition,
                default=str,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    except (TypeError, ValueError) as exc:
        raise ProductionError("Partição de conclusão rápida inválida.") from exc
    return {
        "recipe_id": str(recipe_id),
        "quantity": _qty(Decimal(str(quantity))),
        "position_id": str(position_id or ""),
        "partition": normalized_partition,
    }


def _quick_finish_receipt_exists(idempotency_key: str | None) -> bool:
    if not idempotency_key:
        return False
    from shopman.orderman.models import IdempotencyKey

    return IdempotencyKey.objects.filter(
        scope=QUICK_FINISH_RECEIPT_SCOPE,
        key=str(idempotency_key).strip(),
    ).exists()


def _preflight_quick_finish(
    *,
    recipe_id,
    quantity,
    partition,
    force: bool,
    override_reason: str,
):
    """Validate the command before creating any persistent receipt or WO."""
    from types import SimpleNamespace

    from shopman.craftsman.models import Recipe

    if force and not str(override_reason or "").strip():
        raise ProductionError("Justificativa obrigatória para confirmar a falta.")
    try:
        recipe = Recipe.objects.get(pk=recipe_id, is_active=True)
    except Recipe.DoesNotExist:
        raise ProductionNotFound(
            "Receita de produção não encontrada.",
            resource="recipe",
            identifier=str(recipe_id),
        ) from None
    resolve_partition(
        SimpleNamespace(
            pk=0,
            output_sku=recipe.output_sku,
            target_date=timezone.localdate(),
        ),
        quantity=quantity,
        partition=partition,
    )
    return recipe


def _claim_projected_action_attempt(
    *,
    projected_action_proof: str,
    idempotency_key: str,
    attempt: dict,
) -> None:
    """Bind one projected action proof to exactly one client attempt.

    Every signed action is a single-use capability. Without this claim,
    changing only the idempotency key could reuse one still-fresh projection
    to create another WorkOrder, or emit unlimited no-op confirmation events
    for a target whose revision did not change.
    """
    if not projected_action_proof or not idempotency_key:
        return

    from django.db import IntegrityError, transaction
    from shopman.orderman.models import IdempotencyKey

    proof_digest = hashlib.sha256(projected_action_proof.encode("utf-8")).hexdigest()
    import json

    attempt_digest = hashlib.sha256(
        json.dumps(
            attempt,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    client_key = str(idempotency_key).strip()
    for _attempt in range(2):
        with transaction.atomic():
            claim = (
                IdempotencyKey.objects.select_for_update()
                .filter(scope=PROJECTED_ACTION_CLAIM_SCOPE, key=proof_digest)
                .first()
            )
            if claim is None:
                try:
                    with transaction.atomic():
                        IdempotencyKey.objects.create(
                            scope=PROJECTED_ACTION_CLAIM_SCOPE,
                            key=proof_digest,
                            status="done",
                            response_code=204,
                            response_body={
                                "idempotency_key": client_key,
                                "attempt_digest": attempt_digest,
                            },
                        )
                    return
                except IntegrityError:
                    continue
            claimed_key = str((claim.response_body or {}).get("idempotency_key") or "")
            if claimed_key == client_key:
                if (claim.response_body or {}).get("attempt_digest") != attempt_digest:
                    raise ProductionConflict(
                        "Esta chave já pertence a outra tentativa projetada.",
                        data={"cause": "idempotency_conflict"},
                    )
                return
            raise ProductionConflict(
                "Esta ação projetada já foi consumida por outra tentativa.",
                data={"cause": "projected_action_consumed"},
            )
    raise ProductionConflict(
        "Não foi possível confirmar a posse da ação projetada.",
        data={"cause": "projected_action_claim_conflict"},
    )


def _claim_quick_finish_receipt(
    *,
    idempotency_key: str | None,
    attempt: dict,
    actor: str,
    force: bool,
    override_reason: str,
):
    """Freeze the command and acquire a recoverable execution lease."""
    if not idempotency_key:
        return None, None, None

    from uuid import uuid4

    from django.db import IntegrityError, transaction
    from django.utils.dateparse import parse_datetime
    from shopman.orderman.models import IdempotencyKey

    key = str(idempotency_key).strip()
    for _attempt in range(2):
        with transaction.atomic():
            receipt = (
                IdempotencyKey.objects.select_for_update().filter(scope=QUICK_FINISH_RECEIPT_SCOPE, key=key).first()
            )
            if receipt is None:
                try:
                    receipt = IdempotencyKey.objects.create(
                        scope=QUICK_FINISH_RECEIPT_SCOPE,
                        key=key,
                        status="in_progress",
                        response_body={
                            "attempt": attempt,
                            "actor": str(actor or ""),
                            "force": bool(force),
                            "override_reason": (str(override_reason or "").strip() if force else ""),
                            "phase": "accepted",
                        },
                    )
                except IntegrityError:
                    continue
            body = dict(receipt.response_body or {})
            if body.get("attempt") != attempt or body.get("actor") != str(actor or ""):
                raise ProductionConflict(
                    "Esta chave já pertence a outra tentativa de conclusão rápida.",
                    data={
                        "work_order": body.get("work_order_ref", ""),
                        "cause": "idempotency_conflict",
                    },
                )

            stored_force = bool(body.get("force"))
            requested_reason = str(override_reason or "").strip()
            if receipt.status == "done":
                if stored_force != bool(force) or (force and body.get("override_reason", "") != requested_reason):
                    raise ProductionConflict(
                        "A confirmação não corresponde à tentativa concluída.",
                        data={
                            "work_order": body.get("work_order_ref", ""),
                            "cause": "idempotency_conflict",
                        },
                    )
                return (
                    receipt.pk,
                    (
                        str(body["output_sku"]),
                        str(body["work_order_ref"]),
                        Decimal(str(body["quantity"])),
                    ),
                    None,
                )

            if body.get("phase") == "executing":
                replay = _reconcile_quick_finish_receipt(receipt, body)
                if replay is not None:
                    return receipt.pk, replay, None
                started_at = parse_datetime(str(body.get("execution_started_at") or ""))
                lease_expired = started_at is None or (timezone.now() - started_at) >= timedelta(
                    seconds=QUICK_FINISH_EXECUTION_LEASE_SECONDS
                )
                if not lease_expired:
                    raise ProductionConflict(
                        "A conclusão rápida já está em execução em outra tela.",
                        code="quick_finish_incomplete",
                        data={
                            "work_order": body.get("work_order_ref", ""),
                            "cause": "attempt_in_progress",
                            "recovery_action": "retry",
                            "recovery_label": "Aguardar e reconciliar",
                        },
                    )
            if force and not stored_force:
                if body.get("recovery") != "material_shortage":
                    raise ProductionConflict(
                        "A confirmação forçada não corresponde a uma falta de insumo pendente.",
                        data={
                            "work_order": body.get("work_order_ref", ""),
                            "cause": "idempotency_conflict",
                        },
                    )
                body.update(force=True, override_reason=requested_reason)
                receipt.response_body = body
                receipt.save(update_fields=["response_body"])
            elif stored_force != bool(force) or (force and body.get("override_reason", "") != requested_reason):
                raise ProductionConflict(
                    "A confirmação não corresponde à tentativa original.",
                    data={
                        "work_order": body.get("work_order_ref", ""),
                        "cause": "idempotency_conflict",
                    },
                )
            execution_token = uuid4().hex
            body.update(
                phase="executing",
                execution_force=bool(force),
                execution_started_at=timezone.now().isoformat(),
                execution_token=execution_token,
            )
            receipt.response_body = body
            receipt.save(update_fields=["response_body"])
            return receipt.pk, None, execution_token
    raise ProductionConflict(
        "Não foi possível recuperar a tentativa de conclusão rápida.",
        data={"cause": "idempotency_conflict"},
    )


def _reconcile_quick_finish_receipt(receipt, body: dict):
    """Complete a stranded receipt when its finish event already committed."""
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent

    attempt = dict(body.get("attempt") or {})
    work_order = None
    work_order_ref = str(body.get("work_order_ref") or "")
    if work_order_ref:
        work_order = WorkOrder.objects.select_related("recipe").filter(ref=work_order_ref).first()
    if work_order is None and attempt:
        work_order = production_core.replay_quick_plan(
            recipe_id=attempt.get("recipe_id"),
            quantity=attempt.get("quantity"),
            position_id=attempt.get("position_id"),
            actor=str(body.get("actor") or ""),
            idempotency_key=f"production.quick-plan:{receipt.key}",
        )
    if work_order is None:
        return None

    body["work_order_ref"] = work_order.ref
    finish_key = _finish_idempotency_key(
        work_order,
        quantity=attempt.get("quantity"),
        quality="",
        partition=attempt.get("partition"),
        force=bool(body.get("execution_force")),
        override_reason=str(body.get("override_reason") or ""),
        yield_deviation_confirmed=False,
        yield_deviation_reason="",
        client_key=receipt.key,
    )
    event = WorkOrderEvent.objects.filter(
        work_order=work_order,
        kind=WorkOrderEvent.Kind.FINISHED,
        idempotency_key=finish_key,
    ).first()
    if event is None:
        receipt.response_body = body
        receipt.save(update_fields=["response_body"])
        return None
    if event.actor != str(body.get("actor") or ""):
        raise ProductionConflict(
            "A tentativa concluída pertence a outro operador.",
            data={"work_order": work_order.ref, "cause": "idempotency_conflict"},
        )

    total = Decimal(str(event.payload["finished_qty"]))
    receipt.status = "done"
    receipt.response_code = 200
    receipt.response_body = {
        **body,
        "phase": "finished",
        "effective_force": bool(body.get("execution_force")),
        "output_sku": work_order.output_sku,
        "work_order_ref": work_order.ref,
        "quantity": _qty(total),
    }
    receipt.save(update_fields=["status", "response_code", "response_body"])
    return work_order.output_sku, work_order.ref, total


def _update_quick_finish_receipt(receipt_pk, *, execution_token=None, **facts) -> bool:
    if receipt_pk is None:
        return True
    from django.db import transaction
    from shopman.orderman.models import IdempotencyKey

    with transaction.atomic():
        receipt = IdempotencyKey.objects.select_for_update().get(pk=receipt_pk)
        body = dict(receipt.response_body or {})
        if receipt.status == "done" or body.get("phase") == "finished":
            return False
        if execution_token is not None and body.get("execution_token") != execution_token:
            return False
        receipt.response_body = {**body, **facts}
        receipt.save(update_fields=["response_body"])
        return True


def _complete_quick_finish_receipt(
    receipt_pk,
    *,
    output_sku: str,
    work_order_ref: str,
    quantity: Decimal,
    force: bool,
    execution_token=None,
) -> None:
    if receipt_pk is None:
        return
    from django.db import transaction
    from shopman.orderman.models import IdempotencyKey

    with transaction.atomic():
        receipt = IdempotencyKey.objects.select_for_update().get(pk=receipt_pk)
        body = dict(receipt.response_body or {})
        if receipt.status == "done" and body.get("phase") == "finished":
            if (
                body.get("output_sku") == output_sku
                and body.get("work_order_ref") == work_order_ref
                and Decimal(str(body.get("quantity"))) == Decimal(str(quantity))
                and bool(body.get("effective_force")) == bool(force)
            ):
                return
            raise ProductionConflict(
                "O recibo concluído não corresponde ao resultado desta execução.",
                data={"work_order": work_order_ref, "cause": "idempotency_conflict"},
            )
        if (
            body.get("phase") != "executing"
            or bool(body.get("execution_force")) != bool(force)
            or (execution_token is not None and body.get("execution_token") != execution_token)
        ):
            raise ProductionConflict(
                "A execução da conclusão rápida perdeu sua posse idempotente.",
                code="quick_finish_incomplete",
                data={
                    "work_order": body.get("work_order_ref", work_order_ref),
                    "cause": "execution_lease_lost",
                    "recovery_action": "retry",
                    "recovery_label": "Atualizar e reconciliar",
                },
            )
        receipt.status = "done"
        receipt.response_code = 200
        receipt.response_body = {
            **body,
            "phase": "finished",
            "effective_force": bool(force),
            "output_sku": output_sku,
            "work_order_ref": work_order_ref,
            "quantity": _qty(quantity),
        }
        receipt.save(update_fields=["status", "response_code", "response_body"])


def apply_quick_finish(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str,
    partition=None,
    force: bool = False,
    override_reason: str = "",
    idempotency_key: str | None = None,
    projected_action_proof: str = "",
    approved_shortage: dict | None = None,
):
    """Plan and immediately finish a work order from the operator surface.

    O fechamento passa pelo MESMO caminho do finish normal, COM ou SEM
    ``partition``: guardrail de insumo (``check_finish_materials``), veto
    resolvido na borda, N lotes com percentual congelado, alerta quando a
    rastreabilidade falha.

    Sem partição isto ia direto ao ``quick_finish`` do core, pulando o
    ``apply_finish`` — e a fornada avulsa era o único fechamento da casa que
    fechava sem farinha no estoque, calado. A mesma ação era barrada no
    quiosque de QC (que manda partição) e livre no grid do gestor.

    ## Por que o replay mora AQUI, e não no core

    Esta é a única operação COMPOSTA da produção: ela **cria** a WO e a fecha na
    mesma requisição. Isso derrota a trava do core sem que o core tenha culpa:

    * ``CraftExecution.finish`` tem a trava certa — ``idempotency_key`` com
      ``unique`` no banco, ``select_for_update``, devolve a WO existente no
      replay, e ainda levanta ``IDEMPOTENCY_CONFLICT`` se a mesma chave aparecer
      em OUTRA work order. O core se defende de quem reusa chave entre fornadas.
    * Só que ``_finish_idempotency_key`` inclui o ``work_order.pk``, e aqui o pk
      é **novo a cada tentativa** — chave nova, trava do core nunca alcançada.
      Para o ``apply_finish`` normal aquele pk está certo (escopa a chave àquela
      fornada); é este caminho que não podia depender dele.
    * E ``CraftPlanning.plan`` **não deve** consolidar: duas fornadas avulsas da
      mesma receita no mesmo dia são duas assadeiras de verdade. Onde consolidar
      É o certo — a célula da matriz — quem procura antes de criar é o
      orquestrador (``shop/services/production.set_planned_quantity``), não o
      core. Mesma primitiva, uso diferente, e os dois corretos.

    Então a trava é de REQUISIÇÃO, sobre as duas pernas juntas: sem ela, morrer
    entre o plan e o finish deixaria a primeira WO órfã em PLANNED e o retry
    criaria uma segunda. ``run_idempotent_mutation`` é a mesma primitiva que
    guarda a entrada de mercadoria em Compras.

    Sem ``idempotency_key`` o comportamento é o de antes — a superfície que
    não manda chave não ganha trava, e isso é explícito em vez de silencioso.
    """
    from shopman.craftsman.models import Recipe

    _require_creation_attempt(actor=actor, idempotency_key=idempotency_key)
    quantity = _positive_quantity(quantity)
    if force and not str(override_reason or "").strip():
        raise ProductionError("Justificativa obrigatória para confirmar a falta.")
    quick_key = f"production.quick-plan:{str(idempotency_key).strip()}" if idempotency_key else None
    attempt = _quick_finish_attempt(
        recipe_id=recipe_id,
        quantity=quantity,
        position_id=position_id,
        partition=partition,
    )
    recipe = None
    if not _quick_finish_receipt_exists(idempotency_key):
        recipe = _preflight_quick_finish(
            recipe_id=recipe_id,
            quantity=quantity,
            partition=partition,
            force=force,
            override_reason=override_reason,
        )
    _claim_projected_action_attempt(
        projected_action_proof=projected_action_proof,
        idempotency_key=str(idempotency_key or ""),
        attempt=attempt,
    )
    receipt_pk, receipt_replay, execution_token = _claim_quick_finish_receipt(
        idempotency_key=idempotency_key,
        attempt=attempt,
        actor=actor,
        force=force,
        override_reason=override_reason,
    )
    if receipt_replay is not None:
        return receipt_replay
    work_order = None
    try:
        work_order = production_core.replay_quick_plan(
            recipe_id=recipe_id,
            quantity=quantity,
            position_id=position_id,
            actor=actor,
            idempotency_key=quick_key,
        )
        if work_order is None:
            # An existing accepted receipt may be recovering from a crash before
            # the plan phase. Validate it before producing the first WorkOrder.
            recipe = recipe or _preflight_quick_finish(
                recipe_id=recipe_id,
                quantity=quantity,
                partition=partition,
                force=force,
                override_reason=override_reason,
            )
            work_order = production_core.quick_plan(
                recipe_id=recipe_id,
                quantity=quantity,
                position_id=position_id,
                actor=actor,
                idempotency_key=quick_key,
            )
        _update_quick_finish_receipt(
            receipt_pk,
            execution_token=execution_token,
            phase="executing",
            work_order_ref=work_order.ref,
        )
        wo_ref, total = apply_finish(
            work_order_id=work_order.pk,
            quantity=quantity,
            actor=actor,
            force=force,
            partition=partition,
            expected_rev=work_order.rev,
            idempotency_key=idempotency_key,
            override_reason=override_reason,
            override_action="quick_finish",
            allow_implicit_start=True,
            approved_shortage=approved_shortage,
        )
        _complete_quick_finish_receipt(
            receipt_pk,
            output_sku=work_order.output_sku,
            work_order_ref=wo_ref,
            quantity=total,
            force=force,
            execution_token=execution_token,
        )
        return work_order.output_sku, wo_ref, total
    except Recipe.DoesNotExist:
        raise ProductionNotFound(
            "Receita de produção não encontrada.",
            resource="recipe",
            identifier=str(recipe_id),
        ) from None
    except Exception as exc:
        logger.debug("production_quick_finish_failed", exc_info=True)
        translated = _operator_error(exc)
        if isinstance(translated, ProductionStockShortError):
            _update_quick_finish_receipt(
                receipt_pk,
                execution_token=execution_token,
                phase="planned",
                execution_force=None,
                recovery="material_shortage",
                work_order_ref=translated.work_order_ref,
            )
        elif isinstance(translated, ProductionOrderShortError):
            _update_quick_finish_receipt(
                receipt_pk,
                execution_token=execution_token,
                phase="planned",
                execution_force=None,
                recovery="order_shortage",
                work_order_ref=translated.work_order_ref,
            )
        elif isinstance(translated, ProductionConflict) and work_order is not None:
            _update_quick_finish_receipt(
                receipt_pk,
                execution_token=execution_token,
                phase="planned",
                execution_force=None,
                recovery="retry",
                work_order_ref=work_order.ref,
            )
        elif work_order is None:
            _update_quick_finish_receipt(
                receipt_pk,
                execution_token=execution_token,
                phase="accepted",
                execution_force=None,
                recovery="retry",
            )
        if work_order is not None and not isinstance(
            translated,
            (
                ProductionConflict,
                ProductionNotFound,
                ProductionOrderShortError,
                ProductionStockShortError,
            ),
        ):
            try:
                work_order.refresh_from_db(fields=["status", "rev"])
            except Exception:
                logger.warning(
                    "production.quick_finish_recovery_read_failed work_order=%s",
                    work_order.ref,
                    exc_info=True,
                )
            if work_order.status in ("planned", "started"):
                _update_quick_finish_receipt(
                    receipt_pk,
                    execution_token=execution_token,
                    phase="planned",
                    execution_force=None,
                    recovery="retry",
                    work_order_ref=work_order.ref,
                )
                raise ProductionConflict(
                    "A conclusão rápida não terminou; a mesma fornada foi preservada para retry.",
                    code="quick_finish_incomplete",
                    data={
                        "work_order": work_order.ref,
                        "current_rev": work_order.rev,
                        "cause": type(translated).__name__,
                        "recovery_action": "retry",
                        "recovery_label": "Retomar a mesma fornada",
                    },
                ) from exc
        raise translated from (None if translated is exc else exc)


def apply_planned(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    reason: str = "",
    actor: str,
    force: bool = False,
    source_ref: str = "production_matrix",
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
    work_order_id=None,
    planning_meta: dict | None = None,
    create_new: bool = False,
    approved_shortage: dict | None = None,
    projected_action_proof: str = "",
):
    """Create or adjust one serialized production-matrix cell.

    ``expected_rev`` reaches adjustments; a creation has no previous revision.
    The recipe lock keeps the coverage read and the cell write in one transaction.
    """
    from django.db import transaction
    from shopman.craftsman.models import Recipe

    _require_creation_attempt(actor=actor, idempotency_key=idempotency_key)
    quantity = _positive_quantity(quantity, allow_zero=True)
    attempt_key = f"production.plan:{str(idempotency_key).strip()}" if idempotency_key else None
    attempt_payload = {"force": bool(force)}
    try:
        _claim_projected_action_attempt(
            projected_action_proof=projected_action_proof,
            idempotency_key=str(idempotency_key or ""),
            attempt={
                "recipe_id": str(recipe_id),
                "quantity": _qty(Decimal(str(quantity))),
                "target_date": str(target_date_value),
                "position_ref": str(position_ref or ""),
                "operator_ref": str(operator_ref or ""),
                "source_ref": str(source_ref or ""),
                "work_order_id": str(work_order_id or ""),
                "expected_rev": expected_rev,
                "planning_meta": planning_meta or {},
                "create_new": bool(create_new),
            },
        )
        replay = production_core.replay_planned_quantity(
            recipe_id=recipe_id,
            quantity=quantity,
            target_date_value=target_date_value,
            position_ref=position_ref,
            operator_ref=operator_ref,
            reason=reason,
            actor=actor,
            source_ref=source_ref,
            idempotency_key=attempt_key,
            attempt_payload=attempt_payload,
            planning_meta=planning_meta,
            work_order_id=work_order_id,
            create_new=create_new,
        )
        if replay:
            return replay
        with transaction.atomic():
            # This lock contains the order-coverage read and the cell write in
            # one transaction.  The core acquires the same lock defensively for
            # non-backstage callers.
            Recipe.objects.select_for_update().get(pk=recipe_id, is_active=True)
            resolved_position_ref = _locked_planning_position_ref(position_ref)
            replay = production_core.replay_planned_quantity(
                recipe_id=recipe_id,
                quantity=quantity,
                target_date_value=target_date_value,
                position_ref=position_ref,
                operator_ref=operator_ref,
                reason=reason,
                actor=actor,
                source_ref=source_ref,
                idempotency_key=attempt_key,
                attempt_payload=attempt_payload,
                planning_meta=planning_meta,
                work_order_id=work_order_id,
                create_new=create_new,
            )
            if replay:
                return replay
            shortage = _check_linked_order_coverage(
                recipe_id=recipe_id,
                quantity=quantity,
                target_date_value=target_date_value,
                position_ref=resolved_position_ref,
                operator_ref=operator_ref,
                work_order_id=work_order_id,
                create_new=create_new,
            )
            if force:
                _require_approved_shortage_snapshot(
                    approved_shortage,
                    shortage,
                )
            if shortage and not force:
                raise shortage
            result = production_core.set_planned_quantity(
                recipe_id=recipe_id,
                quantity=quantity,
                target_date_value=target_date_value,
                position_ref=position_ref,
                operator_ref=operator_ref,
                reason=reason,
                actor=actor,
                source_ref=source_ref,
                expected_rev=expected_rev,
                idempotency_key=attempt_key,
                attempt_payload=attempt_payload,
                planning_meta=planning_meta,
                work_order_id=work_order_id,
                resolved_position_ref=resolved_position_ref,
                create_new=create_new,
            )
            if shortage:
                _record_shortage_override(
                    work_order_ref=result[1] or shortage.work_order_ref,
                    action="plan",
                    reason=reason,
                    actor=actor,
                    client_key=idempotency_key,
                    impact={
                        "kind": "order_shortage",
                        "required": _qty(shortage.required),
                        "requested": _qty(shortage.requested),
                        "order_refs": list(shortage.order_refs),
                    },
                )
            return result
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def _locked_planning_position_ref(position_ref: str) -> str:
    """Resolve the default once while preventing a concurrent default swap."""
    requested = str(position_ref or "").strip()
    if requested:
        return requested

    from shopman.stockman.models import Position

    positions = list(Position.objects.select_for_update().order_by("pk"))
    default = next((position for position in positions if position.is_default), None)
    return default.ref if default is not None else ""


def apply_start(
    *,
    work_order_id,
    quantity,
    position_id="",
    operator_ref: str = "",
    note: str = "",
    actor: str,
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
):
    """Start a planned work order from the operator surface."""
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    quantity = _positive_quantity(quantity)
    try:
        with transaction.atomic():
            attempt_key = _mutation_idempotency_key("start", work_order_id, idempotency_key)
            work_order, locked_output_work_orders = _lock_output_work_orders(work_order_id)
            # A committed retry must be validated from its frozen attempt
            # before current demand or catalogs can affect the answer.
            if attempt_key and WorkOrderEvent.objects.filter(idempotency_key=attempt_key).exists():
                return production_core.start_work_order(
                    work_order_id=work_order_id,
                    quantity=quantity,
                    position_id=position_id,
                    operator_ref=operator_ref,
                    note=note,
                    actor=actor,
                    expected_rev=expected_rev,
                    idempotency_key=attempt_key,
                )
            shortage = _locked_work_order_order_shortage(
                work_order,
                candidate_work_orders=locked_output_work_orders,
                requested_quantity=Decimal(str(quantity)),
            )
            if shortage is not None:
                raise shortage
            return production_core.start_work_order(
                work_order_id=work_order_id,
                quantity=quantity,
                position_id=position_id,
                operator_ref=operator_ref,
                note=note,
                actor=actor,
                expected_rev=expected_rev,
                idempotency_key=attempt_key,
            )
    except WorkOrder.DoesNotExist:
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


# Teto de sanidade da duração armada: um timer de forno não passa de 24h.
OVEN_MAX_PLANNED_SECONDS = 86_400


def _abandon_open_oven_run(
    work_order,
    *,
    actor: str,
    transition: str,
    reason: str,
    run_id=None,
):
    """Close an impossible open oven measurement with an append-only fact."""
    from shopman.craftsman.models import WorkOrderEvent
    from shopman.craftsman.services.scheduling import _next_seq

    from shopman.backstage.models import OvenRun

    runs = OvenRun.objects.select_for_update().filter(
        work_order_ref=work_order.ref,
        status="open",
    )
    if run_id is not None:
        runs = runs.filter(pk=run_id)
    run = runs.order_by("pk").first()
    if run is None:
        return None

    run.status = "abandoned"
    run.metadata = {
        **(run.metadata or {}),
        "abandoned_at": timezone.now().isoformat(),
        "abandoned_by": str(actor or ""),
        "abandoned_reason": reason,
        "terminal_transition": transition,
    }
    run.save(update_fields=["status", "metadata"])
    WorkOrderEvent.objects.create(
        work_order=work_order,
        seq=_next_seq(work_order),
        kind=WorkOrderEvent.Kind.OVEN_ABANDONED,
        payload={
            "run_id": run.pk,
            "oven_ref": run.oven_ref,
            "transition": transition,
            "reason": reason,
        },
        actor=actor or "",
        idempotency_key=(f"production.oven-abandon:{transition}:{work_order.pk}:{run.pk}"),
    )
    return run


def apply_oven_arm(
    *,
    work_order_id,
    planned_seconds,
    operator_ref: str = "",
    actor: str = "",
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
):
    """Registra a declaração "enfornou" (ADR-021 §4, BI-PLAN §4).

    O servidor carimba ``armed_at`` no recebimento — mesmo tratamento de
    ``started_at``/``finished_at`` da WorkOrder; sem relógio de cliente.
    Um novo arm enquanto existe run aberto é conflito: a projeção oferece
    apenas ``oven_conclude`` nesse estado, portanto não existe ação autêntica
    de re-arm. Runs abertos só são abandonados por transições de lifecycle.
    """
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.scheduling import _check_rev, _next_seq

    from shopman.backstage.models import OvenRun

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    try:
        seconds = int(planned_seconds)
    except (TypeError, ValueError):
        raise ProductionError("Duração do timer inválida.") from None
    if not 0 < seconds <= OVEN_MAX_PLANNED_SECONDS:
        raise ProductionError("Duração do timer inválida.")

    arm_key = _mutation_idempotency_key("oven-arm", work_order_id, idempotency_key)
    try:
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().select_related("recipe").get(pk=work_order_id)
            if arm_key:
                replay = OvenRun.objects.select_for_update().filter(arm_idempotency_key=arm_key).first()
                if replay:
                    replay_event = WorkOrderEvent.objects.filter(
                        idempotency_key=arm_key,
                        kind=WorkOrderEvent.Kind.OVEN_ARMED,
                    ).first()
                    if (
                        replay.work_order_ref != work_order.ref
                        or replay.planned_seconds != seconds
                        or replay.operator_ref != (operator_ref or actor)
                        or replay_event is None
                        or replay_event.actor != actor
                    ):
                        raise ProductionConflict(
                            "Esta tentativa de forno já foi usada com outros dados.",
                            code="conflict",
                            data={
                                "work_order": work_order.ref,
                                "expected_rev": expected_rev,
                                "current_rev": work_order.rev,
                                "cause": "idempotency_conflict",
                            },
                        )
                    return replay
            if work_order.status != WorkOrder.Status.STARTED:
                raise ProductionConflict(
                    "Só é possível enfornar uma ordem iniciada.",
                    code="conflict",
                    data={
                        "work_order": work_order.ref,
                        "expected_rev": expected_rev,
                        "current_rev": work_order.rev,
                        "current_status": work_order.status,
                        "cause": "invalid_status",
                    },
                )
            _check_rev(work_order, expected_rev)
            open_run = (
                OvenRun.objects.select_for_update()
                .filter(work_order_ref=work_order.ref, status="open")
                .order_by("-armed_at", "-pk")
                .first()
            )
            if open_run is not None:
                raise ProductionConflict(
                    "Esta fornada já possui uma enfornada aberta. Retire-a antes de registrar outra.",
                    code="conflict",
                    data={
                        "work_order": work_order.ref,
                        "expected_rev": expected_rev,
                        "current_rev": work_order.rev,
                        "cause": "oven_run_open",
                        "run_id": open_run.pk,
                    },
                )
            run = OvenRun.objects.create(
                work_order_ref=work_order.ref,
                oven_ref=work_order.position_ref or "",
                operator_ref=operator_ref or actor,
                planned_seconds=seconds,
                arm_idempotency_key=arm_key,
                metadata={},
            )
            WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=_next_seq(work_order),
                kind=WorkOrderEvent.Kind.OVEN_ARMED,
                payload={
                    "run_id": run.pk,
                    "oven_ref": run.oven_ref,
                    "planned_seconds": seconds,
                },
                actor=actor,
                idempotency_key=arm_key,
            )
        return run
    except WorkOrder.DoesNotExist:
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def apply_oven_conclude(
    *,
    work_order_id,
    actor: str = "",
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
):
    """Registra a declaração "retirou" (o Concluir do timer).

    Sem run aberto não existe fato conciliável: retorna conflito tipado. A UI
    mantém o timer e oferece retry/refresh em vez de declarar sucesso fictício.
    """
    from django.db import transaction
    from shopman.craftsman.exceptions import StaleRevision
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.scheduling import _check_rev, _next_seq

    from shopman.backstage.models import OvenRun

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    conclude_key = _mutation_idempotency_key("oven-conclude", work_order_id, idempotency_key)
    try:
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().get(pk=work_order_id)
            if conclude_key:
                replay = OvenRun.objects.select_for_update().filter(conclude_idempotency_key=conclude_key).first()
                if replay:
                    replay_event = WorkOrderEvent.objects.filter(
                        idempotency_key=conclude_key,
                        kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
                    ).first()
                    if replay.work_order_ref != work_order.ref or replay_event is None or replay_event.actor != actor:
                        raise ProductionConflict(
                            "Esta tentativa de forno já pertence a outra fornada.",
                            code="conflict",
                            data={
                                "work_order": work_order.ref,
                                "expected_rev": expected_rev,
                                "current_rev": work_order.rev,
                                "cause": "idempotency_conflict",
                            },
                        )
                    return replay

            if work_order.status != WorkOrder.Status.STARTED:
                raise ProductionConflict(
                    "Só é possível retirar do forno uma ordem iniciada.",
                    code="conflict",
                    data={
                        "work_order": work_order.ref,
                        "expected_rev": expected_rev,
                        "current_rev": work_order.rev,
                        "current_status": work_order.status,
                        "cause": "invalid_status",
                    },
                )

            run = (
                OvenRun.objects.select_for_update()
                .filter(work_order_ref=work_order.ref, status="open")
                .order_by("-armed_at")
                .first()
            )
            if run is None:
                if expected_rev is not None and work_order.rev != expected_rev:
                    raise StaleRevision(work_order, expected_rev)
                raise ProductionConflict(
                    "Nenhuma enfornada aberta foi encontrada. Atualize o painel.",
                    code="oven_run_missing",
                    data={
                        "work_order": work_order.ref,
                        "expected_rev": expected_rev,
                        "current_rev": work_order.rev,
                    },
                )

            _check_rev(work_order, expected_rev)
            run.status = "concluded"
            run.concluded_at = timezone.now()
            run.conclude_idempotency_key = conclude_key
            run.save(
                update_fields=[
                    "status",
                    "concluded_at",
                    "conclude_idempotency_key",
                ]
            )
            WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=_next_seq(work_order),
                kind=WorkOrderEvent.Kind.OVEN_CONCLUDED,
                payload={"run_id": run.pk, "oven_ref": run.oven_ref},
                actor=actor,
                idempotency_key=conclude_key,
            )
        return run
    except WorkOrder.DoesNotExist:
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def resolve_partition(work_order, *, quantity, quality: str = "", partition=None):
    """Normaliza a entrada do operador na partição da fornada (ADR-017 §4).

    Três formas de entrada, uma saída — ``(finished_items, wasted_items)``:

    - ``partition`` explícita (``[{quantity, quality_grade_ref,
      quality_defect_ref, loss}]``): cada grupo vira linha de OUTPUT; grupo com
      ``loss=True`` é perda declarada pelo operador (o que não saiu do forno) e
      vira WASTE com o motivo, sem grau e sem lote; grupo cujo defeito tem
      ``forces_discard`` também vira WASTE (o veto é resolvido AQUI, antes do
      craft.finish — o core nunca interpreta o defeito).
    - ``quality`` sozinho (a superfície de hoje): partição de um grupo só.
    - nada: um grupo no grau padrão do catálogo.

    Referências desconhecidas ou inativas são rejeitadas. Uma resposta de QC
    nunca pode ser reinterpretada silenciosamente como outra classificação.
    """
    from shopman.shop.models import QualityDefect, QualityGrade

    quantity = _positive_quantity(quantity)

    grade_states = dict(QualityGrade.objects.values_list("ref", "is_active"))
    grades = {
        ref: {"label": label, "markdown_percent": markdown}
        for ref, label, markdown in QualityGrade.objects.filter(is_active=True).values_list(
            "ref", "label", "markdown_percent"
        )
    }
    defaults = list(QualityGrade.objects.filter(is_active=True, is_default=True).values_list("ref", flat=True))
    if len(defaults) != 1:
        raise ProductionError("O catálogo de qualidade precisa ter exatamente um grau padrão ativo.")
    default_ref = defaults[0]
    vetoes = set(QualityDefect.objects.filter(forces_discard=True).values_list("ref", flat=True))
    defect_catalog = {
        ref: {"label": label, "is_active": is_active}
        for ref, label, is_active in QualityDefect.objects.values_list("ref", "label", "is_active")
    }

    if partition is not None and str(quality or "").strip():
        raise ProductionError("Informe quality ou partition, nunca os dois.")
    if partition is not None:
        if not partition:
            raise ProductionError("A partição da fornada não pode ser vazia.")
        try:
            partition = [
                {
                    **group,
                    "quantity": _positive_quantity(group.get("quantity")),
                }
                for group in partition
            ]
            partition_total = sum((group["quantity"] for group in partition), Decimal("0"))
        except (AttributeError, TypeError, ValueError, ArithmeticError, ProductionError) as exc:
            raise ProductionError("Partição da fornada inválida.") from exc
        if partition_total != quantity:
            raise ProductionError("A soma dos grupos deve ser exatamente igual à quantidade total informada.")
    else:
        grade = (quality or "").strip().lower() or default_ref
        if grade not in grades:
            state = "inativo" if grade in grade_states else "desconhecido"
            raise ProductionError(f"Grau de qualidade {state}: {grade}.")
        partition = [{"quantity": quantity, "quality_grade_ref": grade}]

    production_date = work_order.target_date or timezone.localdate()

    finished_items: list[dict] = []
    wasted_items: list[dict] = []
    seen_grade_refs: set[str] = set()
    loss_seen = False
    for group in partition:
        grade = str(group.get("quality_grade_ref") or "").strip().lower() or default_ref
        if grade not in grades:
            state = "inativo" if grade in grade_states else "desconhecido"
            raise ProductionError(f"Grau de qualidade {state}: {grade}.")
        defect = str(group.get("quality_defect_ref") or "").strip().lower()
        if defect and not defect_catalog.get(defect, {}).get("is_active", False):
            state = "inativo" if defect in defect_catalog else "desconhecido"
            raise ProductionError(f"Defeito de qualidade {state}: {defect}.")

        if group.get("loss"):
            # Perda declarada: abaixo do piso não existe grau, existe descarte
            # (QC-FORNADA §2). Carrega o motivo, nunca grau nem lote.
            if loss_seen:
                raise ProductionError("A perda deve ser informada em um único grupo.")
            if not defect:
                raise ProductionError("Perda declarada exige um motivo de qualidade ativo.")
            loss_seen = True
            wasted_items.append(
                {
                    "item_ref": work_order.output_sku,
                    "quantity": group.get("quantity"),
                    "quality_defect_ref": defect,
                }
            )
            continue

        if defect in vetoes:
            # Veto é segurança alimentar: as unidades nunca viram lote com
            # desconto — viram perda, carregando o motivo.
            if loss_seen:
                raise ProductionError("A perda deve ser informada em um único grupo.")
            loss_seen = True
            wasted_items.append(
                {
                    "item_ref": work_order.output_sku,
                    "quantity": group.get("quantity"),
                    "quality_defect_ref": defect,
                }
            )
            continue

        # KISS operacional: o estoque é particionado pelo grau, que governa
        # preço/eligibilidade. Motivos diferentes no mesmo grau não criam
        # sublotes comercialmente distintos; o operador informa o principal.
        if grade in seen_grade_refs:
            raise ProductionError(f"O grau de qualidade {grade} só pode aparecer uma vez na fornada.")
        seen_grade_refs.add(grade)

        grade_fact = grades[grade]
        # Grau e motivo são eixos ortogonais. Razoável/Mínimo descrevem uma
        # divergência mesmo se o gestor configurar temporariamente markdown 0;
        # portanto a causa obrigatória nunca pode depender do preço atual.
        if grade in {"fair", "minimal"} and not defect:
            raise ProductionError("Grau Razoável/Mínimo exige um motivo de qualidade ativo.")

        finished_items.append(
            {
                "item_ref": work_order.output_sku,
                "quantity": group.get("quantity"),
                "quality_grade_ref": grade,
                "quality_defect_ref": defect,
                # A semântica comercial é congelada junto da linha. Retry e
                # reparo nunca consultam o catálogo de qualidade atual.
                "meta": {
                    "quality_contract_version": 1,
                    "quality_markdown_percent": grade_fact["markdown_percent"],
                    # Motivo e grau são ortogonais: nunca preencher causa com
                    # o rótulo do grau. A ausência de motivo permanece vazia.
                    "quality_reason": defect_catalog.get(defect, {}).get("label") or "",
                },
                # N grupos = N lotes: o ref base preserva a fórmula histórica; os
                # grupos seguintes ganham sufixo ordinal.
                "batch_ref": _production_batch_ref(
                    work_order,
                    production_date=production_date,
                    ordinal=len(finished_items) + 1,
                ),
            }
        )

    if not finished_items and not wasted_items:
        raise ProductionError("A conclusão precisa informar produção ou perda.")
    return finished_items, wasted_items


def _production_batch_ref(work_order, *, production_date, ordinal: int) -> str:
    """Build a deterministic batch reference that fits Stockman's 50 chars."""
    base = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}"
    natural = base if ordinal == 1 else f"{base}-{ordinal}"
    if len(natural) <= 50:
        return natural
    digest = hashlib.sha256(natural.encode("utf-8")).hexdigest()[:12]
    prefix = str(work_order.output_sku)[:28].rstrip("-") or "batch"
    return f"{prefix}-{production_date:%Y%m%d}-{digest}"


def _quality_correction_batch_ref(work_order, *, event_seq: int, ordinal: int) -> str:
    """Versioned lot ref for an immutable post-close QC correction."""
    production_date = work_order.target_date or timezone.localdate()
    base = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}-qc{event_seq}-{ordinal}"
    if len(base) <= 50:
        return base
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]
    prefix = str(work_order.output_sku)[:24].rstrip("-") or "batch"
    return f"{prefix}-{production_date:%Y%m%d}-qc{event_seq}-{digest}"


def _quality_correction_attempt(partition, reason: str) -> dict:
    """Canonical client intent stored in the event for exact replay checks."""
    groups = []
    for raw in partition or ():
        groups.append(
            {
                "quantity": _qty(_positive_quantity(raw.get("quantity"))),
                "quality_grade_ref": str(raw.get("quality_grade_ref") or "").strip().lower(),
                "quality_defect_ref": str(raw.get("quality_defect_ref") or "").strip().lower(),
                "loss": bool(raw.get("loss")),
            }
        )
    return {"partition": groups, "reason": str(reason or "").strip()}


def _quality_partition_quantity(groups, *, loss: bool) -> Decimal:
    return sum(
        (Decimal(str(group.get("quantity") or "0")) for group in groups if bool(group.get("loss")) is loss),
        Decimal("0"),
    )


def _saleable_quality_signature(groups) -> tuple:
    """Commercial + explanatory QC fact, excluding versioned batch identity."""
    return tuple(
        sorted(
            (
                str(group.get("quality_grade_ref") or ""),
                str(group.get("quality_defect_ref") or ""),
                _qty(Decimal(str(group.get("quantity") or "0"))),
            )
            for group in groups
            if not bool(group.get("loss"))
        )
    )


def _loss_quality_signature(groups) -> tuple:
    return tuple(
        sorted(
            (
                str(group.get("quality_defect_ref") or ""),
                _qty(Decimal(str(group.get("quantity") or "0"))),
            )
            for group in groups
            if bool(group.get("loss"))
        )
    )


def _quality_group_from_item(item: dict, *, loss: bool, batch_ref: str = "") -> dict:
    meta = dict(item.get("meta") or {})
    return {
        "quantity": _qty(Decimal(str(item.get("quantity") or "0"))),
        "quality_grade_ref": "" if loss else str(item.get("quality_grade_ref") or ""),
        "quality_defect_ref": str(item.get("quality_defect_ref") or ""),
        "loss": loss,
        "batch_ref": "" if loss else batch_ref,
        "markdown_percent": 0 if loss else int(meta.get("quality_markdown_percent") or 0),
        "quality_reason": str(meta.get("quality_reason") or ""),
    }


def _locked_quality_source_stock(work_order, before_partition):
    """Lock and prove that the whole effective saleable output is still present."""
    from shopman.stockman.models import Move, Position, Quant

    expected = _quality_partition_quantity(before_partition, loss=False)
    if expected == 0:
        position = Position.objects.select_for_update().filter(is_saleable=True).order_by("pk").first()
        if position is None:
            raise ProductionConflict(
                "Nenhuma posição de venda está configurada para recuperar estas unidades.",
                code="quality_correction_blocked",
                data={"work_order": work_order.ref, "cause": "missing_saleable_position"},
            )
        return [], position.pk

    batch_refs = [str(group.get("batch_ref") or "") for group in before_partition if not bool(group.get("loss"))]
    if not batch_refs or any(not ref for ref in batch_refs):
        raise ProductionConflict(
            "Esta fornada não possui lotes identificáveis para uma correção segura.",
            code="quality_correction_blocked",
            data={"work_order": work_order.ref, "cause": "missing_batch_traceability"},
        )
    quants = list(
        Quant.objects.select_for_update()
        .filter(sku=work_order.output_sku, target_date__isnull=True, batch__in=batch_refs)
        .order_by("pk")
    )
    present = sum((Decimal(str(quant.quantity)) for quant in quants), Decimal("0"))
    if present != expected:
        raise ProductionConflict(
            "A qualidade não pode ser corrigida porque parte desta fornada já saiu do estoque.",
            code="quality_correction_blocked",
            data={
                "work_order": work_order.ref,
                "cause": "stock_already_changed",
                "expected_quantity": _qty(expected),
                "present_quantity": _qty(present),
            },
        )
    # Qualquer saída anterior torna a localização física ambígua. Os lotes
    # versionados da própria correção só possuem a perna positiva, portanto
    # correções encadeadas continuam possíveis sem aceitar lote já movido.
    disallowed_negative = Move.objects.filter(quant__in=quants, delta__lt=0)
    if disallowed_negative.exists():
        raise ProductionConflict(
            "Parte desta fornada já foi movimentada. Nenhuma alteração foi feita.",
            code="quality_correction_blocked",
            data={"work_order": work_order.ref, "cause": "stock_already_moved"},
        )
    position_ids = {quant.position_id for quant in quants if quant.quantity > 0}
    if len(position_ids) != 1:
        raise ProductionConflict(
            "Esta fornada está distribuída em mais de uma posição. Resolva o estoque antes de corrigir o QC.",
            code="quality_correction_blocked",
            data={"work_order": work_order.ref, "cause": "multiple_stock_positions"},
        )
    return quants, next(iter(position_ids))


def _plan_quality_hold_reassignment(
    holds,
    after_partition,
    *,
    capacities: dict[str, Decimal] | None = None,
    require_all: bool = True,
    work_order_ref: str = "",
):
    """Assign each 1:1 active hold to one compatible corrected grade bucket."""
    from shopman.stockman.services.holds import (
        QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
        QUALITY_GRADE_POLICY_VERSION,
        QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    )

    from shopman.shop.models import QualityGrade

    capacities = (
        dict(capacities)
        if capacities is not None
        else {
            str(group.get("quality_grade_ref") or ""): Decimal(str(group.get("quantity") or "0"))
            for group in after_partition
            if not bool(group.get("loss"))
        }
    )
    ranks = dict(QualityGrade.objects.filter(ref__in=capacities).values_list("ref", "rank"))
    planned = []

    def _priority(hold):
        value = (hold.metadata or {}).get("priority")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 2_147_483_647

    ordered = sorted(
        holds,
        key=lambda hold: (
            _priority(hold),
            len((hold.metadata or {}).get(QUALITY_GRADE_ALLOWLIST_METADATA_KEY) or capacities),
            hold.created_at,
            hold.pk,
        ),
    )
    blocked = []
    for hold in ordered:
        metadata = hold.metadata or {}
        if metadata.get(QUALITY_GRADE_POLICY_VERSION_METADATA_KEY) != QUALITY_GRADE_POLICY_VERSION:
            blocked.append(hold)
            continue
        allowlist = metadata.get(QUALITY_GRADE_ALLOWLIST_METADATA_KEY)
        accepted = set(capacities) if allowlist is None else set(allowlist)
        fits = [
            (remaining, grade_ref)
            for grade_ref, remaining in capacities.items()
            if grade_ref in accepted and remaining >= hold.quantity
        ]
        if not fits:
            blocked.append(hold)
            continue
        # Preserve the strongest customer promise first.  A permissive local
        # hold may accept every grade, but that must not make it absorb the
        # discounted bucket while full-price stock is still available.
        _remaining, grade_ref = max(
            fits,
            key=lambda candidate: (
                ranks.get(candidate[1], 0),
                -candidate[0],
                candidate[1],
            ),
        )
        capacities[grade_ref] -= hold.quantity
        planned.append((hold, grade_ref))
    if blocked and require_all:
        order_refs = set()
        reservation_refs = set()
        for hold in blocked:
            metadata = hold.metadata or {}
            order_ref = str(metadata.get("order_ref") or "").strip()
            reference = str(metadata.get("reference") or "").strip()
            if not order_ref and reference.startswith("order:"):
                order_ref = reference.removeprefix("order:")
            if order_ref:
                order_refs.add(order_ref)
            else:
                reservation_refs.add(reference or hold.hold_id)
        affected_refs = sorted({*order_refs, *reservation_refs})
        noun = "promessa" if len(affected_refs) == 1 else "promessas"
        raise ProductionConflict(
            f"Esta correção deixaria {len(affected_refs)} {noun} ao cliente sem produto. "
            "Nenhuma alteração foi feita. Resolva no Gestor: " + ", ".join(affected_refs),
            code="quality_correction_blocked",
            data={
                "work_order": work_order_ref,
                "cause": "ineligible_holds",
                "order_refs": sorted(order_refs),
                "reservation_refs": sorted(reservation_refs),
                "recovery_label": "Abrir o Gestor",
            },
        )
    return planned, capacities


def _quality_correction_batch_dates(work_order, source_batch):
    """Keep shelf life frozen to the production fact, including total-loss recovery."""
    production_date = getattr(source_batch, "production_date", None) or work_order.target_date or timezone.localdate()
    expiry_date = getattr(source_batch, "expiry_date", None)
    if source_batch is None:
        snapshot = (work_order.meta or {}).get("_recipe_snapshot") or {}
        recipe_meta = snapshot.get("production") or work_order.recipe.meta or {}
        shelf_life_days = recipe_meta.get("shelf_life_days")
        if shelf_life_days in (None, ""):
            from shopman.stockman.shelflife import shelf_life_days_for

            shelf_life_days = shelf_life_days_for(work_order.output_sku)
        if shelf_life_days not in (None, ""):
            expiry_date = production_date + timedelta(days=int(shelf_life_days))
    return production_date, expiry_date


def _apply_quality_stock_reclassification(work_order, before_partition, after_items, *, event_seq: int):
    """Version QC lots while balancing transfers and recording loss reversals."""
    from django.db.models import Q
    from shopman.stockman.models import Batch, Hold, HoldStatus, Move, Quant

    source_quants, position_id = _locked_quality_source_stock(work_order, before_partition)
    active_holds = list(
        Hold.objects.select_for_update()
        .filter(quant__in=source_quants, status__in=(HoldStatus.PENDING, HoldStatus.CONFIRMED))
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
        .order_by("pk")
    )
    provisional = [_quality_group_from_item(item, loss=False, batch_ref="") for item in after_items]
    hold_plan, remaining_capacities = _plan_quality_hold_reassignment(
        active_holds,
        provisional,
        work_order_ref=work_order.ref,
    )

    before_saleable = _quality_partition_quantity(before_partition, loss=False)
    after_saleable = sum(
        (Decimal(str(item.get("quantity") or "0")) for item in after_items),
        Decimal("0"),
    )
    recovered = max(after_saleable - before_saleable, Decimal("0"))
    floating_plan = []
    if recovered > 0:
        floating_holds = list(
            Hold.objects.select_for_update()
            .filter(
                quant__isnull=True,
                sku=work_order.output_sku,
                target_date=work_order.target_date,
                status__in=(HoldStatus.PENDING, HoldStatus.CONFIRMED),
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
            .order_by("created_at", "pk")
        )
        floating_plan, remaining_capacities = _plan_quality_hold_reassignment(
            floating_holds,
            provisional,
            capacities=remaining_capacities,
            require_all=False,
            work_order_ref=work_order.ref,
        )

    source_batch = (
        Batch.objects.filter(ref__in=[group.get("batch_ref") for group in before_partition if group.get("batch_ref")])
        .order_by("pk")
        .first()
    )
    production_date, expiry_date = _quality_correction_batch_dates(work_order, source_batch)
    destination_quants = {}
    after_groups = []
    reason = f"Correção de qualidade: {work_order.ref}"
    move_ids = []
    transfer_in_remaining = min(before_saleable, after_saleable)
    for ordinal, item in enumerate(after_items, start=1):
        batch_ref = _quality_correction_batch_ref(work_order, event_seq=event_seq, ordinal=ordinal)
        meta = dict(item.get("meta") or {})
        batch, created = Batch.objects.get_or_create(
            ref=batch_ref,
            defaults={
                "sku": work_order.output_sku,
                "production_date": production_date,
                "expiry_date": expiry_date,
                "quality_grade_ref": item.get("quality_grade_ref", ""),
                "nonconformity_reason": str(meta.get("quality_reason") or ""),
                "nonconformity_percent": int(meta.get("quality_markdown_percent") or 0),
                "notes": f"Reclassificação QC da fornada {work_order.ref}",
            },
        )
        if not created:
            expected = (
                work_order.output_sku,
                str(item.get("quality_grade_ref") or ""),
                int(meta.get("quality_markdown_percent") or 0),
                str(meta.get("quality_reason") or ""),
            )
            actual = (
                batch.sku,
                batch.quality_grade_ref,
                batch.nonconformity_percent,
                batch.nonconformity_reason,
            )
            if actual != expected:
                raise ProductionConflict(
                    "O lote versionado da correção já existe com outro conteúdo.",
                    data={"work_order": work_order.ref, "cause": "correction_batch_conflict"},
                )
        quant, _ = Quant.objects.get_or_create(
            sku=work_order.output_sku,
            position_id=position_id,
            target_date=None,
            batch=batch_ref,
            defaults={"metadata": {"production_qc_correction": work_order.ref}},
        )
        quant = Quant.objects.select_for_update().get(pk=quant.pk)
        if quant.quantity != 0:
            raise ProductionConflict(
                "O saldo do lote versionado da correção não está vazio.",
                data={"work_order": work_order.ref, "cause": "correction_quant_conflict"},
            )
        quantity = Decimal(str(item.get("quantity") or "0"))
        transfer_quantity = min(quantity, transfer_in_remaining)
        if transfer_quantity > 0:
            move = Move.objects.create(
                quant=quant,
                delta=transfer_quantity,
                reason=reason,
                kind=Move.Kind.TRANSFER,
                metadata={
                    "operation": "production_qc_correction",
                    "work_order_ref": work_order.ref,
                    "event_seq": event_seq,
                    "direction": "in",
                },
            )
            move_ids.append(move.pk)
            transfer_in_remaining -= transfer_quantity
        recovery_quantity = quantity - transfer_quantity
        if recovery_quantity > 0:
            move = Move.objects.create(
                quant=quant,
                delta=recovery_quantity,
                reason=f"Perda revertida após conferência: {work_order.ref}",
                kind=Move.Kind.WASTE,
                metadata={
                    "operation": "production_qc_correction",
                    "work_order_ref": work_order.ref,
                    "event_seq": event_seq,
                    "direction": "loss_recovery",
                },
            )
            move_ids.append(move.pk)
        destination_quants[str(item.get("quality_grade_ref") or "")] = quant
        after_groups.append(_quality_group_from_item(item, loss=False, batch_ref=batch_ref))

    for hold, grade_ref in [*hold_plan, *floating_plan]:
        hold.quant = destination_quants[grade_ref]
        hold.save(update_fields=["quant"])

    transfer_out_remaining = min(before_saleable, after_saleable)
    for quant in source_quants:
        quantity = Decimal(str(quant.quantity))
        if quantity <= 0:
            continue
        transfer_quantity = min(quantity, transfer_out_remaining)
        if transfer_quantity > 0:
            move = Move.objects.create(
                quant=quant,
                delta=-transfer_quantity,
                reason=reason,
                kind=Move.Kind.TRANSFER,
                metadata={
                    "operation": "production_qc_correction",
                    "work_order_ref": work_order.ref,
                    "event_seq": event_seq,
                    "direction": "out",
                },
            )
            move_ids.append(move.pk)
            transfer_out_remaining -= transfer_quantity
        waste_quantity = quantity - transfer_quantity
        if waste_quantity > 0:
            move = Move.objects.create(
                quant=quant,
                delta=-waste_quantity,
                reason=f"Perda confirmada na revisão do QC: {work_order.ref}",
                kind=Move.Kind.WASTE,
                metadata={
                    "operation": "production_qc_correction",
                    "work_order_ref": work_order.ref,
                    "event_seq": event_seq,
                    "direction": "loss",
                },
            )
            move_ids.append(move.pk)

    if floating_plan:
        from django.db import transaction
        from shopman.stockman.signals import holds_materialized

        materialized_ids = [hold.hold_id for hold, _grade_ref in floating_plan]

        def _emit_materialized():
            holds_materialized.send(
                sender=_apply_quality_stock_reclassification,
                hold_ids=materialized_ids,
                sku=work_order.output_sku,
                target_date=work_order.target_date,
                to_position=destination_quants[next(iter(destination_quants))].position,
            )

        transaction.on_commit(_emit_materialized)
    return after_groups, {
        "stock_reclassified": True,
        "from_batch_refs": sorted({quant.batch for quant in source_quants}),
        "to_batch_refs": [group["batch_ref"] for group in after_groups],
        "holds_reassigned": len(hold_plan),
        "holds_materialized": len(floating_plan),
        "move_ids": move_ids,
        "saleable_before": _qty(before_saleable),
        "saleable_after": _qty(after_saleable),
        "loss_delta": _qty(before_saleable - after_saleable),
    }


def _quality_correction_replay(*, event_key: str, work_order_id, actor: str, attempt: dict):
    """Resolve an exact retry, including one that waited on the WO lock."""
    from shopman.craftsman.models import WorkOrderEvent

    replay = WorkOrderEvent.objects.select_related("work_order").filter(idempotency_key=event_key).first()
    if replay is None:
        return None
    if (
        replay.kind != WorkOrderEvent.Kind.QUALITY_CORRECTED
        or replay.work_order_id != work_order_id
        or replay.actor != str(actor or "")
        or (replay.payload or {}).get("attempt") != attempt
    ):
        raise ProductionConflict(
            "Esta chave de tentativa já foi usada em outra correção.",
            data={"work_order": replay.work_order.ref, "cause": "idempotency_conflict"},
        )
    return replay.work_order


def _quality_review_replay(*, event_key: str, work_order_id, actor: str, expected_rev: int):
    """Return an exact manager QC confirmation retry."""
    from shopman.craftsman.models import WorkOrderEvent

    replay = WorkOrderEvent.objects.select_related("work_order").filter(idempotency_key=event_key).first()
    if replay is None:
        return None
    if (
        replay.kind != WorkOrderEvent.Kind.QUALITY_REVIEWED
        or replay.work_order_id != work_order_id
        or replay.actor != str(actor or "")
        or (replay.payload or {}).get("attempt")
        != {"work_order_id": work_order_id, "expected_rev": expected_rev}
    ):
        raise ProductionConflict(
            "Esta chave de tentativa já foi usada em outra revisão.",
            data={"work_order": replay.work_order.ref, "cause": "idempotency_conflict"},
        )
    return replay.work_order


def _emit_quality_reviewed(work_order_id: int) -> None:
    """Publish the canonical review fact only after its transaction commits."""
    from django.db import transaction

    def emit() -> None:
        from shopman.craftsman.models import WorkOrder
        from shopman.craftsman.signals import production_changed

        work_order = WorkOrder.objects.get(pk=work_order_id)
        production_changed.send(
            sender=_emit_quality_reviewed,
            product_ref=work_order.output_sku,
            date=work_order.target_date,
            action="quality_reviewed",
            work_order=work_order,
        )

    transaction.on_commit(emit)


def apply_quality_review(
    *,
    work_order_id,
    actor: str,
    expected_rev: int | None,
    idempotency_key: str | None,
):
    """Confirm the effective QC partition without rewriting production facts."""
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.scheduling import _check_rev, _next_seq

    from shopman.shop.services import quality as quality_service

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    event_key = _mutation_idempotency_key("quality-review", work_order_id, idempotency_key)
    try:
        with transaction.atomic():
            replay = _quality_review_replay(
                event_key=event_key,
                work_order_id=work_order_id,
                actor=actor,
                expected_rev=expected_rev,
            )
            if replay is not None:
                return replay

            work_order = WorkOrder.objects.select_for_update().filter(pk=work_order_id).first()
            if work_order is None:
                raise ProductionNotFound(
                    "Ordem de produção não encontrada.",
                    resource="work_order",
                    identifier=str(work_order_id),
                )
            replay = _quality_review_replay(
                event_key=event_key,
                work_order_id=work_order_id,
                actor=actor,
                expected_rev=expected_rev,
            )
            if replay is not None:
                return replay
            if work_order.status != WorkOrder.Status.FINISHED:
                raise ProductionConflict(
                    "Conclua a fornada antes de revisar a qualidade.",
                    data={"work_order": work_order.ref, "cause": "quality_review_requires_finished"},
                )
            if WorkOrderEvent.objects.filter(
                work_order=work_order,
                kind__in=(
                    WorkOrderEvent.Kind.QUALITY_REVIEWED,
                    WorkOrderEvent.Kind.QUALITY_CORRECTED,
                ),
            ).exists():
                raise ProductionConflict(
                    "A qualidade desta fornada já foi revisada.",
                    data={"work_order": work_order.ref, "cause": "quality_already_reviewed"},
                )

            _check_rev(work_order, expected_rev)
            partition = quality_service.effective_partition(work_order)
            if not partition:
                raise ProductionError("A fornada não possui fatos de qualidade para revisar.")
            event = WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=_next_seq(work_order),
                kind=WorkOrderEvent.Kind.QUALITY_REVIEWED,
                payload={
                    "schema_version": 1,
                    "partition": partition,
                    "attempt": {
                        "work_order_id": work_order.pk,
                        "expected_rev": expected_rev,
                    },
                },
                actor=actor,
                idempotency_key=event_key,
            )
            _emit_quality_reviewed(work_order.pk)
            work_order.refresh_from_db(fields=["rev"])
            logger.info(
                "production.quality_reviewed wo=%s event=%s actor=%s",
                work_order.ref,
                event.pk,
                actor,
            )
            return work_order
    except (ProductionError, ProductionNotFound, ProductionConflict):
        raise
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def _record_quality_hold_risk(exc: ProductionConflict) -> None:
    """Keep a blocked physical correction visible after its transaction rolls back."""
    data = dict(getattr(exc, "data", {}) or {})
    if data.get("cause") != "ineligible_holds":
        return
    work_order_ref = str(data.get("work_order") or "")
    if not work_order_ref:
        return

    from shopman.shop.adapters import alert as alert_adapter

    affected = [*data.get("order_refs", []), *data.get("reservation_refs", [])]
    if not alert_adapter.recent_exists(
        "production_quality_hold_risk",
        timezone.now(),
        order_ref=work_order_ref,
    ):
        alert_adapter.create(
            "production_quality_hold_risk",
            "critical",
            (
                f"{work_order_ref}: a correção física foi interrompida para proteger "
                f"{len(affected)} promessa(s) ao cliente. Resolva no Gestor antes de repetir."
            ),
            order_ref=work_order_ref,
        )
    for order_ref in data.get("order_refs", []):
        if alert_adapter.recent_exists(
            "order_production_quality_risk",
            timezone.now(),
            order_ref=order_ref,
        ):
            continue
        alert_adapter.create(
            "order_production_quality_risk",
            "critical",
            (
                f"O pedido {order_ref} foi protegido: uma correção física de {work_order_ref} "
                "reduziria sua cobertura. Combine substituição, próxima fornada ou reembolso "
                "com o cliente antes de liberar a reserva."
            ),
            order_ref=order_ref,
        )


def apply_quality_correction(
    *,
    work_order_id,
    partition,
    reason: str,
    actor: str,
    expected_rev: int | None,
    idempotency_key: str | None,
):
    """Correct post-close QC without rewriting the immutable closing lines."""
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.scheduling import _check_rev, _next_seq

    from shopman.shop.services import campaign as campaign_service
    from shopman.shop.services import quality as quality_service

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    audit_reason = str(reason or "").strip()
    if not audit_reason:
        raise ProductionError("Informe por que a qualidade está sendo corrigida.")
    attempt = _quality_correction_attempt(partition, audit_reason)
    event_key = _mutation_idempotency_key("quality-correction", work_order_id, idempotency_key)
    try:
        with transaction.atomic():
            replay = _quality_correction_replay(
                event_key=event_key,
                work_order_id=work_order_id,
                actor=actor,
                attempt=attempt,
            )
            if replay is not None:
                return replay

            work_order = WorkOrder.objects.select_for_update().filter(pk=work_order_id).first()
            if work_order is None:
                raise ProductionNotFound(
                    "Ordem de produção não encontrada.",
                    resource="work_order",
                    identifier=str(work_order_id),
                )
            # Two identical requests can both miss the optimistic lookup; the
            # loser then waits here while the winner commits.  Re-read after
            # acquiring the aggregate lock so a lost response is replayed
            # instead of being misreported as a stale revision.
            replay = _quality_correction_replay(
                event_key=event_key,
                work_order_id=work_order_id,
                actor=actor,
                attempt=attempt,
            )
            if replay is not None:
                return replay
            if work_order.status != WorkOrder.Status.FINISHED:
                raise ProductionConflict(
                    "Somente uma fornada concluída pode ter a qualidade corrigida.",
                    data={"work_order": work_order.ref, "cause": "quality_correction_requires_finished"},
                )
            if work_order.rev != expected_rev:
                from shopman.craftsman.exceptions import StaleRevision

                raise StaleRevision(work_order, expected_rev)

            before = quality_service.effective_partition(work_order)
            if not before:
                raise ProductionConflict(
                    "A partição original desta fornada não pôde ser identificada.",
                    code="quality_correction_blocked",
                    data={"work_order": work_order.ref, "cause": "missing_quality_partition"},
                )
            total = _quality_partition_quantity(before, loss=False) + _quality_partition_quantity(before, loss=True)
            finished_items, wasted_items = resolve_partition(
                work_order,
                quantity=total,
                partition=partition,
            )
            provisional = [
                *(_quality_group_from_item(item, loss=False) for item in finished_items),
                *(_quality_group_from_item(item, loss=True) for item in wasted_items),
            ]
            before_saleable = _quality_partition_quantity(before, loss=False)
            before_loss = _quality_partition_quantity(before, loss=True)
            after_saleable = _quality_partition_quantity(provisional, loss=False)
            after_loss = _quality_partition_quantity(provisional, loss=True)
            if after_saleable + after_loss != total:
                raise ProductionError("A soma da correção deve manter o total contabilizado da fornada.")
            saleable_changed = _saleable_quality_signature(before) != _saleable_quality_signature(provisional)
            loss_changed = _loss_quality_signature(before) != _loss_quality_signature(provisional)
            if not saleable_changed and not loss_changed:
                raise ProductionError("Nenhuma alteração de qualidade foi informada.")

            _check_rev(work_order, expected_rev)
            event_seq = _next_seq(work_order)
            if saleable_changed:
                saleable_groups, stock_impact = _apply_quality_stock_reclassification(
                    work_order,
                    before,
                    finished_items,
                    event_seq=event_seq,
                )
            else:
                saleable_groups = [dict(group) for group in before if not bool(group.get("loss"))]
                stock_impact = {
                    "stock_reclassified": False,
                    "holds_reassigned": 0,
                    "holds_materialized": 0,
                    "move_ids": [],
                    "saleable_before": _qty(before_saleable),
                    "saleable_after": _qty(after_saleable),
                    "loss_delta": _qty(after_loss - before_loss),
                }
            after = [
                *saleable_groups,
                *(_quality_group_from_item(item, loss=True) for item in wasted_items),
            ]
            communication_impact = campaign_service.reconcile_quality_correction(
                work_order,
                after,
            )
            impact = {
                **stock_impact,
                "communications": communication_impact,
            }
            from shopman.backstage.services.alerts import resolve_alerts

            impact["resolved_production_risks"] = resolve_alerts(
                "production_quality_hold_risk",
                order_ref=work_order.ref,
                actor="production:quality-correction",
            )
            # ``finished`` is the current saleable aggregate consumed by legacy
            # projections. The original FINISHED event and WorkOrderItems stay
            # untouched; this correction event is the immutable authority for
            # the new aggregate.
            work_order.finished = after_saleable
            work_order.save(update_fields=["finished", "updated_at"])
            irreversible = communication_impact["irreversible_announcements"]
            if irreversible:
                from shopman.shop.adapters import alert as alert_adapter

                alert_adapter.create(
                    "production_quality_communication",
                    "warning",
                    (
                        f"A qualidade de {work_order.ref} foi corrigida depois que "
                        f"{len(irreversible)} comunicação(ões) já havia(m) saído ou iniciado. "
                        "Confira a fornada e o histórico de Marketing."
                    ),
                    order_ref=work_order.ref,
                )
            event = WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=event_seq,
                kind=WorkOrderEvent.Kind.QUALITY_CORRECTED,
                payload={
                    "schema_version": 2,
                    "reason": audit_reason,
                    "total_accounted": _qty(total),
                    "saleable_before": _qty(before_saleable),
                    "saleable_after": _qty(after_saleable),
                    "loss_before": _qty(before_loss),
                    "loss_after": _qty(after_loss),
                    "before_partition": before,
                    "after_partition": after,
                    "impact": impact,
                    "attempt": attempt,
                },
                actor=actor,
                idempotency_key=event_key,
            )
            _emit_quality_reviewed(work_order.pk)
            work_order.refresh_from_db(fields=["rev"])
            logger.info(
                "production.quality_corrected wo=%s event=%s actor=%s stock=%s",
                work_order.ref,
                event.pk,
                actor,
                saleable_changed,
            )
            return work_order
    except ProductionConflict as exc:
        try:
            _record_quality_hold_risk(exc)
        except Exception:
            logger.exception("production.quality_hold_risk_alert_failed")
        raise
    except (ProductionError, ProductionNotFound):
        raise
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)


def apply_finish(
    *,
    work_order_id,
    quantity,
    actor: str,
    force: bool = False,
    quality: str = "",
    partition=None,
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
    override_reason: str = "",
    override_action: str = "finish",
    yield_deviation_confirmed: bool = False,
    yield_deviation_reason: str = "",
    allow_implicit_start: bool = False,
    approved_shortage: dict | None = None,
):
    """Finish a work order from the operator surface — escalar ou particionado.

    ``expected_rev``: ver ``apply_void``. Convive com a chave de idempotência sem
    conflito — uma responde "é o MESMO gesto de novo?", a outra "o quadro que você leu
    ainda vale?". A primeira devolve o resultado anterior; a segunda recusa.

    ``set_quality``/``meta["quality"]`` morreram (ADR-017 §3): a qualidade
    agora viaja nas LINHAS de OUTPUT e é derivada de lá por quem precisa
    (broadcast, fomo, relatório). O grau único da superfície de hoje é só uma
    partição de um grupo.
    """
    from django.db import transaction
    from shopman.craftsman.exceptions import CraftError, StaleRevision
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    quantity = _positive_quantity(quantity)
    try:
        with transaction.atomic():
            work_order, locked_output_work_orders = _lock_output_work_orders(work_order_id)
            finish_key = _finish_idempotency_key(
                work_order,
                quantity=quantity,
                quality=quality,
                partition=partition,
                force=force,
                override_reason=override_reason,
                yield_deviation_confirmed=yield_deviation_confirmed,
                yield_deviation_reason=yield_deviation_reason,
                client_key=idempotency_key,
            )
            replay = WorkOrderEvent.objects.filter(
                work_order=work_order,
                kind=WorkOrderEvent.Kind.FINISHED,
                idempotency_key=finish_key,
            ).first()
            if replay:
                if replay.actor != str(actor or ""):
                    raise ProductionConflict(
                        "Esta tentativa pertence a outro operador.",
                        code="conflict",
                        data={
                            "work_order": work_order.ref,
                            "current_rev": work_order.rev,
                            "expected_rev": expected_rev,
                            "cause": "idempotency_conflict",
                        },
                    )
                _record_batch_traceability(
                    work_order_id=work_order_id,
                    replay=True,
                )
                return production_core.finish_work_order(
                    work_order_id=work_order_id,
                    quantity=replay.payload["finished_qty"],
                    actor=actor,
                    idempotency_key=finish_key,
                    expected_rev=expected_rev,
                    idempotent_summary_replay=True,
                )

            if work_order.status in (
                WorkOrder.Status.FINISHED,
                WorkOrder.Status.VOID,
            ):
                raise CraftError(
                    "TERMINAL_STATUS",
                    status=work_order.status,
                    work_order=work_order.ref,
                    expected_rev=expected_rev,
                    current_rev=work_order.rev,
                )
            if work_order.status != WorkOrder.Status.STARTED and not (
                allow_implicit_start and work_order.status == WorkOrder.Status.PLANNED
            ):
                raise ProductionConflict(
                    "Inicie a fornada antes de concluir o QC.",
                    data={
                        "work_order": work_order.ref,
                        "expected_rev": expected_rev,
                        "current_rev": work_order.rev,
                        "cause": "finish_requires_started",
                    },
                )
            if expected_rev is not None and work_order.rev != expected_rev:
                raise StaleRevision(work_order, expected_rev)

            finished_items, wasted_items = resolve_partition(
                work_order,
                quantity=quantity,
                quality=quality,
                partition=partition,
            )
            saleable_quantity = sum(
                (Decimal(str(item["quantity"])) for item in finished_items),
                Decimal("0"),
            )
            reported_quantity = Decimal(str(quantity))
            yield_anchor = work_order.started_qty
            if yield_anchor is None:
                yield_anchor = Decimal(str(work_order.quantity))
            yield_deviation = reported_quantity - yield_anchor
            if yield_deviation < 0:
                raise ProductionError(
                    "A quantidade total deve incluir toda perda da fornada. "
                    "Classifique o déficit com quantidade e motivo."
                )
            deviation_context = None
            if yield_deviation > 0:
                deviation_reason = str(yield_deviation_reason or "").strip()
                if yield_deviation_confirmed is not True:
                    raise ProductionError("Confirme explicitamente a produção acima da quantidade iniciada.")
                if not deviation_reason:
                    raise ProductionError("Informe o motivo da produção acima da quantidade iniciada.")
                deviation_context = {
                    "kind": "yield_overshoot",
                    "anchor_qty": _qty(yield_anchor),
                    "reported_qty": _qty(reported_quantity),
                    "saleable_qty": _qty(saleable_quantity),
                    "deviation_qty": _qty(yield_deviation),
                    "confirmed": True,
                    "reason": deviation_reason,
                    "actor": str(actor or ""),
                }

            # A finished link currently represents the whole order/SKU demand;
            # there is no approved partial-allocation contract.  Therefore a
            # finish that yields less saleable output than its linked demand
            # must fail closed. ``force`` on this endpoint only overrides
            # material availability, never customer demand truth.
            order_shortage = _locked_work_order_order_shortage(
                work_order,
                candidate_work_orders=locked_output_work_orders,
                requested_quantity=sum(
                    (Decimal(str(item["quantity"])) for item in finished_items),
                    Decimal("0"),
                ),
            )
            if order_shortage is not None:
                raise order_shortage

            missing = check_finish_materials(work_order)
            if force:
                current_shortage = (
                    ProductionStockShortError(
                        work_order_ref=work_order.ref,
                        missing=missing,
                    )
                    if missing
                    else None
                )
                _require_approved_shortage_snapshot(
                    approved_shortage,
                    current_shortage,
                )
            if missing and not force:
                raise ProductionStockShortError(
                    work_order_ref=work_order.ref,
                    missing=missing,
                )
            if missing and not str(override_reason or "").strip():
                raise ProductionError("Justificativa é obrigatória para forçar uma falta.")

            if missing:
                # The stock receiver runs synchronously inside finish and must
                # see the exact approved deficit. The outer atomic rolls this
                # event back if finish fails; the locked rev lets us record the
                # authoritative post-mutation revision before the signal fires.
                _record_shortage_override(
                    work_order_ref=work_order.ref,
                    action=override_action,
                    reason=override_reason,
                    actor=actor,
                    client_key=idempotency_key,
                    impact={
                        "kind": "material_shortage",
                        "missing": [
                            {
                                "sku": item.sku,
                                "needed": str(item.needed),
                                "available": str(item.available),
                                "shortage": str(item.shortage),
                            }
                            for item in missing
                        ],
                    },
                    resulting_rev=work_order.rev + 1,
                )
            _abandon_open_oven_run(
                work_order,
                actor=actor,
                transition="finish",
                reason="work_order_finished",
            )
            outcome_context = {
                "committed_order_refs": list((work_order.meta or {}).get("committed_order_refs") or ()),
                **(
                    {
                        "production_outcome": {
                            "kind": "total_loss",
                            "saleable_qty": "0",
                            "loss_qty": _qty(reported_quantity),
                        }
                    }
                    if saleable_quantity == 0
                    else {}
                ),
                **({"yield_deviation": deviation_context} if deviation_context is not None else {}),
            }
            result = production_core.finish_work_order(
                work_order_id=work_order_id,
                quantity=quantity,
                actor=actor,
                finished_items=finished_items,
                wasted_items=wasted_items,
                idempotency_key=finish_key,
                expected_rev=expected_rev,
                event_context=outcome_context,
            )
            if missing:
                _create_stock_short_alert(
                    work_order_id=work_order.pk,
                    error=_missing_summary(missing),
                )
            _record_batch_traceability(work_order_id=work_order_id)
    except WorkOrder.DoesNotExist:
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None
    except Exception as exc:
        logger.debug("production_finish_failed", exc_info=True)
        if isinstance(exc, ProductionBatchTraceabilityError):
            try:
                from shopman.shop.handlers.production_alerts import (
                    create_batch_traceability_alert,
                )

                create_batch_traceability_alert(
                    work_order_ref=exc.work_order_ref,
                    output_sku=exc.output_sku,
                    error=str(exc.cause) or type(exc.cause).__name__,
                )
            except Exception:
                logger.warning(
                    "production_batch_traceability_alert_failed work_order_id=%s",
                    work_order_id,
                    exc_info=True,
                )
        if _looks_like_stock_error(exc):
            _create_stock_short_alert(work_order_id=work_order_id, error=str(exc))
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)
    return result


def _lock_output_work_orders(work_order_id):
    """Lock an output-SKU aggregate in the shared PK order."""
    from shopman.craftsman.models import WorkOrder

    target_snapshot = WorkOrder.objects.only("output_sku").get(pk=work_order_id)
    locked = list(
        WorkOrder.objects.select_for_update()
        .select_related("recipe")
        .prefetch_related("recipe__items", "events")
        .filter(output_sku=target_snapshot.output_sku)
        .order_by("pk")
    )
    target = next(
        (candidate for candidate in locked if candidate.pk == target_snapshot.pk),
        None,
    )
    if target is None:
        raise WorkOrder.DoesNotExist
    return target, locked


def _locked_work_order_order_shortage(
    work_order,
    *,
    candidate_work_orders,
    requested_quantity: Decimal,
) -> ProductionOrderShortError | None:
    """Lock and validate active order demand before a terminal finish.

    WorkOrder is already locked by the caller, so this preserves the global
    WorkOrder → Order lock order used by the reconciliation bridge.
    """
    from shopman.orderman.models import Order

    from shopman.shop.handlers.production_order_sync import (
        ACTIVE_ORDER_STATUSES,
        _allocate_pending_links,
        _match_strategy,
    )

    order_ids = list(
        Order.objects.filter(
            status__in=ACTIVE_ORDER_STATUSES,
            items__sku=work_order.output_sku,
        )
        .values_list("pk", flat=True)
        .distinct()
    )
    orders = list(
        Order.objects.select_for_update()
        .filter(pk__in=order_ids, status__in=ACTIVE_ORDER_STATUSES)
        .prefetch_related("items")
        .order_by("pk")
    )
    open_work_orders = [
        candidate
        for candidate in candidate_work_orders
        if candidate.status in (candidate.Status.PLANNED, candidate.Status.STARTED)
    ]
    desired_orders_by_work_order, desired_work_orders_by_order = _allocate_pending_links(
        orders=orders,
        pending_work_orders=open_work_orders,
        all_work_orders=candidate_work_orders,
        strategy=_match_strategy(),
        # Discover the demand owned by this exact target independently of its
        # submitted output. Otherwise a too-small WO is skipped by the
        # allocator and the shortage guard fails open precisely when needed.
        operational_quantities={work_order.ref: Decimal("1e30")},
        preserve_existing=True,
        preferred_work_order_ref=work_order.ref,
    )
    covered_orders = [order for order in orders if work_order.ref in desired_work_orders_by_order.get(order.ref, ())]

    required = sum(
        (item.qty for order in covered_orders for item in order.items.all() if item.sku == work_order.output_sku),
        Decimal("0"),
    )
    if requested_quantity >= required:
        _persist_locked_order_bindings(
            work_orders=open_work_orders,
            candidate_work_orders=candidate_work_orders,
            orders=orders,
            desired_orders_by_work_order=desired_orders_by_work_order,
            desired_work_orders_by_order=desired_work_orders_by_order,
        )
        return None
    return ProductionOrderShortError(
        work_order_ref=work_order.ref,
        required=required,
        requested=requested_quantity,
        order_refs=tuple(order.ref for order in covered_orders),
        allow_override=False,
    )


def _persist_locked_order_bindings(
    *,
    work_orders,
    candidate_work_orders,
    orders,
    desired_orders_by_work_order,
    desired_work_orders_by_order,
) -> None:
    """Persist the complete SKU allocation before a lossy callback can run.

    The caller owns WorkOrder → Order locks.  Writing both denormalized sides
    here makes the allocation recoverable when either post-commit receiver is
    unavailable; a FINISHED work order then remains an authoritative lineage
    witness for the global reconciler.
    """
    from shopman.shop.handlers.production_order_sync import (
        ORDER_AWAITING_WO_REFS_KEY,
        WORK_ORDER_COMMITTED_ORDER_REFS_KEY,
    )

    for work_order in work_orders:
        meta = {**(work_order.meta or {})}
        current_order_refs = list(meta.get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or ())
        # Open-WO refs are an allocation snapshot, not immutable history.
        updated_order_refs = list(dict.fromkeys(desired_orders_by_work_order.get(work_order.ref, ())))
        if updated_order_refs == current_order_refs:
            continue
        if updated_order_refs:
            meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] = updated_order_refs
        else:
            meta.pop(WORK_ORDER_COMMITTED_ORDER_REFS_KEY, None)
        work_order.meta = meta
        work_order.save(update_fields=["meta", "updated_at"])

    candidate_refs = {candidate.ref for candidate in candidate_work_orders}
    for order in orders:
        data = {**(order.data or {})}
        current_work_order_refs = list(data.get(ORDER_AWAITING_WO_REFS_KEY) or ())
        # Preserve allocations for other SKUs, but replace this entire SKU's
        # candidate set so one order cannot remain owned by two output WOs.
        updated_work_order_refs = list(
            dict.fromkeys(
                [
                    *(ref for ref in current_work_order_refs if ref not in candidate_refs),
                    *desired_work_orders_by_order.get(order.ref, ()),
                ]
            )
        )
        if updated_work_order_refs == current_work_order_refs:
            continue
        if updated_work_order_refs:
            data[ORDER_AWAITING_WO_REFS_KEY] = updated_work_order_refs
        else:
            data.pop(ORDER_AWAITING_WO_REFS_KEY, None)
        order.data = data
        order.save(update_fields=["data", "updated_at"])


def _finish_idempotency_key(
    work_order,
    *,
    quantity,
    quality: str,
    partition,
    force: bool,
    override_reason: str,
    yield_deviation_confirmed: bool,
    yield_deviation_reason: str,
    client_key: str | None = None,
) -> str:
    """Chave estável do fechamento: mesma fornada, mesmo resultado, mesma chave.

    O core devolve a WO existente quando a chave se repete, então o retry do
    operador depois de um erro que veio DEPOIS do commit para de morrer em
    ``TERMINAL_STATUS`` — o hazard em que um receiver posterior estoura e a
    fornada fica correta no banco e impossível de fechar na tela.

    A chave sai do request canônico antes de consultar catálogos mutáveis. Isso
    permite replay mesmo se o grau padrão mudar ou uma opção for desativada
    depois do commit. Reusar a tentativa com outro request gera outra chave e
    cai no conflito terminal, nunca num replay silencioso.

    Derivada no servidor, sem contrato novo com a superfície: o quiosque
    reenvia o mesmo POST e a chave cai igual sozinha.
    """
    import hashlib
    import json

    payload = json.dumps(
        {
            "work_order": work_order.pk,
            "quantity": quantity,
            "quality": str(quality or "").strip().lower(),
            "partition": partition,
            "force": force,
            "override_reason": str(override_reason or "").strip(),
            "yield_deviation_confirmed": yield_deviation_confirmed is True,
            "yield_deviation_reason": str(yield_deviation_reason or "").strip(),
        },
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    attempt = str(client_key or "").strip()
    if attempt:
        return f"production.finish:{work_order.pk}:{attempt}:{digest}"
    return f"production.finish:{work_order.pk}:{digest}"


def apply_advance_step(
    *,
    work_order_id,
    actor: str,
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
) -> int:
    """Advance the manual step pointer of a STARTED work order by one.

    Stores the new index in ``WorkOrder.meta["steps_progress"]`` (1-based).
    Returns the new step index. Capped at the number of recipe steps.
    Raises ProductionError if the work order is not in STARTED state or has
    no recipe steps.
    """
    from django.db import transaction
    from shopman.craftsman.exceptions import StaleRevision
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.execution import CraftExecution

    _require_irreversible_attempt(
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
    )
    attempt_key = _mutation_idempotency_key("advance-step", work_order_id, idempotency_key)
    try:
        with transaction.atomic():
            work_order = WorkOrder.objects.select_for_update().select_related("recipe").get(pk=work_order_id)
            if attempt_key:
                replay = WorkOrderEvent.objects.filter(idempotency_key=attempt_key).first()
                if replay:
                    if (
                        replay.work_order_id != work_order.pk
                        or replay.kind != WorkOrderEvent.Kind.STEP_ADVANCED
                        or replay.actor != str(actor or "")
                    ):
                        raise ProductionConflict(
                            "Esta tentativa já foi usada em outra ação.",
                            data={"work_order": work_order.ref},
                        )
                    return int(replay.payload["step_index"])

            if work_order.status != WorkOrder.Status.STARTED:
                raise ProductionError("Só é possível avançar passo em ordens iniciadas.")
            if expected_rev is not None and work_order.rev != expected_rev:
                raise StaleRevision(work_order, expected_rev)

            snapshot = (work_order.meta or {}).get("_recipe_snapshot") or {}
            production_snapshot = snapshot.get("production") or {}
            if "steps" in production_snapshot:
                steps = production_snapshot["steps"]
            else:
                steps = (work_order.recipe.meta or {}).get("steps") or work_order.recipe.steps or []
            total = len(steps)
            if total <= 0:
                raise ProductionError("Receita sem passos configurados.")

            current = (work_order.meta or {}).get("steps_progress")
            try:
                current_value = int(current) if current not in (None, "") else 0
            except (TypeError, ValueError):
                current_value = 0
            if current_value >= total:
                raise ProductionConflict(
                    "Todos os passos desta fornada já foram concluídos.",
                    code="conflict",
                    data={
                        "work_order": work_order.ref,
                        "expected_rev": expected_rev,
                        "current_rev": work_order.rev,
                        "cause": "steps_complete",
                    },
                )
            new_index = max(1, current_value + 1)
            CraftExecution.advance_step(
                work_order,
                step_index=new_index,
                step_name=str(steps[new_index - 1].get("name") or "")
                if isinstance(steps[new_index - 1], dict)
                else str(steps[new_index - 1] or ""),
                expected_rev=expected_rev,
                actor=actor,
                idempotency_key=attempt_key,
            )
    except WorkOrder.DoesNotExist:
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None
    except Exception as exc:
        translated = _operator_error(exc)
        raise translated from (None if translated is exc else exc)
    return new_index


def _mutation_idempotency_key(
    action: str,
    work_order_id,
    client_key: str | None,
) -> str | None:
    attempt = str(client_key or "").strip()
    if not attempt:
        return None
    return f"production.{action}:{work_order_id}:{attempt}"


def _csv_safe(value) -> str:
    """Neutraliza injeção de fórmula no CSV do relatório.

    Só o campo textual passa por aqui — número entra formatado e não é tocado.
    A regra (gatilhos, exceção de número puro) vive em
    ``shopman.utils.spreadsheet``, compartilhada com o cofre de backup.
    """
    return escape_cell("" if value is None else str(value))


def export_reports_csv(report_kind: str, filters: dict | None = None) -> bytes:
    """Export a production report as UTF-8 BOM CSV for spreadsheet tools."""
    from shopman.backstage.projections.production import build_production_reports

    requested = dict(filters or {})
    requested["report_kind"] = report_kind
    reports = build_production_reports(requested)
    output = StringIO()
    writer = csv.writer(output)

    if reports.filters.report_kind == "operator_productivity":
        writer.writerow(
            [
                "Operador",
                "Nome",
                "Ordens concluídas",
                "Qtd total",
                "Rendimento médio",
                "Tempo médio (min)",
            ]
        )
        for row in reports.operator_rows:
            writer.writerow(
                [
                    _csv_safe(row.operator_ref),
                    _csv_safe(row.operator_name),
                    row.wo_count,
                    row.qty_total,
                    row.yield_avg,
                    row.duration_avg_minutes,
                ]
            )
    elif reports.filters.report_kind == "quality":
        # Sem este ramo o "quality" caía no else e exportava o HISTÓRICO —
        # o gestor baixava a tabela errada com o nome certo.
        writer.writerow(
            [
                "Receita",
                "Nome",
                "Grau",
                "Defeito",
                "Qtd",
                "% da receita",
            ]
        )
        for row in reports.quality_rows:
            writer.writerow(
                [
                    _csv_safe(row.recipe_ref),
                    _csv_safe(row.recipe_name),
                    _csv_safe(row.grade_label),
                    _csv_safe(row.defect_label),
                    row.quantity,
                    row.share,
                ]
            )
    elif reports.filters.report_kind == "recipe_waste":
        writer.writerow(
            [
                "Receita",
                "Nome",
                "Ordens",
                "Perda total",
                "Rendimento médio",
                "Utilização capacidade",
            ]
        )
        for row in reports.waste_rows:
            writer.writerow(
                [
                    _csv_safe(row.recipe_ref),
                    _csv_safe(row.recipe_name),
                    row.wo_count,
                    row.loss_total,
                    row.yield_avg,
                    row.capacity_utilization,
                ]
            )
    else:
        writer.writerow(
            [
                "Ref",
                "Data",
                "Receita",
                "Nome da receita",
                "Posição",
                "Qtd planejada",
                "Qtd iniciada",
                "Qtd concluída",
                "Perda",
                "Rendimento",
                "Operador",
                "Iniciada em",
                "Concluída em",
                "Duração (min)",
            ]
        )
        for row in reports.history_rows:
            writer.writerow(
                [
                    _csv_safe(row.ref),
                    _csv_safe(row.date),
                    _csv_safe(row.recipe_ref),
                    _csv_safe(row.recipe_name),
                    _csv_safe(row.position_ref),
                    row.qty_planned,
                    row.qty_started,
                    row.qty_finished,
                    row.qty_loss,
                    row.yield_rate,
                    _csv_safe(row.operator_ref),
                    _csv_safe(row.started_at),
                    _csv_safe(row.finished_at),
                    row.duration_minutes,
                ]
            )

    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _check_linked_order_coverage(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str,
    operator_ref: str,
    work_order_id=None,
    create_new: bool = False,
) -> ProductionOrderShortError | None:
    try:
        from types import SimpleNamespace

        from shopman.craftsman.models import Recipe, WorkOrder
        from shopman.orderman.models import Order

        from shopman.shop.handlers.production_order_sync import (
            ACTIVE_ORDER_STATUSES,
            _allocate_pending_links,
            _match_strategy,
        )

        recipe = Recipe.objects.get(pk=recipe_id)
        requested = Decimal(str(quantity or "0"))
        target_date = date.fromisoformat(str(target_date_value))
        resolved_position = str(position_ref or "").strip()
        if not resolved_position:
            from shopman.stockman.models import Position

            resolved_position = Position.objects.filter(is_default=True).values_list("ref", flat=True).first() or ""
        all_work_orders = list(
            WorkOrder.objects.select_for_update()
            .prefetch_related("events")
            .filter(output_sku=recipe.output_sku)
            .order_by("pk")
        )
        open_work_orders = [
            work_order
            for work_order in all_work_orders
            if work_order.status in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED)
        ]
        work_orders = sorted(
            (
                work_order
                for work_order in open_work_orders
                if work_order.recipe_id == recipe.pk
                and work_order.target_date == target_date
                and work_order.position_ref == resolved_position
                and work_order.status == WorkOrder.Status.PLANNED
            ),
            key=lambda work_order: (work_order.created_at, work_order.pk),
        )
        if not create_new and len(work_orders) > 1 and work_order_id in (None, ""):
            raise ProductionConflict(
                "Há mais de uma fornada nesta célula; selecione a referência exata.",
                data={
                    "expected_rev": None,
                    "current_rev": None,
                    "cause": "ambiguous_work_order",
                    "candidates": [work_order.ref for work_order in work_orders],
                },
            )
        order_ids = list(
            Order.objects.filter(
                status__in=ACTIVE_ORDER_STATUSES,
                items__sku=recipe.output_sku,
            )
            .values_list("pk", flat=True)
            .distinct()
        )
        active_orders = list(
            Order.objects.select_for_update()
            .filter(
                pk__in=order_ids,
                status__in=ACTIVE_ORDER_STATUSES,
            )
            .prefetch_related("items")
            .order_by("pk")
        )
        hypothetical = None
        candidates = list(open_work_orders)
        target_work_order = next(
            (work_order for work_order in work_orders if str(work_order.pk) == str(work_order_id)),
            None,
        )
        if work_order_id not in (None, "") and target_work_order is None:
            raise ProductionConflict(
                "A fornada selecionada não pertence mais a esta célula.",
                data={
                    "expected_rev": None,
                    "current_rev": None,
                    "cause": "stale_work_order_selection",
                    "candidates": [work_order.ref for work_order in work_orders],
                },
            )
        if not create_new and target_work_order is None and len(work_orders) == 1:
            target_work_order = work_orders[0]
        if (create_new or not work_orders) and requested > 0:
            hypothetical = SimpleNamespace(
                ref="",
                output_sku=recipe.output_sku,
                quantity=requested,
                status=WorkOrder.Status.PLANNED,
                meta={},
                target_date=target_date,
                created_at=timezone.now(),
                pk=max((work_order.pk for work_order in all_work_orders), default=0) + 1,
            )
            candidates.append(hypothetical)
            target_work_order = hypothetical

        if target_work_order is None:
            return None

        # Discover which demand this target owns with effectively unbounded
        # capacity, while every other WO keeps its real remaining capacity.
        # Comparing that demand with ``requested`` catches reductions such as
        # A10/B10 + O1=8/O2=8 where B→7 used to escape the guard.
        _, desired_work_orders_by_order = _allocate_pending_links(
            orders=active_orders,
            pending_work_orders=candidates,
            all_work_orders=all_work_orders,
            strategy=_match_strategy(),
            operational_quantities={target_work_order.ref: Decimal("1e30")},
            preserve_existing=True,
            preferred_work_order_ref=target_work_order.ref,
        )
        covered_orders = [
            order for order in active_orders if target_work_order.ref in desired_work_orders_by_order.get(order.ref, ())
        ]
        active_refs = tuple(dict.fromkeys(order.ref for order in covered_orders))
        if not active_refs:
            return None
        required = sum(
            (item.qty for order in covered_orders for item in order.items.all() if item.sku == recipe.output_sku),
            Decimal("0"),
        )
        if requested < required:
            return ProductionOrderShortError(
                work_order_ref=target_work_order.ref,
                required=required,
                requested=requested,
                order_refs=active_refs,
            )
        return None
    except ProductionError:
        raise
    # Cobertura de pedidos é um guardrail de integridade: falha técnica na
    # validação não é evidência de cobertura suficiente, portanto o planejamento
    # falha fechado em qualquer modo.
    except Exception as exc:
        raise ProductionError(
            "Não foi possível validar os pedidos vinculados; o planejamento não foi alterado."
        ) from exc


def _record_shortage_override(
    *,
    work_order_ref: str,
    action: str,
    reason: str,
    actor: str,
    client_key: str | None,
    impact: dict,
    resulting_rev: int | None = None,
) -> None:
    """Append the accepted override and its impact in the locked transaction."""
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.scheduling import _next_seq

    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        raise ProductionError("Justificativa é obrigatória para forçar uma falta.")

    work_order = WorkOrder.objects.select_for_update().get(ref=work_order_ref)
    attempt = str(client_key or "").strip()
    event_key = f"production.shortage-override:{action}:{work_order.pk}:{attempt}" if attempt else None
    if event_key and WorkOrderEvent.objects.filter(idempotency_key=event_key).exists():
        return

    WorkOrderEvent.objects.create(
        work_order=work_order,
        seq=_next_seq(work_order),
        kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN,
        payload={
            "action": action,
            "reason": normalized_reason,
            "impact": impact,
            "work_order_rev": (work_order.rev if resulting_rev is None else resulting_rev),
        },
        actor=actor,
        idempotency_key=event_key,
    )
    transaction.on_commit(
        lambda: logger.warning(
            "production_shortage_override",
            extra={
                "production_action": action,
                "production_actor": actor,
                "production_reason": normalized_reason,
                "production_work_order": work_order_ref,
                "production_impact": impact,
            },
        )
    )


def _looks_like_stock_error(exc: Exception) -> bool:
    lower = str(exc).lower()
    return any(token in lower for token in ("estoque", "stock", "insuficiente", "inventory"))


def _create_stock_short_alert(*, work_order_id, error: str) -> None:
    try:
        from shopman.shop.handlers.production_alerts import create_stock_short_alert

        work_order = _get_work_order(work_order_id)
        create_stock_short_alert(
            work_order_ref=work_order.ref,
            output_sku=work_order.output_sku,
            error=error,
        )
    except Exception:
        logger.warning("production_stock_short_alert_failed work_order_id=%s", work_order_id, exc_info=True)


def check_finish_materials(work_order) -> list[MissingMaterial]:
    """Validate materials needed to finish a specific WorkOrder.

    Active guardrail when INVENTORY_BACKEND is configured (Buyman WP-B5b): returns
    the missing ingredients so apply_finish() can block (or alert with force=True).
    Returns [] when no backend is configured (standalone). Ingredients carry real
    Stockman stock via the seed.
    """
    backend_path = _craftsman_setting("INVENTORY_BACKEND")
    if not backend_path:
        return []

    material_needs = _material_needs_for_work_order(work_order)
    if not material_needs:
        return []

    try:
        from django.utils.module_loading import import_string

        result = import_string(backend_path)().available(material_needs)
    except Exception as exc:
        # This is an operational writer, not Craftsman's standalone planning
        # API. Once an inventory backend is configured, unavailability is not
        # evidence of sufficient stock and must fail closed in every mode.
        raise ProductionError(f"Falha ao consultar estoque de insumos: {exc}") from exc

    return [
        MissingMaterial(
            sku=status.sku,
            needed=status.needed,
            available=status.available,
        )
        for status in result.materials
        if not status.sufficient
    ]


def _material_needs_for_work_order(work_order):
    from shopman.craftsman.protocols.inventory import MaterialNeed

    recipe = work_order.recipe
    started_qty = work_order.started_qty or work_order.quantity
    snapshot = (work_order.meta or {}).get("_recipe_snapshot")
    if snapshot:
        batch_size = Decimal(str(snapshot["batch_size"]))
        items = snapshot.get("items") or []
    else:
        batch_size = recipe.batch_size
        items = [
            {
                "input_sku": item.input_sku,
                "quantity": str(item.quantity),
                "unit": item.unit,
            }
            for item in recipe.items.filter(is_optional=False).order_by("sort_order")
        ]

    coefficient = started_qty / batch_size
    return [
        MaterialNeed(
            sku=item["input_sku"],
            quantity=Decimal(str(item["quantity"])) * coefficient,
            unit=item.get("unit", "un"),
            position_ref=work_order.position_ref or None,
        )
        for item in items
    ]


def _record_batch_traceability(*, work_order_id, replay: bool = False) -> None:
    """Um ``Batch`` por linha de OUTPUT — N grupos viram N lotes (ADR-017 §5).

    O ``batch_ref`` sai da LINHA (gravado pelo ``resolve_partition``), não de
    fórmula derivada em ``WorkOrder.meta`` — fórmula só admitia um lote por
    ordem, e era por isso que a partição parecia impossível. Grupo com grau de
    desconto grava ``quality_grade_ref`` e ``nonconformity_percent`` (o percentual RESOLVIDO do
    catálogo, congelado no lote: mudar a tabela amanhã não reescreve os lotes
    de ontem) e ``nonconformity_reason`` (somente o label do defeito).

    Falha aqui vira OperatorAlert, não só log: lote não gravado é preço cheio
    indevido e rastreabilidade perdida.
    """
    work_order = _get_work_order(work_order_id)
    snapshot = (work_order.meta or {}).get("_recipe_snapshot") or {}
    recipe_meta = snapshot.get("production") or work_order.recipe.meta or {}

    try:
        from shopman.craftsman.models import WorkOrderItem
        from shopman.stockman.models import Batch

        production_date = work_order.target_date or timezone.localdate()
        shelf_life_days = recipe_meta.get("shelf_life_days")
        expiry_date = None
        if shelf_life_days not in (None, ""):
            expiry_date = production_date + timedelta(days=int(shelf_life_days))

        outputs = WorkOrderItem.objects.filter(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT).exclude(
            batch_ref=""
        )
        for line in outputs:
            quality_fact = line.meta or {}
            frozen = quality_fact.get("batch_traceability") or {}
            existing = Batch.objects.filter(ref=line.batch_ref).first() if replay and not frozen else None
            if existing is not None:
                # Compatibilidade com lotes finalizados antes do snapshot:
                # no replay, o Batch já persistido é a verdade histórica.
                defaults = {
                    "sku": existing.sku,
                    "production_date": existing.production_date,
                    "expiry_date": existing.expiry_date,
                    "notes": existing.notes,
                    "quality_grade_ref": existing.quality_grade_ref,
                    "nonconformity_percent": existing.nonconformity_percent,
                    "nonconformity_reason": existing.nonconformity_reason,
                }
            elif frozen:
                defaults = _thaw_batch_traceability(frozen)
            else:
                markdown = int(quality_fact.get("quality_markdown_percent") or 0)
                defaults = {
                    "sku": line.item_ref,
                    "production_date": production_date,
                    "expiry_date": expiry_date,
                    "notes": f"Produção {work_order.ref}",
                    "quality_grade_ref": line.quality_grade_ref,
                    "nonconformity_percent": markdown,
                    "nonconformity_reason": str(quality_fact.get("quality_reason") or ""),
                }
            if not frozen:
                line.meta = {
                    **quality_fact,
                    "batch_traceability": _freeze_batch_traceability(defaults),
                }
                line.save(update_fields=["meta"])
            # update_or_create, não get_or_create: a ponte de estoque roda
            # ANTES (signal síncrono dentro do craft.finish) e já cria o lote
            # com produção+validade — o fato de qualidade precisa pousar por
            # cima. O congelamento continua: só o fechamento escreve aqui, e
            # ninguém reescreve depois.
            if replay:
                # Replay só pode reparar ausência. Um Batch existente é fato
                # histórico e jamais é reescrito por uma segunda requisição.
                Batch.objects.get_or_create(ref=line.batch_ref, defaults=defaults)
            else:
                Batch.objects.update_or_create(
                    ref=line.batch_ref,
                    defaults=defaults,
                )
    except Exception as exc:
        logger.warning("production_batch_traceability_failed work_order_id=%s", work_order_id, exc_info=True)
        raise ProductionBatchTraceabilityError(
            work_order_ref=work_order.ref,
            output_sku=work_order.output_sku,
            cause=exc,
        ) from exc


def _freeze_batch_traceability(defaults: dict) -> dict:
    return {key: value.isoformat() if isinstance(value, date) else value for key, value in defaults.items()}


def _thaw_batch_traceability(frozen: dict) -> dict:
    defaults = {**frozen}
    for key in ("production_date", "expiry_date"):
        value = defaults.get(key)
        defaults[key] = date.fromisoformat(value) if value else None
    defaults["nonconformity_percent"] = int(defaults.get("nonconformity_percent") or 0)
    defaults["nonconformity_reason"] = str(defaults.get("nonconformity_reason") or "")
    defaults["quality_grade_ref"] = str(defaults.get("quality_grade_ref") or "")
    return defaults


def _get_work_order(work_order_id):
    from shopman.craftsman.models import WorkOrder

    try:
        return WorkOrder.objects.select_related("recipe").prefetch_related("recipe__items").get(pk=work_order_id)
    except (WorkOrder.DoesNotExist, ValueError, TypeError):
        raise ProductionNotFound(
            "Ordem de produção não encontrada.",
            resource="work_order",
            identifier=str(work_order_id),
        ) from None


def _craftsman_setting(name):
    from shopman.craftsman.conf import get_setting

    return get_setting(name)


def _missing_summary(missing: list[MissingMaterial]) -> str:
    return "; ".join(
        f"{item.sku} necessário {_qty(item.needed)}, disponível {_qty(item.available)}" for item in missing
    )


def _qty(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.001")).normalize(), "f")
