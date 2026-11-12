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
    if state == "refused":
        reason = str(request.get("refusal_reason") or "").strip().rstrip(".")
        because = f" Motivo do iFood: {reason}." if reason else ""
        return (
            f"O iFood recusou o cancelamento.{because} "
            "O pedido continua ativo: siga com ele ou tente cancelar de novo com outro motivo."
        )
    if state == "error":
        if request.get("retryable"):
            return "Falha temporária no envio ao iFood. A confirmação continua pendente."
        return "O cancelamento não foi aceito pelo iFood. O pedido continua ativo; confira o motivo e tente novamente."
    return ""


_METHOD_LABELS = {
    "CASH": "Dinheiro", "CREDIT": "Crédito", "DEBIT": "Débito", "PIX": "Pix",
    "MEAL_VOUCHER": "Vale-refeição", "FOOD_VOUCHER": "Vale-alimentação",
}


def payment_summary(order) -> tuple[str, ...]:
    """O pagamento do iFood respondendo à única pergunta do balcão: cobrar ou não?

    Pago online é UMA linha: bandeira, banco e quem bancou o frete grátis não
    mudam nada no despacho e repetiam o total três vezes (pedido 3417, 12/11:
    "Pago online", "OTHER NUBANK" e o desconto da entrega, todos de R$ 49,20).
    O desdobramento continua inteiro em ``Order.data["ifood"]`` para a conciliação.
    Só o que se cobra na porta ganha detalhe: forma, bandeira e troco.
    """
    if order.channel_ref != "ifood":
        return ()
    payments = ((order.data or {}).get("ifood") or {}).get("payments") or {}
    if not payments:
        return ("iFood: pagamento não informado.",) + benefits_summary(order)
    prepaid = _amount(payments.get("prepaid_q"))
    pending = _amount(payments.get("pending_q"))
    lines = []
    if pending:
        if prepaid:
            lines.append(f"Já pago online no iFood: R$ {format_money(prepaid)}")
        lines.append(f"Cobrar na entrega: R$ {format_money(pending)}")
        for method in payments.get("methods") or []:
            if not isinstance(method, dict) or method.get("prepaid") is True:
                continue
            code = str(method.get("method") or "").upper()
            name = _METHOD_LABELS.get(code, "Outra forma")
            brand = str(method.get("brand") or "").strip()
            value = _amount(method.get("value_q"))
            line = f"{name}{' ' + brand if brand else ''}: R$ {format_money(value)}"
            change_for = _amount(method.get("change_for_q"))
            if code == "CASH" and change_for:
                line += f"; troco para R$ {format_money(change_for)}"
                if change_for >= value:
                    line += f", levar R$ {format_money(change_for - value)} de troco"
            lines.append(line)
    elif prepaid:
        lines.append("Pago online no iFood. Nada a cobrar do cliente.")
    return (tuple(lines) or ("iFood: pagamento não informado.",)) + benefits_summary(order)


def benefits_summary(order) -> tuple[str, ...]:
    """Só o desconto que sai do caixa da LOJA (ou cujo responsável não veio).

    Desconto bancado pelo iFood não muda o que a casa recebe nem o que se cobra,
    e listá-lo fazia o pedido parecer ter um problema de valor.
    """
    if order.channel_ref != "ifood":
        return ()
    facts = (order.data or {}).get("ifood") or {}
    benefits = facts.get("benefits") or []
    lines = []
    targets = {"CART": "no carrinho", "DELIVERY_FEE": "na entrega", "ITEM": "no item", "PROGRESSIVE_DISCOUNT_ITEM": "no item"}
    for benefit in benefits:
        if not isinstance(benefit, dict):
            continue
        where = targets.get(str(benefit.get("target") or ""), "")
        suffix = f" ({where})" if where else ""
        shares = [s for s in benefit.get("sponsorships") or [] if isinstance(s, dict)]
        if not shares:
            amount = benefit.get("value_q")
            value = f"R$ {format_money(_amount(amount))}" if amount is not None else "valor não informado"
            lines.append(f"Desconto{suffix}: {value}; responsável não informado pelo iFood")
            continue
        for share in shares:
            if str(share.get("sponsor") or "").upper() != "MERCHANT":
                continue
            amount = share.get("value_q")
            if amount is None:
                lines.append(f"Desconto pago pela loja{suffix}: valor não informado")
            elif _amount(amount):
                lines.append(f"Desconto pago pela loja{suffix}: R$ {format_money(_amount(amount))}")
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
    takeout = _takeout_local(order)
    if takeout is not None:
        lines.append(f"Retirada prevista: {takeout.strftime('%d/%m/%Y às %H:%M')}")
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


# ── O que cabe no CARD ─────────────────────────────────────────────────────────
# As funções acima montam a evidência COMPLETA, e é isso que o detalhe precisa.
# No card elas viravam doze linhas para um pedido de dois itens: o desdobramento
# por bandeira, o CEP, o responsável pela entrega e três linhas de janela. Nada
# disso ajuda a escolher qual pedido pegar — e o card do iFood ficava com o dobro
# da altura do card do PDV, quebrando a leitura em varredura da fila.


def pickup_code(order) -> str:
    """O código que o cliente diz no balcão. Vai ao card com rótulo próprio.

    Sem rótulo ele competia com o número do pedido — dois números de quatro
    dígitos, e o exibido era justamente o que o iFood não usa para nomear nada.
    """
    if order.channel_ref != "ifood":
        return ""
    return str(((order.data or {}).get("ifood") or {}).get("pickup_code") or "").strip()


def _takeout_local(order):
    """Quando o cliente vem buscar o pedido IMEDIATO de retirada (``takeout_at``).

    No agendado quem diz a hora é a janela do agendamento; repetir aqui seria
    dizer duas vezes. Valor sem fuso ou malformado não vira hora na tela.
    """
    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    from shopman.shop.services.order_helpers import get_fulfillment_type

    if order.channel_ref != "ifood" or get_fulfillment_type(order) == "delivery":
        return None
    facts = (order.data or {}).get("ifood") or {}
    if str(facts.get("order_timing") or "").upper() == "SCHEDULED":
        return None
    try:
        dt = parse_datetime(str(facts.get("takeout_at") or ""))
    except (ValueError, TypeError):
        return None
    return timezone.localtime(dt) if dt is not None and timezone.is_aware(dt) else None


def schedule_label(order) -> str:
    """O agendamento em UMA linha: "Agendado · Hoje 21:09–22:09".

    No pedido imediato de retirada, a hora em que o cliente vem: "Retirada às
    19:40". Vazio no imediato sem essa hora. A data só aparece quando não é
    hoje — em pedido para hoje ela é ruído, e quem lê a fila já sabe que dia é.
    """
    if order.channel_ref != "ifood":
        return ""
    facts = (order.data or {}).get("ifood") or {}
    if str(facts.get("order_timing") or "").upper() != "SCHEDULED":
        takeout = _takeout_local(order)
        if takeout is None:
            return ""
        from django.utils import timezone

        day = "" if takeout.date() == timezone.localdate() else f" {takeout:%d/%m}"
        return f"Retirada{day} às {takeout:%H:%M}"

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    schedule = facts.get("schedule") if isinstance(facts.get("schedule"), dict) else {}

    def _local(key):
        try:
            dt = parse_datetime(str(schedule.get(key) or ""))
        except (ValueError, TypeError):
            return None
        return timezone.localtime(dt) if dt is not None and timezone.is_aware(dt) else None

    start, end = _local("delivery_start_at"), _local("delivery_end_at")
    if start is None:
        return "Agendado"
    today = timezone.localdate()
    day = "Hoje" if start.date() == today else start.strftime("%d/%m")
    window = f"{start:%H:%M}–{end:%H:%M}" if end is not None else f"a partir de {start:%H:%M}"
    return f"Agendado · {day} {window}"


def remote_ahead_label(order) -> str:
    """O iFood já passou deste ponto — dito como instrução, não como segundo status.

    O card mostra o status LOCAL ("Em preparo"). Quando o iFood está à frente, uma
    linha só diz o que ele já sabe e o que falta fazer aqui. Sem ela, o pedido
    1416 seguia "Em preparo" um minuto depois de encerrado no iFood (21/09/2026) e
    parecia pedir trabalho que ninguém precisava mais.
    """
    if order.channel_ref != "ifood" or order.status in {"completed", "cancelled", "returned"}:
        return ""
    facts = (order.data or {}).get("ifood") or {}
    if facts.get("remote_concluded"):
        return "Concluído no iFood · Finalize aqui"
    if facts.get("remote_dispatched") and order.status in {"new", "accepted", "preparing"}:
        return "Retirado pelo entregador do iFood · Marque Pronto"
    return ""
