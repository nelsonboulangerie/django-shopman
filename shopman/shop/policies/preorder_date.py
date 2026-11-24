"""A data de uma encomenda, com a sacola: pode ser combinada, ou por que não.

Três réguas, na ordem em que o cliente as entende, e uma porta só para as três
(OC-14: uma regra comercial, um lugar):

1. a régua da DATA da casa (``services.preorder_dates.date_refusal``): passada,
   além do máximo, dia fechado;
2. um pedido, uma data (``policies.order_date_before_batch``): a sacola presa a
   uma fornada que só sai depois da data escolhida;
3. a antecedência por produto (lead time), que depende do carrinho e do plano
   da data.

Quem pergunta é a Concierge, antes de gravar o recebimento, no orçamento e na
hora de fechar o pedido. O gate de commit recusa de qualquer jeito; dizer aqui é
dizer antes da cotação, com o item e o dia.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone


def chosen_day(raw: str | None, *, today: date | None = None) -> tuple[date | None, str | None]:
    """O dia que a cliente escolheu no "Para quando?" do cardápio (OC-33 B1).

    Devolve ``(dia, recusa)``. Vazio ou HOJE é ``(None, None)``: hoje é o
    cardápio de sempre, sem data (X13). Data ilegível ou que a casa não combina
    (passada, além do máximo, dia fechado: ``preorder_dates.date_refusal``) volta com a
    frase da recusa, para a tela dizer por quê. A loja pergunta isto ao ler o
    cardápio do dia e ao pôr o primeiro item na sacola daquele dia.
    """
    from shopman.shop.services.preorder_dates import date_refusal

    text = str(raw or "").strip()
    if not text:
        return None, None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return None, "Data inválida. Use AAAA-MM-DD."
    today = today or timezone.localdate()
    if day == today:
        return None, None
    refusal = date_refusal(day, today=today)
    if refusal:
        return None, refusal
    return day, None


def cart_day_refusal(day: date, *, today: date | None = None) -> str | None:
    """Por que a sacola inteira não pode passar para ``day`` (OC-33 B1, o "Trocar"), ou ``None``.

    Dia futuro: a régua da data da casa (passada, além do máximo, fechado). Hoje:
    só se ainda há horário hoje; depois do último horário a frase é a do checkout.
    """
    from shopman.shop.services.preorder_dates import date_refusal

    today = today or timezone.localdate()
    if day != today:
        return date_refusal(day, today=today)
    from shopman.shop.services import fulfillment_window

    if not fulfillment_window.delivery_windows_for(today):
        return "Já encerramos o atendimento de hoje. Escolha outra data."
    return None


def cart_day_change_refusal(*, day_label: str, names: list[str]) -> dict[str, str]:
    """A frase de quando a troca de dia deixaria item de fora (OC-33 B1, o "Trocar").

    Nomeia cada item que não dá no dia novo. Nada mudou ainda: a cliente escolhe
    seguir sem eles ou manter o dia que tinha.
    """
    if len(names) == 1:
        title = f"{names[0]} não está disponível para {day_label}"
        detail = f"Você pode seguir para {day_label} sem ele, ou manter o dia que tinha."
    else:
        title = f"Estes itens não estão disponíveis para {day_label}"
        detail = f"Você pode seguir para {day_label} sem eles, ou manter o dia que tinha."
    return {"title": title, "detail": detail}


def preorder_date_errors(
    delivery_date: str,
    *,
    cart_lines=None,
    channel_ref: str | None = None,
    session_key: str = "",
) -> dict[str, str]:
    """``{"delivery_date": frase}`` quando a data não pode ser combinada; ``{}`` quando pode.

    Data ilegível não é recusa desta régua (quem lê a data recusa o formato).
    """
    from datetime import date as date_type

    errors: dict[str, str] = {}
    today = timezone.localdate()
    try:
        chosen_date = date_type.fromisoformat(delivery_date)
    except ValueError:
        return errors

    # Passada, além do máximo e dia fechado: a mesma régua do reagendamento do
    # operador (``shop.services.preorder_dates``).
    from shopman.shop.services.preorder_dates import date_refusal

    refusal = date_refusal(chosen_date, today=today)
    if refusal:
        errors["delivery_date"] = refusal
        return errors

    # Um pedido, uma data: a sacola presa a uma fornada que só sai depois da
    # data escolhida.
    if session_key:
        from shopman.shop.policies.order_date_before_batch import order_date_before_batch_refusal

        batch_refusal = order_date_before_batch_refusal(
            session_key, chosen_date, list(cart_lines or []), channel_ref=channel_ref,
        )
        if batch_refusal is not None:
            errors["delivery_date"] = batch_refusal.message
            return errors

    lead_time_error = _lead_time_refusal(
        chosen_date,
        today=today,
        cart_lines=cart_lines,
        channel_ref=channel_ref,
        session_key=session_key,
    )
    if lead_time_error:
        errors["delivery_date"] = lead_time_error
    return errors


def _lead_time_refusal(
    chosen_date,
    *,
    today,
    cart_lines,
    channel_ref: str | None,
    session_key: str,
) -> str | None:
    """Encomenda dentro do lead time de cada produto do carrinho.

    O gate vale só para DEMANDA: data futura sem cobertura (fornada planejada /
    estoque válido na data) para a quantidade pedida. Encomenda com plano
    existente e compra do estoque físico de hoje passam direto — a regra do
    dono é sobre registrar demanda que a produção não alcança.
    """
    if not cart_lines or chosen_date <= today:
        return None

    from decimal import Decimal

    from shopman.shop.projections import checkout_context
    from shopman.shop.services import availability, lead_time

    session_held: dict[str, int] | None = None
    for line in cart_lines:
        sku = getattr(line, "sku", None)
        if not sku:
            continue
        hours = lead_time.effective_lead_time_hours(sku, channel_ref)
        if hours <= 0:
            continue
        earliest = lead_time.earliest_allowed_date(sku, channel_ref)
        if chosen_date >= earliest:
            continue

        # A data está cedo demais para DEMANDA — mas fornada planejada (ou
        # estoque válido na data) honra o compromisso e passa.
        if session_held is None:
            session_held = (
                checkout_context.session_held_qty(session_key, target_date=chosen_date)
                if session_key
                else {}
            )
        qty = int(getattr(line, "qty", 0) or 0)
        needed = max(qty - session_held.get(sku, 0), 0)
        if needed == 0:
            continue  # a própria sessão já reservou quants da data
        decision = availability.check(
            sku, Decimal(needed), channel_ref=channel_ref, target_date=chosen_date
        )
        if decision["ok"] and decision.get("is_tracked") is not False:
            continue

        name = getattr(line, "name", None) or sku
        return (
            f"{name} precisa de {hours}h de antecedência. "
            f"A primeira data possível é {earliest.strftime('%d/%m')}."
        )
    return None
