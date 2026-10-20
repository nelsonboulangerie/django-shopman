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
- **os adicionais** escolhidos na linha (``meta["options"]``, "+ Ovo frito")
  baixam, na mesma directive, o insumo que o cadastro da opção declara
  (``consumes``, congelado na linha no momento da venda). A marca aqui é o
  próprio ``consumes``: nenhuma fornada conhece o adicional, então ele baixa
  mesmo quando o item não tem ficha ``made_to_order``;
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
from decimal import ROUND_DOWN, Decimal, InvalidOperation

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
    """As linhas que valem agora, combos abertos, somadas por SKU (ordem estável).

    A MESMA leitura que a reserva e a baixa do próprio SKU usam
    (``stock._items_to_hold``: o snapshot, ou o pedido ajustado quando houve
    ajuste): o insumo sai pelo que o pedido vendeu, nem mais nem menos.
    """
    from shopman.shop.services.stock import _expand_if_bundle, _items_to_hold

    totals: dict[str, Decimal] = {}
    for item in _items_to_hold(order):
        meta = item.get("meta") or {}
        if meta.get("non_production") or meta.get("type") == "delivery_fee":
            continue
        for comp in _expand_if_bundle(item["sku"], Decimal(str(item["qty"]))):
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


def _base_unit_quantity(sku: str, qty: Decimal, unit: str) -> tuple[Decimal, str]:
    """``qty`` na unidade-base do insumo, quando a conversão é definicional.

    O cadastro do adicional é escrito na unidade-base (Admin, aba Escolhas), e o
    validador dele só aceita unidade da mesma dimensão. Se o insumo conta em
    outra grafia da mesma dimensão (``g`` no cadastro, ``kg`` no insumo),
    converte; sem base conhecida, fica como veio.
    """
    from shopman.utils import units

    from shopman.shop.adapters.sku_validator import get_composed_sku_validator

    info = get_composed_sku_validator().get_sku_info(sku)
    base = units.normalize(getattr(info, "unit", "") if info is not None else "")
    if base and units.normalize(unit) != base and units.same_dimension(unit, base):
        return units.convert(qty, unit, base).quantize(_Q), base
    return qty, unit


def _option_requirements(order) -> list[dict]:
    """O insumo dos adicionais escolhidos nas linhas que valem agora.

    Cada opção da linha (``meta["options"]``) leva o ``consumes`` CONGELADO na
    venda (``product_options.resolve_selection``): ``[{sku, qty, unit}]`` por
    unidade do item. A baixa é ``qty do insumo × qty da opção × qty da linha``.
    Opção sem ``ref`` (iFood) não é desta casa e não baixa.

    O ``consumes`` cadastrado é a marca explícita: ao contrário da ficha, não
    depende de ``made_to_order``, porque nenhuma fornada conhece o adicional que
    o cliente escolheu na linha.

    Devolve uma entrada por opção por linha: ``{sold_sku, line_qty, sold_qty,
    group, ref, name, items: [(sku, qty, unit)]}``. ``sold_qty`` é o total do
    SKU no pedido, a mesma régua da ficha: o cancelamento parcial acerta na
    proporção do item.
    """
    from shopman.shop import product_options
    from shopman.shop.services.stock import _items_to_hold

    totals: dict[str, Decimal] = {}
    found: list[dict] = []
    for item in _items_to_hold(order):
        meta = item.get("meta") or {}
        if meta.get("non_production") or meta.get("type") == "delivery_fee":
            continue
        try:
            line_qty = Decimal(str(item.get("qty") or 0))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if line_qty <= 0:
            continue
        sold_sku = str(item.get("sku") or "")
        totals[sold_sku] = totals.get(sold_sku, Decimal("0")) + line_qty
        for option in product_options.own_options(product_options.line_options(meta)):
            try:
                option_qty = Decimal(str(option.get("qty") or 1))
            except (InvalidOperation, TypeError, ValueError):
                option_qty = Decimal("1")
            items = []
            for entry in option.get("consumes") or []:
                if not isinstance(entry, dict):
                    continue
                input_sku = str(entry.get("sku") or "").strip()
                try:
                    per_unit = Decimal(str(entry.get("qty") or 0))
                except (InvalidOperation, TypeError, ValueError):
                    logger.warning(
                        "made_to_order: qty ilegível no adicional %s de %s: %r",
                        option.get("ref"), sold_sku, entry.get("qty"),
                    )
                    continue
                if not input_sku or per_unit <= 0:
                    continue
                qty, unit = _base_unit_quantity(
                    input_sku, (per_unit * option_qty * line_qty).quantize(_Q), str(entry.get("unit") or ""),
                )
                items.append((input_sku, qty, unit))
            if items:
                found.append({
                    "sold_sku": sold_sku,
                    "line_qty": line_qty,
                    "group": str(option.get("group") or ""),
                    "ref": str(option.get("ref") or ""),
                    "name": str(option.get("name") or option.get("ref") or ""),
                    "items": items,
                })
    for requirement in found:
        requirement["sold_qty"] = totals[requirement["sold_sku"]]
    return found


def _consumable_quants(sku: str):
    """De onde a ficha tira ``sku``, na ordem em que tira: a régua da fornada.

    Espelho de ``craftsman.contrib.stockman.handlers.consumable_quants`` (o
    orquestrador não importa ``contrib`` do Core, mesma razão de
    ``package_opening._open_quants``): produção e estoque primeiro, vitrine fora
    salvo ``CONSUME_FROM_SALEABLE_POSITIONS`` e então por último; dentro de cada
    grupo, presente antes de futuro.
    """
    from django.db.models import Case, F, IntegerField, Value, When
    from shopman.craftsman.conf import get_setting
    from shopman.stockman.services.queries import StockQueries

    quants = StockQueries.list_quants(sku, include_empty=False)
    if not get_setting("CONSUME_FROM_SALEABLE_POSITIONS"):
        quants = quants.exclude(position__is_saleable=True)
    return quants.annotate(
        _shop_window=Case(
            When(position__is_saleable=True, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by("_shop_window", F("target_date").asc(nulls_first=True), "pk")


# ── Venda: agenda e baixa ────────────────────────────────────────────


def schedule_consumption(order) -> bool:
    """Agenda a baixa de insumo da venda, se o pedido tem item feito na hora.

    Chamada por ``stock.fulfill``. Uma vez na vida do pedido (recibo
    permanente): o ``fulfill`` que roda de novo não agenda outra baixa.
    """
    if is_test_order(order):
        return False
    skus = [sku for sku, _qty in _sold_components(order)]
    if not made_to_order_recipes(skus) and not _option_requirements(order):
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
    from shopman.stockman import Move

    return Move.objects.filter(
        kind=Move.Kind.MAKE,
        metadata__source=SOURCE_SALE,
        metadata__order_ref=order_ref,
    ).select_related("quant")


def _settlement_moves(order_ref: str):
    from shopman.stockman import Move

    return Move.objects.filter(
        metadata__source=SOURCE_SALE_CANCEL,
        metadata__order_ref=order_ref,
    )


def _issue_sale(input_sku: str, needed: Decimal, *, reason: str, metadata: dict) -> Decimal:
    """Tira ``needed`` de ``input_sku`` pela régua da fornada; devolve quanto saiu.

    O que falta não levanta: quem chama registra a falta e alerta.
    """
    from shopman.stockman import Move
    from shopman.stockman.services.movements import StockMovements

    remaining = needed
    for quant in _consumable_quants(input_sku):
        if remaining <= 0:
            break
        take = min(remaining, quant.available)
        if take <= 0:
            continue
        StockMovements.issue(quantity=take, quant=quant, reason=reason, kind=Move.Kind.MAKE, metadata=metadata)
        remaining -= take
    return needed - remaining


def consume(order) -> dict:
    """Escreve a baixa de insumo da venda. Uma transação; idempotente.

    Devolve o registro gravado em ``Order.data[ORDER_DATA_KEY]``. Pedido que já
    foi cancelado quando a directive rodou (cancelamento nos segundos entre a
    venda e o worker) baixa e acerta na mesma passada: a regra do preparado
    vale igual.
    """
    from shopman.orderman.models import Order

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
                issued = _issue_sale(
                    input_sku,
                    needed,
                    reason=f"Consumo de venda: {order.ref}",
                    metadata={
                        "source": SOURCE_SALE,
                        "order_ref": order.ref,
                        "sold_sku": sold_sku,
                        "sold_qty": str(sold_qty),
                        "recipe_ref": recipe.ref,
                    },
                )
                remaining = needed - issued
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

        # Os adicionais escolhidos (``meta["options"]``): uma linha do registro
        # por opção de cada item, com o insumo que o cadastro dela declara.
        for req in _option_requirements(order):
            line = {
                "sku": req["sold_sku"],
                "qty": str(req["line_qty"]),
                "option": {"group": req["group"], "ref": req["ref"], "name": req["name"]},
                "items": [],
            }
            for input_sku, needed, unit in req["items"]:
                issued = _issue_sale(
                    input_sku,
                    needed,
                    reason=f"Consumo de venda (adicional {req['name']}): {order.ref}",
                    metadata={
                        "source": SOURCE_SALE,
                        "order_ref": order.ref,
                        "sold_sku": req["sold_sku"],
                        "sold_qty": str(req["sold_qty"]),
                        "option_group": req["group"],
                        "option_ref": req["ref"],
                    },
                )
                remaining = needed - issued
                line["items"].append(
                    {"sku": input_sku, "unit": unit, "needed": str(needed), "issued": str(issued)}
                )
                if remaining > 0:
                    shortfalls.append(
                        {
                            "sku": input_sku,
                            "unit": unit,
                            "sold_sku": req["sold_sku"],
                            "option": req["name"],
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

    from shopman.shop.services.stock import _items_to_hold

    if is_test_order(order) or not _items_to_hold(order):
        return False
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
            except (InvalidOperation, TypeError, ValueError):
                logger.warning("made_to_order: qty ilegível no ticket %s: %r", ticket.pk, item.get("qty"))
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
    from shopman.stockman import Move
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
    who = (
        f"o adicional {short['option']} de {short['sold_sku']}"
        if short.get("option")
        else f"a ficha de {short['sold_sku']}"
    )
    create_operator_alert(
        type="stock_sale_ingredient_short",
        severity="warning",
        message=(
            f"Faltou {sku} no estoque para a venda do pedido {order.ref}: {who} "
            f"pede {_fmt(short['needed'], short['unit'])} e saíram "
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
