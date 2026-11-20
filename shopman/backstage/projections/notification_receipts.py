"""Comprovante de entrega dos avisos ao cliente, para o detalhe do pedido.

Lê a evidência que o ``NotificationSendHandler`` grava em
``Directive.payload["notification_delivery"]`` (ver
``docs/reference/comprovante-de-entrega.md``). Uma linha por aviso: o que
saiu, por qual canal, quando, com qual identificador do provedor, e o estado
final.

A regra da tela é uma só: **"Entregue" só com comprovante**. Aceite sem
identificador do provedor é "Aceito pelo provedor, sem comprovante", e
registro sem a marca de comprovante cai nesse estado, nunca no de entregue.
Não expõe destinatário: só o canal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Directive
from shopman.utils.formatting import format_local

from shopman.shop.services import notification as notification_svc

logger = logging.getLogger(__name__)

#: Quantos avisos o detalhe mostra (os mais recentes). Pedido comum tem 3 a 6.
MAX_RECEIPTS = 30

_CHANNEL_LABELS = {
    "manychat": "WhatsApp",
    "whatsapp": "WhatsApp",
    "email": "E-mail",
    "sms": "SMS",
    "console": "Console",
}

STATE_DELIVERED = "delivered"
STATE_ACCEPTED_NO_RECEIPT = "accepted_no_receipt"
STATE_UNKNOWN = "unknown"
STATE_FAILED = "failed"
STATE_SKIPPED = "skipped"
STATE_QUEUED = "queued"
STATE_SENDING = "sending"

#: (rótulo, tom) de cada estado final. O tom é do kit: ok, warning, danger, muted.
_STATES = {
    STATE_DELIVERED: ("Entregue com comprovante", "ok"),
    STATE_ACCEPTED_NO_RECEIPT: ("Aceito pelo provedor, sem comprovante", "warning"),
    STATE_UNKNOWN: ("Aceite não confirmado", "danger"),
    STATE_FAILED: ("Falhou em todos os canais", "danger"),
    STATE_SKIPPED: ("Não enviado", "muted"),
    STATE_QUEUED: ("Na fila", "muted"),
    STATE_SENDING: ("Enviando", "muted"),
}

_ATTEMPT_OUTCOMES = {
    notification_svc.PROOF_RECEIPT: "aceito, com comprovante",
    notification_svc.PROOF_NO_RECEIPT: "aceito, sem comprovante",
    "unknown": "sem resposta clara do provedor",
    "failed": "recusado",
}

_SKIP_REASONS = {
    "customer_opt_out": "O cliente não autorizou avisos.",
    "expected_no_contact": "Não há contato do cliente.",
    "payment_not_pending": "O pagamento não está mais pendente.",
    "preorder_not_awaiting": "A encomenda não espera mais a data.",
    "rescheduled": "A data mudou antes do envio.",
    "payment_link_already_paid": "O cliente já pagou.",
    "payment_link_order_cancelled": "O pedido foi cancelado.",
    "payment_link_expired": "O link venceu.",
    "payment_link_unavailable": "O link não está disponível.",
    "payment_taken_over_at_counter": "O pagamento passou para o balcão.",
}

#: Motivo com sufixo variável: o processo que não fala com ninguém de fora
#: (``external_suppressed:<motivo>``, o seed e o ambiente de teste). Sem este
#: prefixo o operador lia "O aviso foi omitido." sem saber por quê.
_SKIP_REASON_PREFIXES = (
    ("external_suppressed:", "Avisos ao cliente desligados neste ambiente."),
)

#: O que dizer quando o motivo gravado não tem tradução: o fato, e o gesto.
_SKIP_FALLBACK = "O aviso não saiu. Fale com o cliente por outro meio, se precisar."


def _skip_reason(reason: str) -> str:
    if reason in _SKIP_REASONS:
        return _SKIP_REASONS[reason]
    for prefix, text in _SKIP_REASON_PREFIXES:
        if reason.startswith(prefix):
            return text
    return _SKIP_FALLBACK


@dataclass(frozen=True)
class NotificationAttemptProjection:
    """Um salto da cadeia (WhatsApp, e-mail, SMS) de um aviso."""

    channel_label: str
    outcome: str  # receipt | no_receipt | unknown | failed
    outcome_label: str
    time_display: str
    provider_id: str = ""


@dataclass(frozen=True)
class NotificationReceiptProjection:
    """O comprovante de um aviso ao cliente: o que saiu, por onde, quando e com que prova."""

    template: str
    label: str
    # Aviso crítico: a cadeia segue até ter comprovante, e o operador é alertado
    # quando termina sem ele (``CRITICAL_NOTIFICATION_TEMPLATES``).
    critical: bool
    state: str
    state_label: str
    tone: str
    channel_label: str
    time_display: str
    # Identificador que o provedor devolveu (Message-ID do e-mail, id da Meta).
    # Vazio quando não há comprovante.
    provider_id: str
    detail: str
    attempts: tuple[NotificationAttemptProjection, ...] = ()
    # O botão que resolve o aviso que não saiu por canal nenhum (WP-G07): o WhatsApp
    # de quem está no balcão, com o MESMO texto. Vazio nos outros estados.
    fallback_whatsapp_url: str = ""


def _time_display(raw, fallback=None) -> str:
    moment = parse_datetime(str(raw or "")) if raw else None
    if moment is None:
        moment = fallback
    if moment is None:
        return ""
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return format_local(moment, "%d/%m às {clock}")


def _template_label(template: str) -> str:
    from shopman.shop.notification_copy import template_label

    return template_label(template)


def _state(directive: Directive, evidence: dict) -> str:
    status = str(evidence.get("status") or "")
    if status == "accepted":
        # Fail-closed: sem a marca explícita de comprovante, nunca "Entregue".
        if evidence.get("proof") == notification_svc.PROOF_RECEIPT and evidence.get("message_id"):
            return STATE_DELIVERED
        return STATE_ACCEPTED_NO_RECEIPT
    if status == "unknown":
        return STATE_UNKNOWN
    if status == "started":
        return STATE_SENDING if directive.status == Directive.Status.RUNNING else STATE_UNKNOWN
    if status == "skipped":
        return STATE_SKIPPED
    if status == "failed" or directive.status == Directive.Status.FAILED:
        return STATE_FAILED
    if directive.status == Directive.Status.RUNNING:
        return STATE_SENDING
    if directive.status == Directive.Status.QUEUED:
        return STATE_QUEUED
    # Processado sem evidência gravada: não sabemos, e a tela diz que não sabe.
    return STATE_UNKNOWN


def _detail(state: str, evidence: dict) -> str:
    if state == STATE_DELIVERED:
        return "O provedor registrou a mensagem e devolveu o identificador. Isso não confirma leitura."
    if state == STATE_ACCEPTED_NO_RECEIPT:
        if evidence.get("critical"):
            return "Nenhum canal devolveu comprovante. Confirme com o cliente que ele recebeu."
        return "O provedor aceitou o envio, mas não devolveu identificador da mensagem."
    if state == STATE_UNKNOWN:
        return "Não dá para saber se o aviso saiu. Confirme com o cliente antes de reenviar."
    if state == STATE_FAILED:
        return "Nenhum canal aceitou o envio. Fale com o cliente por outro meio."
    if state == STATE_SKIPPED:
        return _skip_reason(str(evidence.get("reason") or ""))
    return ""


def _attempts(evidence: dict) -> tuple[NotificationAttemptProjection, ...]:
    raw = evidence.get("attempts")
    if not isinstance(raw, list):
        return ()
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        outcome = str(item.get("outcome") or "")
        result.append(
            NotificationAttemptProjection(
                channel_label=_CHANNEL_LABELS.get(str(item.get("backend") or ""), "Canal desconhecido"),
                outcome=outcome,
                outcome_label=_ATTEMPT_OUTCOMES.get(outcome, "sem registro"),
                time_display=_time_display(item.get("recorded_at")),
                provider_id=str(item.get("message_id") or ""),
            )
        )
    return tuple(result)


def build_receipt(directive: Directive) -> NotificationReceiptProjection:
    payload = directive.payload or {}
    evidence = payload.get("notification_delivery") or {}
    if not isinstance(evidence, dict):
        evidence = {}
    template = str(payload.get("template") or "")
    state = _state(directive, evidence)
    state_label, tone = _STATES[state]
    provider_id = str(evidence.get("message_id") or "") if state == STATE_DELIVERED else ""
    return NotificationReceiptProjection(
        template=template,
        label=_template_label(template),
        critical=bool(evidence.get("critical")) or notification_svc.is_critical_notification(template),
        state=state,
        state_label=state_label,
        tone=tone,
        channel_label=_CHANNEL_LABELS.get(str(evidence.get("backend") or ""), ""),
        time_display=_time_display(evidence.get("recorded_at"), fallback=directive.created_at),
        provider_id=provider_id,
        detail=_detail(state, evidence),
        attempts=_attempts(evidence),
    )


#: O motivo de omissão que diz "este aviso não cabe a este pedido": não é falha
#: nem envio que deixou de sair, é aviso que não existe. A lista não o mostra
#: (beta 06/11: "Não enviado · Este aviso não se aplica" se contradizia).
_NOT_APPLICABLE_REASON = "notification_not_required"


def _applies(directive: Directive) -> bool:
    evidence = (directive.payload or {}).get("notification_delivery") or {}
    if not isinstance(evidence, dict):
        return True
    return not (evidence.get("status") == "skipped" and evidence.get("reason") == _NOT_APPLICABLE_REASON)


def build_notification_receipts(order) -> tuple[NotificationReceiptProjection, ...]:
    """Os avisos deste pedido ao cliente, do mais antigo ao mais recente.

    O aviso que não se aplica ao pedido (``notification_not_required``) fica de
    fora: ele não falhou nem deixou de sair, ele não existe para este pedido.
    """
    # No iFood quem avisa o cliente é o app do iFood, e o contato que chega é
    # mascarado: nenhum aviso nosso pode sair. Listar cada um como "Não enviado"
    # fazia o pedido parecer com defeito (pedido 3417, 12/11).
    if getattr(order, "channel_ref", "") == "ifood":
        return ()
    directives = list(
        Directive.objects.filter(topic=notification_svc.TOPIC, payload__order_ref=order.ref)
        .order_by("-created_at", "-pk")[:MAX_RECEIPTS]
    )
    directives.reverse()
    receipts = []
    for directive in directives:
        if not _applies(directive):
            continue
        receipt = build_receipt(directive)
        if receipt.state == STATE_FAILED:
            receipt = replace(receipt, fallback_whatsapp_url=_fallback_whatsapp_url(order, directive))
        receipts.append(receipt)
    return tuple(receipts)


def _fallback_whatsapp_url(order, directive) -> str:
    """O ``wa.me`` do cliente com o texto do aviso que não saiu; vazio sem WhatsApp.

    Todo aviso que falhou em todos os canais traz o botão que resolve: o WhatsApp de
    quem está no balcão, com o MESMO texto que o cliente leria. Só no que falhou: o
    "Não enviado" pode ser o cliente que não aceita mensagem, e aí não se oferece.
    O texto é montado sem cunhar link pessoal (ler a tela não grava nada): os links
    saem na forma comum, que pede a entrada do cliente.
    """
    import copy
    from urllib.parse import quote

    from shopman.backstage.projections import order_queue
    from shopman.shop.adapters import notification_manychat
    from shopman.shop.adapters._notification_templates import render_message

    data = copy.deepcopy(order.data or {})
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    wa_url = order_queue._customer_contact(order, customer).get("customer_whatsapp_url", "")
    if not wa_url:
        return ""
    customer.pop("uuid", None)
    plain = copy.copy(order)
    plain.data = data
    payload = dict(directive.payload or {})
    template = str(payload.get("template") or "")
    try:
        context = notification_svc._build_context(plain, payload, template)
        event = notification_svc._qualify_template(template, context)
        message = render_message(event, context, notification_manychat.MESSAGE_TEMPLATES)
    except Exception:  # noqa: BLE001 — a tela do pedido não cai por causa do plano B
        logger.warning("notification_receipts.fallback_text_failed template=%s", template, exc_info=True)
        return ""
    return f"{wa_url}?text={quote(message.replace('*', '').strip())}"


__all__ = [
    "NotificationAttemptProjection",
    "NotificationReceiptProjection",
    "build_notification_receipts",
    "build_receipt",
]
