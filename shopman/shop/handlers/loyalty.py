"""
Loyalty handlers — earn points on completion, redeem points on commit,
revoke earned points and restore redeemed points on cancellation/return.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.adapters import get_adapter
from shopman.shop.directives import LOYALTY_EARN, LOYALTY_REDEEM, LOYALTY_RESTORE, LOYALTY_REVOKE

logger = logging.getLogger(__name__)


class LoyaltyEarnHandler:
    """Awards loyalty points on order completion. Topic: loyalty.earn"""

    topic = LOYALTY_EARN

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")

        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        # Um earn atrasado (fila parada, retry com backoff) pode chegar depois do
        # cancelamento — creditar aqui deixaria pontos de uma venda que não existe,
        # e o revoke pode já ter passado e concluído que não havia nada a estornar.
        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            logger.info(
                "loyalty.earn: order %s is %s, skipping credit", order_ref, order.status
            )
            return

        customer_ref = _customer_ref_for_order(order)
        if not customer_ref:
            logger.warning("loyalty.earn: no customer_ref on order %s, skipping", order_ref)
            return

        # Calculate points: points_per_real por R$ 1,00 (100 centavos),
        # configurável via Shop.defaults["loyalty"] (admin).
        from shopman.shop.loyalty_config import resolve_loyalty_config

        config = resolve_loyalty_config()
        points = (order.total_q // 100) * config.points_per_real
        if points <= 0:
            return

        try:
            adapter = get_adapter("customer")

            # Enroll if not yet enrolled (idempotent)
            adapter.enroll_loyalty(customer_ref)

            reference = f"order:{order.ref}"
            # At-least-once: retry da directive não pode creditar duas vezes.
            if adapter.has_loyalty_transaction(
                customer_ref, reference=reference, transaction_type="earn"
            ):
                logger.info("loyalty.earn: already credited for %s, skipping", reference)
                return

            # Award points
            adapter.earn_points(
                customer_ref=customer_ref,
                points=points,
                description=f"Pedido {order.ref}",
                reference=reference,
                created_by="system",
            )

            logger.info("loyalty.earn: +%d points for %s (order %s)", points, customer_ref, order_ref)

        except Exception as exc:
            raise DirectiveTransientError(str(exc)) from exc


class LoyaltyRedeemHandler:
    """Redeems loyalty points on order commit. Topic: loyalty.redeem"""

    topic = LOYALTY_REDEEM

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        order_ref = payload.get("order_ref")
        points = int(payload.get("points", 0))

        if not order_ref or points <= 0:
            return

        try:
            from shopman.orderman.models import Order
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        # Um redeem atrasado (fila parada, retry com backoff) pode chegar depois
        # do cancelamento — debitar aqui tiraria pontos de uma venda que não
        # existe, e o restore pode já ter passado e concluído que não havia
        # nada a devolver.
        if order.status in (Order.Status.CANCELLED, Order.Status.RETURNED):
            logger.info(
                "loyalty.redeem: order %s is %s, skipping debit", order_ref, order.status
            )
            return

        customer_ref = _customer_ref_for_order(order)
        if not customer_ref:
            logger.warning("loyalty.redeem: no customer_ref on order %s, skipping", order_ref)
            return

        try:
            adapter = get_adapter("customer")

            reference = f"order:{order_ref}"
            # At-least-once: retry da directive não pode debitar duas vezes.
            if adapter.has_loyalty_transaction(
                customer_ref, reference=reference, transaction_type="redeem"
            ):
                logger.info("loyalty.redeem: already debited for %s, skipping", reference)
                return

            adapter.redeem_points(
                customer_ref=customer_ref,
                points=points,
                description=f"Resgate pedido {order_ref}",
                reference=reference,
                created_by="system",
            )

            logger.info("loyalty.redeem: -%d points for %s (order %s)", points, customer_ref, order_ref)

        except Exception as exc:
            raise _redeem_directive_error(exc, order_ref=order_ref, points=points) from exc


class LoyaltyRevokeHandler:
    """Reverses earned points on cancellation/return. Topic: loyalty.revoke"""

    topic = LOYALTY_REVOKE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")
        reason = str(payload.get("reason") or "cancelled")

        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        customer_ref = _customer_ref_for_order(order)
        if not customer_ref:
            logger.info("loyalty.revoke: no customer_ref on order %s, skipping", order_ref)
            return

        try:
            adapter = get_adapter("customer")
            reference = f"order:{order.ref}"

            # At-least-once: retry da directive não pode estornar duas vezes.
            if adapter.has_loyalty_transaction(
                customer_ref, reference=reference, transaction_type="adjust"
            ):
                logger.info("loyalty.revoke: already reversed for %s, skipping", reference)
                return

            if not adapter.has_loyalty_transaction(
                customer_ref, reference=reference, transaction_type="earn"
            ):
                # Earn ainda em voo? Esperar assentar: ou ele credita (o próximo
                # retry estorna) ou vê o pedido cancelado e pula (guard do earn).
                if _live_earn_directive_exists(order_ref):
                    raise DirectiveTransientError(
                        f"earn for {order_ref} still queued, retrying later"
                    )
                # Nunca creditou (pedido nunca completou, earn pulou, ou terminal).
                logger.info("loyalty.revoke: nothing earned for %s, skipping", reference)
                return

            # A transação earn é a fonte da verdade — a taxa (points_per_real)
            # pode ter mudado entre o crédito e o estorno.
            points = adapter.get_loyalty_transaction_points(
                customer_ref, reference=reference, transaction_type="earn"
            )
            if points <= 0:
                logger.info("loyalty.revoke: no positive earn for %s, skipping", reference)
                return

            reason_label = "devolvido" if reason == "returned" else "cancelado"
            adapter.adjust_points(
                customer_ref=customer_ref,
                points=-points,
                description=f"Estorno pedido {order.ref} ({reason_label})",
                reference=reference,
                created_by="system",
            )

            logger.info(
                "loyalty.revoke: -%d points for %s (order %s, %s)",
                points, customer_ref, order_ref, reason,
            )

        except DirectiveTransientError:
            raise
        except Exception as exc:
            raise DirectiveTransientError(str(exc)) from exc


class LoyaltyRestoreHandler:
    """Returns redeemed points on cancellation/return. Topic: loyalty.restore"""

    topic = LOYALTY_RESTORE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")
        reason = str(payload.get("reason") or "cancelled")

        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        customer_ref = _customer_ref_for_order(order)
        if not customer_ref:
            logger.info("loyalty.restore: no customer_ref on order %s, skipping", order_ref)
            return

        try:
            adapter = get_adapter("customer")
            reference = f"order:{order.ref}"
            # O revoke deste mesmo pedido grava `adjust` na reference original e
            # deduplica por ela — a devolução escreve numa reference própria
            # para nenhum dos dois tomar a transação do outro como a sua.
            restore_reference = f"{reference}:restore"

            # At-least-once: retry da directive não pode devolver duas vezes.
            if adapter.has_loyalty_transaction(
                customer_ref, reference=restore_reference, transaction_type="adjust"
            ):
                logger.info("loyalty.restore: already restored for %s, skipping", reference)
                return

            # A transação redeem é a fonte da verdade (points negativos) — se o
            # débito nunca aconteceu (guard do redeem, ou terminal com alerta
            # loyalty_redeem_uncovered), devolver seria creditar em dobro.
            points = -adapter.get_loyalty_transaction_points(
                customer_ref, reference=reference, transaction_type="redeem"
            )
            if points <= 0:
                # Redeem ainda em voo? Esperar assentar: ou ele debita (o próximo
                # retry devolve) ou vê o pedido cancelado e pula (guard do redeem).
                if _live_redeem_directive_exists(order_ref):
                    raise DirectiveTransientError(
                        f"redeem for {order_ref} still queued, retrying later"
                    )
                logger.info("loyalty.restore: nothing redeemed for %s, skipping", reference)
                return

            reason_label = "devolvido" if reason == "returned" else "cancelado"
            adapter.adjust_points(
                customer_ref=customer_ref,
                points=points,
                description=f"Devolução do resgate pedido {order.ref} ({reason_label})",
                reference=restore_reference,
                created_by="system",
            )

            logger.info(
                "loyalty.restore: +%d points for %s (order %s, %s)",
                points, customer_ref, order_ref, reason,
            )

        except DirectiveTransientError:
            raise
        except Exception as exc:
            raise DirectiveTransientError(str(exc)) from exc


def _live_earn_directive_exists(order_ref: str) -> bool:
    return Directive.objects.filter(
        topic=LOYALTY_EARN,
        status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
        payload__order_ref=order_ref,
    ).exists()


def _live_redeem_directive_exists(order_ref: str) -> bool:
    return Directive.objects.filter(
        topic=LOYALTY_REDEEM,
        status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
        payload__order_ref=order_ref,
    ).exists()


def _redeem_directive_error(exc: Exception, *, order_ref: str, points: int):
    """Saldo insuficiente nunca se cura com retry → terminal; resto é transiente.

    Mas o desconto de pontos JÁ foi aplicado ao total no commit — um terminal
    silencioso é receita perdida invisível. Alertar o operador para conciliar.
    """
    from shopman.guestman.exceptions import CustomerError

    if isinstance(exc, CustomerError) and getattr(exc, "code", "") == "LOYALTY_INSUFFICIENT_POINTS":
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="loyalty_redeem_uncovered",
            severity="critical",
            message=(
                f"Pedido {order_ref} recebeu desconto de {points} pontos, mas o "
                "saldo do cliente ficou insuficiente na hora de debitar (corrida "
                "de resgate). O desconto foi dado sem baixa de pontos — conciliar."
            ),
            order_ref=order_ref,
            dedupe_key=f"loyalty_redeem_uncovered:{order_ref}",
        )
        return DirectiveTerminalError(str(exc))
    return DirectiveTransientError(str(exc))


def _customer_ref_for_order(order) -> str:
    data = order.data or {}
    customer_ref = data.get("customer_ref")
    if customer_ref:
        return str(customer_ref)

    try:
        from shopman.shop.services import customer as customer_service

        customer_service.ensure(order)
        order.refresh_from_db()
    except Exception:
        logger.warning("loyalty.customer_ref_resolution_failed order=%s", order.ref, exc_info=True)
        return ""

    return str((order.data or {}).get("customer_ref") or "")
