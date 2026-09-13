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
        return ("iFood: pagamento não informado.",) + benefits_summary(order)
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
    return (tuple(lines) or ("iFood: pagamento não informado.",)) + benefits_summary(order)


def benefits_summary(order) -> tuple[str, ...]:
    if order.channel_ref != "ifood":
        return ()
    facts = (order.data or {}).get("ifood") or {}
    benefits = facts.get("benefits") or []
    lines = []
    targets = {"CART": "carrinho", "DELIVERY_FEE": "entrega", "ITEM": "item", "PROGRESSIVE_DISCOUNT_ITEM": "item (progressivo)"}
    sponsors = {"IFOOD": "iFood", "MERCHANT": "Loja", "EXTERNAL": "Parceiro externo", "CHAIN": "Rede"}
    for benefit in benefits:
        if not isinstance(benefit, dict):
            continue
        target = str(benefit.get("target") or "destino não informado")
        label = targets.get(target, target)
        if benefit.get("target_id") is not None:
            label += f" #{benefit['target_id']}"
        amount = benefit.get("value_q")
        value = f"R$ {format_money(_amount(amount))}" if amount is not None else "valor não informado"
        shares = []
        for share in benefit.get("sponsorships") or []:
            if not isinstance(share, dict):
                continue
            sponsor = str(share.get("sponsor") or "Responsável não informado")
            sponsor_label = sponsors.get(sponsor, sponsor)
            amount = share.get("value_q")
            contribution = f"R$ {format_money(_amount(amount))}" if amount is not None else "valor não informado"
            shares.append(f"{sponsor_label}: {contribution}")
        lines.append(f"Desconto ({label}): {value}; " + ("; ".join(shares) or "responsável não informado pelo iFood"))
    if not benefits:
        total = _amount((facts.get("totals") or {}).get("benefits_q"))
        if total:
            lines.append(f"Desconto: R$ {format_money(total)}; responsável não informado pelo iFood")
    return tuple(lines)


def operation_summary(order) -> tuple[str, ...]:
    if order.channel_ref != "ifood":
        return ()
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from shopman.shop.services import ifood_schedule
    from shopman.shop.services.order_helpers import get_fulfillment_type

    facts = (order.data or {}).get("ifood") or {}
    lines = []
    pickup_code = str(facts.get("pickup_code") or "").strip()
    if pickup_code:
        lines.append(f"Código de retirada: {pickup_code}")
    if get_fulfillment_type(order) == "delivery":
        provider = str(facts.get("delivered_by") or "").upper()
        lines.append({"IFOOD": "Entrega por entregador iFood", "MERCHANT": "Entrega própria da loja"}.get(provider, "Responsável pela entrega não informado pelo iFood"))
    if str(facts.get("order_timing") or "").upper() == "SCHEDULED":
        lines.append("Pedido agendado no iFood")
        raw_schedule = facts.get("schedule")
        schedule = raw_schedule if isinstance(raw_schedule, dict) else {}
        for key, label in (("preparation_start_at", "Início do preparo"), ("delivery_start_at", "Início da janela"), ("delivery_end_at", "Fim da janela")):
            value = schedule.get(key)
            try:
                dt = parse_datetime(str(value)) if value else None
            except (ValueError, TypeError):
                dt = None
            if dt is not None and timezone.is_aware(dt):
                lines.append(f"{label}: {timezone.localtime(dt).strftime('%d/%m/%Y às %H:%M')}")
        reason = ifood_schedule.block_reason(order)
        if reason:
            lines.append(reason)
    return tuple(lines)
