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
  próprio fechamento, conforme os Termos do serviço: "até o fim do expediente").
- ``paid_waits_cutoff`` — ``True`` (padrão): o pago só libera no corte.
  ``False``: o pago segue a mesma régua do não pago (hora + tolerância).
- ``retention`` — quanto a loja retém dos itens FEITOS para a encomenda não
  retirada (DEV-2026-089, decisão do dono de 24/11/2026): ``{"percent": 40,
  "decided_at": "2026-11-24", "provisional": true}``. A revenda volta inteira, e
  o que volta à venda também. **Sem padrão no código**: sem o bloco (ou com um
  percentual acima do teto dos Termos, :data:`TERMS_RETENTION_CAP_PERCENT`), o
  gesto recusa com o motivo, porque reter sem regra publicada é cobrar o que os
  Termos não dizem.

Configuração de loja: mora na ``Shop`` (ADR-042), nunca em env ou settings.
Mesmo padrão dataclass-driven de ``preorder_kitchen_policy``.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TOLERANCE_MINUTES = 60
DEFAULT_CUTOFF_MINUTES_BEFORE_CLOSE = 0
DEFAULT_PAID_WAITS_CUTOFF = True

BLOCK = "no_show"

#: O teto que os Termos publicam ("retemos até 40% do valor", 24/11/2026). Não é a
#: regra: a regra é o ``retention.percent`` da loja, que pode ser menor e nunca
#: maior. A trava ``test_retencao_do_nao_retirado.py`` confere este número com o
#: texto de ``termos.vue``; trocar um sem o outro reprova.
TERMS_RETENTION_CAP_PERCENT = 40


@dataclass(frozen=True)
class RetentionRule:
    """Quanto a loja retém do valor dos itens feitos para a encomenda não retirada."""

    percent: int
    decided_at: str = ""
    provisional: bool = False


@dataclass(frozen=True)
class NoShowPolicy:
    tolerance_minutes: int = DEFAULT_TOLERANCE_MINUTES
    cutoff_minutes_before_close: int = DEFAULT_CUTOFF_MINUTES_BEFORE_CLOSE
    paid_waits_cutoff: bool = DEFAULT_PAID_WAITS_CUTOFF
    retention: RetentionRule | None = None

    def retention_refusal(self) -> str:
        """Por que a regra de retenção não serve agora ("" quando serve)."""
        if self.retention is None:
            return (
                "A retenção do não retirado não está configurada nesta loja "
                "(Admin, Loja, padrões, no_show.retention)."
            )
        if self.retention.percent > TERMS_RETENTION_CAP_PERCENT:
            return (
                f"A retenção configurada ({self.retention.percent}%) passa do que os Termos "
                f"publicam ({TERMS_RETENTION_CAP_PERCENT}%)."
            )
        return ""

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
            retention=_retention(block.get("retention")),
        )


def _retention(raw) -> RetentionRule | None:
    """A regra gravada na loja, ou ``None`` quando ela falta ou não é um percentual de 0 a 100."""
    if not isinstance(raw, dict):
        return None
    percent = raw.get("percent")
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
        return None
    return RetentionRule(
        percent=percent,
        decided_at=str(raw.get("decided_at") or ""),
        provisional=raw.get("provisional") is True,
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
