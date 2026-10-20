"""Baixa de insumo na venda do item feito na hora (ADR-040).

O que se faz quando o cliente pede (café, chá, croque) tem ficha, e a ficha não
é fornada: nenhuma ``WorkOrder`` desconta o insumo dela. Este service é o
escritor ÚNICO dessa saída, e roda por directive, nunca no caminho da venda:

- **na venda** (:func:`schedule_consumption`, chamada por ``stock.fulfill``, o
  mesmo ponto em que o pedido baixa o próprio SKU): agenda
  ``stock.consume_made_to_order``, uma vez na vida do pedido;
- **o handler** (:func:`consume`) acha a ficha marcada
  ``Recipe.meta["made_to_order"] = true`` de cada item, desconta UM nível dela
  (o bechamel do croque sai como bechamel, que a fornada dele já pôs no
  estoque) e escreve ``issue(kind=MAKE)`` com ``metadata.source = "sale"``.
  O que faltou não trava nada: baixa o que existe e o resto vira alerta;
- **no cancelamento** (:func:`schedule_cancellation_settlement` e
  :func:`settle_cancellation`), a regra do dono, de 20/10/2026: *"não é antes
  ou depois de pago que define, é antes ou depois de preparado"*. O que não
  foi preparado volta ao estoque (``RETURN``); o que foi preparado é perda
  (``WASTE``).

**O que é "preparado".** O fato que o sistema registra é o ticket do KDS: o
item está num ticket que a estação INICIOU (``started_at``) ou concluiu
(``completed_at``/``status="done"``). Começar a fazer já gasta o insumo (o
café moído não volta para o pacote), então iniciado conta como preparado. O
item que não passou por ticket nenhum (balcão que tira o café sem KDS, rota de
cozinha que não pega o produto) não tem fato que diga "não foi feito", e aí a
regra é a conservadora para o estoque: conta como preparado, vira perda. Devolver
sem prova inflaria o saldo, que é o defeito que este ADR existe para matar.

**Idempotência.** A directive de baixa e a de acerto nascem por
``create_persistently_deduped`` (recibo permanente por pedido), e cada efeito
roda numa transação só. O guarda final é o próprio ledger: com movimento de
``source="sale"`` para o pedido, a baixa já aconteceu; com
``source="sale_cancel"``, o acerto já aconteceu.
"""

from __future__ import annotations

import logging
from decimal import ROUND_DOWN, Decimal

from django.db import transaction

from shopman.shop.services.order_helpers import is_test_order

logger = logging.getLogger(__name__)

#: ``Recipe.meta``: a ficha é montada na venda (não é fornada nem está desligada).
MADE_TO_ORDER_KEY = "made_to_order"

#: ``Move.metadata["source"]`` das pernas deste service.
SOURCE_SALE = "sale"
SOURCE_SALE_CANCEL = "sale_cancel"

#: ``Move.metadata["outcome"]`` do acerto de cancelamento.
OUTCOME_RETURNED = "returned"
OUTCOME_WASTED = "wasted"

#: ``Order.data``: o registro legível do que a venda baixou e de como o
#: cancelamento acertou. Rastro para tela e auditoria; o guarda é o ledger.
ORDER_DATA_KEY = "made_to_order_consumption"

CONSUME_RECEIPT_SCOPE = "stock:made_to_order_consumption"
SETTLE_RECEIPT_SCOPE = "stock:made_to_order_cancellation"

_Q = Decimal("0.001")


class AmbiguousRecipe(Exception):
    """Duas fichas feitas na hora para o mesmo SKU: a baixa não escolhe."""


# ── Leitura da ficha ─────────────────────────────────────────────────


def made_to_order_recipes(skus) -> dict[str, list]:
    """``sku`` → fichas marcadas como feitas na hora (com itens pré-carregados)."""
    from shopman.craftsman.models import Recipe

    skus = sorted({sku for sku in skus if sku})
    if not skus:
        return {}
    found: dict[str, list] = {}
    for recipe in (
        Recipe.objects.filter(output_sku__in=skus, **{f"meta__{MADE_TO_ORDER_KEY}": True})
        .prefetch_related("items")
        .order_by("pk")
    ):
        found.setdefault(recipe.output_sku, []).append(recipe)
    return found


def _sold_components(order) -> list[tuple[str, Decimal]]:
    """As linhas que valem agora, combos abertos, somadas por SKU (ordem estável)."""
    from shopman.shop.services import order_composition
    from shopman.shop.services.stock import _expand_if_bundle

    totals: dict[str, Decimal] = {}
    for item in order_composition.effective_items(order):
        meta = item.meta or {}
        if meta.get("non_production") or meta.get("type") == "delivery_fee":
            continue
        for comp in _expand_if_bundle(item.sku, Decimal(str(item.qty))):
            sku = comp["sku"]
            totals[sku] = totals.get(sku, Decimal("0")) + Decimal(str(comp["qty"]))
    return [(sku, qty) for sku, qty in totals.items() if qty > 0]


def _one_level_requirements(recipe, sold_qty: Decimal) -> list[tuple[str, Decimal, str]]:
    """O que a ficha manda tirar do estoque para ``sold_qty``, um nível só.

    A BRUTA (``gross_quantity``), como a fornada: a casca sai do estoque. Item
    opcional (ingrediente alternativo) não entra, também como a fornada. Nunca
    desce até a folha: insumo que tem ficha própria (bechamel, salada) sai como
    ele mesmo, porque a fornada dele já descontou o que ele leva.
    """
    batch = Decimal(str(recipe.batch_size or 1))
    lines = []
    for item in sorted(recipe.items.all(), key=lambda ri: (ri.sort_order, ri.pk)):
        if item.is_optional:
            continue
        qty = (item.gross_quantity * sold_qty / batch).quantize(_Q)
        if qty > 0:
            lines.append((item.input_sku, qty, item.unit))
    return lines


# ── Venda: agenda e baixa ────────────────────────────────────────────


def schedule_consumption(order) -> bool:
    """Agenda a baixa de insumo da venda, se o pedido tem item feito na hora.

    Chamada por ``stock.fulfill``. Uma vez na vida do pedido (recibo
    permanente): o ``fulfill`` que roda de novo não agenda outra baixa.
    """
    if is_test_order(order):
        return False
    skus = [sku for sku, _qty in _sold_components(order)]
    if not made_to_order_recipes(skus):
        return False
    from shopman.shop.directives import STOCK_CONSUME_MADE_TO_ORDER, create_persistently_deduped

    directive = create_persistently_deduped(
        STOCK_CONSUME_MADE_TO_ORDER,
        payload={"order_ref": order.ref, "channel_ref": order.channel_ref},
        dedupe_key=order.ref,
        receipt_scope=CONSUME_RECEIPT_SCOPE,
    )
    return directive is not None


def _sale_moves(order_ref: str):
    from shopman.stockman.models.move import Move

    return Move.objects.filter(
        kind=Move.Kind.MAKE,
        metadata__source=SOURCE_SALE,
        metadata__order_ref=order_ref,
    ).select_related("quant")


def _settlement_moves(order_ref: str):
    from shopman.stockman.models.move import Move

    return Move.objects.filter(
        metadata__source=SOURCE_SALE_CANCEL,
        metadata__order_ref=order_ref,
    )


def consume(order) -> dict:
    """Escreve a baixa de insumo da venda. Uma transação; idempotente.

    Devolve o registro gravado em ``Order.data[ORDER_DATA_KEY]``. Pedido que já
    foi cancelado quando a directive rodou (cancelamento nos segundos entre a
    venda e o worker) baixa e acerta na mesma passada: a regra do preparado
    vale igual.
    """
    from shopman.craftsman.contrib.stockman.handlers import consumable_quants
    from shopman.orderman.models import Order
    from shopman.stockman.models.move import Move
    from shopman.stockman.services.movements import StockMovements

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if is_test_order(order):
            return {}
        if _sale_moves(order.ref).exists():
            logger.info("made_to_order.consume: já baixado order=%s", order.ref)
            return dict((order.data or {}).get(ORDER_DATA_KEY) or {})

        sold = _sold_components(order)
        recipes = made_to_order_recipes([sku for sku, _qty in sold])
        lines: list[dict] = []
        shortfalls: list[dict] = []
        ambiguous: list[str] = []
        for sold_sku, sold_qty in sold:
            candidates = recipes.get(sold_sku) or []
            if not candidates:
                continue
            if len(candidates) > 1:
                ambiguous.append(sold_sku)
                continue
            recipe = candidates[0]
            line = {
                "sku": sold_sku,
                "qty": str(sold_qty),
                "recipe_ref": recipe.ref,
                "items": [],
            }
            for input_sku, needed, unit in _one_level_requirements(recipe, sold_qty):
                remaining = needed
                for quant in consumable_quants(input_sku):
                    if remaining <= 0:
                        break
                    take = min(remaining, quant.available)
                    if take <= 0:
                        continue
                    StockMovements.issue(
                        quantity=take,
                        quant=quant,
                        reason=f"Consumo de venda: {order.ref}",
                        kind=Move.Kind.MAKE,
                        metadata={
                            "source": SOURCE_SALE,
                            "order_ref": order.ref,
                            "sold_sku": sold_sku,
                            "sold_qty": str(sold_qty),
                            "recipe_ref": recipe.ref,
                        },
                    )
                    remaining -= take
                issued = needed - remaining
                line["items"].append(
                    {"sku": input_sku, "unit": unit, "needed": str(needed), "issued": str(issued)}
                )
                if remaining > 0:
                    shortfalls.append(
                        {
                            "sku": input_sku,
                            "unit": unit,
                            "sold_sku": sold_sku,
                            "needed": str(needed),
                            "issued": str(issued),
                            "short": str(remaining),
                        }
                    )
            lines.append(line)

        from django.utils import timezone

        record = {"consumed_at": timezone.now().isoformat(), "lines": lines}
        if shortfalls:
            record["shortfalls"] = shortfalls
        if ambiguous:
            record["ambiguous_skus"] = ambiguous
        data = dict(order.data or {})
        data[ORDER_DATA_KEY] = record
        order.data = data
        order.save(update_fields=["data", "updated_at"])

        cancelled = order.status == Order.Status.CANCELLED

    for short in shortfalls:
        _alert_shortfall(order, short)
    for sku in ambiguous:
        _alert_ambiguous(order, sku)
    if cancelled:
        settle_cancellation(order)
    logger.info(
        "made_to_order.consume: order=%s linhas=%d faltas=%d",
        order.ref, len(lines), len(shortfalls),
    )
    return record


# ── Cancelamento: devolve ou vira perda ──────────────────────────────


def schedule_cancellation_settlement(order) -> bool:
    """Agenda o acerto de cancelamento, se a venda agendou baixa de insumo.

    Chamada pelo ``on_cancelled``. Sem baixa agendada não há o que acertar; com
    baixa ainda na fila, quem acerta é ela própria quando rodar (ela vê o
    pedido cancelado). Recibo permanente: um ``on_cancelled`` repetido não
    agenda outro acerto.
    """
    from shopman.orderman.models import IdempotencyKey

    if not IdempotencyKey.objects.filter(scope=CONSUME_RECEIPT_SCOPE, key=order.ref).exists():
        return False
    from shopman.shop.directives import STOCK_SETTLE_MADE_TO_ORDER_CANCELLATION, create_persistently_deduped

    directive = create_persistently_deduped(
        STOCK_SETTLE_MADE_TO_ORDER_CANCELLATION,
        payload={"order_ref": order.ref, "channel_ref": order.channel_ref},
        dedupe_key=order.ref,
        receipt_scope=SETTLE_RECEIPT_SCOPE,
    )
    return directive is not None


def _ticket_is_prepared(ticket) -> bool:
    """A estação começou (ou terminou) o ticket? Começar já gasta o insumo."""
    return bool(ticket.started_at or ticket.completed_at or ticket.status == "done")


def unprepared_quantities(order) -> dict[str, Decimal]:
    """``sku`` → quanto do item ficou num ticket que a estação nunca começou.

    Só o ticket do KDS prova que o item NÃO foi feito. O que não passou por
    ticket fica fora daqui, e quem chama o trata como preparado (conservador).
    """
    from shopman.shop.adapters import kds as kds_adapter

    unprepared: dict[str, Decimal] = {}
    if not getattr(order, "session_key", ""):
        return unprepared
    for ticket in kds_adapter.get_tickets(order):
        if _ticket_is_prepared(ticket):
            continue
        for item in ticket.items or []:
            sku = str((item or {}).get("sku") or "")
            if not sku:
                continue
            try:
                qty = Decimal(str(item.get("qty") or 0))
            except Exception:
                continue
            if qty > 0:
                unprepared[sku] = unprepared.get(sku, Decimal("0")) + qty
    return unprepared


def settle_cancellation(order) -> dict:
    """Acerta o insumo da venda cancelada: o não preparado volta, o preparado é perda.

    Por movimento de baixa da venda, na proporção do item: ``RETURN`` do que não
    foi preparado, na mesma posição de onde saiu; o preparado ganha o par
    ``RETURN`` + ``WASTE`` no mesmo saldo, que deixa o número como está e
    reclassifica a saída de consumo de venda para perda. A parte devolvida é
    arredondada PARA BAIXO: na dúvida de um grama, ele fica como perda.
    Uma transação; idempotente pelo ledger.
    """
    from django.utils import timezone
    from shopman.orderman.models import Order
    from shopman.stockman.models.move import Move
    from shopman.stockman.services.movements import StockMovements

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != Order.Status.CANCELLED:
            return {}
        if _settlement_moves(order.ref).exists():
            logger.info("made_to_order.settle: já acertado order=%s", order.ref)
            return dict(((order.data or {}).get(ORDER_DATA_KEY) or {}).get("cancellation") or {})
        moves = list(_sale_moves(order.ref).order_by("pk"))
        if not moves:
            return {}

        unprepared = unprepared_quantities(order)
        returned: dict[str, Decimal] = {}
        wasted: dict[str, Decimal] = {}
        for move in moves:
            meta = move.metadata or {}
            sold_sku = str(meta.get("sold_sku") or "")
            sold_qty = Decimal(str(meta.get("sold_qty") or "0"))
            issued = -move.delta
            if issued <= 0:
                continue
            fraction = Decimal("0")
            if sold_qty > 0:
                fraction = min(unprepared.get(sold_sku, Decimal("0")), sold_qty) / sold_qty
            back = (issued * fraction).quantize(_Q, rounding=ROUND_DOWN)
            lost = issued - back
            sku = move.quant.sku
            base_meta = {
                "source": SOURCE_SALE_CANCEL,
                "order_ref": order.ref,
                "sold_sku": sold_sku,
                "sale_move_id": move.pk,
            }
            if back > 0:
                Move.objects.create(
                    quant=move.quant,
                    delta=back,
                    kind=Move.Kind.RETURN,
                    reason=f"Cancelamento antes do preparo: {order.ref}",
                    metadata={**base_meta, "outcome": OUTCOME_RETURNED},
                )
                returned[sku] = returned.get(sku, Decimal("0")) + back
            if lost > 0:
                Move.objects.create(
                    quant=move.quant,
                    delta=lost,
                    kind=Move.Kind.RETURN,
                    reason=f"Cancelamento depois do preparo: {order.ref}",
                    metadata={**base_meta, "outcome": OUTCOME_WASTED},
                )
                StockMovements.issue(
                    quantity=lost,
                    quant=move.quant,
                    reason=f"Perda: preparado e cancelado ({order.ref})",
                    kind=Move.Kind.WASTE,
                    metadata={**base_meta, "outcome": OUTCOME_WASTED},
                )
                wasted[sku] = wasted.get(sku, Decimal("0")) + lost

        settlement = {
            "settled_at": timezone.now().isoformat(),
            "returned": {sku: str(qty) for sku, qty in returned.items()},
            "wasted": {sku: str(qty) for sku, qty in wasted.items()},
        }
        data = dict(order.data or {})
        record = dict(data.get(ORDER_DATA_KEY) or {})
        record["cancellation"] = settlement
        data[ORDER_DATA_KEY] = record
        order.data = data
        order.save(update_fields=["data", "updated_at"])

    logger.info(
        "made_to_order.settle: order=%s devolvido=%s perda=%s",
        order.ref, settlement["returned"], settlement["wasted"],
    )
    return settlement


# ── Alertas ──────────────────────────────────────────────────────────


def _fmt(value: str, unit: str = "") -> str:
    text = format(Decimal(str(value)).normalize(), "f").replace(".", ",")
    return f"{text} {unit}".strip()


def _alert_shortfall(order, short: dict) -> None:
    """Faltou insumo na venda: a venda seguiu, o saldo do insumo precisa de conferência.

    Um alerta ativo por insumo (não por pedido): enquanto ninguém resolve, as
    vendas seguintes não repetem o aviso, e cada uma guarda a falta no próprio
    ``Order.data``.
    """
    from shopman.shop.services.observability import create_operator_alert

    sku = short["sku"]
    create_operator_alert(
        type="stock_sale_ingredient_short",
        severity="warning",
        message=(
            f"Faltou {sku} no estoque para a venda do pedido {order.ref}: a ficha de "
            f"{short['sold_sku']} pede {_fmt(short['needed'], short['unit'])} e saíram "
            f"{_fmt(short['issued'], short['unit'])}. "
            f"A venda seguiu. Conte o {sku} e ajuste no Estoque."
        ),
        dedupe_key=f"stock_sale_ingredient_short:{sku}",
    )


def _alert_ambiguous(order, sold_sku: str) -> None:
    from shopman.shop.services.observability import create_operator_alert

    create_operator_alert(
        type="stock_sale_recipe_ambiguous",
        severity="error",
        message=(
            f"{sold_sku} tem duas fichas marcadas como feitas na hora, e a venda do pedido "
            f"{order.ref} não baixou insumo dele. Deixe uma ficha só com a marca."
        ),
        dedupe_key=f"stock_sale_recipe_ambiguous:{sold_sku}",
    )
