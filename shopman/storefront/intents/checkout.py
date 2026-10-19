"""Checkout: regras do pedido que dependem do carrinho e da data.

Funções puras chamadas pelas portas de pedido: o troco para dinheiro na
entrega (``parse_change_for``, checkout da loja em ``storefront/api/views.py``)
e a data de encomenda com lead time (``_validate_preorder``, concierge em
``storefront/concierge/tools.py``).
"""

from __future__ import annotations

from django.utils import timezone

from shopman.shop.projections import checkout_context

# ── Payment helpers ───────────────────────────────────────────────────────────


def parse_change_for(raw: str) -> int:
    """'50'/'50,00'/'50.00' (Reais) → centavos. Vazio/inválido → 0."""
    text = (raw or "").strip().replace("R$", "").replace(" ", "").replace(",", ".")
    if not text:
        return 0
    try:
        value = float(text)
    except ValueError:
        return 0
    return max(int(round(value * 100)), 0)


# ── Validation helpers ────────────────────────────────────────────────────────


def _validate_preorder(
    delivery_date: str,
    *,
    cart_lines=None,
    channel_ref: str | None = None,
    session_key: str = "",
) -> dict[str, str]:
    from datetime import date as date_type
    errors: dict[str, str] = {}
    today = timezone.localdate()
    try:
        chosen_date = date_type.fromisoformat(delivery_date)
    except ValueError:
        return errors

    # Passada, além do máximo e dia fechado: a mesma régua do reagendamento do
    # operador (``shop.services.preorder_dates``). O lead time fica aqui porque
    # depende do carrinho.
    from shopman.shop.services.preorder_dates import date_refusal

    refusal = date_refusal(chosen_date, today=today)
    if refusal:
        errors["delivery_date"] = refusal
        return errors

    lead_time_error = _validate_lead_time(
        chosen_date,
        today=today,
        cart_lines=cart_lines,
        channel_ref=channel_ref,
        session_key=session_key,
    )
    if lead_time_error:
        errors["delivery_date"] = lead_time_error
    return errors


def _validate_lead_time(
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
            f"{name} precisa de {hours}h de antecedência — "
            f"primeira data possível: {earliest.strftime('%d/%m')}."
        )
    return None
