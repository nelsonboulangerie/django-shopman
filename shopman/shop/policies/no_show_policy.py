"""Quando o "Não retirado" libera — ``Shop.defaults["no_show"]``.

Decisão do dono (WP-G11): pedido de retirada que ficou pronto e o cliente não
veio buscar é encerrado por um Gerente, e **o dinheiro segue o produto** (o que
volta à venda é devolvido; o que se perdeu fica com a loja). Esta política só
diz QUANDO o gesto passa a existir; quem decide o destino de cada linha e do
dinheiro é ``services/no_show``.

Chaves (todas opcionais; sem o bloco, valem os padrões declarados abaixo):

- ``tolerance_minutes`` — quanto a casa espera depois da hora combinada (ou,
  sem hora combinada, depois de o pedido ficar pronto). Padrão 60.
- ``cutoff_minutes_before_close`` — pedido PAGO espera o corte do dia
  combinado: o fechamento da loja menos estes minutos. Padrão 0 (o corte é o
  próprio fechamento, como dizem os Termos: "até o fim do expediente").
- ``paid_waits_cutoff`` — ``True`` (padrão): o pago só libera no corte.
  ``False``: o pago segue a mesma régua do não pago (hora + tolerância).

Configuração de loja: mora na ``Shop`` (ADR-042), nunca em env ou settings.
Mesmo padrão dataclass-driven de ``preorder_kitchen_policy``.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TOLERANCE_MINUTES = 60
DEFAULT_CUTOFF_MINUTES_BEFORE_CLOSE = 0
DEFAULT_PAID_WAITS_CUTOFF = True

BLOCK = "no_show"


@dataclass(frozen=True)
class NoShowPolicy:
    tolerance_minutes: int = DEFAULT_TOLERANCE_MINUTES
    cutoff_minutes_before_close: int = DEFAULT_CUTOFF_MINUTES_BEFORE_CLOSE
    paid_waits_cutoff: bool = DEFAULT_PAID_WAITS_CUTOFF

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> NoShowPolicy:
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get(BLOCK), dict):
            block = defaults[BLOCK]
        paid_waits = block.get("paid_waits_cutoff")
        return cls(
            tolerance_minutes=_minutes(block.get("tolerance_minutes"), fallback=DEFAULT_TOLERANCE_MINUTES),
            cutoff_minutes_before_close=_minutes(
                block.get("cutoff_minutes_before_close"), fallback=DEFAULT_CUTOFF_MINUTES_BEFORE_CLOSE
            ),
            paid_waits_cutoff=paid_waits if isinstance(paid_waits, bool) else DEFAULT_PAID_WAITS_CUTOFF,
        )


def _minutes(value, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return fallback
    return coerced if coerced >= 0 else fallback


def resolve_no_show_policy() -> NoShowPolicy:
    """Política efetiva, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return NoShowPolicy.from_defaults(defaults)
