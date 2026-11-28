"""A forma de pagamento que uma sessão de teste leva ao commit.

Pedido sem forma de pagamento não existe (decisão do dono, 06/11/2026, GES-03):
o commit recusa (``policies.order_payment.PaymentMethodRule``). Os testes que montam a
sessão à mão dizem a forma pelo canal: a única que ele aceita, ou dinheiro
quando ele aceita várias (o pedido que não exige cobrança antecipada).
"""

from __future__ import annotations


def payment_for(channel) -> dict:
    """``{"method": ...}`` para o canal (instância ou ref)."""
    from shopman.shop.config import ChannelConfig

    methods = ChannelConfig.for_channel(channel).payment.available_methods
    return {"method": methods[0] if len(methods) == 1 else "cash"}


def with_payment(channel, data: dict | None = None) -> dict:
    """``data`` da sessão com a forma de pagamento do canal (a de ``data`` vence)."""
    data = dict(data or {})
    data.setdefault("payment", payment_for(channel))
    return data
