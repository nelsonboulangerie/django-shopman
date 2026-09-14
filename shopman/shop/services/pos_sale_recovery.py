"""Durable POS settlement context: original order, drawer and operator.

The context is committed with the order. Local settlement and its receipt share
one transaction. A gateway attempt is claimed before leaving the transaction;
an uncertain attempt can only be repaired from an existing Payman intent.
"""

from __future__ import annotations

import logging

from django.db import transaction
from shopman.cashman.models import Entry, Shift
from shopman.orderman.models import IdempotencyKey, Order

from shopman.shop.services.pos_intent import PosCommittedSaleError, PosIntentError

logger = logging.getLogger(__name__)
SCOPE = "pos:committed-settlement:v1"


def prepare(order_ref: str, *, shift_id: int, operator_username: str) -> None:
    """Called inside the order transaction; no context can outlive a rollback."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Settlement context must commit with the order")
    IdempotencyKey.objects.get_or_create(
        scope=SCOPE,
        key=order_ref,
        defaults={
            "status": "in_progress",
            "expires_at": None,
            "response_body": {"state": "ready", "shift_id": shift_id, "operator_username": operator_username},
        },
    )


def _error(order_ref, *, code="sale_settlement_failed", message="", recovery=""):
    return PosCommittedSaleError(
        code=code,
        order_ref=order_ref,
        status=409,
        field="payment",
        focus="payment",
        message=message or f"Venda {order_ref} criada; o registro do pagamento ainda precisa ser conferido.",
        recovery=recovery
        or "Mantenha esta tentativa. Não refaça a venda; confira o pedido e o turno original no gestor.",
    )


def _as_error(order_ref, exc):
    if isinstance(exc, PosCommittedSaleError):
        return exc
    if isinstance(exc, PosIntentError):
        return PosCommittedSaleError(**exc.as_dict(), status=exc.status, order_ref=order_ref)
    logger.exception("pos_settlement_recovery_failed order=%s", order_ref)
    return _error(order_ref)


def _save(context, state):
    context.response_body = {**context.response_body, "state": state}
    context.status = "done" if state == "done" else "failed" if state == "failed" else "in_progress"
    context.response_code = 200 if state == "done" else None
    context.save(update_fields=["response_body", "status", "response_code"])


def _sale_entry(order_ref, shift_id=None):
    entries = Entry.objects.filter(kind=Entry.Kind.SALE, order_ref=order_ref)
    if shift_id is not None:
        entries = entries.filter(shift_id=shift_id)
    return entries.first()


def settle(order_ref: str) -> dict:
    """Return current payment details only after settlement is durably recorded.

    No caller-supplied tender/amount/shift enters recovery. For an interrupted
    gateway call, absence of a local intent is uncertainty, never permission to
    send another charge. A linked intent can repair a missing drawer entry.
    """
    from shopman.shop.services import payment, pos

    failure = None
    gateway_claimed = False
    with transaction.atomic():
        context = IdempotencyKey.objects.select_for_update().filter(scope=SCOPE, key=order_ref).first()
        order = Order.objects.select_for_update().get(ref=order_ref)
        payment_data = (order.data or {}).get("payment") or {}
        gateway = (
            payment_data.get("method") in {"pix", "card", "link"}
            and payment_data.get("collection", "terminal") == "terminal"
        )
        if context is None:
            # Legacy successful sales remain readable. A legacy failure without
            # drawer provenance requires review; the retry's drawer is not proof.
            if not _sale_entry(order_ref) or (gateway and not payment_data.get("intent_ref")):
                raise _error(order_ref, code="sale_settlement_context_missing")
            return pos._pos_payment_response(order) if gateway else {}
        original = context.response_body or {}
        shift = Shift.objects.filter(pk=original.get("shift_id")).first()
        if shift is None:
            raise _error(order_ref, code="sale_settlement_context_missing")
        operator_username = str(original.get("operator_username") or "")
        if original.get("state") == "done":
            if not _sale_entry(order_ref, shift.pk):
                raise _error(order_ref, code="sale_settlement_receipt_inconsistent")
            return pos._pos_payment_response(order) if gateway else {}
        if order.status in {Order.Status.CANCELLED, Order.Status.RETURNED}:
            raise _error(
                order_ref,
                code="sale_no_longer_settleable",
                message=f"Venda {order_ref} já cancelada ou devolvida; não será criada outra cobrança.",
            )
        if shift.status != Shift.Status.OPEN:
            raise _error(
                order_ref,
                code="cash_shift_closed_mid_sale",
                message=f"Venda {order_ref} criada; o turno original {shift.pk} está fechado.",
            )

        # Recover the operational stamp if the previous process stopped between
        # the database COMMIT and the original post-commit continuation.
        if not (order.data or {}).get("pos_committed_at"):
            session_data = (order.snapshot or {}).get("data") or {}
            pos._mark_tab_committed(
                order_ref=order_ref,
                tab_ref=str(session_data.get("tab_ref") or ""),
                operator_username=operator_username,
                session_data=session_data,
            )
            order.refresh_from_db()
        order = pos._reconcile_order_payment_to_total(order)
        payment_data = (order.data or {}).get("payment") or {}
        if gateway:
            attempted = (
                original.get("state") != "ready"
                or payment_data.get("intent_ref")
                or payment_data.get("idempotency_key")
                or payment_data.get("error")
            )
            if attempted:
                # This helper only restores persisted Payman data. No provider
                # calls are allowed in this branch or under the context lock.
                if not payment.restore_existing_intent(order):
                    raise _error(
                        order_ref,
                        code="sale_payment_outcome_unknown",
                        message=f"Venda {order_ref} criada; a resposta da cobrança está em consulta.",
                        recovery="Não crie outra cobrança. Confira o gateway e o pedido original no gestor.",
                    )
                order.refresh_from_db()
                intent_ref = (order.data.get("payment") or {}).get("intent_ref")
                method = order.data["payment"]["method"]
                operator = pos._user_for_actor(operator_username) or shift.opened_by
                try:
                    with transaction.atomic():
                        pos._record_sale(
                            order,
                            shift=shift,
                            operator=operator,
                            cash_q=0,
                            payment_ref=intent_ref,
                            intents={method: intent_ref},
                        )
                except Exception as exc:
                    logger.warning("pos_settlement_receipt_failed order=%s", order_ref)
                    failure = _as_error(order_ref, exc)
                else:
                    _save(context, "done")
            else:
                _save(context, "gateway_started")
                gateway_claimed = True
        else:
            try:
                # _settle_pos_sale uses its own savepoint for the financial
                # writes. Catch outside that savepoint to preserve the existing
                # closed-drawer note/reconciliation path when it raises.
                pos._settle_pos_sale(order, shift=shift, operator_username=operator_username)
            except Exception as exc:
                logger.warning("pos_settlement_local_failed order=%s", order_ref)
                failure = _as_error(order_ref, exc)
                _save(context, "failed")
            else:
                _save(context, "done")
    if failure:
        raise failure
    if gateway_claimed:
        # Exactly one first attempt leaves the context lock to contact gateway.
        try:
            result = pos._settle_pos_sale(order, shift=shift, operator_username=operator_username)
            order.refresh_from_db()
            if result.get("status") == "error" or not (order.data.get("payment") or {}).get("intent_ref"):
                raise _error(
                    order_ref,
                    code="sale_payment_outcome_unknown",
                    message=f"Venda {order_ref} criada; a cobrança ainda não foi confirmada pelo gateway.",
                )
        except PosCommittedSaleError:
            raise
        except Exception as exc:
            raise _as_error(order_ref, exc) from exc
        with transaction.atomic():
            context = IdempotencyKey.objects.select_for_update().get(scope=SCOPE, key=order_ref)
            _save(context, "done")
    order = Order.objects.get(ref=order_ref)
    return pos._pos_payment_response(order) if gateway else {}
