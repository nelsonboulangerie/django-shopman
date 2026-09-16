"""Evidência de entrega da cobrança para superfícies do POS.

Não expõe destinatário. O canal é o backend que aceitou o envio; fila não é
entrega e leitura pelo cliente nunca é inferida.
"""
from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from shopman.shop.services import notification

_CHANNELS = {"manychat": ("whatsapp", "WhatsApp"), "email": ("email", "e-mail"), "sms": ("sms", "SMS")}
_REASONS = {
    "customer_opt_out": "O cliente não autorizou notificações.",
    "expected_no_contact": "Não há contato disponível.",
    "notification_not_required": "A notificação não se aplica.",
    "payment_not_pending": "O pagamento não está mais pendente.",
}


def _when(raw: object) -> str:
    parsed = parse_datetime(str(raw or ""))
    if parsed is None:
        return ""
    local = timezone.localtime(parsed) if timezone.is_aware(parsed) else parsed
    return local.strftime("%Hh%M")


def build_pos_payment_delivery(order) -> dict:
    template = notification.payment_notice_template(order)
    if not template:
        return _empty()
    directive = notification.latest_delivery(order, template)
    refusal = notification.payment_notice_refusal(order)
    if directive is None:
        return {
            **_empty(), "template": template, "status": "not_sent",
            "notice": refusal.message if refusal else "Cobrança pronta para enviar ao cliente.",
            "reason_code": refusal.code if refusal else "", "can_send": refusal is None,
            "action": "send" if refusal is None else "", "action_label": "Enviar ao cliente" if refusal is None else "",
        }

    evidence = (directive.payload or {}).get("notification_delivery") or {}
    state = str(evidence.get("status") or "")
    backend = str(evidence.get("backend") or "")
    channel, channel_label = _CHANNELS.get(backend, ("", ""))
    reason_code = str(evidence.get("reason") or "")
    if state == "accepted":
        when = _when(evidence.get("recorded_at"))
        notice = f"Envio aceito pelo {channel_label or 'serviço'}{(' às ' + when) if when else ''}. Leitura não confirmada."
        status = "accepted"
    elif state in {"started", "unknown"}:
        status = "unknown" if state == "unknown" else "sending"
        notice = "Aceite do envio ainda não confirmado. Não reenvie agora."
    elif state == "skipped":
        status = "skipped"
        notice = _REASONS.get(reason_code, "A cobrança não foi enviada.")
    elif state == "failed" or directive.status == "failed":
        status = "failed"
        notice = "O envio falhou em todos os canais disponíveis."
    elif directive.status == "queued":
        status, notice = "queued", "Envio na fila. O canal usado aparecerá aqui após o aceite."
    elif directive.status == "running":
        status, notice = "sending", "Envio em processamento; aceite ainda não confirmado."
    else:
        status, notice = "unknown", "Processamento concluído sem confirmação de envio."

    can_resend = status in {"accepted", "failed"} and refusal is None
    return {
        "template": template, "status": status, "channel": channel, "channel_label": channel_label,
        "notice": notice, "reason_code": reason_code, "can_send": False, "can_resend": can_resend,
        "action": "resend" if can_resend else "", "action_label": "Reenviar" if can_resend else "",
    }


def _empty() -> dict:
    return {"template": "", "status": "not_sent", "channel": "", "channel_label": "", "notice": "",
            "reason_code": "", "can_send": False, "can_resend": False, "action": "", "action_label": ""}


__all__ = ["build_pos_payment_delivery"]
