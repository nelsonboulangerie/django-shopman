"""Trocar o item que falta na encomenda, no PDV (#2765).

O diálogo "Resolver" da promessa em risco, no Gestor, tem a escolha "Trocar por
<produto>": ela abre o PDV em ``preorders/<ref>?swap=<sku em falta>`` (``swap``
repetido quando mais de um item falta). O endereço leva só a INTENÇÃO; o que a
tela mostra sai daqui, lido na hora em que a Caixa abre a encomenda:

- as alternativas de cada item, pela MESMA função do aviso e do diálogo
  (``order_promise.alternatives_for``): ``()`` quando a busca rodou e não achou
  nada, ``None`` quando ela não pôde rodar (aí a tela não afirma que não há);
- quanto a encomenda fica com cada troca, pela prévia da edição que já existe
  (``order_edit.plan``), com a quantidade da LINHA do pedido: a diferença de
  preço e o que acontece com ela;
- a revisão que a gravação confere (``operational_revision(field="edit")``).

Nada aqui grava. A troca grava pela edição da encomenda
(``POST pos/preorders/<ref>/swap/``, que relê as alternativas e chama
``order_edit.edit``). SKU que não é item do pedido é ignorado em silêncio.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.backstage.projections import order_promise
from shopman.shop.services import order_composition

#: Quantos SKUs um endereço pode pedir de uma vez (o resto é ignorado).
MAX_SWAP_SKUS = 10
_ZERO = Decimal("0")


@dataclass(frozen=True)
class PreorderSwapOptionProjection:
    """Uma alternativa para o item que falta: uma linha da lista, um toque.

    ``label`` é o verbo do diálogo "Resolver" ("Trocar por Fendu").
    ``available_display`` diz o que o lote da data cobre ("10 livres para
    amanhã"). ``difference_display`` é a diferença de preço da encomenda inteira
    ("R$ 4,00 a mais", "R$ 2,00 a menos", "Mesmo total"); ``money`` diz o que
    acontece com ela, na frase da prévia da edição. ``reason`` vem preenchido
    quando a edição recusaria esta troca (e então ``enabled`` é falso).
    ``refund_q`` é o que volta ao cliente quando a troca fica mais barata numa
    encomenda paga (e o gerente assina).
    """

    sku: str
    name: str
    label: str
    available_display: str
    qty_label: str
    enabled: bool = True
    reason: str = ""
    total_before_q: int = 0
    total_after_q: int = 0
    difference_q: int = 0
    total_before_display: str = ""
    total_after_display: str = ""
    difference_display: str = ""
    money: str = ""
    requires_manager_approval: bool = False
    refund_q: int = 0


@dataclass(frozen=True)
class PreorderSwapItemProjection:
    """Um item do pedido que o endereço pediu para trocar.

    ``qty`` é a quantidade da linha do pedido (texto de tela, "4", "0,35"), e é
    ela que a troca leva. ``fact`` é a frase do aviso quando o item está em risco
    ("Faltam 4x Baguete. O lote de amanhã foi cancelado."), vazia quando não
    está. ``searched`` é falso quando a busca não pôde rodar: a tela não diz que
    não há alternativa. ``empty_phrase`` é a frase da busca que rodou e não
    achou nada.
    """

    sku: str
    name: str
    qty: str
    qty_label: str
    fact: str
    searched: bool
    options: tuple[PreorderSwapOptionProjection, ...] = ()
    empty_phrase: str = ""


@dataclass(frozen=True)
class PreorderSwapProjection:
    """A troca pedida pelo endereço: os itens, a revisão e a porta da edição.

    ``refusal`` (com ``refusal_code``) diz por que a encomenda não se edita
    agora (pronta, NFC-e autorizada, iFood): a tela mostra o aviso e não oferece
    a troca. ``base_revision`` e ``expected_actor_id`` são o que a gravação
    manda de volta.
    """

    order_ref: str
    base_revision: str
    expected_actor_id: int | None
    refusal_code: str = ""
    refusal: str = ""
    items: tuple[PreorderSwapItemProjection, ...] = ()


def requested_skus(raw) -> list[str]:
    """Os SKUs do endereço, sem vazios nem repetidos, na ordem em que vieram."""
    out: list[str] = []
    for value in raw or ():
        sku = str(value or "").strip()
        if sku and sku not in out:
            out.append(sku)
        if len(out) >= MAX_SWAP_SKUS:
            break
    return out


def editable_lines(order) -> list:
    """As linhas de produto do pedido (sem a taxa de entrega e afins), como a edição as lê."""
    from shopman.shop.services import order_edit

    return [item for item in order_composition.effective_items(order) if not order_edit._is_fixed_line(item)]


def swapped_lines(order, sku: str, offer: str) -> list[dict] | None:
    """A lista FINAL de itens com ``sku`` trocado por ``offer``, na quantidade da linha.

    As linhas que ficam vão pelo ``line_id`` (mantêm o preço vendido); a nova
    entra sem ``line_id``, a preço de catálogo no canal do pedido, no lugar da
    primeira linha de ``sku``. ``None`` quando ``sku`` não é item do pedido.
    """
    lines = editable_lines(order)
    own = [item for item in lines if item.sku == sku]
    if not own:
        return None
    qty = sum((Decimal(str(item.qty)) for item in own), _ZERO)
    out: list[dict] = []
    for item in lines:
        if item.sku != sku:
            out.append({"line_id": item.line_id, "sku": item.sku, "qty": _qty_body(Decimal(str(item.qty)))})
        elif item is own[0]:
            out.append({"sku": offer, "qty": _qty_body(qty)})
    return out


def build_preorder_swap(order, skus, *, user=None) -> PreorderSwapProjection:
    """O que a tela da encomenda mostra para os SKUs que o endereço pediu para trocar."""
    from shopman.shop.services import operator_orders, order_edit

    code, refusal = order_edit.state_refusal(order)
    projection = PreorderSwapProjection(
        order_ref=order.ref,
        base_revision=operator_orders.operational_revision(order, field="edit"),
        expected_actor_id=getattr(user, "pk", None),
        refusal_code=code,
        refusal=refusal,
    )
    lines = editable_lines(order)
    wanted = [sku for sku in requested_skus(skus) if any(item.sku == sku for item in lines)]
    if not wanted or refusal:
        return projection

    promise = order_promise.read_for([order]).get(order.ref)
    facts = {
        item.sku: f"{item.label}. {item.detail}" if item.detail else item.label
        for item in (promise.items if promise is not None else ())
        if item.at_risk
    }
    target = order_promise._alternatives_date(order, timezone.localdate())
    items = []
    for sku in wanted:
        own = [item for item in lines if item.sku == sku]
        qty = sum((Decimal(str(item.qty)) for item in own), _ZERO)
        name = own[0].name or sku
        found = order_promise.alternatives_for(order, sku)
        items.append(PreorderSwapItemProjection(
            sku=sku,
            name=name,
            qty=_qty_text(qty),
            qty_label=f"{_qty_text(qty)}x {name}",
            fact=facts.get(sku, ""),
            searched=found is not None,
            options=tuple(_option(order, sku, qty, alternative) for alternative in (found or ())),
            empty_phrase=order_promise._nothing_alike(target) if found == () else "",
        ))
    return replace(projection, items=tuple(items))


def _option(order, sku: str, qty: Decimal, alternative) -> PreorderSwapOptionProjection:
    """A alternativa com a prévia da edição: quanto a encomenda fica e o que acontece com a diferença."""
    from shopman.backstage.projections import order_promise_resolution as resolution
    from shopman.backstage.projections import order_queue
    from shopman.shop.services import order_edit

    base = {
        "sku": alternative.sku,
        "name": alternative.name,
        "label": f"Trocar por {alternative.name}",
        "available_display": alternative.available_display,
        "qty_label": f"{_qty_text(qty)}x {alternative.name}",
    }
    try:
        plan = order_edit.plan(order, lines=swapped_lines(order, sku, alternative.sku))
    except order_edit.EditRefused as exc:
        return PreorderSwapOptionProjection(**base, enabled=False, reason=exc.message)
    settlement = plan.settlement
    refunds = settlement.kind in order_edit.REFUND_KINDS
    if refunds:
        money = order_queue.refund_effect(settlement.amount_q, resolution._refund_method(settlement))
    else:
        money = order_edit.money_for_customer(plan)
    return PreorderSwapOptionProjection(
        **base,
        total_before_q=plan.previous_total_q,
        total_after_q=plan.total_q,
        difference_q=plan.difference_q,
        total_before_display=_brl(plan.previous_total_q),
        total_after_display=_brl(plan.total_q),
        difference_display=difference_display(plan.difference_q),
        money=money,
        requires_manager_approval=plan.requires_manager_approval,
        refund_q=settlement.amount_q if refunds else 0,
    )


def difference_display(difference_q: int) -> str:
    """ "R$ 4,00 a mais", "R$ 2,00 a menos" ou "Mesmo total"."""
    if difference_q > 0:
        return f"{_brl(difference_q)} a mais"
    if difference_q < 0:
        return f"{_brl(-difference_q)} a menos"
    return "Mesmo total"


def _brl(value_q: int) -> str:
    return f"R$ {format_money(int(value_q))}"


def _qty_text(value: Decimal) -> str:
    """A quantidade de tela: "4", "0,35"."""
    return format(value.normalize(), "f").replace(".", ",")


def _qty_body(value: Decimal) -> str:
    """A quantidade como o corpo da edição a recebe: "4", "0.35"."""
    return format(value.normalize(), "f")
