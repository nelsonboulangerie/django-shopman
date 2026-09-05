"""
Stockman Signal Handlers for Craftsman (vNext).

Listens to the single `production_changed` signal and dispatches
to appropriate Stockman actions. This is the *single canonical* craftsman→
stockman write path for the stock ledger (there is no InventoryProtocol write
backend — that seam is read-only, for ingredient-availability validation).

- planned: Create planned Quant (future stock) for finished goods
- finished: Consume the recipe's ingredients (kind=MAKE) and realize the
  planned output into the saleable position (kind=MAKE)
- voided: Cancel planned Quant for the WorkOrder

All output and ingredient moves are emitted with ``Move.Kind.MAKE`` — the two
legs (ingredients out, finished goods in) of a single production event.

Registered by CraftsmanStockmanConfig.ready().
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from django.dispatch import receiver
from shopman.craftsman.signals import production_changed, production_stock_shortfall

logger = logging.getLogger(__name__)

STARTED_BATCH = "started"

# Marcadores duráveis das duas pernas do ledger de produção, em
# ``WorkOrder.meta`` (JSONField que já existe — dado contextual, sem migração
# de schema). São o GUARDA de quem re-roda: ``_handle_finished`` não é
# idempotente (o ``realize`` credita o ``actual`` cheio, independente do saldo
# planejado), então re-executar sem guarda credita a vitrine EM DOBRO.
#
# Uma marca por perna, e não uma por handler, porque a falha típica é
# parcial: o insumo baixa antes do ``try`` do output, então o drift real é
# "insumo consumido, vitrine zerada" — re-rodar tudo consumiria o insumo
# duas vezes para consertar a vitrine uma.
STOCK_CONSUMED_KEY = "stock_consumed_at"
STOCK_REALIZED_KEY = "stock_realized_at"


def _stockman_available() -> bool:
    """Check if Stockman is installed."""
    try:
        from shopman.stockman.services.movements import StockMovements  # noqa: F401

        return True
    except ImportError:
        return False


@receiver(production_changed)
def handle_production_changed(sender, product_ref, date, **kwargs):
    """
    React to production changes (plan, adjust, start, finish, void).

    - planned: Create planned Quant in Stockman (future stock for finished goods)
    - adjusted: Update planned Quant quantity
    - started: Split planned vs expected supply
    - finished: Consume ingredients (MAKE) + realize planned output (MAKE)
    - voided: Cancel (zero out) the planned Quant
    """
    action = kwargs.get("action")
    work_order = kwargs.get("work_order")

    if not action:
        # Backward compat: signal without action kwarg — just log
        logger.info(
            "Production changed (no action): product_ref=%s date=%s",
            product_ref,
            date,
        )
        return

    if not _stockman_available():
        logger.debug(
            "Stockman not installed, skipping production_changed handler: "
            "action=%s product_ref=%s",
            action,
            product_ref,
        )
        return

    if action == "planned":
        _handle_planned(work_order, product_ref, date)
    elif action == "adjusted":
        _handle_adjusted(work_order, product_ref, date, kwargs.get("previous_quantity"))
    elif action == "started":
        _handle_started(work_order, product_ref, date)
    elif action == "voided":
        _handle_voided(work_order, product_ref, date)
    elif action == "finished":
        _handle_finished(work_order, product_ref, date)
    else:
        logger.warning("Unknown production_changed action: %s", action)


def _leg_done(work_order, key: str) -> bool:
    return bool((work_order.meta or {}).get(key))


def _stamp_leg(work_order, key: str) -> None:
    """Carimba a perna, durável, sem tocar em mais nada.

    Chamada SEMPRE antes de escrever a perna, e sempre sob o lock de
    :func:`_leg_lock` — ver o comentário de lá. O carimbo e a escrita da perna
    ficam na mesma transação: se a perna estourar, o carimbo volta atrás junto.

    ``update()`` de propósito: ``save()`` dispararia ``auto_now`` no
    ``updated_at`` (que as telas de operação usam como "mexeu agora") e
    reescreveria o objeto inteiro por cima de quem estiver editando o meta em
    paralelo. O ``rev`` do controle otimista é bumpado só pelo ``_check_rev``,
    então continua intacto.
    """
    from django.utils import timezone
    from shopman.craftsman.models import WorkOrder

    meta = dict(work_order.meta or {})
    if meta.get(key):
        return
    meta[key] = timezone.now().isoformat()
    work_order.meta = meta
    WorkOrder.objects.filter(pk=work_order.pk).update(meta=meta)


@contextmanager
def _leg_lock(work_order):
    """Trava a linha da WorkOrder e devolve o ``meta`` FRESCO do banco.

    O defeito que isto fecha: dois toques simultâneos no FINALIZAR creditavam a
    vitrine em dobro. O ``production_changed`` sai FORA do ``atomic`` do
    ``CraftExecution.finish``, e as pernas carimbavam o marcador DEPOIS de
    escrever — entre o COMMIT da WorkOrder e o carimbo havia uma janela em que
    ``stock_legs_complete()`` respondia falso. A segunda requisição passava pela
    idempotência (o core devolve a WO existente), caía em
    ``_ensure_stock_ledger_closed``, lia o ledger como "aberto" e reexecutava as
    duas pernas. Medido com dois quiosques reais: 24 madeleines viraram 48 na
    vitrine, e a farinha baixou 1,0 kg onde a receita pede 0,5.

    O marcador sozinho não bastava porque a leitura e a escrita dele eram dois
    atos separados. Aqui viram um só: quem chega segundo BLOQUEIA no
    ``select_for_update`` até o primeiro commitar, e então lê o carimbo já
    gravado e desiste. Ler o ``meta`` do banco (e não do objeto em memória, que
    pode ser um snapshot de antes do commit alheio) é parte da trava.

    Uma transação por PERNA, e não uma para as duas, porque a falha típica é
    parcial: o insumo baixa e o output estoura. Manter as pernas separadas
    preserva o estado "insumo consumido, vitrine zerada" que o
    ``sweep_unrealized_production`` sabe consertar sem consumir o insumo de novo.

    Em banco sem ``SELECT FOR UPDATE`` (SQLite de teste local) o lock é no-op —
    a serialização real vale onde a loja roda, no PostgreSQL.
    """
    from django.db import transaction
    from shopman.craftsman.models import WorkOrder

    with transaction.atomic():
        fresh = (
            WorkOrder.objects.select_for_update()
            .filter(pk=work_order.pk)
            .values_list("meta", flat=True)
            .first()
        )
        if fresh is not None:
            work_order.meta = fresh
        yield


def stock_legs_complete(work_order) -> bool:
    """As duas pernas do ledger de produção já foram escritas?"""
    return _leg_done(work_order, STOCK_CONSUMED_KEY) and _leg_done(
        work_order, STOCK_REALIZED_KEY
    )


def realize_finished_production(work_order) -> None:
    """Reexecuta as pernas de estoque de uma WO ``finished`` que não fechou.

    Entrada do sweeper de recuperação. Chama o handler direto, sem reemitir
    ``production_changed``: o signal acordaria também os outros receivers
    (sync de pedido, alerta de yield, anúncio, campanha) e duplicaria o que
    eles já fizeram. Cada perna é guardada pelo seu marcador, então re-rodar
    só refaz o que faltou.
    """
    _handle_finished(work_order, work_order.output_sku, work_order.target_date)


def _resolve_position(ref: str):
    """Resolve a Position by ref string. Returns None if not found."""
    from shopman.stockman.models import Position

    if not ref:
        return None
    return Position.objects.filter(ref=ref).first()


def _find_planned_quant(work_order, product_ref, date):
    """Locate the WO's planned quant.

    ``get_quant`` is a COORDINATE lookup (position=None ⇒ position IS NULL),
    but planned quants live at the WO's position. Try the resolved position
    first; if coordinates diverge (legacy WO, renamed position), fall back to
    the date's planned batch at any position.
    """
    from shopman.stockman.models import Quant
    from shopman.stockman.services.queries import StockQueries

    quant = StockQueries.get_quant(
        product_ref,
        target_date=date,
        position=_resolve_position(work_order.position_ref),
    )
    if quant is None:
        quant = (
            Quant.objects.filter(sku=product_ref, target_date=date, batch="")
            .order_by("pk")
            .first()
        )
    return quant


def _handle_planned(work_order, product_ref, date):
    """Create a planned Quant for the finished goods output."""
    if not work_order or not date:
        logger.warning(
            "Cannot create planned quant: work_order=%s date=%s",
            work_order,
            date,
        )
        return

    from shopman.stockman.services.movements import StockMovements

    # Use WO.position_ref to determine position (string ref → Position.ref)
    position = _resolve_position(work_order.position_ref)

    try:
        StockMovements.receive(
            quantity=work_order.quantity,
            sku=product_ref,
            position=position,
            target_date=date,
            reason=f"Produção planejada: {work_order.ref}",
            kind="make",  # Move.Kind.MAKE — produção (saída produzida)
        )
        logger.info(
            "Planned quant created: sku=%s qty=%s target_date=%s position=%s ref=%s",
            product_ref,
            work_order.quantity,
            date,
            work_order.position_ref or "(default)",
            work_order.ref,
        )
    except Exception:
        logger.warning(
            "Failed to create planned quant for %s (non-fatal)",
            work_order.ref,
            exc_info=True,
        )


def _handle_adjusted(work_order, product_ref, date, previous_quantity=None):
    """
    Aplica o DELTA da mudança de quantidade da WO ao Quant planejado.

    O Quant planejado é COMPARTILHADO por todas as WOs do mesmo (sku, data,
    posição) — `StockMovements.receive` faz get_or_create. Setar o Quant para a
    quantidade absoluta desta WO clobberava a contribuição das outras. Aqui
    aplicamos apenas ``delta = nova - antiga`` desta WO ao total compartilhado.
    """
    if not work_order or not date:
        logger.warning(
            "Cannot adjust planned quant: work_order=%s date=%s",
            work_order,
            date,
        )
        return

    from decimal import Decimal

    from shopman.stockman.services.movements import StockMovements

    try:
        quant = _find_planned_quant(work_order, product_ref, date)
        if quant is None:
            # Nenhum Quant ainda — cria com a contribuição desta WO (defensivo).
            StockMovements.receive(
                quantity=work_order.quantity,
                sku=product_ref,
                position=_resolve_position(work_order.position_ref),
                target_date=date,
                reference=work_order.ref,
                reason=f"Produção planejada (ajuste): {work_order.ref}",
                kind="make",  # Move.Kind.MAKE
            )
        elif previous_quantity is None:
            # Sem a quantidade anterior não dá para isolar o delta — não clobbear
            # o Quant compartilhado. (Único emissor de "adjusted" já envia; guarda.)
            logger.warning(
                "Adjust sem previous_quantity para %s — pulando p/ não clobbear "
                "o Quant compartilhado",
                work_order.ref,
            )
            return
        else:
            delta = Decimal(str(work_order.quantity)) - Decimal(str(previous_quantity))
            new_total = max(quant.quantity + delta, Decimal("0"))
            StockMovements.adjust(
                quant,
                new_total,
                reason=f"Ajuste WO {work_order.ref} (Δ {delta:+})",
            )
        logger.info(
            "Planned quant adjusted (delta): sku=%s qty=%s prev=%s target_date=%s ref=%s",
            product_ref,
            work_order.quantity,
            previous_quantity,
            date,
            work_order.ref,
        )
    except Exception:
        logger.warning(
            "Failed to adjust planned quant for %s (non-fatal)",
            work_order.ref,
            exc_info=True,
        )


def _handle_started(work_order, product_ref, date):
    """
    Materialize started supply as an operationally expected quant.

    The remaining quantity stays as plain planned supply. This lets Stockman
    distinguish what is merely planned from what is already expected because it
    effectively entered production.
    """
    if not work_order or not date:
        logger.warning(
            "Cannot materialize started supply: work_order=%s date=%s",
            work_order,
            date,
        )
        return

    from shopman.stockman.services.movements import StockMovements
    from shopman.stockman.services.queries import StockQueries

    started_qty = work_order.started_qty or work_order.quantity
    position = _resolve_position(work_order.position_ref)

    try:
        planned_quant = StockQueries.get_quant(product_ref, target_date=date, position=position)
        if planned_quant is None:
            planned_quant = StockQueries.get_quant(product_ref, target_date=date)

        if planned_quant is not None:
            remaining_planned = max(planned_quant.quantity - started_qty, 0)
            StockMovements.adjust(
                planned_quant,
                remaining_planned,
                reason=f"Entrada em produção: {work_order.ref}",
            )

        StockMovements.receive(
            quantity=started_qty,
            sku=product_ref,
            position=position,
            target_date=date,
            batch=STARTED_BATCH,
            reason=f"Produção iniciada: {work_order.ref}",
            kind="make",  # Move.Kind.MAKE
        )
        logger.info(
            "Started supply materialized: sku=%s started=%s target_date=%s position=%s ref=%s",
            product_ref,
            started_qty,
            date,
            work_order.position_ref or "(default)",
            work_order.ref,
        )
    except Exception:
        logger.warning(
            "Failed to materialize started supply for %s (non-fatal)",
            work_order.ref,
            exc_info=True,
        )


def _handle_voided(work_order, product_ref, date):
    """
    Cancel the planned Quant by adjusting it to zero.

    Uses adjust(quant, 0) to remove the planned stock.
    """
    if not work_order:
        logger.warning("Cannot void planned quant: no work_order provided")
        return

    if not date:
        logger.info(
            "WorkOrder %s voided without target_date — no planned quant to cancel",
            work_order.ref,
        )
        return

    from shopman.stockman.services.movements import StockMovements
    from shopman.stockman.services.queries import StockQueries

    try:
        quant = _find_planned_quant(work_order, product_ref, date)
        started_quant = StockQueries.get_quant(
            product_ref,
            target_date=date,
            position=_resolve_position(work_order.position_ref),
            batch=STARTED_BATCH,
        )

        if quant is None and started_quant is None:
            logger.debug(
                "No planned or started quant found for sku=%s date=%s (already cancelled?)",
                product_ref,
                date,
            )
            return

        # DELTA por WO: subtrai a contribuição DESTA WO do Quant compartilhado,
        # em vez de zerar o total (que mataria as outras WOs do mesmo sku/data).
        # Contribuições: o que entrou em produção (started_qty) vive no batch
        # STARTED; o restante (quantity - started_qty) vive no planejado.
        from decimal import Decimal

        started_qty = Decimal(str(work_order.started_qty or 0))
        planned_contribution = max(Decimal(str(work_order.quantity)) - started_qty, Decimal("0"))

        if quant is not None and quant.quantity > 0 and planned_contribution > 0:
            new_total = max(quant.quantity - planned_contribution, Decimal("0"))
            StockMovements.adjust(
                quant,
                new_quantity=new_total,
                reason=f"WO cancelada: {work_order.ref} (−{planned_contribution})",
            )
        if started_quant is not None and started_quant.quantity > 0 and started_qty > 0:
            new_started = max(started_quant.quantity - started_qty, Decimal("0"))
            StockMovements.adjust(
                started_quant,
                new_quantity=new_started,
                reason=f"WO cancelada após início: {work_order.ref} (−{started_qty})",
            )
        logger.info(
            "Planned/started quants cancelled: sku=%s target_date=%s ref=%s",
            product_ref,
            date,
            work_order.ref,
        )
    except Exception:
        logger.warning(
            "Failed to cancel planned quant for %s (non-fatal)",
            work_order.ref,
            exc_info=True,
        )


def _consume_materials(work_order):
    """Deduct a finished WorkOrder's ingredients from stock (kind=MAKE).

    Reads the persisted CONSUMPTION ``WorkOrderItem`` rows and issues each
    ingredient from available stock — the ingredients-out leg of the production
    (MAKE) event. Greedy across the ingredient's quants, present stock first.

    A shortfall stays non-fatal (consistent with the other handlers; pre-go-live
    ingredients are not yet first-class — FEFO and strict near-expiry gating land
    with Buyman/Material, see BUYMAN-PROCUREMENT-PLAN). But it is not swallowed:
    what could not be consumed is RETURNED so :func:`_handle_finished` can announce
    it (``production_stock_shortfall``) and the shop turns it into an OperatorAlert.
    Falhar fechado NÃO cabe aqui (a fornada já foi produzida); então falhar
    GRITANDO — dinheiro/estoque não pode divergir só no log.

    Returns a list of shortfall dicts (``{sku, needed, issued, short}``), empty
    when everything the recipe demanded was fully deducted.
    """
    from django.db.models import F
    from shopman.craftsman.models import WorkOrderItem
    from shopman.stockman.models.move import Move
    from shopman.stockman.services.movements import StockMovements
    from shopman.stockman.services.queries import StockQueries

    shortfalls = []
    for item in work_order.items.filter(kind=WorkOrderItem.Kind.CONSUMPTION):
        remaining = item.quantity
        if remaining <= 0:
            continue

        quants = StockQueries.list_quants(item.item_ref, include_empty=False).order_by(
            F("target_date").asc(nulls_first=True), "pk",
        )
        for quant in quants:
            if remaining <= 0:
                break
            take = min(remaining, quant.available)
            if take <= 0:
                continue
            try:
                StockMovements.issue(
                    quantity=take,
                    quant=quant,
                    reason=f"Consumo de produção: {work_order.ref}",
                    kind=Move.Kind.MAKE,
                )
                remaining -= take
            except Exception:
                logger.warning(
                    "Failed to issue ingredient %s for %s (non-fatal)",
                    item.item_ref, work_order.ref, exc_info=True,
                )

        if remaining > 0:
            logger.warning(
                "Insufficient stock to consume ingredient %s for %s: short by %s",
                item.item_ref, work_order.ref, remaining,
            )
            shortfalls.append(
                {
                    "sku": item.item_ref,
                    "needed": item.quantity,
                    "issued": item.quantity - remaining,
                    "short": remaining,
                }
            )

    return shortfalls


def _write_off_yield_shortfall(work_order, product_ref, date, finished_qty):
    """Rendimento MENOR que o iniciado: lançar a perda como WASTE no ledger.

    Sem isso o resíduo fica eterno no quant ``batch='started'`` — a
    availability o classifica como ``in_production`` e ele continua
    PROMETÍVEL sob ``planned_ok``, vendendo unidades que nunca existirão.
    Só baixa o que restou de fato no quant (o planejado pode agregar outras WOs).
    """
    from decimal import Decimal

    from shopman.stockman.models.move import Move
    from shopman.stockman.models.quant import Quant
    from shopman.stockman.services.queries import StockQueries

    started_qty = work_order.started_qty or work_order.quantity
    shortfall = Decimal(str(started_qty)) - Decimal(str(finished_qty))
    if shortfall <= 0:
        return

    # get_quant é lookup por COORDENADA (position=None ⇒ position IS NULL) —
    # o quant started vive na posição da WO. Busca na posição resolvida e,
    # se divergir, cai para o lote started da data em qualquer posição.
    quant = StockQueries.get_quant(
        product_ref,
        target_date=date,
        position=_resolve_position(work_order.position_ref),
        batch=STARTED_BATCH,
    )
    if quant is None:
        quant = (
            Quant.objects.filter(
                sku=product_ref, target_date=date, batch=STARTED_BATCH, _quantity__gt=0
            )
            .order_by("pk")
            .first()
        )
    if quant is None:
        return
    write_off = min(shortfall, Decimal(str(quant.quantity)))
    if write_off <= 0:
        return

    Move.objects.create(
        quant=quant,
        delta=-write_off,
        reason=f"Perda de rendimento: {work_order.ref} (iniciado {started_qty}, rendeu {finished_qty})",
        kind="waste",  # Move.Kind.WASTE
    )
    logger.info(
        "Yield shortfall written off: sku=%s qty=%s (WO %s)",
        product_ref, write_off, work_order.ref,
    )


def _handle_finished(work_order, product_ref, date):
    """
    Realize production: consume ingredients, then transfer planned stock →
    saleable position (both legs kind=MAKE).

    Ingredients are deducted from stock via _consume_materials. Output uses
    WO.position_ref to find the source (production) position and moves to the
    first saleable position (vitrine); holds are migrated by stock.realize().
    """
    if not work_order:
        logger.warning("Cannot realize production: no work_order provided")
        return

    # Ingredients-out leg — independent of planned-output target_date.
    # Carimbo ANTES de escrever, sob o lock: quem chega no meio espera, lê o
    # carimbo e desiste. Mesma transação, então uma falha desfaz as duas coisas.
    shortfalls = []
    with _leg_lock(work_order):
        if not _leg_done(work_order, STOCK_CONSUMED_KEY):
            _stamp_leg(work_order, STOCK_CONSUMED_KEY)
            shortfalls = _consume_materials(work_order)

    # Anúncio FORA do lock (perna já commitada): a sub-baixa vira OperatorAlert no
    # shop, que não pode ser importado daqui (core, ADR-001). Só quando o consume
    # de fato rodou (guarda do carimbo) e faltou algo — re-run do sweeper não
    # reanuncia, e o dedup de 12h no shop cobre a corrida.
    if shortfalls:
        production_stock_shortfall.send(
            sender=type(work_order),
            work_order=work_order,
            shortfalls=shortfalls,
        )

    with _leg_lock(work_order):
        _realize_output_leg(work_order, product_ref, date)


def _realize_output_leg(work_order, product_ref, date):
    """Perna de SAÍDA: realiza o planejado na vitrine. Roda sob ``_leg_lock``."""
    if _leg_done(work_order, STOCK_REALIZED_KEY):
        return

    if not date:
        logger.info(
            "WorkOrder %s finished without target_date — no planned output to realize",
            work_order.ref,
        )
        _stamp_leg(work_order, STOCK_REALIZED_KEY)
        return

    from shopman.stockman.models import Position
    from shopman.stockman.services.planning import StockPlanning
    from shopman.stockman.services.queries import StockQueries

    finished_qty = work_order.finished or work_order.quantity

    try:
        # Find saleable destination (vitrine). A intenção sempre foi "a
        # primeira posição de venda da loja" — mas Position.Meta.ordering
        # é ['ref'], então .first() sem order_by escolhia por ALFABETO e
        # qualquer posição saleable de nome menor (ex.: uma vitrine de
        # véspera) roubava a fornada recém-assada, que sumia dos canais
        # que a excluem. Ordem de criação (pk) é estável e corresponde à
        # posição de venda primária do deployment.
        to_position = (
            Position.objects.filter(is_saleable=True).order_by("pk").first()
        )
        if not to_position:
            # Sem marcador de propósito: falta uma posição de venda no
            # catálogo, e a fornada VOLTA a ser realizável no minuto em que
            # alguém criar uma. O sweeper insiste (e reclama) até lá.
            logger.warning(
                "No saleable position found — cannot realize %s",
                work_order.ref,
            )
            return

        # Find planned quant (may be at position_ref position or default)
        from_position = _resolve_position(work_order.position_ref)
        quant = StockQueries.get_quant(
            product_ref, target_date=date, position=from_position, batch=STARTED_BATCH,
        )
        from_batch = STARTED_BATCH if quant is not None else ""
        if quant is None:
            quant = StockQueries.get_quant(
                product_ref, target_date=date, position=from_position,
            )
        if quant is None:
            quant = StockQueries.get_quant(product_ref, target_date=date, batch=STARTED_BATCH)
            if quant is not None:
                from_batch = STARTED_BATCH
        if quant is None:
            # Fallback: try without position filter
            quant = StockQueries.get_quant(product_ref, target_date=date)
        if quant is None:
            # Não há o que realizar (WO sem planejado, ou já consumido por
            # outro caminho). A perna terminou: marcar, senão o sweeper volta
            # nesta WO para sempre.
            logger.info(
                "No planned quant for %s @ %s — nothing to realize",
                product_ref,
                date,
            )
            _stamp_leg(work_order, STOCK_REALIZED_KEY)
            return

        # A partição de qualidade (ADR-017) nomeia os lotes da fornada nas
        # linhas de OUTPUT — e o estoque deve carregá-los: é o quant.batch que
        # liga o hold ao lote com desconto congelado (lot_pricing). Sem linhas
        # (finish escalar, dado legado) ou com soma divergente do finished,
        # tudo cai no lote diário — nunca se perde fornada por partição torta.
        from shopman.craftsman.models import WorkOrderItem

        partition_lines = list(
            WorkOrderItem.objects.filter(
                work_order=work_order,
                kind=WorkOrderItem.Kind.OUTPUT,
                item_ref=product_ref,
            ).exclude(batch_ref="")
        )
        if partition_lines and sum(
            line.quantity for line in partition_lines
        ) == finished_qty:
            legs = [(line.quantity, line.batch_ref) for line in partition_lines]
        else:
            if partition_lines:
                logger.warning(
                    "Partition lines of %s do not sum to finished_qty=%s — "
                    "realizing into the daily lot instead",
                    work_order.ref,
                    finished_qty,
                )
            legs = [(finished_qty, "")]

        # Carimbo ANTES do realize, pelo mesmo motivo da perna de insumo: a
        # janela entre escrever e carimbar era o que deixava um segundo
        # fechamento simultâneo creditar a vitrine de novo.
        _stamp_leg(work_order, STOCK_REALIZED_KEY)
        for leg_qty, leg_batch in legs:
            StockPlanning.realize(
                product=type("P", (), {"sku": product_ref})(),
                target_date=date,
                actual_quantity=leg_qty,
                to_position=to_position,
                from_position=from_position,
                from_batch=from_batch,
                reason=f"Produção concluída: {work_order.ref}",
                to_batch=leg_batch,
            )
        logger.info(
            "Production realized: sku=%s qty=%s %s → %s em %s lote(s) (WO %s)",
            product_ref,
            finished_qty,
            work_order.position_ref or "(default)",
            to_position.ref,
            len(legs),
            work_order.ref,
        )

        _write_off_yield_shortfall(work_order, product_ref, date, finished_qty)
    except Exception:
        # "Insumo consumido e NADA realizado" não cabe numa linha de log. Quando
        # esta perna falha a WorkOrder já está FINISHED (o send é pós-commit), a
        # vitrine fica zero e o retry do operador morre em TERMINAL_STATUS —
        # irrecuperável pela mesma API. Engolir aqui deixava a divergência
        # invisível: `warning` não chega ao Sentry e nenhuma tela reclama.
        # `exception` (ERROR) chega, e propagar leva o erro até o operador —
        # é o mesmo tratamento da perna de insumos, que já propaga.
        logger.exception(
            "Failed to realize production for %s: insumos consumidos e nada "
            "realizado (divergência de estoque)",
            work_order.ref,
        )
        raise
