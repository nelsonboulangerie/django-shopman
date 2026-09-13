"""Operator-facing iFood facts, without creating local payment or cancellation effects."""

from shopman.utils.monetary import format_money


def _amount(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def cancellation_notice(order) -> str:
    if order.channel_ref != "ifood" or order.status in {"cancelled", "completed", "returned"}:
        return ""
    request = (order.data or {}).get("ifood_cancellation_request") or {}
    state = request.get("state")
    if state == "queued":
        return "Solicitação de cancelamento na fila. O pedido ainda não foi cancelado."
    if state == "sent":
        return "Cancelamento solicitado. Aguardando confirmação do iFood."
    if state == "error":
        if request.get("retryable"):
            return "Falha temporária no envio ao iFood. A confirmação continua pendente."
        return "O cancelamento não foi aceito pelo iFood. O pedido continua ativo; confira o motivo e tente novamente."
    return ""


def payment_summary(order) -> tuple[str, ...]:
    if order.channel_ref != "ifood":
        return ()
    payments = ((order.data or {}).get("ifood") or {}).get("payments") or {}
    if not payments:
        return ("iFood: pagamento não informado.",)
    prepaid = _amount(payments.get("prepaid_q"))
    pending = _amount(payments.get("pending_q"))
    lines = []
    if prepaid:
        lines.append(f"Pago online no iFood: R$ {format_money(prepaid)}")
    if pending:
        lines.append(f"Pagamento pendente no iFood: R$ {format_money(pending)}")
    labels = {"CASH": "Dinheiro", "CREDIT": "Crédito", "DEBIT": "Débito", "PIX": "Pix", "MEAL_VOUCHER": "Vale-refeição", "FOOD_VOUCHER": "Vale-alimentação"}
    for method in payments.get("methods") or []:
        if not isinstance(method, dict):
            continue
        name = labels.get(str(method.get("method") or "").upper(), str(method.get("method") or "Pagamento"))
        brand = str(method.get("brand") or "").strip()
        value = _amount(method.get("value_q"))
        suffix = "online" if method.get("prepaid") is True else "pendente" if method.get("prepaid") is False else "conforme iFood"
        line = f"{name}{' ' + brand if brand else ''}: R$ {format_money(value)} ({suffix})"
        change_for = _amount(method.get("change_for_q"))
        if str(method.get("method") or "").upper() == "CASH" and method.get("prepaid") is False and change_for:
            line += f"; troco para R$ {format_money(change_for)}"
            if change_for >= value:
                line += f", troco R$ {format_money(change_for - value)}"
        lines.append(line)
    return tuple(lines) or ("iFood: pagamento não informado.",)
