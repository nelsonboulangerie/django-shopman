"""Pricing rules — the operator-facing definition of each pricing modifier.

Each rule class declares a modifier's identity (``code``), its admin label and
``default_params``. Its ``RuleConfig`` row is the single source of truth for
that modifier's runtime behaviour: enabled state, params and channel scope.

Execution is rule-driven. The modifiers in ``shop.modifiers`` that read their
params through ``get_channel_rule_params`` (``AvailabilityDiscountModifier``,
``TimeWindowDiscountModifier``) skip entirely when their ``RuleConfig`` is
disabled or not scoped to the channel being priced — so disabling a rule in the
admin truly disables the discount.
"""

from __future__ import annotations

from datetime import time

from shopman.shop.rules import BaseRule


class D1Rule(BaseRule):
    """Desconto D-1 — sobras do dia anterior."""

    code = "shop.d1_discount"
    label = "Desconto de ontem"
    rule_type = "modifier"
    default_params = {"discount_percent": 50}

    def __init__(self, *, discount_percent: int = 50):
        self.discount_percent = discount_percent


class EmployeeRule(BaseRule):
    """Desconto para funcionários (faixa de preço == staff).

    ``pickup_only`` é o guarda que separa benefício de canal: o funcionário
    compra pelo site com o desconto, mas precisa **retirar**. Com entrega, o
    preço de funcionário viajaria para qualquer endereço — e aí o benefício
    deixa de ser "o pão dele" e vira um canal de preço para terceiros, sem
    ninguém ver. No balcão isso não acontece porque alguém entrega na mão.

    Novo parâmetro entra com default: ``RuleConfig`` antigo (sem a chave no JSON)
    continua instanciando. O caminho contrário — chave nos DADOS que a classe não
    conhece — era fatal (``TypeError`` engolido, regra desligada em silêncio; o
    incidente `da69c714`). Desde a faxina de 2026-08-13 o ``load_rule`` descarta
    a chave órfã com WARNING nomeado e a regra segue viva; o conserto correto do
    rename continua sendo migração de dados (ver 0010).
    """

    code = "shop.employee_discount"
    label = "Desconto Funcionário"
    rule_type = "modifier"
    default_params = {"discount_percent": 20, "price_tier": "staff", "pickup_only": True}

    def __init__(
        self,
        *,
        discount_percent: int = 20,
        price_tier: str = "staff",
        pickup_only: bool = True,
    ):
        self.discount_percent = discount_percent
        self.price_tier = price_tier
        self.pickup_only = pickup_only


class HappyHourRule(BaseRule):
    """Desconto happy hour — horário configurável."""

    code = "shop.happy_hour"
    label = "Happy Hour"
    rule_type = "modifier"
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
