"""Frete grátis de grupo de clientes: qual vale e se cobre o pedido.

A vantagem ``free_shipping`` de um grupo (``PriceTierAdvantage.config["min_order_q"]``)
zera a taxa de entrega do membro a partir de um pedido mínimo. Cliente em dois grupos
com frete grátis fica com o de MENOR mínimo: a taxa só zera uma vez, e o que importa
ao cliente é a partir de quanto ele já ganha (regra do dono, 14/10: vale a melhor
vantagem para o cliente, sem acumular).

Sem Django, sem banco: a vantagem é qualquer objeto com ``config`` (o model ou um
``SimpleNamespace`` de teste). O mínimo é perguntado à política de mínimo da promoção,
a mesma régua do limiar da loja.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from shopman.shop.policies.promotion import promotion_minimum_eligible


def free_shipping_minimum_q(config: Mapping[str, Any] | None) -> int:
    """O pedido mínimo do frete grátis do grupo, em centavos. ``0`` = sempre."""
    try:
        return max(0, int((config or {}).get("min_order_q") or 0))
    except (TypeError, ValueError):
        return 0


def best_group_free_shipping(advantages: Iterable[Any]) -> Any | None:
    """A vantagem de frete grátis de menor mínimo, ou ``None``.

    ``advantages`` chega já na ordem de desempate (prioridade da vantagem, depois a do
    grupo): ``min`` é estável, então no empate do mínimo a primeira dá o nome.
    """
    found = list(advantages)
    if not found:
        return None
    return min(found, key=lambda advantage: free_shipping_minimum_q(getattr(advantage, "config", None)))


def group_free_shipping_for_order(advantages: Iterable[Any], *, merchandise_q: int) -> Any | None:
    """A vantagem que dá frete grátis a ESTE pedido, ou ``None`` se o mínimo não foi alcançado."""
    best = best_group_free_shipping(advantages)
    if best is None:
        return None
    minimum_q = free_shipping_minimum_q(getattr(best, "config", None))
    if not promotion_minimum_eligible(min_order_q=minimum_q, merchandise_subtotal_q=merchandise_q):
        return None
    return best
