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

from dataclasses import dataclass

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Directive

from shopman.shop.services import notification as notification_svc

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
    "notification_not_required": "Este aviso não se aplica.",
    "payment_not_pending": "O pagamento não está mais pendente.",
    "preorder_not_awaiting": "A encomenda não espera mais a data.",
    "rescheduled": "A data mudou antes do envio.",
    "payment_link_already_paid": "O cliente já pagou.",
    "payment_link_order_cancelled": "O pedido foi cancelado.",
    "payment_link_expired": "O link venceu.",
    "payment_link_unavailable": "O link não está disponível.",
}


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


def _time_display(raw, fallback=None) -> str:
    moment = parse_datetime(str(raw or "")) if raw else None
    if moment is None:
        moment = fallback
    if moment is None:
        return ""
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return timezone.localtime(moment).strftime("%d/%m às %H:%M")


def _template_label(template: str) -> str:
    from shopman.shop.services.marketing_platform_configuration import WHATSAPP_EVENT_LABELS

    return WHATSAPP_EVENT_LABELS.get(template) or template.replace("_", " ").capitalize()


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
        return "Nenhum canal aceitou o envio."
    if state == STATE_SKIPPED:
        return _SKIP_REASONS.get(str(evidence.get("reason") or ""), "O aviso foi omitido.")
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


def build_notification_receipts(order) -> tuple[NotificationReceiptProjection, ...]:
    """Os avisos deste pedido ao cliente, do mais antigo ao mais recente."""
    directives = list(
        Directive.objects.filter(topic=notification_svc.TOPIC, payload__order_ref=order.ref)
        .order_by("-created_at", "-pk")[:MAX_RECEIPTS]
    )
    directives.reverse()
    return tuple(build_receipt(directive) for directive in directives)


__all__ = [
    "NotificationAttemptProjection",
    "NotificationReceiptProjection",
    "build_notification_receipts",
    "build_receipt",
]
