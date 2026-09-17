"""Política de Marketing da loja — ``Shop.defaults["marketing"]`` + resolução.

Hoje uma chave só, editável no Admin (página "Integrações" do ShopAdmin) e lida pela
aprovação de campanha (``shopman/shop/services/marketing_approval.py``):

- ``whatsapp_minimum_audience`` — quantas pessoas elegíveis uma campanha GERAL por
  WhatsApp precisa ter para ser aprovada. Existe para que uma campanha "geral" não vire
  mensagem mirada em uma pessoa escolhida a dedo. No ensaio
  (``SHOPMAN_MARKETING_WHATSAPP_MODE=canary``) não vale: quem recebe já é só a lista de
  canário que a operação controla.

O padrão é ``1`` por decisão do dono (2026-09-17): no começo da operação um mínimo alto
seguraria campanhas boas antes de a casa sentir o impacto. Subir o número é decisão da
loja, no Admin, sem deploy.

Mesmo padrão dataclass-driven de ``purchase_policy`` e ``loyalty_config``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_WHATSAPP_MINIMUM_AUDIENCE = 1
#: Piso aceito. Zero não é "sem mínimo": seria aprovar campanha para ninguém.
WHATSAPP_MINIMUM_AUDIENCE_FLOOR = 1


@dataclass(frozen=True)
class MarketingPolicy:
    """Política de Marketing resolvida (padrões ← ``Shop.defaults["marketing"]``)."""

    whatsapp_minimum_audience: int = DEFAULT_WHATSAPP_MINIMUM_AUDIENCE

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> MarketingPolicy:
        """Constrói a partir de ``Shop.defaults`` (chave ausente → padrão)."""
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get("marketing"), dict):
            block = defaults["marketing"]
        raw = block.get("whatsapp_minimum_audience")
        if raw is None:
            return cls()
        return cls(whatsapp_minimum_audience=_coerce_minimum_audience(raw))


def _coerce_minimum_audience(raw) -> int:
    # O Admin só grava inteiro >= 1; valor fora disso veio de edição crua do JSON. Cair
    # no padrão mantém a aprovação funcionando, mas grita: é uma POLÍTICA que ninguém
    # decidiu, e em silêncio o gestor veria um número e a aprovação obedeceria outro.
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < WHATSAPP_MINIMUM_AUDIENCE_FLOOR:
        logger.warning(
            "marketing_policy.whatsapp_minimum_audience_invalid type=%s",
            type(raw).__name__,
        )
        return DEFAULT_WHATSAPP_MINIMUM_AUDIENCE
    return raw


def resolve_marketing_policy() -> MarketingPolicy:
    """Política de Marketing efetiva, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return MarketingPolicy.from_defaults(defaults)
