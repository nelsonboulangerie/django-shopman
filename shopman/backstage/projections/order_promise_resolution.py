"""O diálogo "Resolver" da promessa em risco (WP-G08): as escolhas e a mensagem ao cliente.

Leitura pura, por pedido, feita na hora em que o diálogo abre
(``GET orders/<ref>/promise-resolution/``). O aviso "Promessa em risco" diz o
fato e leva um botão só, "Resolver" (dono, 19/11/2026: "talvez a questão da
quebra da promessa exija algo mais complexo que um Alerta... Um modal"). Aqui
mora o que o diálogo mostra:

- o fato, uma frase por item em risco (as mesmas do aviso);
- o que fazer, UMA escolha por linha, nesta ordem: trocar por cada sugestão,
  remarcar, tirar só o item que falta, cancelar o pedido inteiro. Cada escolha
  diz se está aberta, o porquê quando não está, o que acontece com o dinheiro e
  como ela se conclui (``conclude``);
- o aviso aprovado que abre a conversa (WP-G07, ``notice``): qual dos três
  ("Faltou um item", "Precisamos remarcar", "Vai atrasar") e os itens que ele
  marca. O diálogo do "Avisar o cliente" envia; aqui só se diz qual;
- a mensagem ao cliente de cada escolha, pronta para conferir, copiar ou abrir
  no WhatsApp. É PROPOSTA: segue a conversa depois que o cliente responde ao
  aviso, e o operador só conclui quando ele disser o que prefere.

Nada aqui grava nem envia. As réguas são as que já existem, nenhuma
reimplementada: as sugestões vêm de ``order_promise.alternatives_for`` (a mesma
do aviso); remarcar, de ``reschedule.state_refusal``; tirar o item, da prévia
``order_edit.plan`` com a lista final; cancelar, de
``order_queue._cancel_capability`` e ``_cancel_money_effect``. As frases ao
cliente moram em ``shop/notification_copy`` (``PROMISE_PROPOSAL_COPY``).

O modelo aprovado na Meta é fixo, e a proposta é sob medida (o produto
oferecido, o valor devolvido): pela API sai só o modelo, que convida o cliente a
responder. Trocar e remarcar abrem o PDV; tirar o item usa ``POST
orders/<ref>/edit/``; cancelar usa o cancelar que já existe.

O cartão do painel não leva nada disto (nenhum dado do cliente no painel,
#2434): só a ação "Resolver". Por isso o endpoint é por pedido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote, urlencode

from django.utils import formats, timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.backstage.projections import order_promise
from shopman.shop import notification_copy
from shopman.shop.services import order_composition
from shopman.shop.services import payment as payment_svc

KIND_SWAP = "swap"
KIND_RESCHEDULE = "reschedule"
KIND_REMOVE = "remove"
KIND_CANCEL = "cancel"

#: Como a escolha se conclui: abrir o PDV, gravar a edição, ou o diálogo de cancelar.
CONCLUDE_LINK = "link"
CONCLUDE_EDIT = "edit"
CONCLUDE_CANCEL = "cancel"

NOT_AT_RISK = "Este pedido não tem mais promessa em risco."
NOTICE_FIRST = 'Primeiro, avise o cliente com o aviso "{label}". Quando ele responder, mande a proposta da escolha.'
NOTICE_REFUSED = "Copie a mensagem ou chame o cliente no WhatsApp."
NO_WHATSAPP = "Este pedido não tem WhatsApp do cliente."
POS_NOT_CONFIGURED = "O endereço do PDV não está configurado."
ONLY_ITEM = "É o único item do pedido: cancele o pedido."
LINES_NOT_FOUND = "O que falta não é uma linha deste pedido. Troque, remarque ou cancele."

LABEL_RESCHEDULE = "Remarcar para outro dia ou outro lote"
LABEL_REMOVE = "Tirar só o item que falta e devolver a diferença"
LABEL_CANCEL = "Cancelar o pedido inteiro"

#: Causas em que a reserva não está presa a lote nenhum: o item falta no estoque.
_STOCK_CAUSES = frozenset({
    order_promise.CAUSE_STOCK_SHORT, order_promise.CAUSE_NEVER_HELD, order_promise.CAUSE_HOLD_RELEASED,
})
_ZERO = Decimal("0")


@dataclass(frozen=True)
class OrderPromiseContactProjection:
    """Dá para chamar o cliente no WhatsApp? ``reason`` diz por que não."""

    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class OrderPromiseNoticeProjection:
    """O aviso aprovado que abre a conversa com o cliente (WP-G07).

    ``kind`` é o do "Avisar o cliente" (``item_missing`` | ``reschedule`` |
    ``delayed``) e ``label`` o nome do gesto. ``line_ids``: as linhas que o aviso
    "Faltou um item" já traz marcadas (as dos itens em risco). ``enabled``:
    o aviso cabe neste pedido; fechado, ``reason`` diz por quê. ``note`` é a
    linha que diz a ordem dos passos.
    """

    enabled: bool
    kind: str
    label: str
    note: str
    reason: str = ""
    line_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderPromiseEditLineProjection:
    """Uma linha da lista FINAL de itens, no formato de ``POST orders/<ref>/edit/``."""

    line_id: str
    sku: str
    qty: str


@dataclass(frozen=True)
class OrderPromiseConcludeProjection:
    """Como a escolha se conclui, depois que o cliente responde.

    ``kind``: ``link`` (abre ``href``, o PDV), ``edit`` (``POST
    orders/<ref>/edit/`` com ``items``, a lista final, e ``payload_schema``, a
    base que o comando confere: ``base_revision`` e ``expected_actor_id``) ou
    ``cancel`` (o diálogo de cancelar que já existe). ``label`` é o nome do
    botão que conclui.
    """

    kind: str
    label: str
    href: str = ""
    items: tuple[OrderPromiseEditLineProjection, ...] = ()
    payload_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderPromiseChoiceProjection:
    """Uma escolha de "O que fazer" no diálogo "Resolver".

    ``kind``: ``swap`` | ``reschedule`` | ``remove`` | ``cancel``. ``key`` é
    estável (``swap:<sku em falta>:<sku oferecido>``, ou o próprio ``kind``).
    ``detail`` é a linha de apoio: quanto há do produto oferecido, ou o que
    acontece com o dinheiro. ``enabled``/``reason``: a escolha fechada continua
    na lista, com o porquê escrito. ``message`` é a proposta ao cliente e
    ``whatsapp_url`` a conversa já com ela escrita; os dois vêm vazios na
    escolha fechada (não se propõe o que a casa não pode fazer) e
    ``whatsapp_url`` também quando o pedido não tem WhatsApp.
    ``requires_manager_approval``: concluir pede o gerente.
    """

    key: str
    kind: str
    label: str
    detail: str
    enabled: bool
    reason: str
    message: str
    whatsapp_url: str
    conclude: OrderPromiseConcludeProjection
    requires_manager_approval: bool = False


@dataclass(frozen=True)
class OrderPromiseResolutionProjection:
    """O diálogo "Resolver" de um pedido com a promessa em risco.

    ``facts``: uma frase por item em risco, as mesmas do aviso. ``choices``: as
    escolhas na ordem em que a tela as lista (trocas, remarcar, tirar o item,
    cancelar). ``notice``: o aviso aprovado que abre a conversa.
    """

    order_ref: str
    code: str
    customer_name: str
    facts: tuple[str, ...]
    contact: OrderPromiseContactProjection
    notice: OrderPromiseNoticeProjection
    choices: tuple[OrderPromiseChoiceProjection, ...]


# ── A leitura ────────────────────────────────────────────────────────────────


def build_promise_resolution(order: Order, *, user=None) -> OrderPromiseResolutionProjection | None:
    """O diálogo deste pedido, lido agora; ``None`` quando a promessa não está em risco.

    As sugestões são recalculadas na abertura (a leitura da promessa roda de
    novo): o que o aviso mostrou há dez minutos pode já ter sido vendido.
    """
    from shopman.backstage.projections import order_queue
    from shopman.shop.services.operator_orders import short_ref

    promise = order_promise.read_for([order]).get(order.ref)
    if promise is None or promise.state != order_promise.STATE_AT_RISK:
        return None
    risky = tuple(item for item in promise.items if item.at_risk)
    customer_data = (order.data or {}).get("customer") or {}
    if not isinstance(customer_data, dict):
        customer_data = {}
    whatsapp_url = order_queue._customer_contact(order, customer_data).get("customer_whatsapp_url", "")
    reading = _Reading(
        order=order,
        user=user,
        risky=risky,
        code=short_ref(order.ref),
        whatsapp_url=whatsapp_url,
        # Sem permissão, toda escolha vem fechada com o motivo (a rota já exige a
        # permissão; aqui é a mesma régua para quem chama a leitura de outro lugar).
        permission_reason="" if order_queue._manages_orders(user) else order_queue._PERMISSION_REASON,
    )
    return OrderPromiseResolutionProjection(
        order_ref=order.ref,
        code=reading.code,
        customer_name=order_queue._format_customer_display(
            customer_data.get("name", "") or customer_data.get("phone", "") or (order.data or {}).get("customer_phone", "")
            or order_queue._customer_handle(order) or ""
        ),
        facts=tuple(f"{item.label}. {item.detail}" for item in risky),
        contact=OrderPromiseContactProjection(enabled=bool(whatsapp_url), reason="" if whatsapp_url else NO_WHATSAPP),
        notice=_notice(reading),
        choices=(*_swap_choices(reading), _reschedule_choice(reading), _remove_choice(reading), _cancel_choice(reading)),
    )


def _notice(reading: _Reading) -> OrderPromiseNoticeProjection:
    """Qual aviso aprovado abre a conversa, com os itens já marcados.

    O lote atrasado (todos os itens em risco só atrasaram) é "Vai atrasar"; a
    encomenda em que todos os itens estão em risco é "Precisamos remarcar"; o
    resto é "Faltou um item", com as linhas dos itens em risco. O aviso que não
    cabe (pedido do dia não remarca, encomenda de outro dia não atrasa) cai no
    "Faltou um item". As réguas são as do ``customer_notice``.
    """
    from shopman.shop.services import customer_notice

    order = reading.order
    offered = {entry.kind: entry for entry in customer_notice.availability(order)}
    risky_skus = {item.sku for item in reading.risky}
    order_skus = {item.sku for item in order.items.all()}
    if all(item.cause == order_promise.CAUSE_BATCH_LATE for item in reading.risky):
        wanted = customer_notice.DELAYED
    elif order_skus and order_skus <= risky_skus:
        wanted = customer_notice.RESCHEDULE
    else:
        wanted = customer_notice.ITEM_MISSING
    kind = wanted if offered[wanted].enabled else customer_notice.ITEM_MISSING
    entry = offered[kind]
    reason = reading.permission_reason or entry.reason
    if reason:
        return OrderPromiseNoticeProjection(
            enabled=False, kind=kind, label=entry.label, note=NOTICE_REFUSED, reason=reason,
        )
    line_ids = (
        tuple(line.line_id for line in order.items.all().order_by("pk") if line.sku in risky_skus)
        if kind == customer_notice.ITEM_MISSING
        else ()
    )
    return OrderPromiseNoticeProjection(
        enabled=True, kind=kind, label=entry.label, note=NOTICE_FIRST.format(label=entry.label), line_ids=line_ids,
    )


@dataclass(frozen=True)
class _Reading:
    """O que todas as escolhas do pedido leem igual."""

    order: Order
    user: Any
    risky: tuple[order_promise.OrderPromiseItemProjection, ...]
    code: str
    whatsapp_url: str
    permission_reason: str

    def pos_href(self, **query) -> str:
        """O pedido aberto no PDV (``preorders/<ref>``), ou vazio sem o endereço do app."""
        from shopman.backstage.projections.hub import surface_link

        path = f"preorders/{quote(self.order.ref, safe='')}"
        pairs = [(key, value) for key, values in query.items() for value in values]
        return surface_link("pos", f"{path}?{urlencode(pairs)}" if pairs else path)

    def choice(
        self, *, key: str, kind: str, label: str, detail: str = "", reason: str = "", proposal: str = "",
        conclude: OrderPromiseConcludeProjection, requires_manager_approval: bool = False, **values: str,
    ) -> OrderPromiseChoiceProjection:
        """A escolha pronta: fechada, não leva mensagem; aberta, leva a proposta e a conversa."""
        reason = self.permission_reason or reason
        message = "" if reason else self._message(proposal, **values)
        return OrderPromiseChoiceProjection(
            key=key,
            kind=kind,
            label=label,
            detail="" if self.permission_reason else detail,
            enabled=not reason,
            reason=reason,
            message=message,
            whatsapp_url=f"{self.whatsapp_url}?text={quote(message, safe='')}" if message and self.whatsapp_url else "",
            conclude=conclude,
            requires_manager_approval=bool(requires_manager_approval) and not reason,
        )

    def _message(self, proposal: str, **values: str) -> str:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return notification_copy.promise_proposal(
            proposal,
            shop_name=str(shop) if shop is not None else "",
            customer_name=_first_name(self.order),
            order_ref_short=self.code,
            items=[_told(item) for item in self.risky],
            **values,
        )


# ── As escolhas ──────────────────────────────────────────────────────────────


def _swap_choices(reading: _Reading) -> list[OrderPromiseChoiceProjection]:
    """ "Trocar por <produto>": uma por sugestão de cada item em falta, as MESMAS do aviso.

    A troca acontece no PDV, que é onde mora a edição da encomenda: o endereço
    leva só o SKU em falta (``?swap=<sku>``, repetido quando mais de um item em
    falta tem sugestão, com o desta escolha na frente), e o PDV pede as
    alternativas ao servidor na hora (``order_promise.alternatives_for``). A
    régua de quem pode trocar é a da edição (``order_edit.state_refusal``).
    """
    from shopman.shop.services import order_edit

    swappable = [item for item in reading.risky if item.alternatives]
    if not swappable:
        return []
    _code, refusal = order_edit.state_refusal(reading.order)
    choices = []
    for item in swappable:
        href = reading.pos_href(swap=[item.sku, *(other.sku for other in swappable if other.sku != item.sku)])
        reason = refusal or ("" if href else POS_NOT_CONFIGURED)
        named = len(reading.risky) > 1
        for option in item.alternatives:
            choices.append(reading.choice(
                key=f"{KIND_SWAP}:{item.sku}:{option.sku}",
                kind=KIND_SWAP,
                label=f"Trocar {item.name} por {option.name}" if named else f"Trocar por {option.name}",
                detail=option.available_display,
                reason=reason,
                proposal="swap_named" if named else "swap",
                conclude=OrderPromiseConcludeProjection(
                    kind=CONCLUDE_LINK, label="Trocar no PDV", href="" if reason or reading.permission_reason else href,
                ),
                item=item.name,
                offer=option.name,
            ))
    return choices


def _reschedule_choice(reading: _Reading) -> OrderPromiseChoiceProjection:
    """ "Remarcar para outro dia ou outro lote": o pedido aberto no PDV, onde mora o remarcar (D-003)."""
    from shopman.shop.services import reschedule

    href = reading.pos_href()
    reason = reschedule.state_refusal(reading.order) or ("" if href else POS_NOT_CONFIGURED)
    return reading.choice(
        key=KIND_RESCHEDULE,
        kind=KIND_RESCHEDULE,
        label=LABEL_RESCHEDULE,
        reason=reason,
        proposal="reschedule",
        conclude=OrderPromiseConcludeProjection(
            kind=CONCLUDE_LINK, label="Remarcar no PDV", href="" if reason or reading.permission_reason else href,
        ),
    )


def _remove_label(reading: _Reading, *, refund_q: int | None = None) -> str:
    """O rótulo do "tirar", dizendo o que acontece quando o item só atrasou (#2809 item 7).

    O pão atrasado ainda vai sair: "Tirar só o item que falta" sugeria falta. No atraso,
    o rótulo nomeia o item e o dinheiro ("Tirar o item atrasado (Croissant) e devolver
    R$ 13,00"), e a cliente decide. A concordância é com "item", não com o produto: o
    catálogo não sabe se é "o" ou "a". Decisão da coordenação em 22/11/2026, reversível.
    """
    if not reading.risky or any(item.cause != order_promise.CAUSE_BATCH_LATE for item in reading.risky):
        return LABEL_REMOVE
    if len(reading.risky) == 1:
        label = f"Tirar o item atrasado ({reading.risky[0].name})"
    else:
        label = "Tirar os itens atrasados"
    return f"{label} e devolver {_brl(refund_q)}" if refund_q else label


def _remove_choice(reading: _Reading) -> OrderPromiseChoiceProjection:
    """ "Tirar só o item que falta e devolver a diferença": a edição que já existe, com a lista final.

    A prévia é ``order_edit.plan``: ela diz o total novo, o destino da diferença
    e se o gerente precisa assinar. Fechada quando a edição é recusada (com a
    frase dela) ou quando tirar o que falta deixaria o pedido sem item nenhum.
    """
    from shopman.backstage.projections import order_queue
    from shopman.shop.services import operator_orders, order_edit

    order = reading.order
    closed = OrderPromiseConcludeProjection(kind=CONCLUDE_EDIT, label="Tirar o item")

    def refused(reason: str) -> OrderPromiseChoiceProjection:
        return reading.choice(key=KIND_REMOVE, kind=KIND_REMOVE, label=_remove_label(reading), reason=reason, conclude=closed)

    _code, refusal = order_edit.state_refusal(order)
    if refusal or reading.permission_reason:
        return refused(refusal)
    lines, whole = _lines_without_the_missing(order, reading.risky)
    if lines is None:
        return refused(LINES_NOT_FOUND)
    if not lines:
        return refused(ONLY_ITEM)
    items = [{"line_id": line.line_id, "sku": line.sku, "qty": line.qty} for line in lines]
    try:
        plan = order_edit.plan(order, lines=items)
    except order_edit.EditRefused as exc:
        return refused(exc.message)

    settlement = plan.settlement
    refunds = settlement.kind in order_edit.REFUND_KINDS
    if refunds:
        # A frase do operador é a do cancelar, com o valor e o caminho da prévia.
        detail = order_queue.refund_effect(settlement.amount_q, _refund_method(settlement))
        proposal = {"proposal": "remove_refund", "amount": _brl(settlement.amount_q), "route": _refund_route(plan)}
    else:
        detail = order_edit.money_for_customer(plan)
        proposal = {"proposal": "remove", "total": _brl(plan.total_q)}
    removed = "part" if not whole else "one" if len(reading.risky) == 1 else "many"
    return reading.choice(
        key=KIND_REMOVE,
        kind=KIND_REMOVE,
        label=_remove_label(reading, refund_q=settlement.amount_q if refunds else None),
        detail=detail,
        conclude=OrderPromiseConcludeProjection(
            kind=CONCLUDE_EDIT,
            label="Tirar o item",
            items=tuple(lines),
            payload_schema={
                "base_revision": operator_orders.operational_revision(order, field="edit"),
                "expected_actor_id": getattr(reading.user, "pk", None),
            },
        ),
        requires_manager_approval=plan.requires_manager_approval,
        removed=notification_copy.PROMISE_REMOVED[removed],
        **proposal,
    )


def _cancel_choice(reading: _Reading) -> OrderPromiseChoiceProjection:
    """ "Cancelar o pedido inteiro": a régua e a frase do dinheiro do cancelar do detalhe."""
    from shopman.backstage.projections import order_queue

    order = reading.order
    capability = order_queue._cancel_capability(order, reading.user)
    method = str(((order.data or {}).get("payment") or {}).get("method") or "")
    money = order_queue._cancel_money_effect(order, method, order_queue._payment_status(order))
    # A mensagem só fala de dinheiro quando a frase do operador também fala (no
    # iFood o dinheiro é da plataforma) e a casa sabe por onde ele volta.
    captured_q = payment_svc.captured_balance_q(order) if money["cancel_money_effect"] else None
    route = _cancel_route(method)
    if captured_q and route:
        proposal = {"proposal": "cancel_refund", "amount": _brl(captured_q), "route": route}
    else:
        proposal = {"proposal": "cancel"}
    return reading.choice(
        key=KIND_CANCEL,
        kind=KIND_CANCEL,
        label=LABEL_CANCEL,
        detail=money["cancel_money_effect"],
        reason="" if capability["can_cancel"] else capability["cancel_block_label"],
        conclude=OrderPromiseConcludeProjection(kind=CONCLUDE_CANCEL, label="Cancelar pedido"),
        requires_manager_approval=capability["cancel_requires_approval"],
        **proposal,
    )


# ── Tirar o item: a lista final ──────────────────────────────────────────────


def _lines_without_the_missing(order, risky) -> tuple[list[OrderPromiseEditLineProjection] | None, bool]:
    """A lista final de linhas de produto, sem o que falta de cada item em risco.

    Falta tudo: a linha sai. Falta parte: a quantidade cai (das últimas linhas
    do produto para as primeiras, quando ele está em mais de uma). O item cujo
    lote está atrasado não tem falta contada: o que se tira é ele inteiro.

    Devolve ``(linhas, tirou_inteiro)``: ``None`` quando algum item em risco não
    é linha do pedido (o que a reserva guarda é parte de outro item), e
    ``tirou_inteiro`` diz se todo item em risco saiu por completo.
    """
    from shopman.shop.services import order_edit

    editable = [item for item in order_composition.effective_items(order) if not order_edit.is_fixed_line(item)]
    keep = {item.line_id: Decimal(str(item.qty)) for item in editable}
    whole = True
    for risk in risky:
        own = [item for item in editable if item.sku == risk.sku]
        if not own:
            return None, False
        ordered = sum((keep[item.line_id] for item in own), _ZERO)
        missing = _quantity(risk.missing_qty)
        to_remove = min(missing, ordered) if missing > 0 else ordered
        if to_remove < ordered:
            whole = False
        for item in reversed(own):
            taken = min(keep[item.line_id], to_remove)
            keep[item.line_id] -= taken
            to_remove -= taken
    return [
        OrderPromiseEditLineProjection(line_id=item.line_id, sku=item.sku, qty=_quantity_text(keep[item.line_id]))
        for item in editable
        if keep[item.line_id] > 0
    ], whole


def _quantity(text: str) -> Decimal:
    """A quantidade de tela ("10", "0,35") de volta a número."""
    return Decimal(str(text or "0").replace(",", "."))


def _quantity_text(value: Decimal) -> str:
    """A quantidade como o corpo da edição a recebe: "2", "0.35"."""
    return format(value.normalize(), "f")


# ── As frases ────────────────────────────────────────────────────────────────


def _brl(value_q: int) -> str:
    return f"R$ {format_money(int(value_q))}"


def _first_name(order) -> str:
    """O primeiro nome do cliente DESTE pedido; vazio quando o pedido não tem nome de gente."""
    from shopman.backstage.projections import order_queue

    customer = (order.data or {}).get("customer") or {}
    name = str(customer.get("name") or "").strip() if isinstance(customer, dict) else ""
    if not name or order_queue._is_masked_name(name) or any(ch.isdigit() for ch in name):
        return ""
    return name.split()[0]


def _told(item) -> dict[str, str]:
    """O item em risco como a mensagem o conta: o nome e o que houve, nas palavras do cliente.

    A frase só afirma o que a casa sabe. O lote cancelado, fechado com menos ou
    já fechado "não vai ficar pronto"; o que a Produção ainda pode fazer "pode
    não ficar pronto"; o lote atrasado "está atrasado"; o estoque menor que o
    reservado "está em falta"; a reserva que se soltou "pode faltar".
    """
    cause = item.cause
    if cause == order_promise.CAUSE_BATCH_LATE:
        return {"name": item.name, "situation": "late"}
    if cause in (order_promise.CAUSE_STOCK_SHORT, order_promise.CAUSE_NEVER_HELD):
        situation = "out_of_stock"
    elif cause == order_promise.CAUSE_HOLD_RELEASED:
        situation = "may_be_missing"
    elif cause in order_promise.PRODUCTION_CAUSES:
        situation = "may_not_be_ready"
    else:
        situation = "not_ready"
    partial = item.reservation == order_promise.RESERVATION_PARTIAL
    return {
        "name": item.name,
        "situation": f"{situation}_partial" if partial else situation,
        "day": "" if cause in _STOCK_CAUSES else _day_for_customer(item.batch_date),
        "lacking": f"{'falta' if item.missing_qty == '1' else 'faltam'} {item.missing_qty} de {item.qty}" if partial else "",
    }


def _day_for_customer(day_iso: str) -> str:
    """ " hoje", " amanhã", " para sábado, 21/11"; vazio para o dia que já passou."""
    try:
        day = date.fromisoformat(day_iso)
    except ValueError:
        return ""
    today = timezone.localdate()
    if day < today:
        return ""
    if day == today:
        return " hoje"
    if day == today + timedelta(days=1):
        return " amanhã"
    return f" para {formats.date_format(day, 'l').lower()}, {formats.date_format(day, 'd/m')}"


def _refund_method(settlement) -> str:
    """O meio que a frase do operador lê, pelo CAMINHO da devolução (não pelo nome do meio):
    o Pix atestado no balcão volta pela maquininha, e é isso que a prévia diz."""
    from shopman.shop.services import order_edit

    if settlement.kind == order_edit.SETTLE_REFUND_CASH:
        return "cash"
    if settlement.kind == order_edit.SETTLE_REFUND_CARD_MACHINE:
        return "credit"
    return "pix" if settlement.method == "pix" else "card"


def _refund_route(plan) -> str:
    """Por onde a diferença volta, na frase do cliente (a régua de ``order_edit.money_for_customer``)."""
    from shopman.shop.services import order_edit

    settlement = plan.settlement
    if settlement.kind == order_edit.SETTLE_REFUND_CASH:
        where = "na entrega" if plan.fulfillment_after == "delivery" else "na retirada"
        return f"{notification_copy.PROMISE_REFUND_ROUTE['cash']} {where}"
    return notification_copy.PROMISE_REFUND_ROUTE["pix" if settlement.method == "pix" else "card"]


def _cancel_route(method: str) -> str:
    """Por onde o dinheiro do pedido cancelado volta, na frase do cliente; vazio quando a casa não sabe dizer."""
    from shopman.shop.services.order_edit import CARD_MACHINE_METHODS

    if method == "pix":
        return notification_copy.PROMISE_REFUND_ROUTE["pix"]
    if method in {"card", "link"} or method in CARD_MACHINE_METHODS:
        return notification_copy.PROMISE_REFUND_ROUTE["card"]
    if method == "cash":
        return notification_copy.PROMISE_REFUND_ROUTE["cash"]
    return ""


__all__ = [
    "NOT_AT_RISK",
    "OrderPromiseChoiceProjection",
    "OrderPromiseConcludeProjection",
    "OrderPromiseContactProjection",
    "OrderPromiseEditLineProjection",
    "OrderPromiseResolutionProjection",
    "build_promise_resolution",
]
