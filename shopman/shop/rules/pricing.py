"""Pricing rules — the operator-facing definition of each pricing modifier.

Each rule class declares a modifier's identity (``code``), its admin label and
``default_params``. Its ``RuleConfig`` row is the single source of truth for
that modifier's runtime behaviour: enabled state, params and channel scope.

Execution is rule-driven. The modifiers in ``shop.modifiers`` that read their
params through ``get_channel_rule_params`` (``TimeWindowDiscountModifier``)
skip entirely when their ``RuleConfig`` is disabled or not scoped to the
channel being priced — so disabling a rule in the admin truly disables the
discount.
"""

from __future__ import annotations

from datetime import time

from shopman.shop.rules import BaseRule


class HappyHourRule(BaseRule):
    """Desconto por horário (Happy Hour, a "Hora da Xepa" da casa).

    É liquidação de fim de dia de quem está na loja: vale só nos canais listados
    no ``RuleConfig`` (decisão do dono, 14/10/2026: só no balcão). Sem canal
    listado, não vale em lugar nenhum. O "vazio = todos" das outras regras levava
    a Xepa ao site e ao iFood com um clique a menos no Admin.
    """

    code = "shop.happy_hour"
    label = "Happy Hour"
    rule_type = "modifier"
    channels_required = True
    default_params = {"discount_percent": 25, "start": "17:30", "end": "18:00"}

    def __init__(
        self,
        *,
        discount_percent: int = 25,
        start: str = "17:30",
        end: str = "18:00",
    ):
        self.discount_percent = discount_percent
        self.start = time.fromisoformat(start)
        self.end = time.fromisoformat(end)
