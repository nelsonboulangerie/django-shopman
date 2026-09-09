"""
Production service — coordenação em torno do WorkOrder (WP-S5).

Movimentação física de estoque (consumo de insumos + entrada do acabado) é
integrada ao Core via `production_changed` → contrib/stockman (caminho de escrita
único e canônico).

Este módulo é o gancho explícito do orquestrador: logging estruturado e pontos
únicos para evoluir (alertas ao operador, integrações externas).
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

logger = logging.getLogger(__name__)

PLANNING_RECEIPT_SCOPE = "production:planning-attempt"


def _decimal_wire(value) -> str:
    """Canonical decimal identity for receipts, attempts and wire facts."""
    return format(Decimal(str(value)).normalize(), "f")


def suggest_for(target_date: date, output_skus: list[str] | None = None):
    """Sugestões de produção com a config da loja aplicada.

    Ponto único de resolução: estação (mês da data-alvo), multiplicador de alta
    demanda e margem de segurança vêm de ``ProductionConfig`` — CLI, projections
    e matriz enxergam exatamente a mesma sugestão.

    O calendário também entra aqui: quem sabe quando a loja abre é o
    orquestrador, então é ele que tira da amostra os dias fechados. Sem isso um
    domingo de portas fechadas entra na média como um domingo fraco e puxa a
    sugestão da semana inteira para baixo.
    """
    from shopman.craftsman import suggest as formula_suggest
    from shopman.craftsman.conf import get_setting

    from shopman.shop.production_config import ProductionConfig

    suggestion = ProductionConfig.load().suggestion
    window_days = int(get_setting("HISTORICAL_DAYS") or 28)
    return formula_suggest(
        target_date,
        output_skus=output_skus,
        season_months=suggestion.season_months_for(target_date.month),
        high_demand_multiplier=suggestion.high_demand_multiplier_decimal,
        safety_pct=suggestion.safety_stock_percent_decimal,
        exclude_dates=untrustworthy_days(days=window_days),
        selling_window=selling_window_for(target_date),
    )


def selling_window_for(day: date):
    """O par (abre, fecha) do dia, do horário declarado da loja.

    É com ele que a fórmula extrapola a demanda dos dias que esgotaram: o pão
    que acabou às 10h vendeu numa fração do expediente, e a fração só é
    calculável sabendo quando o expediente começa. Sem horário configurado
    devolve None, e a fórmula prefere contar o que vendeu a inventar o resto.
    """
    from shopman.shop.services.business_calendar import selling_hours_for

    return selling_hours_for(day)


def untrustworthy_days(*, days: int, until: date | None = None) -> frozenset[date]:
    """Dias que não devem ensinar demanda, por qualquer motivo.

    Duas famílias, mesmo efeito: dia em que a casa **não abriu** (calendário) e
    dia **atrapalhado** por um episódio (faltou luz, equipamento parado). O
    segundo é tão enganoso quanto o primeiro — vender pouco porque a loja
    estava sem energia não é sinal de que a procura caiu.
    """
    from shopman.shop.adapters.episodes import disrupted_days

    until = until or timezone.localdate()
    closed = closed_days_within(days=days, until=until)
    disrupted = disrupted_days(since=until - timedelta(days=days), until=until)
    return closed | disrupted


def closed_days_within(*, days: int, until: date | None = None) -> frozenset[date]:
    """Dias sem expediente na janela ``[until - days, until)``.

    Degrada para vazio se o calendário não estiver configurado — nunca esconde
    dias por engano (a sugestão prefere amostra a mais do que amostra fantasma).
    """
    from shopman.shop.services.business_calendar import is_open_on

    until = until or timezone.localdate()
    return frozenset(day for offset in range(1, days + 1) if not is_open_on(day := until - timedelta(days=offset)))


def reserve_materials(work_order) -> None:
    """Ponto de coordenação ao planejar produção.

    O Stockman reage ao signal `production_changed` (action=planned/started).
    Aqui registramos o evento de domínio para auditoria e extensões futuras.
    """
    logger.info(
        "production.reserve_materials: wo=%s qty=%s ref=%s",
        work_order.ref,
        work_order.quantity,
        work_order.output_sku,
    )


def emit_goods(work_order) -> None:
    """Ponto de coordenação ao encerrar produção com saída real.

    Consumo de insumos e entrada do acabado ocorrem via signal
    `production_changed` → contrib/stockman (caminho de escrita único).
    """
    logger.info(
        "production.emit_goods: wo=%s finished=%s ref=%s",
        work_order.ref,
        work_order.finished,
        work_order.output_sku,
    )
    _open_waitlist_window(work_order)


def _open_waitlist_window(work_order) -> None:
    """A fornada saiu: quem estava na fila por ela é chamado a confirmar.

    Este é o sinal de MATERIALIZAÇÃO do WP-P2E. A reserva de fila esperava
    exatamente isto, e sem o chamado ela esperaria para sempre — o cliente
    olharia "previsto para hoje" no dia seguinte. Serve FCFS até a fornada
    acabar (``waitlist.open_window``); quem não couber continua na fila.
    """
    sku = getattr(work_order, "output_sku", "") or ""
    qty = getattr(work_order, "finished", None)
    if not sku or not qty or qty <= 0:
        return
    try:
        from shopman.shop.services import waitlist

        waitlist.open_window(sku, qty_available=qty)
    except Exception:
        logger.warning(
            "production._open_waitlist_window failed wo=%s sku=%s",
            work_order.ref,
            sku,
            exc_info=True,
        )


def notify(work_order, event: str) -> None:
    """Registro de lifecycle de produção (log estruturado).

    Eventos felizes (planned/started/finished/voided) ficam no ledger + log —
    sinal, não ruído. Notificação ativa ao operador acontece nos ALERTAS
    (production_alerts._notify_operator, opt-in via
    ``production.notifications``): atraso, yield baixo, esquecimento, falta
    de insumo.
    """
    logger.info(
        "production.notify: wo=%s event=%s",
        work_order.ref,
        event,
    )


def void_work_order(
    work_order_id,
    *,
    actor: str,
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
    reason: str = "Estornado via produção rápida",
) -> str:
    """Void a work order and return its reference.

    ⚠️ ``expected_rev`` é a revisão que a TELA leu. O core faz compare-and-swap com ela
    (`_check_rev`) e levanta ``StaleRevision`` se o quadro envelheceu. ``None`` mantém o
    last-write-wins, que é o contrato documentado do craftsman para uso standalone —
    quem quer a garantia manda o número.
    """
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution

    work_order = WorkOrder.objects.get(pk=work_order_id)
    CraftExecution.void(
        order=work_order,
        reason=reason,
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
        fail_closed=True,
    )
    return work_order.ref


def _replay_planning_attempt(*, attempt_key, attempt: dict, actor: str, quantity):
    """Return the immutable event for an already accepted planning attempt.

    This lookup deliberately runs before recipe/default-position/current-cell
    reads.  A retry is a question about the request that was accepted, not
    about configuration or mutable WorkOrder fields at retry time.
    """
    if not attempt_key:
        return None

    from shopman.craftsman.exceptions import CraftError
    from shopman.craftsman.models import WorkOrderEvent

    event = (
        WorkOrderEvent.objects.filter(idempotency_key=attempt_key)
        .select_related("work_order", "work_order__recipe")
        .first()
    )
    if not event:
        return None

    accepted_kinds = {
        WorkOrderEvent.Kind.PLANNED,
        WorkOrderEvent.Kind.PLANNING_CONFIRMED,
        WorkOrderEvent.Kind.ADJUSTED,
        WorkOrderEvent.Kind.VOIDED,
    }
    frozen_attempt = event.payload.get("attempt")
    same_attempt = (
        event.kind in accepted_kinds
        and event.actor == str(actor or "")
        and isinstance(frozen_attempt, dict)
        and frozen_attempt == attempt
    )
    if not same_attempt:
        raise CraftError(
            "IDEMPOTENCY_CONFLICT",
            idempotency_key=attempt_key,
            work_order=event.work_order.ref,
            existing_work_order=event.work_order.ref,
        )
    return event


def _planning_replay_result(event, quantity) -> tuple[str, str, Decimal, str]:
    from shopman.craftsman.models import WorkOrderEvent

    if event.kind == WorkOrderEvent.Kind.VOIDED:
        return event.work_order.output_sku, "", quantity, "cleared"
    action = str(event.payload.get("result") or "")
    if not action:
        action = "created" if event.kind == WorkOrderEvent.Kind.PLANNED else "adjusted"
    return event.work_order.output_sku, event.work_order.ref, quantity, action


def _planning_receipt_result(receipt, *, attempt_key, attempt: dict, actor: str):
    """Validate and decode one globally serialized planning receipt."""
    from shopman.craftsman.exceptions import CraftError

    body = receipt.response_body if isinstance(receipt.response_body, dict) else {}
    if body.get("attempt") != attempt or body.get("actor") != str(actor or ""):
        raise CraftError(
            "IDEMPOTENCY_CONFLICT",
            idempotency_key=attempt_key,
            work_order=str(body.get("work_order_ref") or ""),
            existing_work_order=str(body.get("work_order_ref") or ""),
        )
    if receipt.status != "done":
        raise CraftError(
            "IDEMPOTENCY_CONFLICT",
            idempotency_key=attempt_key,
            work_order=str(body.get("work_order_ref") or ""),
            existing_work_order=str(body.get("work_order_ref") or ""),
            status=receipt.status,
        )
    return body


def _replay_planning_receipt(*, attempt_key, attempt: dict, actor: str):
    if not attempt_key:
        return None
    from shopman.orderman.models import IdempotencyKey

    receipt = IdempotencyKey.objects.filter(
        scope=PLANNING_RECEIPT_SCOPE,
        key=attempt_key,
    ).first()
    if receipt is None:
        return None
    return _planning_receipt_result(
        receipt,
        attempt_key=attempt_key,
        attempt=attempt,
        actor=actor,
    )


def _planning_receipt_tuple(receipt: dict) -> tuple[str, str, Decimal, str]:
    return (
        str(receipt.get("output_sku") or ""),
        str(receipt.get("work_order_ref") or ""),
        Decimal(str(receipt.get("quantity") or "0")),
        str(receipt.get("result") or ""),
    )


def _claim_planning_receipt(
    *,
    attempt_key: str | None,
    attempt: dict,
    actor: str,
):
    """Claim the single planning ledger before any accepted state mutation."""
    if not attempt_key:
        return None, None

    from django.db import IntegrityError, transaction
    from shopman.orderman.models import IdempotencyKey

    for _attempt in range(2):
        receipt = (
            IdempotencyKey.objects.select_for_update().filter(scope=PLANNING_RECEIPT_SCOPE, key=attempt_key).first()
        )
        if receipt is not None:
            return receipt, _planning_receipt_result(
                receipt,
                attempt_key=attempt_key,
                attempt=attempt,
                actor=actor,
            )
        try:
            # The savepoint keeps the outer planning transaction usable when
            # two different cells race on the same globally unique attempt.
            with transaction.atomic():
                receipt = IdempotencyKey.objects.create(
                    scope=PLANNING_RECEIPT_SCOPE,
                    key=attempt_key,
                    status="in_progress",
                    response_body={
                        "attempt": attempt,
                        "actor": str(actor or ""),
                    },
                )
            return receipt, None
        except IntegrityError:
            continue

    receipt = IdempotencyKey.objects.select_for_update().get(
        scope=PLANNING_RECEIPT_SCOPE,
        key=attempt_key,
    )
    return receipt, _planning_receipt_result(
        receipt,
        attempt_key=attempt_key,
        attempt=attempt,
        actor=actor,
    )


def _complete_planning_receipt(
    receipt,
    *,
    attempt: dict,
    actor: str,
    output_sku: str,
    work_order_ref: str,
    quantity: Decimal,
    result: str,
) -> None:
    if receipt is None:
        return
    receipt.status = "done"
    receipt.response_code = 200
    receipt.response_body = {
        "attempt": attempt,
        "actor": str(actor or ""),
        "output_sku": output_sku,
        "work_order_ref": work_order_ref,
        "quantity": _decimal_wire(quantity),
        "result": result,
    }
    receipt.save(update_fields=["status", "response_code", "response_body"])


def replay_planned_quantity(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    reason: str = "",
    actor: str,
    source_ref: str = "production_matrix",
    idempotency_key: str | None = None,
    attempt_payload: dict | None = None,
    planning_meta: dict | None = None,
    work_order_id=None,
    create_new: bool = False,
) -> tuple[str, str, Decimal, str] | None:
    """Resolve a matrix retry exclusively from its immutable event."""
    qty = _non_negative_decimal(quantity, error="Quantidade planejada inválida.")
    target_date = _target_date_or_today(target_date_value)
    normalized_planning_meta = _canonical_planning_meta(planning_meta)
    attempt = {
        "operation": "set_planned_quantity",
        "recipe_id": str(recipe_id),
        "quantity": _decimal_wire(qty),
        "target_date": target_date.isoformat(),
        "requested_position_ref": str(position_ref or "").strip(),
        "operator_ref": str(operator_ref or "").strip(),
        "reason": str(reason or ""),
        "source_ref": str(source_ref or ""),
        "requested_work_order_id": str(work_order_id or ""),
        "create_new": bool(create_new),
        "planning_meta": normalized_planning_meta,
        **dict(attempt_payload or {}),
    }
    receipt = _replay_planning_receipt(
        attempt_key=str(idempotency_key or "").strip() or None,
        attempt=attempt,
        actor=actor,
    )
    if receipt:
        return _planning_receipt_tuple(receipt)
    event = _replay_planning_attempt(
        attempt_key=str(idempotency_key or "").strip() or None,
        attempt=attempt,
        actor=actor,
        quantity=qty,
    )
    if event:
        return _planning_replay_result(event, qty)
    return None


def replay_quick_plan(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str,
    idempotency_key: str | None,
):
    """Resolve an accepted quick-plan attempt without mutable lookups."""
    qty = _positive_decimal(quantity, error="Quantidade inválida.")
    attempt = {
        "operation": "quick_plan",
        "recipe_id": str(recipe_id),
        "quantity": _decimal_wire(qty),
        "requested_position_id": str(position_id or ""),
        "source_ref": "quick_production",
    }
    receipt = _replay_planning_receipt(
        attempt_key=str(idempotency_key or "").strip() or None,
        attempt=attempt,
        actor=actor,
    )
    if receipt:
        from shopman.craftsman.models import WorkOrder

        return WorkOrder.objects.select_related("recipe").get(ref=receipt["work_order_ref"])
    event = _replay_planning_attempt(
        attempt_key=str(idempotency_key or "").strip() or None,
        attempt=attempt,
        actor=actor,
        quantity=qty,
    )
    return event.work_order if event else None


def quick_plan(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str = "",
    idempotency_key: str | None = None,
):
    """Plan a same-day ad-hoc work order (fornada avulsa).

    Nasce sem previsto herdado de plano nenhum — o previsto É o que o operador
    declarou. Quem fecha é sempre o ``apply_finish`` do backstage, com ou sem
    partição: é lá que mora o guardrail de insumo.
    """
    from django.db import transaction
    from shopman.craftsman.models import Recipe, WorkOrder
    from shopman.craftsman.services.scheduling import CraftPlanning

    qty = _positive_decimal(quantity, error="Quantidade inválida.")
    attempt_key = str(idempotency_key or "").strip() or None
    attempt = {
        "operation": "quick_plan",
        "recipe_id": str(recipe_id),
        "quantity": _decimal_wire(qty),
        "requested_position_id": str(position_id or ""),
        "source_ref": "quick_production",
    }
    receipt_replay = _replay_planning_receipt(
        attempt_key=attempt_key,
        attempt=attempt,
        actor=actor,
    )
    if receipt_replay:
        return WorkOrder.objects.select_related("recipe").get(ref=receipt_replay["work_order_ref"])
    replay = _replay_planning_attempt(
        attempt_key=attempt_key,
        attempt=attempt,
        actor=actor,
        quantity=qty,
    )
    if replay:
        return replay.work_order
    position_ref = _position_ref(position_id)

    try:
        with transaction.atomic():
            # Serializes idempotency check + insert for ad-hoc attempts.  The
            # signal emitted by ``plan`` also remains inside this outer atomic.
            recipe = Recipe.objects.select_for_update().get(
                pk=recipe_id,
                is_active=True,
            )
            replay = _replay_planning_attempt(
                attempt_key=attempt_key,
                attempt=attempt,
                actor=actor,
                quantity=qty,
            )
            if replay:
                return replay.work_order
            receipt, receipt_replay = _claim_planning_receipt(
                attempt_key=attempt_key,
                attempt=attempt,
                actor=actor,
            )
            if receipt_replay:
                return WorkOrder.objects.select_related("recipe").get(ref=receipt_replay["work_order_ref"])
            work_order = CraftPlanning.plan(
                recipe,
                qty,
                date=timezone.localdate(),
                position_ref=position_ref,
                source_ref="quick_production",
                actor=actor,
                idempotency_key=attempt_key,
                fail_closed=True,
                attempt_payload=attempt,
            )
            _complete_planning_receipt(
                receipt,
                attempt=attempt,
                actor=actor,
                output_sku=work_order.output_sku,
                work_order_ref=work_order.ref,
                quantity=qty,
                result="created",
            )
            return work_order
    except (Recipe.DoesNotExist, ValueError, TypeError) as exc:
        raise ValueError("Receita inválida.") from exc


def set_planned_quantity(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    reason: str = "",
    actor: str,
    source_ref: str = "production_matrix",
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
    attempt_payload: dict | None = None,
    planning_meta: dict | None = None,
    work_order_id=None,
    resolved_position_ref: str | None = None,
    create_new: bool = False,
) -> tuple[str, str, Decimal, str]:
    """Create, adjust, or consolidate one serialized production matrix cell.

    ``expected_rev`` reaches an existing cell. Creating has no previous revision;
    duplicate consolidation is serialized housekeeping inside the same transaction.
    """
    from django.db import transaction
    from shopman.craftsman.exceptions import CraftError, StaleRevision
    from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.execution import CraftExecution
    from shopman.craftsman.services.scheduling import CraftPlanning, _next_seq

    qty = _non_negative_decimal(quantity, error="Quantidade planejada inválida.")
    target_date = _target_date_or_today(target_date_value)
    requested_position = str(position_ref or "").strip()
    operator = str(operator_ref or "").strip()
    attempt_key = str(idempotency_key or "").strip() or None
    normalized_planning_meta = _canonical_planning_meta(planning_meta)
    attempt = {
        "operation": "set_planned_quantity",
        "recipe_id": str(recipe_id),
        "quantity": _decimal_wire(qty),
        "target_date": target_date.isoformat(),
        "requested_position_ref": requested_position,
        "operator_ref": operator,
        "reason": str(reason or ""),
        "source_ref": str(source_ref or ""),
        "requested_work_order_id": str(work_order_id or ""),
        "create_new": bool(create_new),
        "planning_meta": normalized_planning_meta,
        **dict(attempt_payload or {}),
    }
    receipt_replay = _replay_planning_receipt(
        attempt_key=attempt_key,
        attempt=attempt,
        actor=actor,
    )
    if receipt_replay:
        return _planning_receipt_tuple(receipt_replay)
    replay = _replay_planning_attempt(
        attempt_key=attempt_key,
        attempt=attempt,
        actor=actor,
        quantity=qty,
    )
    if replay:
        return _planning_replay_result(replay, qty)

    position = (
        str(resolved_position_ref)
        if resolved_position_ref is not None
        else requested_position or _default_position_ref()
    )

    with transaction.atomic():
        try:
            # Locking the recipe serializes every cell for that recipe.  It is
            # intentionally a little broader than recipe/date/position and is
            # portable across PostgreSQL and the SQLite test suite.
            recipe = Recipe.objects.select_for_update().get(pk=recipe_id, is_active=True)
        except (Recipe.DoesNotExist, ValueError, TypeError) as exc:
            raise ValueError("Receita inválida.") from exc

        replay = _replay_planning_attempt(
            attempt_key=attempt_key,
            attempt=attempt,
            actor=actor,
            quantity=qty,
        )
        if replay:
            return _planning_replay_result(replay, qty)
        receipt, receipt_replay = _claim_planning_receipt(
            attempt_key=attempt_key,
            attempt=attempt,
            actor=actor,
        )
        if receipt_replay:
            return _planning_receipt_tuple(receipt_replay)

        extra_meta = {
            **_formula_meta(
                recipe=recipe,
                target_date=target_date,
                quantity=qty,
                source_ref=source_ref,
            ),
            **normalized_planning_meta,
        }
        locked_planned_orders = list(
            WorkOrder.objects.select_for_update()
            .filter(
                recipe=recipe,
                target_date=target_date,
                position_ref=position,
                status=WorkOrder.Status.PLANNED,
            )
            .order_by("pk")
        )
        planned_orders = sorted(
            locked_planned_orders,
            key=lambda work_order: (work_order.created_at, work_order.pk),
        )

        if create_new and (expected_rev is not None or work_order_id not in (None, "")):
            raise CraftError(
                "INVALID_CREATE_TARGET",
                expected_rev=expected_rev,
                work_order=str(work_order_id or ""),
            )

        if not planned_orders or create_new:
            if expected_rev is not None or work_order_id not in (None, ""):
                raise CraftError(
                    "STALE_REVISION",
                    expected_rev=expected_rev,
                    current_rev=None,
                    work_order="",
                )
            if qty == 0:
                if create_new:
                    raise CraftError("INVALID_QUANTITY", quantity=qty)
                _complete_planning_receipt(
                    receipt,
                    attempt=attempt,
                    actor=actor,
                    output_sku=recipe.output_sku,
                    work_order_ref="",
                    quantity=qty,
                    result="cleared",
                )
                return recipe.output_sku, "", qty, "cleared"
            work_order = CraftPlanning.plan(
                recipe,
                qty,
                date=target_date,
                position_ref=position,
                operator_ref=operator,
                source_ref=source_ref,
                actor=actor,
                meta=extra_meta,
                idempotency_key=attempt_key,
                fail_closed=True,
                attempt_payload=attempt,
                attempt_result="created",
            )
            _complete_planning_receipt(
                receipt,
                attempt=attempt,
                actor=actor,
                output_sku=recipe.output_sku,
                work_order_ref=work_order.ref,
                quantity=qty,
                result="created",
            )
            return recipe.output_sku, work_order.ref, qty, "created"

        if work_order_id not in (None, ""):
            work_order = next(
                (candidate for candidate in planned_orders if str(candidate.pk) == str(work_order_id)),
                None,
            )
            if work_order is None:
                raise CraftError(
                    "STALE_REVISION",
                    expected_rev=expected_rev,
                    current_rev=None,
                    work_order="",
                    candidates=[candidate.ref for candidate in planned_orders],
                )
        elif len(planned_orders) == 1:
            work_order = planned_orders[0]
        else:
            raise CraftError(
                "AMBIGUOUS_WORK_ORDER",
                expected_rev=expected_rev,
                current_rev=None,
                work_order="",
                candidates=[candidate.ref for candidate in planned_orders],
            )
        effective_rev = expected_rev
        if effective_rev is None and not attempt_key:
            # Transitional compatibility for trusted in-process callers.  The
            # HTTP contract always has an attempt key and therefore never gets
            # last-write-wins semantics.
            effective_rev = work_order.rev
        if effective_rev is None or work_order.rev != effective_rev:
            raise StaleRevision(work_order, expected_rev)

        if qty == 0:
            CraftExecution.void(
                order=work_order,
                reason="Planejamento zerado na matriz",
                actor=actor,
                expected_rev=effective_rev,
                idempotency_key=attempt_key,
                fail_closed=True,
                attempt_payload=attempt,
                attempt_result="cleared",
            )
            _complete_planning_receipt(
                receipt,
                attempt=attempt,
                actor=actor,
                output_sku=recipe.output_sku,
                work_order_ref="",
                quantity=qty,
                result="cleared",
            )
            return recipe.output_sku, "", qty, "cleared"

        adjusted = work_order.quantity != qty or bool(extra_meta)
        if adjusted:
            CraftPlanning.adjust(
                work_order,
                quantity=qty,
                reason=reason or "Planejamento informado na matriz",
                actor=actor,
                expected_rev=effective_rev,
                idempotency_key=attempt_key,
                fail_closed=True,
                attempt_payload=attempt,
                attempt_result="adjusted",
            )

        if not adjusted and attempt_key:
            WorkOrderEvent.objects.create(
                work_order=work_order,
                seq=_next_seq(work_order),
                kind=WorkOrderEvent.Kind.PLANNING_CONFIRMED,
                payload={
                    "quantity": _decimal_wire(qty),
                    "result": "unchanged",
                    "attempt": attempt,
                },
                actor=actor,
                idempotency_key=attempt_key,
            )

        if extra_meta:
            work_order.meta = {**(work_order.meta or {}), **extra_meta}
            work_order.save(update_fields=["meta", "updated_at"])

        result = "adjusted" if adjusted else "unchanged"
        _complete_planning_receipt(
            receipt,
            attempt=attempt,
            actor=actor,
            output_sku=recipe.output_sku,
            work_order_ref=work_order.ref,
            quantity=qty,
            result=result,
        )
        return recipe.output_sku, work_order.ref, qty, result


def start_work_order(
    *,
    work_order_id,
    quantity,
    position_id="",
    operator_ref: str = "",
    note: str = "",
    actor: str,
    expected_rev: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[str, Decimal]:
    """Mark a planned WorkOrder as started.

    ``expected_rev``: ver ``void_work_order``.
    """
    from shopman.craftsman.exceptions import CraftError
    from shopman.craftsman.models import WorkOrder, WorkOrderEvent
    from shopman.craftsman.services.scheduling import CraftPlanning

    qty = _positive_decimal(quantity, error="Quantidade iniciada inválida.")
    work_order = WorkOrder.objects.get(pk=work_order_id)
    requested_operator = str(operator_ref or "").strip()
    normalized_note = str(note or "").strip()
    attempt = {
        "operation": "start_work_order",
        "work_order_id": str(work_order_id),
        "quantity": _decimal_wire(qty),
        "requested_position_id": str(position_id or ""),
        "requested_operator_ref": requested_operator,
        "note": normalized_note,
    }
    if idempotency_key:
        replay = WorkOrderEvent.objects.filter(idempotency_key=idempotency_key).select_related("work_order").first()
        if replay is not None and replay.payload.get("attempt") is not None:
            if (
                replay.work_order_id != work_order.pk
                or replay.kind != WorkOrderEvent.Kind.STARTED
                or replay.actor != str(actor or "")
                or replay.payload.get("attempt") != attempt
            ):
                raise CraftError(
                    "IDEMPOTENCY_CONFLICT",
                    idempotency_key=idempotency_key,
                    work_order=work_order.ref,
                    existing_work_order=replay.work_order.ref,
                )
            return replay.work_order.ref, Decimal(str(replay.payload["quantity"]))

    position_ref = _position_ref(position_id) if position_id else work_order.position_ref
    operator = requested_operator or work_order.operator_ref
    CraftPlanning.start(
        work_order,
        quantity=qty,
        position_ref=position_ref,
        operator_ref=operator,
        note=normalized_note,
        actor=actor,
        expected_rev=expected_rev,
        idempotency_key=idempotency_key,
        fail_closed=True,
        attempt_payload=attempt,
    )
    return work_order.ref, qty


def finish_work_order(
    *,
    work_order_id,
    quantity=None,
    actor: str,
    finished_items: list[dict] | None = None,
    wasted_items: list[dict] | None = None,
    idempotency_key: str | None = None,
    expected_rev: int | None = None,
    event_context: dict | None = None,
    idempotent_summary_replay: bool = False,
) -> tuple[str, Decimal]:
    """Finish an existing WorkOrder — escalar ou particionado (ADR-017).

    ``expected_rev``: ver ``void_work_order``. Convive com ``idempotency_key`` sem
    conflito — uma responde "é o MESMO gesto de novo?", a outra "o quadro que você
    leu ainda vale?". A primeira devolve o resultado anterior; a segunda recusa.

    O escalar (``quantity``) continua válido e grava uma linha sem grau. Com
    ``finished_items``, cada grupo vira uma linha de OUTPUT carregando
    ``quality_grade_ref``/``quality_defect_ref``/``batch_ref`` — a fornada de
    40 que produz 32+8+3 em vez de "38". ``wasted_items`` leva as unidades
    vetadas com o defeito que as vetou.

    Com ``idempotency_key``, o core devolve a WO existente em vez de estourar
    ``TERMINAL_STATUS`` quando o mesmo fechamento chega duas vezes — é assim
    que o retry do operador deixa de ser beco sem saída.
    """
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution

    work_order = WorkOrder.objects.get(pk=work_order_id)
    if finished_items:
        CraftExecution.finish(
            order=work_order,
            finished=finished_items,
            wasted=wasted_items or None,
            actor=actor,
            idempotency_key=idempotency_key,
            expected_rev=expected_rev,
            fail_closed=True,
            event_context=event_context,
            _idempotent_summary_replay=idempotent_summary_replay,
        )
        total = sum(Decimal(str(item["quantity"])) for item in finished_items)
    else:
        total = _positive_decimal(quantity, error="Quantidade concluída inválida.")
        CraftExecution.finish(
            order=work_order,
            finished=total,
            actor=actor,
            idempotency_key=idempotency_key,
            expected_rev=expected_rev,
            fail_closed=True,
            event_context=event_context,
            _idempotent_summary_replay=idempotent_summary_replay,
        )

    _ensure_stock_ledger_closed(work_order)
    _ensure_order_links_closed(work_order)
    return work_order.ref, total


def _ensure_stock_ledger_closed(work_order) -> None:
    """O retry tem que CONSERTAR, não só devolver 200.

    No replay o core devolve a WO existente e não reemite
    ``production_changed`` — certo quando o que falhou foi um receiver
    posterior (tudo já commitado), errado quando o que falhou foi a própria
    perna de estoque: aí o segundo toque "daria certo" com a vitrine ainda
    zerada, e a divergência só sumiria da vista.

    Os marcadores por perna dizem qual dos dois casos é, e são eles que
    guardam a reexecução (sem guarda, refazer credita a vitrine em dobro).
    No caminho feliz isto é uma consulta e nada mais.

    ⚠️ A leitura daqui é um ATALHO, não a decisão. Ela roda sem trava, e num
    fechamento simultâneo (dois quiosques, mesma chave de idempotência) pode
    pegar a fornada no instante entre o COMMIT da WorkOrder e o commit da perna
    de estoque — foi exatamente assim que 24 madeleines viraram 48. Quem decide
    de verdade é o ``_leg_lock`` dentro do handler: ele trava a linha, relê o
    marcador do banco e desiste se a perna já foi escrita. Aqui, na dúvida,
    chamamos; lá, sob trava, o handler não repete.
    """
    from shopman.craftsman import realize_finished_production, stock_legs_complete

    work_order.refresh_from_db(fields=["meta"])
    if stock_legs_complete(work_order):
        return
    logger.warning(
        "production.finish: ledger de estoque não confirmado em %s — reconferindo sob trava",
        work_order.ref,
    )
    realize_finished_production(work_order)
    work_order.refresh_from_db(fields=["meta"])
    if not stock_legs_complete(work_order):
        from shopman.stockman.exceptions import StockError

        raise StockError(
            "CONCURRENT_MODIFICATION",
            work_order=work_order.ref,
            reason="ledger de produção permaneceu incompleto após reconciliação",
        )


def _ensure_order_links_closed(work_order) -> None:
    """Rede de segurança do vínculo pedido↔fornada — irmã de ``_ensure_stock_ledger_closed``.

    O receiver de sinal do sync (``link_work_order_to_orders``) é BLINDADO: um
    erro nele não derruba o finish. Blindar sozinho deixaria o vínculo órfão se
    ele estourasse — e o replay idempotente do finish não reemite
    ``production_changed``. Então, no MESMO caminho guardado que fecha o ledger
    de estoque (roda logo após o ``.send()`` e também no replay), refazemos o
    vínculo: ``append-if-absent``, idempotente, uma consulta e nada mais no
    caminho feliz. Cosmético — a falha vira log, nunca aborta a fornada
    (ao contrário do estoque, que grita).
    """
    try:
        from shopman.shop.handlers.production_order_sync import (
            link_active_orders_to_work_order,
        )

        work_order.refresh_from_db(fields=["meta"])
        link_active_orders_to_work_order(work_order)
    except Exception:
        logger.warning(
            "production.finish: vínculo de pedido não confirmado em %s (não-fatal)",
            getattr(work_order, "ref", "?"),
            exc_info=True,
        )


def _merge_committed_order_links(primary, duplicates: list) -> None:
    """Preserve order links when duplicate planned WOs are consolidated."""
    try:
        from shopman.orderman.models import Order

        from shopman.shop.handlers.production_order_sync import (
            ORDER_AWAITING_WO_REFS_KEY,
            WORK_ORDER_COMMITTED_ORDER_REFS_KEY,
        )
    except Exception:
        logger.debug("production.consolidate_links_unavailable", exc_info=True)
        return

    refs = list((primary.meta or {}).get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or [])
    for duplicate in duplicates:
        refs.extend((duplicate.meta or {}).get(WORK_ORDER_COMMITTED_ORDER_REFS_KEY) or [])
    refs = list(dict.fromkeys(ref for ref in refs if ref))
    primary.meta = {
        **(primary.meta or {}),
        "consolidated_work_order_refs": list(
            dict.fromkeys(
                [
                    *list((primary.meta or {}).get("consolidated_work_order_refs") or []),
                    *[duplicate.ref for duplicate in duplicates],
                ]
            )
        ),
    }
    if refs:
        primary.meta[WORK_ORDER_COMMITTED_ORDER_REFS_KEY] = refs
    primary.save(update_fields=["meta", "updated_at"])

    duplicate_refs = {duplicate.ref for duplicate in duplicates}
    for order in Order.objects.select_for_update().filter(ref__in=refs).order_by("pk"):
        awaiting_refs = list((order.data or {}).get(ORDER_AWAITING_WO_REFS_KEY) or [])
        updated_refs = list(dict.fromkeys(primary.ref if ref in duplicate_refs else ref for ref in awaiting_refs))
        if primary.ref not in updated_refs:
            updated_refs.append(primary.ref)
        if updated_refs != awaiting_refs:
            order.data = {
                **(order.data or {}),
                ORDER_AWAITING_WO_REFS_KEY: updated_refs,
            }
            order.save(update_fields=["data", "updated_at"])


def _get_active_recipe(recipe_id):
    from shopman.craftsman.models import Recipe

    try:
        return Recipe.objects.get(pk=recipe_id, is_active=True)
    except (Recipe.DoesNotExist, ValueError, TypeError) as exc:
        raise ValueError("Receita inválida.") from exc


def _positive_decimal(value, *, error: str = "quantidade inválida") -> Decimal:
    try:
        qty = Decimal(str(value).strip())
        # `Decimal("Infinity")` passa em `<= 0` (é False) e viraria quantidade
        # infinita; não-finito é inválido tanto quanto `<= 0`.
        if not qty.is_finite() or qty <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(error) from exc
    return qty


def _non_negative_decimal(value, *, error: str = "quantidade inválida") -> Decimal:
    try:
        qty = Decimal(str(value).strip())
        if not qty.is_finite() or qty < 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(error) from exc
    return qty


def _position_ref(position_id) -> str:
    if position_id:
        from shopman.stockman import Position

        try:
            return Position.objects.get(pk=position_id).ref
        except (Position.DoesNotExist, ValueError, TypeError) as exc:
            raise ValueError("Posição inválida.") from exc
    return _default_position_ref()


def _default_position_ref() -> str:
    from shopman.stockman import Position

    default_pos = Position.objects.filter(is_default=True).first()
    return default_pos.ref if default_pos else ""


def _target_date_or_today(value) -> date:
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return timezone.localdate()
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise ValueError("Data de produção inválida.") from exc


def _canonical_planning_meta(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Metadados de planejamento inválidos.")
    allowed = {"formula_basis", "stocking_request"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError("Metadados de planejamento não autorizados: " + ", ".join(unknown))
    try:
        return json.loads(
            json.dumps(
                value,
                cls=DjangoJSONEncoder,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Metadados de planejamento inválidos.") from exc


def _formula_meta(*, recipe, target_date: date, quantity: Decimal, source_ref: str) -> dict:
    if source_ref != "formula:suggestion":
        return {}
    try:
        lines = suggest_for(target_date, output_skus=[recipe.output_sku])
        basis = {}
        for line in lines:
            if line.recipe.pk == recipe.pk:
                basis = dict(line.basis or {})
                break
        if not basis:
            basis = {
                "date": target_date.isoformat(),
                "output_sku": recipe.output_sku,
                "recipe_ref": recipe.ref,
            }
        basis["accepted_quantity"] = _decimal_wire(quantity)
        return {"formula_basis": basis}
    except Exception:
        logger.debug("production.formula_basis_unavailable recipe=%s", recipe.ref, exc_info=True)
        return {}
