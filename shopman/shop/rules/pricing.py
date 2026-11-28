"""Pricing rules — the operator-facing definition of each pricing modifier.

Each rule class declares a modifier's identity (``code``), its admin label and
the params it requires. Its ``RuleConfig`` row is the single source of truth for
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
    #: A janela e o percentual são da casa, não do produto: moram no
    #: ``RuleConfig.params`` (descritor da Instância), sem default em código.
    REQUIRED_PARAMS = ("discount_percent", "start", "end")

    def __init__(self, *, discount_percent: int | float, start: str, end: str):
        self.discount_percent, self.start, self.end = self.parse_params(
            {"discount_percent": discount_percent, "start": start, "end": end}
        )

    @classmethod
    def parse_params(cls, params: dict) -> tuple[int | float, time, time]:
        """``(percentual, início, fim)`` de ``RuleConfig.params``; ``ValueError`` se faltar ou não valer."""
        missing = [key for key in cls.REQUIRED_PARAMS if key not in (params or {})]
        if missing:
            raise ValueError(f"happy_hour sem {', '.join(missing)} em params")
        percent = params["discount_percent"]
        if isinstance(percent, bool) or not isinstance(percent, (int, float)) or not 0 <= percent <= 100:
            raise ValueError(f"happy_hour discount_percent inválido: {percent!r}")
        try:
            start = time.fromisoformat(str(params["start"]))
            end = time.fromisoformat(str(params["end"]))
        except ValueError as exc:
            raise ValueError(f"happy_hour com horário inválido: {exc}") from exc
        return percent, start, end

    @classmethod
    def validate_params(cls, params: dict) -> None:
        cls.parse_params(params)
