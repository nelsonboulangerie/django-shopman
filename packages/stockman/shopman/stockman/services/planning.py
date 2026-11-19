"""
Stock planning — production planning operations (plan, replan, realize).

Extension that builds on top of movements for production scheduling.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from shopman.stockman.conf import stockman_settings
from shopman.stockman.exceptions import StockError
from shopman.stockman.models.batch import Batch
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.models.hold import Hold
from shopman.stockman.models.move import Move
from shopman.stockman.models.quant import Quant
from shopman.stockman.services.holds import (
    QUALITY_GRADE_ALLOWLIST_METADATA_KEY,
    QUALITY_GRADE_POLICY_VERSION,
    QUALITY_GRADE_POLICY_VERSION_METADATA_KEY,
    delivery_reason,
)

logger = logging.getLogger("shopman.stockman")


def _carried_reason(hold_pk: int) -> str:
    """Motivo da perna que devolve ao saldo de produção uma entrega que seguiu adiante."""
    return delivery_reason(hold_pk, "segue com o lote")


def _early_deliveries(quant, *, limit):
    """Entregas feitas contra este saldo de produção que ainda não chegaram ao lote.

    O fato é do ledger. ``fulfill`` baixa a reserva do quant em que ela está,
    mesmo quando ele ainda é saldo de produção, e a reserva fica ``fulfilled``
    ancorada ali. O que esse saldo deve ao lote é o líquido, por reserva, da
    conta da entrega (:func:`delivery_reason`): a baixa, menos o que já seguiu
    adiante, menos o que foi devolvido. Nenhum contador além dos ``Move``.

    Devolve ``[(hold, quantidade, kind, quita)]`` na ordem das entregas, até
    ``limit``. Entrega maior que o que cabe segue em parte, e o resto continua
    devido ao mesmo saldo (a reserva só muda de quant quando quita).
    """
    holds = list(quant.holds.filter(status=HoldStatus.FULFILLED).order_by("resolved_at", "pk"))
    if not holds:
        return []

    accounts = {delivery_reason(hold.pk): hold.pk for hold in holds}
    in_account = Q()
    for base in accounts:
        in_account |= Q(reason=base) | Q(reason__startswith=f"{base} ")
    owed = dict.fromkeys(accounts.values(), Decimal("0"))
    kinds = {}
    ledger = Move.objects.filter(in_account, quant=quant).order_by("pk")
    for reason, delta, kind in ledger.values_list("reason", "delta", "kind"):
        hold_pk = next(pk for base, pk in accounts.items() if reason == base or reason.startswith(f"{base} "))
        owed[hold_pk] -= delta
        kinds.setdefault(hold_pk, kind)

    room = Decimal(str(limit))
    deliveries = []
    for hold in holds:
        if room <= 0:
            break
        pending = owed[hold.pk]
        if pending <= 0:
            continue
        part = min(pending, room)
        deliveries.append((hold, part, kinds[hold.pk], part == pending))
        room -= part
    return deliveries


def _return_early_deliveries(quant, deliveries, *, user=None) -> Decimal:
    """Perna de origem: o saldo de produção recebe de volta o que segue adiante."""
    for hold, quantity, kind, _settles in deliveries:
        Move.objects.create(quant=quant, delta=quantity, reason=_carried_reason(hold.pk), kind=kind, user=user)
    return sum((quantity for _hold, quantity, _kind, _settles in deliveries), Decimal("0"))


def _charge_early_deliveries(quant, deliveries, *, user=None) -> None:
    """Perna de destino: a entrega passa a pesar em ``quant``, e a reserva o acompanha."""
    for hold, quantity, kind, settles in deliveries:
        Move.objects.create(quant=quant, delta=-quantity, reason=delivery_reason(hold.pk), kind=kind, user=user)
        if settles:
            hold.quant = quant
            hold.save(update_fields=["quant"])


# Default TTL for holds after stock materializes (minutes).
#
# Matches the normal cart-hold default: once a planned hold materializes
# it behaves like any other ready-stock reservation. Client-side activity
# (``bump_session_hold_expiry``) extends it normally from this point on.
DEFAULT_MATERIALIZED_HOLD_TTL_MINUTES = 30


class StockPlanning:
    """Production planning methods."""

    @classmethod
    def plan(cls, quantity, product, target_date, position=None, user=None, reason="Produção planejada", **metadata):
        """
        Plan future production.

        Shortcut for receive() with mandatory target_date.

        Args:
            quantity: Amount to plan
            product: Product object (must have .sku)
            target_date: Target production date
        """
        from shopman.stockman.services.movements import StockMovements

        return StockMovements.receive(
            quantity=quantity,
            sku=product.sku,
            position=position,
            target_date=target_date,
            user=user,
            reason=reason,
            **metadata,
        )

    @classmethod
    def replan(cls, quantity, product, target_date, reason, user=None, position=None, batch=""):
        """
        Adjust existing plan.

        Finds Quant(sku, target_date, position, batch) and adjusts quantity.
        """
        from shopman.stockman.services.movements import StockMovements
        from shopman.stockman.services.queries import StockQueries

        quant = StockQueries.get_quant(product.sku, target_date=target_date, position=position, batch=batch)

        if quant is None:
            raise StockError("QUANT_NOT_FOUND", product=str(product), target_date=target_date)

        StockMovements.adjust(quant, quantity, reason, user)
        quant.refresh_from_db()
        return quant

    @classmethod
    def carry_deliveries(cls, from_quant, to_quant, *, limit, user=None) -> Decimal:
        """Leva de um saldo de produção para o seguinte o que já foi entregue contra ele.

        É o passo de quem move a contribuição de um lote entre saldos de
        produção (o "Iniciar": do planejado para o que está em produção). A
        entrega feita contra a origem acompanha a contribuição, até ``limit``;
        sem isso o destino nasce cheio e oferece de novo o que já saiu. O
        ``realize`` faz o mesmo ao fechar, do saldo de produção para o lote.

        Par de pernas que soma zero, no ``kind`` da entrega original: a venda
        continua contada uma vez só, agora no saldo que de fato a pagou.

        Returns:
            Quantidade levada.

        Raises:
            StockError('INVALID_CARRY'): origem não é saldo de produção, ou
                origem e destino não são saldos distintos do mesmo SKU.
        """
        if from_quant.target_date is None or from_quant.pk == to_quant.pk or from_quant.sku != to_quant.sku:
            raise StockError("INVALID_CARRY", from_quant=from_quant.pk, to_quant=to_quant.pk)

        with transaction.atomic():
            locked = {
                quant.pk: quant
                for quant in Quant.objects.select_for_update()
                .filter(pk__in=[from_quant.pk, to_quant.pk])
                .order_by("pk")
            }
            source, destination = locked[from_quant.pk], locked[to_quant.pk]
            early = _early_deliveries(source, limit=limit)
            carried = _return_early_deliveries(source, early, user=user)
            _charge_early_deliveries(destination, early, user=user)
            if carried:
                logger.info(
                    "stock.carry_deliveries",
                    extra={
                        "sku": source.sku,
                        "from_quant": source.pk,
                        "to_quant": destination.pk,
                        "qty": str(carried),
                    },
                )
            return carried

    @classmethod
    def realize(
        cls,
        product,
        target_date,
        actual_quantity,
        to_position,
        from_position=None,
        from_batch="",
        user=None,
        reason="Produção realizada",
        kind=Move.Kind.MAKE,
        to_batch="",
        to_quality_grade_ref="",
    ):
        """
        Realize production (planned -> physical).

        1. Finds planned Quant
        2. Adjusts quantity if actual_quantity differs
        3. Transfers to physical position (target_date=None)
        4. Holds are transferred automatically
        """
        if actual_quantity <= 0:
            raise StockError("INVALID_QUANTITY", requested=actual_quantity)

        from shopman.stockman.services.queries import StockQueries

        sku = product.sku
        quant = StockQueries.get_quant(
            sku,
            target_date=target_date,
            position=from_position,
            batch=from_batch,
        )

        if quant is None and from_position is not None:
            # Fallback: try without position
            quant = StockQueries.get_quant(sku, target_date=target_date, batch=from_batch)

        if quant is None and from_batch:
            quant = StockQueries.get_quant(sku, target_date=target_date, position=from_position)

        if quant is None and from_batch and from_position is not None:
            quant = StockQueries.get_quant(sku, target_date=target_date)

        if quant is None:
            raise StockError("QUANT_NOT_FOUND", product=str(product), target_date=target_date)

        with transaction.atomic():
            locked_quant = Quant.objects.select_for_update().get(pk=quant.pk)

            # Cada realize credita um LOTE datado, não um acumulador eterno sem
            # lote. A validade de quant sem data é julgada pelo created_at do
            # quant — um físico único por posição envelhece uma vez e engole
            # toda fornada nova para sempre (ficou invisível no alpha em
            # 26/08/2026). Com o lote, a validade é da fornada: a esquecida de
            # ontem, expedida hoje, envelhece pela data em que foi assada.
            #
            # ``to_batch`` é o lote nomeado pela partição de qualidade
            # (ADR-017); sem ele, o lote do dia. Nos dois casos o Batch ganha
            # produção+validade — e NUNCA sobrescreve fatos congelados pela
            # inspeção (get_or_create): o desconto gravado no fechamento é
            # imutável aqui.
            batch_ref = to_batch or f"{sku}-{target_date:%Y%m%d}"
            shelflife = getattr(product, "shelf_life_days", None)
            if shelflife is None:
                from shopman.stockman.shelflife import shelf_life_days_for

                shelflife = shelf_life_days_for(sku)
            batch, batch_created = Batch.objects.select_for_update().get_or_create(
                ref=batch_ref,
                defaults={
                    "sku": sku,
                    "production_date": target_date,
                    "expiry_date": (target_date + timedelta(days=shelflife) if shelflife is not None else None),
                    "quality_grade_ref": to_quality_grade_ref,
                },
            )
            if batch.sku != sku:
                raise StockError(
                    "BATCH_SKU_CONFLICT",
                    batch=batch_ref,
                    current=batch.sku,
                    requested=sku,
                )
            if to_quality_grade_ref and not batch_created:
                if batch.quality_grade_ref and batch.quality_grade_ref != to_quality_grade_ref:
                    raise StockError(
                        "BATCH_QUALITY_CONFLICT",
                        batch=batch_ref,
                        current=batch.quality_grade_ref,
                        requested=to_quality_grade_ref,
                    )
                if not batch.quality_grade_ref:
                    batch.quality_grade_ref = to_quality_grade_ref
                    batch.save(update_fields=["quality_grade_ref"])

            physical_quant, _ = Quant.objects.get_or_create(
                sku=sku, position=to_position, target_date=None, batch=batch_ref, defaults={"metadata": {}}
            )

            # Transfer from planned → physical. The planned Quant may hold
            # more stock (from multiple WOs) — debit only what was finished.
            # Rendimento MAIOR que o planejado (forno rendeu 55 de 50): o
            # débito é limitado ao saldo planejado e o físico recebe o total
            # real — o excedente é ganho de produção, nunca perda do lote.
            #
            # Saldo MENOR que o realizado também acontece quando parte do lote
            # foi entregue antes de ele fechar (#2724). Não é ganho: a entrega
            # segue para o lote (o saldo de produção a recebe de volta aqui, o
            # lote a paga logo abaixo), as pernas de produção continuam dizendo
            # o realizado inteiro e a vitrine recebe só o que ainda não saiu.
            early = _early_deliveries(locked_quant, limit=actual_quantity)
            delivered_early = _return_early_deliveries(locked_quant, early, user=user)
            planned_balance = Decimal(str(locked_quant.quantity)) + delivered_early
            planned_debit = min(actual_quantity, max(planned_balance, Decimal("0")))
            if planned_debit > 0:
                Move.objects.create(
                    quant=locked_quant, delta=-planned_debit, reason=f"Transferência: {reason}", kind=kind, user=user
                )

            Move.objects.create(
                quant=physical_quant,
                delta=actual_quantity,
                reason=f"Recebido de produção: {reason}",
                kind=kind,
                user=user,
            )
            _charge_early_deliveries(physical_quant, early, user=user)

            # Transfer holds up to actual_quantity. The pool covers the holds
            # anchored on the planned quant AND floating demand holds
            # (quant=None) for the same sku/date — demand registered before a
            # plan existed materializes together with the batch.
            #
            # Order: ``metadata.priority`` ascending (missing = last), then
            # FIFO by created_at. Priority is a neutral integer the caller
            # stamps at hold creation (e.g. committed orders outrank cart
            # reservations when the batch is short).
            #
            # Holds that were against planned stock get a TTL now
            # (the clock starts when stock materializes).
            #
            # O que já foi entregue ocupa o lote antes de qualquer reserva.
            transferred = delivered_early
            materialized_hold_ids = []
            now = timezone.now()
            hold_ttl_minutes = getattr(
                stockman_settings,
                "MATERIALIZED_HOLD_TTL_MINUTES",
                DEFAULT_MATERIALIZED_HOLD_TTL_MINUTES,
            )
            materialized_expires_at = now + timedelta(minutes=hold_ttl_minutes)

            active_statuses = [HoldStatus.PENDING, HoldStatus.CONFIRMED]
            anchored = locked_quant.holds.filter(status__in=active_statuses)
            floating = Hold.objects.filter(
                quant__isnull=True,
                sku=sku,
                target_date=target_date,
                status__in=active_statuses,
            ).filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now))

            def _priority(hold):
                value = (hold.metadata or {}).get("priority")
                try:
                    return (0, int(value)) if value is not None else (1, 0)
                except (TypeError, ValueError):
                    return (1, 0)

            def _accepts_output_grade(hold):
                metadata = hold.metadata or {}
                if metadata.get(QUALITY_GRADE_POLICY_VERSION_METADATA_KEY) != QUALITY_GRADE_POLICY_VERSION:
                    # Hold legado sem canal/escopo congelado: não existe base
                    # segura para presumir que um lote rebaixado era elegível.
                    return False
                allowlist = metadata.get(QUALITY_GRADE_ALLOWLIST_METADATA_KEY)
                if allowlist is None:
                    return True
                return bool(to_quality_grade_ref and to_quality_grade_ref in set(allowlist))

            pool = sorted(
                filter(_accepts_output_grade, [*anchored, *floating]),
                key=lambda hold: (*_priority(hold), hold.created_at),
            )

            for hold in pool:
                if transferred >= actual_quantity:
                    break
                if transferred + hold.quantity > actual_quantity:
                    continue
                hold.quant = physical_quant
                # Start the clock: set expires_at if hold had no timeout
                # (was a purchase intention against planned stock)
                update_fields = ["quant"]
                if hold.expires_at is None:
                    hold.expires_at = materialized_expires_at
                    update_fields.append("expires_at")
                hold.save(update_fields=update_fields)
                transferred += hold.quantity
                materialized_hold_ids.append(hold.hold_id)

            physical_quant.refresh_from_db()
            logger.info(
                "stock.realize",
                extra={
                    "sku": sku,
                    "target": str(target_date),
                    "actual_qty": str(actual_quantity),
                    "to_position": str(to_position),
                    "materialized_holds": len(materialized_hold_ids),
                },
            )

            # Emit signal after transaction commits (holds visible to receivers)
            if materialized_hold_ids:
                from shopman.stockman.signals import holds_materialized

                def _emit_signal():
                    holds_materialized.send(
                        sender=StockPlanning,
                        hold_ids=materialized_hold_ids,
                        sku=sku,
                        target_date=target_date,
                        to_position=to_position,
                    )

                transaction.on_commit(_emit_signal)

            return physical_quant
