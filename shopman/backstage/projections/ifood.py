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
        return ("iFood: pagamento não informado.",)
    prepaid = _amount(payments.get("prepaid_q"))
    pending = _amount(payments.get("pending_q"))
    lines = []
    if pending:
        if prepaid:
            lines.append(f"Já pago online no iFood: R$ {format_money(prepaid)}")
        due = []
        for method in payments.get("methods") or []:
            if not isinstance(method, dict) or method.get("prepaid") is True:
                continue
            code = str(method.get("method") or "").upper()
            name = _METHOD_LABELS.get(code, "Outra forma")
            brand = str(method.get("brand") or "").strip()
            value = _amount(method.get("value_q"))
            how = f"{name}{' ' + brand if brand else ''}"
            change = ""
            change_for = _amount(method.get("change_for_q"))
            if code == "CASH" and change_for:
                change = f"; troco para R$ {format_money(change_for)}"
                if change_for >= value:
                    change += f" (levar R$ {format_money(change_for - value)})"
            due.append((how, value, change))
        if len(due) == 1:
            # Uma forma só: valor, forma e troco numa linha, sem repetir o total.
            how, _value, change = due[0]
            how = how[:1].lower() + how[1:]
            lines.append(f"Cobrar na entrega: R$ {format_money(pending)} em {how}{change}")
        else:
            lines.append(f"Cobrar na entrega: R$ {format_money(pending)}")
            lines.extend(f"{how}: R$ {format_money(value)}{change}" for how, value, change in due)
    elif prepaid:
        # A linha de cima já diz "iFood · Pago online"; aqui, só o gesto.
        lines.append("Nada a cobrar do cliente.")
    return (tuple(lines) or ("iFood: pagamento não informado.",))


_FEE_LABELS = {
    "SMALL_ORDER_FEE": "Taxa de pedido mínimo do iFood",
    "SERVICE_FEE": "Taxa de serviço do iFood",
}


def total_lines(order):
    """O que leva dos itens ao total do pedido iFood, linha por linha.

    No pedido 3417 (12/11/2026) os itens davam R$ 48,00 e o total R$ 49,20, sem
    nada na tela que explicasse a diferença: era uma taxa do iFood paga pelo
    cliente (``additionalFees``). A entrega grátis bancada pelo iFood fica de
    fora: sai do total e entra de novo, e não muda nada para quem despacha.
    Só entram linhas que mudam a conta; a soma fecha com ``orderAmount``.
    """
    from shopman.backstage.projections.order_pricing import OrderDiscountLineProjection

    if order.channel_ref != "ifood":
        return ()
    facts = (order.data or {}).get("ifood") or {}
    totals = facts.get("totals") or {}
    benefits = [b for b in facts.get("benefits") or [] if isinstance(b, dict)]
    lines = []

    delivery_benefits = sum(_amount(b.get("value_q")) for b in benefits if b.get("target") == "DELIVERY_FEE")
    delivery_net = _amount(totals.get("delivery_fee_q")) - delivery_benefits
    if delivery_net > 0:
        lines.append(OrderDiscountLineProjection(kind="delivery", label="Taxa de entrega", amount_display=f"+R$ {format_money(delivery_net)}"))

    fees = [f for f in facts.get("additional_fees") or [] if isinstance(f, dict) and _amount(f.get("value_q"))]
    if fees:
        for fee in fees:
            label = _FEE_LABELS.get(str(fee.get("type") or "").upper()) or str(fee.get("description") or "").strip() or "Taxa do iFood paga pelo cliente"
            lines.append(OrderDiscountLineProjection(kind="fee", label=label, amount_display=f"+R$ {format_money(_amount(fee.get('value_q')))}"))
    elif _amount(totals.get("additional_fees_q")):
        lines.append(OrderDiscountLineProjection(
            kind="fee", label="Taxa do iFood paga pelo cliente",
            amount_display=f"+R$ {format_money(_amount(totals.get('additional_fees_q')))}",
        ))

    by_sponsor = {"store": 0, "ifood": 0, "unknown": 0}
    for benefit in benefits:
        if benefit.get("target") == "DELIVERY_FEE":
            continue
        shares = [x for x in benefit.get("sponsorships") or [] if isinstance(x, dict)]
        if not shares:
            # Sem o desdobramento não se afirma quem paga: nem iFood, nem loja.
            by_sponsor["unknown"] += _amount(benefit.get("value_q"))
            continue
        for share in shares:
            key = "store" if str(share.get("sponsor") or "").upper() == "MERCHANT" else "ifood"
            by_sponsor[key] += _amount(share.get("value_q"))
    if by_sponsor["ifood"]:
        lines.append(OrderDiscountLineProjection(kind="discount", label="Desconto do iFood", amount_display=f"−R$ {format_money(by_sponsor['ifood'])}"))
    if by_sponsor["store"]:
        lines.append(OrderDiscountLineProjection(kind="discount", label="Desconto da loja", amount_display=f"−R$ {format_money(by_sponsor['store'])}"))
    if by_sponsor["unknown"]:
        lines.append(OrderDiscountLineProjection(kind="discount", label="Desconto (responsável não informado pelo iFood)", amount_display=f"−R$ {format_money(by_sponsor['unknown'])}"))
    if not benefits and _amount(totals.get("benefits_q")):
        lines.append(OrderDiscountLineProjection(kind="discount", label="Desconto (responsável não informado pelo iFood)", amount_display=f"−R$ {format_money(_amount(totals.get('benefits_q')))}"))
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
    if pickup_code_label(order):
        lines.append(pickup_code_label(order).replace(" · ", ": "))
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


_LOGISTICS_STEPS = (
    # (fato, rótulo) do mais adiantado para o mais antigo: vale o primeiro presente.
    ("DELIVERY_DROP_CODE_VALIDATION_SUCCESS", "Entregue ao cliente"),
    ("ARRIVED_AT_DESTINATION", "Entregador chegou ao cliente"),
    ("COLLECTED", "Saiu com o entregador do iFood"),
    ("ARRIVED_AT_ORIGIN", "Entregador do iFood na loja"),
    ("DELIVERY_PICKUP_CODE_REQUESTED", "Entregador do iFood na loja"),
    ("GOING_TO_ORIGIN", "Entregador a caminho da loja"),
    ("ASSIGN_DRIVER", "Entregador do iFood designado"),
)


def logistics_label(order) -> str:
    """Onde está o entregador do iFood, numa frase, pelo último fato recebido.

    Com entregador do iFood, depois do aceite quem conduz é o iFood (dono,
    12/11/2026): o Gestor mostra o andamento no lugar de pedir "Pronto".
    Vazio fora do iFood, sem entregador do iFood ou sem nenhum fato ainda.
    """
    if order.channel_ref != "ifood":
        return ""
    facts = (order.data or {}).get("ifood") or {}
    if str(facts.get("delivered_by") or "").upper() != "IFOOD":
        return ""
    if order.status in {"completed"} or facts.get("remote_concluded"):
        return "Concluído no iFood"
    logistics = facts.get("logistics") if isinstance(facts.get("logistics"), dict) else {}
    if facts.get("remote_dispatched") and not any(
        logistics.get(step) for step in ("DELIVERY_DROP_CODE_VALIDATION_SUCCESS", "ARRIVED_AT_DESTINATION")
    ):
        return "Saiu com o entregador do iFood"
    for step, label in _LOGISTICS_STEPS:
        if logistics.get(step):
            if step == "ASSIGN_DRIVER":
                meta = logistics[step].get("metadata") if isinstance(logistics[step].get("metadata"), dict) else {}
                name = str(meta.get("workerName") or meta.get("driverName") or "").strip()
                if name:
                    return f"{label}: {name}"
            return label
    return ""


def pickup_code_label(order) -> str:
    """O código com o nome do que ele é: na entrega, quem o diz é o ENTREGADOR.

    Na entrega pelo iFood o ``pickupCode`` é o código que o entregador informa
    para coletar a sacola; "Código de retirada" fazia parecer código do cliente.
    """
    code = pickup_code(order)
    if not code:
        return ""
    from shopman.shop.services.order_helpers import get_fulfillment_type

    if get_fulfillment_type(order) == "delivery":
        return f"Código do entregador · {code}"
    return f"Código de retirada · {code}"


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
    ifood_courier = str(facts.get("delivered_by") or "").upper() == "IFOOD"
    if facts.get("remote_dispatched") and (
        order.status in {"new", "accepted"} or (order.status == "preparing" and not ifood_courier)
    ):
        # Em preparo o DSP fecha sozinho (``ifood_events._collected_by_ifood_courier``);
        # antes do preparo nada é inventado, e quem conduz é o operador.
        return "Retirado pelo entregador do iFood · Marque Pronto"
    return ""
