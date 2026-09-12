"""Troco do PDV na fila canônica de alertas do gestor, com resolução pela causa."""

from django.db import transaction
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services.alerts import create_alert


def notify_change_request(*, shift, operator, amount_q, denominations, note):
    message = (
        f"Troco solicitado no PDV {shift.terminal.label or shift.terminal.ref}: "
        f"R$ {format_money(amount_q)}. Operador: {operator.get_username()}. "
        "Leve o troco até o balcão e confirme o atendimento no PDV."
    )
    if denominations:
        message += " Denominações: " + ", ".join(f"R$ {format_money(q)}" for q in denominations) + "."
    if note:
        message += f" Observação: {note}"
    return create_alert(type="cash_change_requested", audience="operations", message=message)


def resolve_change_request(*, request, actor):
    # O vínculo nasce junto com o evento imutável; pedidos legados não o têm.
    alert_id = (request.payload or {}).get("alert_id")
    if not alert_id:
        return
    with transaction.atomic():
        alert = OperatorAlert.objects.select_for_update().filter(
            pk=alert_id, type="cash_change_requested", resolved_at__isnull=True,
        ).first()
        if alert is None:
            return
        alert.resolved_at = timezone.now()
        alert.resolved_by = actor[:100]
        alert.acknowledged = True
        alert.rev += 1
        alert.save(update_fields=["resolved_at", "resolved_by", "acknowledged", "rev"])
