"""O que falta neste pedido (WP-G05): as pendências do detalhe, cada uma com o gesto que resolve.

Leitura pura. O detalhe do Gestor abria com os fatos espalhados: a nota recusada
era uma pílula cinza, a DANFE só existia no cartão do painel, a cobrança vencida
aparecia em três formas e o estorno do cancelado não aparecia em nenhuma. Aqui
eles viram UMA lista, na ordem de gravidade, e cada linha traz a ação que já
existe para resolvê-la (reprocessar a nota, imprimir a DANFE, reenviar a
cobrança, cancelar). Linha sem ação é a que ninguém da casa resolve com um
toque: ela diz quem resolve.

Três regras desta lista:

- **um fato, uma linha**: a cobrança vencida, o link que não chegou e a
  encomenda barrada sem pagamento são o mesmo fato (falta o dinheiro) e moram
  na mesma linha;
- **espera saudável não é erro**: o que se resolve sozinho com o tempo (o Pix
  dentro do prazo, o dia da encomenda, o lote) sai em ``info``;
- **o dinheiro do cancelado é o da loja**: o mesmo ``payment.cancelled_money``
  que o acompanhamento do cliente lê, com a frase que ele lê.

Nada aqui grava, e nada aqui inventa ação: toda ``ref`` de ação ou está em
``actions`` do detalhe (``requeue-fiscal``, ``resend-payment-link``, ``cancel``,
``refund-retry``) ou é um gesto de tela que já existia (``print-danfe``,
``contact-customer``).
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.services import payment as payment_svc

TONE_ERROR = "error"
TONE_WARNING = "warning"
TONE_INFO = "info"
_TONE_ORDER = {TONE_ERROR: 0, TONE_WARNING: 1, TONE_INFO: 2}

#: Gestos de tela que resolvem uma pendência e não são mutação do protocolo de intenção.
ACTION_PRINT_DANFE = "print-danfe"
ACTION_CONTACT_CUSTOMER = "contact-customer"

#: Os estados do dinheiro de um pedido cancelado, como o Gestor os nomeia.
MONEY_REFUND_REQUESTED = "refund_requested"
MONEY_REFUNDED = "refunded"
MONEY_REFUND_FAILED = "refund_failed"
MONEY_CARD_HOLD_RELEASED = "card_hold_released"
MONEY_NOTHING_CHARGED = "nothing_charged"

_MONEY_LABELS = {
    MONEY_REFUND_REQUESTED: "Estorno pedido",
    MONEY_REFUNDED: "Estornado",
    MONEY_REFUND_FAILED: "Estorno não saiu",
    MONEY_CARD_HOLD_RELEASED: "Reserva do cartão desfeita",
    MONEY_NOTHING_CHARGED: "Nada foi cobrado",
}
#: O dinheiro já está onde devia: nada mais a fazer.
_MONEY_SETTLED = frozenset({MONEY_REFUNDED, MONEY_CARD_HOLD_RELEASED, MONEY_NOTHING_CHARGED})
#: Só o que MOVEU dinheiro troca o rótulo do pagamento no resumo ("Pix · Estornado").
_MONEY_RELABELS_PAYMENT = frozenset({MONEY_REFUND_REQUESTED, MONEY_REFUNDED, MONEY_REFUND_FAILED})

#: Os avisos do sino que levam ao pedido e pediam um gesto que o detalhe não tinha (P1-19).
ALERT_REFUND_FAILED = "payment_refund_failed"
ALERT_FISCAL_CANCEL_FAILED = "fiscal_cancel_failed"
ALERT_PHASE_STUCK = "lifecycle_phase_stuck"
ALERT_PREORDER_UNPAID = "preorder_activation_blocked_unpaid"
_DETAIL_ALERT_TYPES = (ALERT_REFUND_FAILED, ALERT_FISCAL_CANCEL_FAILED, ALERT_PHASE_STUCK, ALERT_PREORDER_UNPAID)

#: Bloqueios do avanço que NÃO se resolvem só esperando: pedem alguém.
_BLOCKS_NEEDING_SOMEONE = frozenset({"ifood_delivery_unknown", "device_unavailable"})
_BLOCK_PAYMENT = "payment_not_captured"
_BLOCK_PREORDER_NOT_DUE = "preorder_not_due"
_BLOCK_WAITLIST = "waitlist_fermata"
_BLOCK_FALLBACK_LABELS = {"device_unavailable": "Sem maquininha disponível"}

#: Pedido encerrado: a sacola já saiu (ou nunca vai sair), e papel que faltou não é mais pendência.
_CLOSED_STATUSES = frozenset({Order.Status.COMPLETED, Order.Status.CANCELLED, Order.Status.RETURNED})

#: A produção que o pedido espera, nas mesmas palavras do cartão do painel.
_PRODUCTION_STATE = {"planned": "não começou", "started": "em andamento"}

#: O prefixo com que ``NFCeEmitHandler`` grava a resposta do emissor na Directive.
_FISCAL_ERROR_PREFIX = "NFC-e emission failed: "


@dataclass(frozen=True)
class OrderPendingActionProjection:
    """O gesto que resolve uma pendência.

    ``ref`` é uma ação de ``actions`` do detalhe ou um gesto de tela
    (:data:`ACTION_PRINT_DANFE`, :data:`ACTION_CONTACT_CUSTOMER`). ``enabled`` e
    ``reason`` são os da própria ação: a faixa nunca oferece o que o servidor
    recusaria. ``href`` só existe na conversa com o cliente.
    """

    ref: str
    label: str
    enabled: bool = True
    reason: str = ""
    href: str = ""


@dataclass(frozen=True)
class OrderPendingProjection:
    """Uma linha de "O que falta neste pedido": o fato, o motivo e o que fazer.

    ``tone``: ``error`` (alguém precisa agir), ``warning`` (confira) ou ``info``
    (espera que se resolve sozinha). ``key`` é estável, para a tela e os testes.
    ``failure``: o que deu errado na última vez que alguém tentou o gesto desta
    linha (hoje, só o estorno tentado de novo). A tela escreve na própria linha,
    em tom de erro; vazio quando ninguém tentou ou a última tentativa deu certo.
    """

    key: str
    tone: str
    label: str
    reason: str = ""
    actions: tuple[OrderPendingActionProjection, ...] = ()
    failure: str = ""


@dataclass(frozen=True)
class CancelledMoneyProjection:
    """O destino do dinheiro de um pedido cancelado, como o Gestor o lê.

    ``state``: ``refund_requested`` · ``refunded`` · ``refund_failed`` ·
    ``card_hold_released`` · ``nothing_charged``. ``customer_line`` é a frase
    que o cliente lê no acompanhamento da loja (as mesmas chaves de copy);
    vazia quando o estorno falhou, porque a loja ainda diz "estamos devolvendo".
    ``settled``: o dinheiro já está onde devia.
    """

    state: str
    label: str
    amount_display: str
    customer_line: str
    settled: bool


def _money(value_q: int) -> str:
    return f"R$ {format_money(value_q)}"


# ── O dinheiro do cancelado ──────────────────────────────────────────────────


def _customer_money_line(money) -> str:
    """A frase do acompanhamento da loja para este destino do dinheiro.

    As chaves são as de ``storefront/presentation/order_tracking`` (o backstage
    não importa a loja; lê o mesmo catálogo de copy, com a edição do Admin).
    """
    from shopman.shop.projections.copy import build_copy

    copy = build_copy("TRACKING_MONEY")
    pix = money.method == "pix"
    if money.outcome == "refunded":
        if money.late_pix:
            line = copy.message("TRACKING_MONEY_LATE_PIX_REFUNDED")
        elif pix:
            line = copy.message("TRACKING_MONEY_REFUNDED_PIX")
        else:
            line = copy.message("TRACKING_MONEY_REFUNDED_CARD")
    elif money.outcome == "refund_requested":
        if money.late_pix:
            line = copy.message("TRACKING_MONEY_LATE_PIX_REFUNDING")
        elif pix:
            line = copy.message("TRACKING_MONEY_REFUNDING_PIX")
        else:
            line = copy.message("TRACKING_MONEY_REFUNDING_CARD")
    elif money.outcome == "card_hold_released":
        line = copy.message("TRACKING_MONEY_CARD_HOLD_RELEASED")
    elif money.outcome == "nothing_charged":
        line = copy.message("TRACKING_MONEY_NOTHING_CHARGED")
    else:
        line = ""
    return line.replace("{amount}", _money(money.amount_q))


def open_alert_types(order: Order) -> frozenset[str]:
    """Os avisos ABERTOS deste pedido que o detalhe traduz em pendência. Uma consulta."""
    from shopman.backstage.models import OperatorAlert

    return frozenset(
        OperatorAlert.objects.filter(
            order_ref=order.ref, resolved_at__isnull=True, type__in=_DETAIL_ALERT_TYPES,
        ).values_list("type", flat=True)
    )


def cancelled_money(order: Order, *, alerts: frozenset[str] | None = None) -> CancelledMoneyProjection | None:
    """O dinheiro do pedido cancelado, em um de cinco estados. ``None`` sem o que afirmar.

    Quem conta o dinheiro é ``payment.cancelled_money`` (o Payman, todos os
    intents, já descontado o que fica com a loja no "não retirado"). O terceiro
    estado do estorno é o que o código tem para a falha: o aviso
    ``payment_refund_failed`` aberto enquanto a devolução não fechou. Estorno
    que fechou vence o aviso: o Payman é o fato.
    """
    money = payment_svc.cancelled_money(order)
    if money is None:
        return None
    state = money.outcome
    if state == MONEY_REFUND_REQUESTED:
        if alerts is None:
            alerts = open_alert_types(order)
        if ALERT_REFUND_FAILED in alerts:
            state = MONEY_REFUND_FAILED
    if state not in _MONEY_LABELS:
        return None
    return CancelledMoneyProjection(
        state=state,
        label=_MONEY_LABELS[state],
        amount_display=_money(money.amount_q) if money.amount_q else "",
        customer_line="" if state == MONEY_REFUND_FAILED else _customer_money_line(money),
        settled=state in _MONEY_SETTLED,
    )


def payment_label(money: CancelledMoneyProjection | None) -> str:
    """O rótulo do pagamento no resumo do cancelado ("Estornado"), ou ``""``.

    Só quando dinheiro se moveu: o resumo dizia "Pix · Reembolsado" ao lado de
    "Pagamento estornado" no histórico, duas palavras para o mesmo fato (P2-25).
    """
    return money.label if money is not None and money.state in _MONEY_RELABELS_PAYMENT else ""


def _quoted(line: str) -> str:
    return f" O cliente lê na loja: “{line}”" if line else ""


#: Por onde o estorno tentado de novo volta, no fim de "pede esse estorno outra vez…".
_RETRY_DESTINATION = {"pix": " ao Pix do cliente", "card": " ao cartão do cliente"}


def _refund_retry_pending(order: Order, plan, by_ref: dict, *, amount_display: str):
    """ "Estorno não saiu" com o gesto (WP-G13): o valor, o que o botão faz e a última resposta.

    ``amount_display`` é o que falta voltar: o do cancelado (``cancelled_money``)
    ou, fora dele, o da régua do gesto (``plan.amount_q``).

    A falha da tentativa mora na própria linha (``failure``), vinda do pedido
    (``refund_retry.last_attempt``): quem abre o pedido depois lê o que o gateway
    respondeu, e não um aviso que já sumiu.
    """
    from django.utils import timezone
    from shopman.utils.formatting import format_local

    from shopman.backstage.services import refund_retry

    action = by_ref.get(refund_retry.ACTION_REF)
    amount = f" de {amount_display}" if amount_display else ""
    parts = [f"A devolução{amount} não chegou ao cliente."]
    if plan.block_reason:
        # Sem caminho daqui: a frase diz por quê, e não promete um botão que não age.
        parts.append(plan.block_reason)
    else:
        # Quase sempre é o valor inteiro que falta; quando só parte dele volta por
        # gateway, a frase diz quanto o botão pede.
        asked = "esse estorno" if _money(plan.amount_q) == amount_display else _money(plan.amount_q)
        parts.append(
            f"Tentar de novo pede {asked} outra vez{_RETRY_DESTINATION.get(plan.method, '')}, "
            "com a autorização de um gerente."
        )
    failure = ""
    attempt = refund_retry.last_attempt(order)
    if attempt is not None and attempt.message and attempt.outcome != refund_retry.OUTCOME_UNRECORDED:
        when = format_local(timezone.localtime(attempt.at), "%d/%m às {clock}")
        failure = f"Última tentativa, em {when}: {_sentence(attempt.message)}"
    return OrderPendingProjection(
        key="refund",
        tone=TONE_ERROR,
        label=_MONEY_LABELS[MONEY_REFUND_FAILED],
        reason=" ".join(parts),
        actions=() if plan.block_reason else _from_action(action),
        failure=failure,
    )


def _money_pending(
    order: Order, money: CancelledMoneyProjection | None, alerts: frozenset[str], *, refund_retry_plan=None, by_ref=None,
):
    if money is not None and money.state == MONEY_REFUND_REQUESTED:
        return OrderPendingProjection(
            key="refund",
            tone=TONE_INFO,
            label=money.label,
            reason=(
                f"A devolução de {money.amount_display} foi pedida e ainda não foi confirmada."
                f"{_quoted(money.customer_line)}"
            ),
        )
    failed = (money is not None and money.state == MONEY_REFUND_FAILED) or (
        ALERT_REFUND_FAILED in alerts and (money is None or not money.settled)
    )
    if not failed:
        return None
    if money is not None and money.state == MONEY_REFUND_FAILED and refund_retry_plan is not None:
        return _refund_retry_pending(order, refund_retry_plan, by_ref or {}, amount_display=money.amount_display)
    if money is None and refund_retry_plan is not None and refund_retry_plan.failed:
        # Fora do cancelado (devolução, encomenda editada que ficou mais barata,
        # pagamento que chegou depois do balcão): o valor é o da régua do gesto.
        amount_display = _money(refund_retry_plan.amount_q) if refund_retry_plan.amount_q else ""
        return _refund_retry_pending(order, refund_retry_plan, by_ref or {}, amount_display=amount_display)
    # Sem o que pedir de novo daqui (nada mais a devolver pelo meio online, ou o
    # Payman mudo): quem conclui é o suporte.
    amount = f" de {money.amount_display}" if money is not None and money.amount_display else ""
    return OrderPendingProjection(
        key="refund",
        tone=TONE_ERROR,
        label=_MONEY_LABELS[MONEY_REFUND_FAILED],
        reason=(
            f"A devolução{amount} não chegou ao cliente. O suporte já recebeu o aviso e conclui o "
            "estorno no Pix ou no cartão. Se o cliente perguntar, diga que o estorno está sendo feito."
        ),
    )


# ── Nota fiscal e DANFE ──────────────────────────────────────────────────────


def fiscal_failure_reason(order: Order) -> str:
    """O que o emissor respondeu na recusa da NFC-e, ou ``""`` quando não há resposta.

    Mora na última Directive de emissão (``last_error``). Só a resposta do
    emissor vira frase de tela; erro interno do worker fica de fora.
    """
    from shopman.orderman.models import Directive

    from shopman.shop.directives import FISCAL_EMIT_NFCE

    row = (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)
        .order_by("-created_at", "-pk")
        .values_list("status", "last_error")
        .first()
    )
    if row is None or row[0] != "failed":
        return ""
    error = str(row[1] or "").strip()
    if not error.startswith(_FISCAL_ERROR_PREFIX):
        return ""
    return error[len(_FISCAL_ERROR_PREFIX):].strip().rstrip(".")


def _fiscal_pending(order: Order, fiscal_status: str, by_ref: dict):
    if fiscal_status != "failed":
        return None
    answer = fiscal_failure_reason(order)
    told = f"Resposta do emissor: {answer}. " if answer else ""
    action = by_ref.get("requeue-fiscal")
    return OrderPendingProjection(
        key="nfce",
        tone=TONE_ERROR,
        label="NFC-e não autorizada",
        reason=f"{told}Se reprocessar não resolver, chame o contador.",
        actions=_from_action(action, label="Reprocessar NFC-e"),
    )


def _fiscal_cancel_pending(order: Order, alerts: frozenset[str]):
    if ALERT_FISCAL_CANCEL_FAILED not in alerts:
        return None
    key = str((order.data or {}).get("nfce_access_key") or "").strip()
    with_key = f" Chave de acesso: {key}." if key else ""
    return OrderPendingProjection(
        key="nfce_cancel",
        tone=TONE_ERROR,
        label="NFC-e não foi cancelada",
        reason=(
            "A nota deste pedido continua valendo na SEFAZ. Quem resolve é o contador: "
            f"fora do prazo, o cancelamento é feito por outro documento.{with_key}"
        ),
    )


def _danfe_pending(order: Order, danfe):
    if danfe is None or danfe.state != "not_printed" or order.status in _CLOSED_STATUSES:
        return None
    return OrderPendingProjection(
        key="danfe",
        tone=TONE_WARNING,
        label="DANFE não impressa",
        reason=danfe.problem or "A DANFE deste pedido ainda não saiu em nenhuma impressora.",
        actions=(
            OrderPendingActionProjection(
                ref=ACTION_PRINT_DANFE,
                label="Reimprimir DANFE" if danfe.printed else "Imprimir DANFE",
            ),
        ),
    )


# ── Pagamento, bloqueio do avanço e produção ─────────────────────────────────


def _from_action(action, *, label: str = "") -> tuple[OrderPendingActionProjection, ...]:
    """A ação do detalhe como gesto da pendência, com a guarda e o motivo dela."""
    if action is None:
        return ()
    return (
        OrderPendingActionProjection(
            ref=action.ref, label=label or action.label, enabled=bool(action.enabled), reason=action.reason or "",
        ),
    )


def _cancel_action(by_ref: dict, cancel_capability: dict) -> tuple[OrderPendingActionProjection, ...]:
    if not cancel_capability.get("can_cancel"):
        return ()
    label = "Cancelar pedido (pede gerente)" if cancel_capability.get("cancel_requires_approval") else "Cancelar pedido"
    return _from_action(by_ref.get("cancel"), label=label)


def _contact_action(whatsapp_url: str) -> tuple[OrderPendingActionProjection, ...]:
    if not whatsapp_url:
        return ()
    return (OrderPendingActionProjection(ref=ACTION_CONTACT_CUSTOMER, label="Chamar no WhatsApp", href=whatsapp_url),)


def _production_lines(awaiting_work_orders) -> str:
    return " ".join(
        f"Produção de {wo.recipe_name}: {_PRODUCTION_STATE[wo.status]}."
        for wo in awaiting_work_orders
        if wo.status in _PRODUCTION_STATE
    )


def _clean(label: str) -> str:
    return str(label or "").rstrip("…").strip()


def _payment_pending(
    order: Order,
    *,
    block_label: str,
    block_reason: str,
    lapsed: bool,
    link_problem: str,
    unpaid_at_kitchen_hour: bool,
    by_ref: dict,
    cancel_capability: dict,
    whatsapp_url: str,
):
    """Falta o dinheiro: uma linha só, com o que a casa pode fazer agora."""
    resend = _from_action(by_ref.get("resend-payment-link"))
    if unpaid_at_kitchen_hour:
        return OrderPendingProjection(
            key="payment",
            tone=TONE_ERROR,
            label="Encomenda sem pagamento não foi para a Cozinha",
            reason=" ".join(
                part for part in (
                    "Chegou a hora do preparo e o pagamento não entrou.",
                    _sentence(block_reason),
                    "Cobre o cliente ou cancele a encomenda.",
                ) if part
            ),
            actions=(*resend, *_cancel_action(by_ref, cancel_capability), *_contact_action(whatsapp_url)),
        )
    if lapsed:
        return OrderPendingProjection(
            key="payment",
            tone=TONE_ERROR,
            label=_clean(block_label),
            reason=_sentence(block_reason),
            actions=(*_cancel_action(by_ref, cancel_capability), *_contact_action(whatsapp_url)),
        )
    if link_problem:
        return OrderPendingProjection(
            key="payment",
            tone=TONE_WARNING,
            label=_clean(block_label),
            reason=" ".join(part for part in (link_problem, _sentence(block_reason)) if part),
            actions=(*resend, *_contact_action(whatsapp_url)),
        )
    return OrderPendingProjection(
        key="payment", tone=TONE_INFO, label=_clean(block_label), reason=_sentence(block_reason), actions=resend,
    )


def _sentence(text: str) -> str:
    """As horas da cobrança ("gerado às 21h55 · expira às 22h25") como frase."""
    text = str(text or "").strip()
    if not text:
        return ""
    text = f"{text[:1].upper()}{text[1:]}"
    return text if text.endswith(".") else f"{text}."


def _block_pending(
    *, block: str, block_label: str, block_reason: str, schedule_label: str, awaiting_work_orders,
):
    """O avanço espera um fato que não é o dinheiro."""
    tone = TONE_WARNING if block in _BLOCKS_NEEDING_SOMEONE else TONE_INFO
    label = _clean(block_label) or _BLOCK_FALLBACK_LABELS.get(block, "Avanço bloqueado")
    reason = block_reason
    if block == _BLOCK_PREORDER_NOT_DUE and schedule_label:
        reason = f"Combinado: {schedule_label}. O preparo abre nesse dia."
    elif block == _BLOCK_WAITLIST:
        reason = " ".join(
            part for part in ("O preparo abre quando o lote ficar pronto.", _production_lines(awaiting_work_orders)) if part
        )
    return OrderPendingProjection(key="advance", tone=tone, label=label, reason=reason)


def build_pending(
    order: Order,
    *,
    actions,
    fiscal_status: str,
    block: str,
    block_label: str,
    block_reason: str,
    payment_lapsed: bool,
    link_problem: str,
    cancel_capability: dict,
    danfe,
    awaiting_work_orders,
    money: CancelledMoneyProjection | None,
    alerts: frozenset[str],
    schedule_label: str = "",
    whatsapp_url: str = "",
    refund_retry_plan=None,
) -> tuple[OrderPendingProjection, ...]:
    """As pendências do pedido, do que pede alguém agora ao que só espera.

    Recebe os fatos que :func:`order_queue.build_operator_order` já calculou
    (nada é lido duas vezes) e devolve a lista pronta: a tela desenha, não
    decide.
    """
    by_ref = {action.ref: action for action in actions}
    pending: list[OrderPendingProjection] = []

    # No pedido NOVO o único bloqueio com frase é o do pagamento que vence (Pix ou link).
    payment_block = bool(block_label or block_reason) and (
        block == _BLOCK_PAYMENT or order.status == Order.Status.NEW
    )
    unpaid_at_kitchen_hour = ALERT_PREORDER_UNPAID in alerts and payment_block
    if payment_block:
        pending.append(_payment_pending(
            order,
            block_label=block_label,
            block_reason=block_reason,
            lapsed=payment_lapsed,
            link_problem=link_problem,
            unpaid_at_kitchen_hour=unpaid_at_kitchen_hour,
            by_ref=by_ref,
            cancel_capability=cancel_capability,
            whatsapp_url=whatsapp_url,
        ))
    elif block_label or block_reason:
        pending.append(_block_pending(
            block=block, block_label=block_label, block_reason=block_reason,
            schedule_label=schedule_label, awaiting_work_orders=awaiting_work_orders,
        ))

    # O lote que o pedido espera, quando o avanço não está barrado por ele (P2-20).
    if block != _BLOCK_WAITLIST:
        production = _production_lines(awaiting_work_orders)
        if production:
            pending.append(OrderPendingProjection(key="production", tone=TONE_INFO, label="Esperando o lote", reason=production))

    for item in (
        _fiscal_pending(order, fiscal_status, by_ref),
        _fiscal_cancel_pending(order, alerts),
        _danfe_pending(order, danfe),
        _money_pending(order, money, alerts, refund_retry_plan=refund_retry_plan, by_ref=by_ref),
    ):
        if item is not None:
            pending.append(item)

    if ALERT_PHASE_STUCK in alerts:
        pending.append(OrderPendingProjection(
            key="phase",
            tone=TONE_ERROR,
            label="Etapa automática travada",
            reason=(
                "O que o sistema faz sozinho nesta etapa (estoque, nota, aviso ao cliente) pode não ter "
                "acontecido. O suporte já recebeu o aviso. Até ele conferir, não refaça a etapa à mão."
            ),
        ))

    return tuple(sorted(pending, key=lambda item: _TONE_ORDER[item.tone]))
