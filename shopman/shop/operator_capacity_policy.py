"""Limites de capacidade dos apps de operação — ``Shop.defaults["operator_capacity"]``.

Os apps Nuxt de operador (PDV, Cozinha, Pedidos, Produção, Central, Marketing, B.I.,
Compras) rodam em contêineres com memória e CPU contadas. Cada app lê o uso do
PRÓPRIO contêiner (cgroup ou soma dos processos) e mostra no rail; estes limites dizem quando a leitura
deixa de ser neutra e quando vira aviso para o gestor:

- ``attention_percent`` — a partir deste uso (memória ou CPU, o maior) o indicador
  fica âmbar. Padrão 75.
- ``critical_percent`` — a partir deste uso o indicador fica vermelho e, se ficar
  acima por ``sustain_minutes``, nasce um ``OperatorAlert`` crítico. Padrão 90.
- ``sustain_minutes`` — quanto tempo acima do crítico antes de avisar. Existe para
  que um pico de dez segundos (a abertura do caixa, um relatório pesado) não vire
  alarme. Padrão 5.

Limiar de negócio mora no Admin (página "Integrações" do ShopAdmin), sem deploy.
Mesmo padrão dataclass-driven de ``marketing_policy``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_ATTENTION_PERCENT = 75
DEFAULT_CRITICAL_PERCENT = 90
DEFAULT_SUSTAIN_MINUTES = 5

PERCENT_FLOOR = 1
PERCENT_CEILING = 100
SUSTAIN_MINUTES_FLOOR = 1
SUSTAIN_MINUTES_CEILING = 60

_BLOCK = "operator_capacity"


@dataclass(frozen=True)
class OperatorCapacityPolicy:
    """Limites resolvidos (padrões ← ``Shop.defaults["operator_capacity"]``)."""

    attention_percent: int = DEFAULT_ATTENTION_PERCENT
    critical_percent: int = DEFAULT_CRITICAL_PERCENT
    sustain_minutes: int = DEFAULT_SUSTAIN_MINUTES

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> OperatorCapacityPolicy:
        """Constrói a partir de ``Shop.defaults`` (chave ausente → padrão)."""
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get(_BLOCK), dict):
            block = defaults[_BLOCK]

        attention = _coerce(
            block.get("attention_percent"),
            "attention_percent",
            DEFAULT_ATTENTION_PERCENT,
            PERCENT_FLOOR,
            PERCENT_CEILING,
        )
        critical = _coerce(
            block.get("critical_percent"),
            "critical_percent",
            DEFAULT_CRITICAL_PERCENT,
            PERCENT_FLOOR,
            PERCENT_CEILING,
        )
        sustain = _coerce(
            block.get("sustain_minutes"),
            "sustain_minutes",
            DEFAULT_SUSTAIN_MINUTES,
            SUSTAIN_MINUTES_FLOOR,
            SUSTAIN_MINUTES_CEILING,
        )
        if attention >= critical:
            # O Admin recusa este par; gravado assim, só por edição crua do JSON.
            # Os dois voltam ao padrão juntos: misturar um valor decidido com um
            # padrão produziria um par que ninguém escolheu.
            logger.warning(
                "operator_capacity_policy.thresholds_inverted attention=%s critical=%s",
                attention,
                critical,
            )
            attention, critical = DEFAULT_ATTENTION_PERCENT, DEFAULT_CRITICAL_PERCENT
        return cls(attention_percent=attention, critical_percent=critical, sustain_minutes=sustain)

    def as_payload(self) -> dict[str, int]:
        return {
            "attention_percent": self.attention_percent,
            "critical_percent": self.critical_percent,
            "sustain_minutes": self.sustain_minutes,
        }


def _coerce(raw, key: str, default: int, floor: int, ceiling: int) -> int:
    if raw is None:
        return default
    # O Admin só grava inteiro dentro da faixa; fora disso veio de edição crua do
    # JSON. Cair no padrão mantém o monitor de pé, mas grita: em silêncio o gestor
    # veria um número no Admin e o alerta obedeceria outro.
    if isinstance(raw, bool) or not isinstance(raw, int) or not floor <= raw <= ceiling:
        logger.warning(
            "operator_capacity_policy.%s_invalid type=%s",
            key,
            type(raw).__name__,
        )
        return default
    return raw


def resolve_operator_capacity_policy() -> OperatorCapacityPolicy:
    """Limites efetivos, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return OperatorCapacityPolicy.from_defaults(defaults)
