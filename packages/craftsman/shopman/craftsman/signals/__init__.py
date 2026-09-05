"""
Craftsman Signals.

Single signal for all production state changes.
Emitted on plan, adjust, start, finish, void.

Usage:
    from shopman.craftsman.signals import production_changed

    @receiver(production_changed)
    def on_production_changed(sender, product_ref, date, **kwargs):
        ...
"""

from django.dispatch import Signal

# Emitted when production state changes (plan, adjust, start, finish, void)
# kwargs: product_ref (str), date (date|None), sender=WorkOrder
production_changed = Signal()

# Emitted quando o FECHAMENTO baixou MENOS insumo que a ficha pede (estoque
# insuficiente). A baixa é best-effort por design (insumo ainda não é
# first-class pré-go-live; FEFO/gating estrito chegam com Buyman/Material), então
# a fornada NÃO falha — mas a sub-baixa não pode ficar só no log: é dinheiro/
# estoque, e a regra da casa é falhar GRITANDO. A ponte craftsman→stockman é
# core e não importa `shopman.shop`; então ela ANUNCIA por este sinal e um
# handler no shop (production_alerts) traduz para OperatorAlert. Ponto-a-ponto
# multi-app => sinal (ADR-001).
# kwargs: work_order (WorkOrder), shortfalls (list[dict] com sku/needed/issued/short),
#         sender=WorkOrder
production_stock_shortfall = Signal()

__all__ = ["production_changed", "production_stock_shortfall"]
