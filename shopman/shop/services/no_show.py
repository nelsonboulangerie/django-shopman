"""Não retirado (WP-G11): o pedido de retirada ficou pronto e o cliente não veio.

Decisão do dono, numa frase: **o dinheiro segue o produto**. Cláusula dos
Termos: "Pedido não retirado até o fim do expediente do dia combinado: o que
ainda puder voltar à venda é devolvido pelo mesmo meio de pagamento; o que se
perdeu fica com a loja."

O gesto é de Gerente (PIN), pelo Gestor, e termina o pedido em ``cancelled``
com o motivo próprio ``not_picked_up``. Tudo o que foi decidido fica num bloco
só, ``order.data["no_show"]``, gravado ANTES da transição: o ``on_cancelled``
do lifecycle não muda, e os services que ele já chama leem o bloco.

- **estoque** (``stock.revert_fulfilled`` → :func:`stock_plan`): a linha
  ``restock`` volta ao MESMO lote de onde saiu; a linha ``loss`` vira perda com
  motivo;
- **dinheiro** (``payment.retained_q``): o devolvível de um cancelado com o
  bloco é ``capturado − retido``, no gateway, no dinheiro e na maquininha;
- **aviso ao cliente** (``policies/no_show_reason``, por
  ``cancel_reasons.customer_text``): diz para onde o dinheiro foi.

O destino de cada linha é decidido AQUI, pelo servidor, a partir de fatos
(:class:`LineFacts` → :func:`decide_destiny`). A decisão mora numa função só
para que aceitar uma escolha da tela, um dia, seja trocar essa função.

Três perguntas separadas, como no cancelamento do operador:

    régua (snapshot.lifecycle.transitions) → o canal deixa pronto virar cancelado?
    política (aqui)                        → é pedido de retirada, e já deu a hora?
    autorização (view + PIN)               → um Gerente assinou?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.formatting import format_clock, format_local
from shopman.utils.monetary import format_money

from shopman.shop.policies import no_show_reason
from shopman.shop.policies.no_show_policy import resolve_no_show_policy

logger = logging.getLogger(__name__)

#: ``order.data``: o registro inteiro do gesto.
ORDER_DATA_KEY = "no_show"

#: Código de máquina de ``order.data["cancellation_reason"]`` e a chave do motivo.
REASON = no_show_reason.KEY

#: O destino de uma linha.
RESTOCK = "restock"
LOSS = "loss"

#: Por que uma linha é perda (``""`` na linha que volta à venda).
WHY_MADE_TO_ORDER = "made_to_order"
WHY_NO_STOCK = "no_stock"
WHY_LOT_EXPIRED = "lot_expired"

#: ``Move.metadata["source"]`` da perda escrita no estoque.
MOVE_SOURCE = "no_show"

#: Os meios que o próprio sistema estorna no gateway, e por onde o dinheiro volta.
_GATEWAY_REFUND_DESTINATION = {"pix": "ao Pix do cliente", "card": "no cartão do cliente", "link": "no cartão do cliente"}


class NoShowRefused(ValueError):
    """O gesto não existe para este pedido agora. Nada foi alterado."""


class NoShowStale(NoShowRefused):
    """O pedido mudou depois que a tela leu a prévia. Nada foi alterado."""


# ── O destino de cada linha ──────────────────────────────────────────────────


@dataclass(frozen=True)
class LineFacts:
    """O que se sabe de uma linha na hora do gesto. Só fatos, nenhuma decisão."""

    #: Feita quando o cliente pede (ficha vigente "Na hora"): não volta à venda.
    made_to_order: bool
    #: A reserva de estoque da linha foi baixada: há o que devolver ao balcão.
    stock_fulfilled: bool
    #: O lote de onde a linha saiu não chega ao próximo dia de venda
    #: (:func:`next_selling_day`): vencido, ou vence hoje com a loja já fechada.
    lot_expired: bool


def decide_destiny(facts: LineFacts) -> tuple[str, str]:
    """``(destino, por quê)`` de uma linha: a ÚNICA função que decide.

    Vira perda a linha feita sob encomenda, a que não tem estoque baixado (não
    há o que devolver ao balcão) e a de lote vencido. O resto volta à venda.
    """
    if facts.made_to_order:
        return LOSS, WHY_MADE_TO_ORDER
    if not facts.stock_fulfilled:
        return LOSS, WHY_NO_STOCK
    if facts.lot_expired:
        return LOSS, WHY_LOT_EXPIRED
    return RESTOCK, ""


def _decimal(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return number if number.is_finite() else Decimal("0")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized if normalized != 0 else Decimal("0"), "f")


def _merchandise_items(order) -> list:
    """As linhas que valem agora, sem a taxa de entrega (não é mercadoria)."""
    from shopman.shop.services import order_composition
    from shopman.shop.services.order_edit import DELIVERY_FEE_SKU

    return [
        item
        for item in order_composition.effective_items(order)
        if str(item.sku or "") != DELIVERY_FEE_SKU
        and (item.meta if isinstance(item.meta, dict) else {}).get("type") != "delivery_fee"
    ]


def _components(sku: str, qty: Decimal) -> list[tuple[str, Decimal]]:
    """Os SKUs que a linha tira do estoque (o combo aberto; o resto é ele mesmo)."""
    from shopman.shop.services.stock import _expand_if_bundle

    return [(str(comp["sku"]), _decimal(comp["qty"])) for comp in _expand_if_bundle(sku, qty)]


def _hold_entries(order) -> list[dict]:
    return [
        entry
        for entry in (order.data or {}).get("hold_ids") or []
        if isinstance(entry, dict) and entry.get("hold_id")
    ]


def _line_facts(order, items, *, now: datetime) -> dict[str, LineFacts]:
    """``line_id`` → os fatos da linha, lidos do estoque e das fichas."""
    from shopman.shop.adapters import get_adapter
    from shopman.shop.services import made_to_order

    components = {item.line_id: _components(item.sku, _decimal(item.qty)) for item in items}
    skus = sorted({sku for comps in components.values() for sku, _qty in comps})
    recipes = made_to_order.made_to_order_recipes(skus)
    entries = _hold_entries(order)
    lots = get_adapter("stock").hold_lot_facts(
        [entry["hold_id"] for entry in entries], on=next_selling_day(now)
    )
    by_sku: dict[str, list[dict]] = {}
    for entry in entries:
        by_sku.setdefault(str(entry.get("sku") or ""), []).append(lots.get(entry["hold_id"]) or {})

    facts: dict[str, LineFacts] = {}
    for item in items:
        comp_skus = [sku for sku, _qty in components[item.line_id]]
        held = [by_sku.get(sku) or [] for sku in comp_skus]
        facts[item.line_id] = LineFacts(
            made_to_order=any(sku in recipes for sku in comp_skus),
            stock_fulfilled=bool(held) and all(lot and all(fact.get("fulfilled") for fact in lot) for lot in held),
            lot_expired=any(fact.get("expired") for lot in held for fact in lot),
        )
    return facts


def next_selling_day(now: datetime):
    """O primeiro dia em que a mercadoria devolvida ainda poderia ser vendida.

    "O que ainda puder voltar à venda" depende da hora (dono, 17/11/2026:
    "dependendo do horário isso vira perda"). Com a loja aberta, é hoje. Depois
    do fechamento de hoje (ou em dia sem expediente), é amanhã: o lote cujo
    último dia de venda é hoje já não tem balcão para voltar, e é perda. Sem
    essa régua, o pão de hoje não retirado no fechamento "voltava à venda" numa
    loja fechada, e a loja devolvia o dinheiro de um produto que ia para o lixo.
    """
    from shopman.shop.services import business_calendar

    local = timezone.localtime(now)
    today = local.date()
    try:
        hours = business_calendar.selling_hours_for(today)
    except Exception:
        # Sem ler o expediente, não se afirma que a loja fechou: vale hoje.
        logger.warning("no_show.selling_hours_unreadable day=%s", today, exc_info=True)
        return today
    if hours is not None and local < timezone.make_aware(datetime.combine(today, hours[1])):
        return today
    return today + timedelta(days=1)


def line_decisions(order, *, now: datetime | None = None) -> list[dict]:
    """As linhas com o destino e o valor de cada uma.

    O valor é o mesmo cálculo da devolução (``handlers/returns``): o preço pago
    por unidade (já com o desconto rateado) vezes a quantidade.
    """
    now = now or timezone.now()
    items = _merchandise_items(order)
    facts = _line_facts(order, items, now=now)
    lines = []
    for item in items:
        qty = _decimal(item.qty)
        destiny, why = decide_destiny(facts[item.line_id])
        lines.append({
            "line_id": item.line_id,
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": _decimal_text(qty),
            "destiny": destiny,
            "reason": why,
            "value_q": int(item.unit_price_q * qty),
        })
    return lines


# ── O dinheiro ───────────────────────────────────────────────────────────────


def money_split(lines: list[dict], paid_q: int) -> tuple[int, int]:
    """``(refund_q, retained_q)``: a loja fica com o valor do que se perdeu, e só com ele.

    A cláusula dos Termos tem duas metades, e a conta parte da segunda: "o que
    se perdeu fica com a loja". O retido é o valor das linhas perdidas, limitado
    ao que foi de fato capturado; TODO o resto do capturado volta ao cliente.

    Partir do retido (e não do devolvível) é o que protege os dois lados fora do
    caso redondo: quem pagou só um sinal não leva de volta o valor do que se
    perdeu, e quem pagou a mais (pedido reduzido depois de pago) recebe de volta
    também o excedente, que nunca foi de produto nenhum. Pedido não pago: zero e
    zero.
    """
    paid_q = max(0, int(paid_q or 0))
    loss_q = sum(int(line["value_q"]) for line in lines if line["destiny"] == LOSS)
    retained_q = min(paid_q, max(0, loss_q))
    return paid_q - retained_q, retained_q


def _refund_destination(order) -> str:
    """O fim da frase "R$ 12,00 …": por onde o devolvível volta, pela forma de pagamento."""
    from shopman.shop.services.order_edit import CARD_MACHINE_METHODS

    method = str(((order.data or {}).get("payment") or {}).get("method") or "")
    if method in _GATEWAY_REFUND_DESTINATION:
        return f"serão estornados {_GATEWAY_REFUND_DESTINATION[method]}."
    if method == "cash":
        return "em dinheiro ficam a devolver no caixa do PDV."
    if method in CARD_MACHINE_METHODS:
        return "ficam a estornar na maquininha, pelo PDV."
    return "ficam a devolver ao cliente."


def money_sentence(order, *, paid_q: int, refund_q: int, retained_q: int) -> str:
    """O que o gesto faz com o dinheiro, por extenso, dito ao Gerente antes de confirmar."""
    if _on_account(order):
        return _account_sentence(refund_q=refund_q, retained_q=retained_q)
    if paid_q <= 0:
        return "O pedido não foi pago: não há dinheiro a devolver."
    if refund_q <= 0:
        return f"Nada volta ao cliente: R$ {format_money(retained_q)} ficam com a loja, pelo que se perdeu."
    back = f"R$ {format_money(refund_q)} {_refund_destination(order)}"
    if retained_q <= 0:
        return back
    return f"{back} R$ {format_money(retained_q)} ficam com a loja, pelo que se perdeu."


def _account_sentence(*, refund_q: int, retained_q: int) -> str:
    """A venda só em conta: o que sai da conta do cliente e o que continua nela."""
    if refund_q <= 0 and retained_q <= 0:
        return "Nada a mexer na conta do cliente: este pedido não deve nada."
    if refund_q <= 0:
        return f"Nada sai da conta do cliente: R$ {format_money(retained_q)} continuam nela, pelo que se perdeu."
    out = f"R$ {format_money(refund_q)} saem da conta do cliente."
    if retained_q <= 0:
        return out
    return f"{out} R$ {format_money(retained_q)} continuam nela, pelo que se perdeu."


# ── Quem pode, e a partir de quando ──────────────────────────────────────────


def is_candidate(order) -> bool:
    """O gesto EXISTE para este pedido? Pronto, de retirada, fora do iFood e do balcão.

    É o recorte de quando a tela oferece a ação. Se ela já pode ser tocada
    (a hora) é :func:`block_reason`.
    """
    from shopman.shop.services import pos_sales_mode
    from shopman.shop.services.order_helpers import get_fulfillment_type

    return (
        order.status == Order.Status.READY
        and order.channel_ref != "ifood"
        and get_fulfillment_type(order) != "delivery"
        and not pos_sales_mode.is_pos_counter_order(order)
    )


def eligibility_reason(order) -> str:
    """Por que o gesto não existe para este pedido ("" quando existe)."""
    from shopman.shop.services import payment, pos_sales_mode
    from shopman.shop.services.order_helpers import get_fulfillment_type

    if order.channel_ref == "ifood":
        return "Pedido do iFood: o que não foi retirado é resolvido no portal do iFood."
    if order.status == Order.Status.CANCELLED:
        return "Este pedido já está cancelado."
    if order.status != Order.Status.READY:
        return "Não retirado é para pedido pronto, esperando a retirada."
    if get_fulfillment_type(order) == "delivery":
        return "Este pedido é de entrega: não retirado é só para retirada."
    if pos_sales_mode.is_pos_counter_order(order):
        return "Venda de balcão não tem retirada a esperar."
    payment_data = (order.data or {}).get("payment") or {}
    if payment._pays_on_account(payment_data):
        # Só em conta: a dívida fica com o valor do que se perdeu (#2697). A conta
        # já acertada e a venda que mistura a conta com outra forma não passam.
        if not payment.pays_only_on_account(payment_data):
            return "Parte na conta da casa e parte em outra forma de pagamento: o não retirado deste pedido é com o Dono."
        if payment.account_debt_settled(order):
            return "A conta deste pedido já foi acertada: o não retirado dele é com o Dono."
    if not order.can_transition_to(Order.Status.CANCELLED):
        return "Este canal não permite encerrar um pedido pronto como não retirado."
    return ""


def _on_account(order) -> bool:
    from shopman.shop.services import payment

    return payment.pays_only_on_account((order.data or {}).get("payment") or {})


def _paid_q(order) -> int | None:
    """O que o cliente pagou ou, na venda só em conta, o que ele deve dela.

    Na conta da casa a régua é a mesma: o que se perdeu fica (como dívida), o
    resto sai da conta.
    """
    from shopman.shop.services import payment

    if _on_account(order):
        return payment.open_account_debt_q(order)
    return payment.captured_balance_q(order)


def _commitment_day(order, promised: datetime | None):
    """O dia combinado: a data do pedido, o dia da hora combinada ou o dia da venda."""
    from shopman.shop.services.order_helpers import get_commitment_date

    day = get_commitment_date(order)
    if day is not None:
        return day
    anchor = promised or order.created_at
    return timezone.localtime(anchor).date() if anchor is not None else None


def release_gate(order, *, now: datetime | None = None) -> tuple[datetime | None, str]:
    """``(a partir de quando, a frase do porquê)``. ``None`` = já liberado.

    - NÃO pago: hora combinada + tolerância; sem hora combinada, a hora em que
      ficou pronto + tolerância.
    - PAGO (algo capturado): o corte do dia combinado, que é o fechamento da
      loja naquele dia menos ``cutoff_minutes_before_close``. Dia já passado:
      liberado. Dia sem expediente declarado (ou ``paid_waits_cutoff``
      desligado): a régua do não pago.

    Pagamento ilegível conta como pago: na dúvida, o gesto espera o corte.
    """
    from shopman.shop.services import business_calendar, fulfillment_window

    now = now or timezone.now()
    policy = resolve_no_show_policy()
    tolerance = timedelta(minutes=policy.tolerance_minutes)
    promised = fulfillment_window.promised_at(order)

    paid_q = _paid_q(order)
    paid = paid_q is None or paid_q > 0
    if paid and policy.paid_waits_cutoff:
        day = _commitment_day(order, promised)
        today = timezone.localtime(now).date()
        if day is not None and day < today:
            return None, ""
        hours = business_calendar.selling_hours_for(day) if day is not None else None
        if hours is not None:
            closes_at = timezone.make_aware(datetime.combine(day, hours[1]))
            cutoff = closes_at - timedelta(minutes=policy.cutoff_minutes_before_close)
            if now >= cutoff:
                return None, ""
            return cutoff, f"Pedido pago: o não retirado libera no corte do dia, {_when(cutoff, now)}."

    if promised is not None:
        at = promised + tolerance
        if now >= at:
            return None, ""
        return at, (
            f"A retirada foi combinada para {_when(promised, now, after_para=True)}: "
            f"o não retirado libera {_when(at, now)}."
        )
    ready_at = order.ready_at
    if ready_at is None:
        return None, ""
    at = ready_at + tolerance
    if now >= at:
        return None, ""
    return at, f"O pedido ficou pronto {_when(ready_at, now)}: o não retirado libera {_when(at, now)}."


def _when(moment: datetime, now: datetime, *, after_para: bool = False) -> str:
    """"às 18h" hoje; "em 20/11 às 18h" em outro dia.

    ``after_para`` é a forma que segue "para" ("combinada para as 15h", "para
    20/11 às 15h"): ali não há crase nem "em".
    """
    local = timezone.localtime(moment)
    clock = format_clock(local)
    one_o_clock = clock.startswith("1h")
    at_clock = f"{'à' if one_o_clock else 'às'} {clock}"
    if local.date() == timezone.localtime(now).date():
        return f"{'a' if one_o_clock else 'as'} {clock}" if after_para else at_clock
    day = format_local(local, "%d/%m")
    return f"{day} {at_clock}" if after_para else f"em {day} {at_clock}"


def block_reason(order, *, now: datetime | None = None) -> str:
    """Por que o gesto não pode ser feito AGORA ("" quando pode)."""
    reason = eligibility_reason(order)
    if reason:
        return reason
    _at, why = release_gate(order, now=now)
    return why


# ── Prévia e comando ─────────────────────────────────────────────────────────


def _plan(order, *, now: datetime) -> dict:
    """As linhas e o dinheiro do gesto, como seriam gravados agora."""
    lines = line_decisions(order, now=now)
    paid_q = _paid_q(order)
    known = paid_q is not None
    refund_q, retained_q = money_split(lines, paid_q or 0)
    return {
        "lines": lines,
        "paid_q": max(0, int(paid_q or 0)),
        "refund_q": refund_q,
        "retained_q": retained_q,
        "payment_known": known,
        "on_account": _on_account(order),
    }


def _revision(order, plan: dict) -> str:
    from shopman.shop.services.remote_mutations import mutation_fingerprint

    state = {
        "status": order.status,
        "total_q": order.total_q,
        "lines": [[line["line_id"], line["qty"], line["destiny"], line["value_q"]] for line in plan["lines"]],
        "paid_q": plan["paid_q"],
        "refund_q": plan["refund_q"],
        "retained_q": plan["retained_q"],
    }
    return mutation_fingerprint({"version": 1, "order": order.ref, "field": "no_show", "state": state})


def revision(order, *, now: datetime | None = None) -> str:
    """A base do gesto: o estado, as linhas com o destino e o dinheiro que a tela leu.

    Destino e dinheiro entram na base de propósito: o lote que vence à
    meia-noite ou o pagamento que chega depois da prévia mudam o que o Gerente
    assinou, e a tela velha é recusada.
    """
    return _revision(order, _plan(order, now=now or timezone.now()))


def preview(order, *, now: datetime | None = None) -> dict:
    """O que o gesto faria agora, sem gravar nada: linhas, dinheiro e os dois textos."""
    now = now or timezone.now()
    reason = eligibility_reason(order)
    releases_at = None
    if not reason:
        releases_at, reason = release_gate(order, now=now)
    plan = _plan(order, now=now)
    if not reason and not plan["payment_known"]:
        reason = "Não deu para ler o pagamento deste pedido agora. Tente de novo em instantes."
    block = {"paid_q": plan["paid_q"], "refund_q": plan["refund_q"], "retained_q": plan["retained_q"]}
    customer_block = {**block, "on_account": plan["on_account"]}
    return {
        "allowed": not reason,
        "block_reason": reason,
        "releases_at": releases_at.isoformat() if releases_at is not None else "",
        "lines": plan["lines"],
        **block,
        "money_sentence": money_sentence(order, **block),
        "customer_text": no_show_reason.customer_text(customer_block),
        "revision": _revision(order, plan),
    }


def mark_not_picked_up(
    order,
    *,
    actor: str,
    approved_by: str,
    now: datetime | None = None,
    expected_revision: str | None = None,
) -> dict:
    """Encerra o pedido como não retirado e devolve o bloco gravado.

    Sob lock, numa transação: grava ``order.data["no_show"]`` e cancela com o
    motivo ``not_picked_up`` (``cancellation.cancel``). O estoque, o dinheiro e
    o aviso saem do ``on_cancelled`` de sempre, lendo o bloco.

    ``approved_by`` é o Gerente que assinou (o ``username`` verificado pelo PIN,
    nunca o nome que veio no corpo). ``expected_revision`` é a base que a tela
    leu (:func:`revision`): diferente da de agora, a tela é velha e o gesto é
    recusado (:class:`NoShowStale`).

    Idempotente: pedido que já foi encerrado como não retirado devolve o bloco
    que está gravado, sem tocar em nada.
    """
    from shopman.shop.services import payment
    from shopman.shop.services.cancellation import cancel

    now = now or timezone.now()
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        existing = (locked.data or {}).get(ORDER_DATA_KEY)
        if locked.status == Order.Status.CANCELLED and isinstance(existing, dict):
            return dict(existing)
        payment.lock_order_payment(locked)

        reason = block_reason(locked, now=now)
        if reason:
            raise NoShowRefused(reason)
        plan = _plan(locked, now=now)
        if not plan["payment_known"]:
            raise NoShowRefused("Não deu para ler o pagamento deste pedido agora. Tente de novo em instantes.")
        if expected_revision is not None and _revision(locked, plan) != expected_revision:
            raise NoShowStale("O pedido mudou depois que você abriu o não retirado. Confira e tente de novo.")

        block = {
            "at": now.isoformat(),
            "actor": str(actor or ""),
            "approved_by": str(approved_by or ""),
            "lines": plan["lines"],
            "paid_q": plan["paid_q"],
            "refund_q": plan["refund_q"],
            "retained_q": plan["retained_q"],
            # Venda só em conta: ``paid_q`` é a dívida, e ``refund_q`` sai da conta.
            "on_account": plan["on_account"],
        }
        cancelled = cancel(
            locked,
            reason=REASON,
            actor=str(actor or "system"),
            extra_data={ORDER_DATA_KEY: block, "cancellation_reason_key": REASON},
        )
        if not cancelled:
            # ``cancel`` relê a régua do canal sob o mesmo lock; chegar aqui é o
            # canal recusar a transição. Nada foi gravado.
            raise NoShowRefused("Este canal não permite encerrar um pedido pronto como não retirado.")

    logger.info(
        "no_show.mark_not_picked_up order=%s actor=%s approved_by=%s refund_q=%s retained_q=%s",
        order.ref, actor, approved_by, block["refund_q"], block["retained_q"],
    )
    return block


# ── Estoque: o que cada reserva faz ──────────────────────────────────────────


def stock_plan(order) -> dict[str, tuple[Decimal, Decimal]] | None:
    """``hold_id`` → ``(volta ao lote, vira perda)``. ``None`` sem o bloco.

    O dinheiro segue o produto, então o estoque segue a linha: de cada SKU volta
    ao balcão exatamente a quantidade das linhas ``restock``; o resto da reserva
    é perda. A linha feita na hora fica FORA da perda daqui: o que ela gastou é
    insumo, e quem acerta o insumo (volta ou perda) é
    ``made_to_order.settle_cancellation``, que o cancelamento já chama. A
    reserva do próprio SKU dela, quando existe, só volta ao ledger.
    """
    from shopman.shop.services import made_to_order

    block = (order.data or {}).get(ORDER_DATA_KEY)
    if not isinstance(block, dict):
        return None
    restock_left: dict[str, Decimal] = {}
    for line in block.get("lines") or []:
        if not isinstance(line, dict) or line.get("destiny") != RESTOCK:
            continue
        for sku, qty in _components(str(line.get("sku") or ""), _decimal(line.get("qty"))):
            restock_left[sku] = restock_left.get(sku, Decimal("0")) + qty

    entries = _hold_entries(order)
    recipes = made_to_order.made_to_order_recipes([str(entry.get("sku") or "") for entry in entries])
    plan: dict[str, tuple[Decimal, Decimal]] = {}
    for entry in entries:
        sku = str(entry.get("sku") or "")
        qty = _decimal(entry.get("qty"))
        if qty <= 0:
            continue
        if sku in recipes:
            plan[entry["hold_id"]] = (qty, Decimal("0"))
            continue
        back = min(qty, restock_left.get(sku, Decimal("0")))
        restock_left[sku] = restock_left.get(sku, Decimal("0")) - back
        plan[entry["hold_id"]] = (back, qty - back)
    return plan


__all__ = [
    "LOSS",
    "MOVE_SOURCE",
    "ORDER_DATA_KEY",
    "REASON",
    "RESTOCK",
    "LineFacts",
    "NoShowRefused",
    "NoShowStale",
    "block_reason",
    "decide_destiny",
    "eligibility_reason",
    "is_candidate",
    "line_decisions",
    "mark_not_picked_up",
    "money_sentence",
    "money_split",
    "next_selling_day",
    "preview",
    "release_gate",
    "revision",
    "stock_plan",
]
