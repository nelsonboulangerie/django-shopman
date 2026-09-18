"""Política de Marketing da loja — ``Shop.defaults["marketing"]`` + resolução.

Duas políticas moram aqui, as duas editáveis no Admin (página "Integrações" do
ShopAdmin), sem deploy e sem migração:

- ``whatsapp_minimum_audience`` — quantas pessoas elegíveis uma campanha GERAL por
  WhatsApp precisa ter para ser aprovada. Existe para que uma campanha "geral" não vire
  mensagem mirada em uma pessoa escolhida a dedo. No ensaio
  (``SHOPMAN_MARKETING_WHATSAPP_MODE=canary``) não vale: quem recebe já é só a lista de
  canário que a operação controla. O padrão é ``1`` por decisão do dono (2026-09-17): no
  começo da operação um mínimo alto seguraria campanhas boas antes de a casa sentir o
  impacto.

- **o limiar de cerimônia do disparo** — a partir de quantas PESSOAS a confirmação deixa
  de ser "leia o resumo e toque" e passa a pedir frase digitada + senha, e depois TOTP +
  duplo controle. Decisão do dono (2026-09-17): *"2% da base de clientes. Ou threshold
  para gasto, o que chegar primeiro"*. Ver ``ceremony_threshold`` e
  [ADR-032](../../docs/decisions/adr-032-marketing-ceremony-threshold-is-proportional.md).

Mesmo padrão dataclass-driven de ``purchase_policy`` e ``loyalty_config``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil

logger = logging.getLogger(__name__)

DEFAULT_WHATSAPP_MINIMUM_AUDIENCE = 1
#: Piso aceito. Zero não é "sem mínimo": seria aprovar campanha para ninguém.
WHATSAPP_MINIMUM_AUDIENCE_FLOOR = 1

#: Percentual da base de clientes a partir do qual o disparo pede cerimônia forte.
#: Decisão do dono, textual: "estabeleço: 2% da base de clientes".
DEFAULT_CEREMONY_AUDIENCE_PERCENT = Decimal("2")
#: Piso do limiar, em pessoas. É ele que responde quando a base é pequena, desconhecida
#: ou zero — e por isso ele é o lado FECHADO da conta: quanto menor, mais cedo a casa
#: pede senha. ⚠️ PALPITE a confirmar com o dono: dez mensagens é o menor disparo que
#: ainda parece "a casa falando com gente", e não um teste.
DEFAULT_CEREMONY_RECIPIENT_FLOOR = 10
#: Teto de gasto estimado de um disparo antes da cerimônia forte, em centavos.
#: ⚠️ PALPITE a confirmar com o dono. R$ 50,00 é o que ele deixaria sair sem senha.
DEFAULT_CEREMONY_SPEND_LIMIT_Q = 5_000
#: Custo de UMA mensagem direta (template de WhatsApp cobrado por mensagem), em centavos.
#: ⚠️ PALPITE a confirmar: o preço real vem do contrato dele com Meta/ManyChat e muda por
#: categoria de template e por país. Fica arredondado para CIMA de propósito — custo
#: superestimado faz o teto de gasto morder antes, nunca depois. Postagem pública não
#: entra nesta conta: não tem custo por pessoa.
DEFAULT_DIRECT_MESSAGE_COST_Q = 7
#: Quantas vezes o limiar de frase+senha para exigir TOTP + duplo controle. Dez preserva
#: a razão 50→500 que a política anterior tinha, agora sem número absoluto no código.
DEFAULT_CEREMONY_DUAL_CONTROL_MULTIPLE = 10
#: Pisos aceitos na leitura do JSON. Zero é permitido em percentual, gasto e custo — e
#: em todos os três zero aperta, nunca afrouxa (o limiar cai no piso em pessoas).
CEREMONY_RECIPIENT_FLOOR_MINIMUM = 1
CEREMONY_DUAL_CONTROL_MULTIPLE_MINIMUM = 1


@dataclass(frozen=True, slots=True)
class CeremonyThreshold:
    """O limiar resolvido, em PESSOAS, e a conta que o produziu.

    ``typed`` é a partir de quantos destinatários o disparo pede frase digitada + senha;
    ``dual_control``, a partir de quantos pede TOTP + segunda pessoa. Os demais campos
    existem para que o Admin mostre a conta ao gestor em vez de um número mágico.
    """

    typed: int
    dual_control: int
    base_size: int
    from_percent: int
    from_spend: int | None
    binding: str  # "percent" | "spend" | "floor"


@dataclass(frozen=True)
class MarketingPolicy:
    """Política de Marketing resolvida (padrões ← ``Shop.defaults["marketing"]``)."""

    whatsapp_minimum_audience: int = DEFAULT_WHATSAPP_MINIMUM_AUDIENCE
    ceremony_audience_percent: Decimal = DEFAULT_CEREMONY_AUDIENCE_PERCENT
    ceremony_recipient_floor: int = DEFAULT_CEREMONY_RECIPIENT_FLOOR
    ceremony_spend_limit_q: int = DEFAULT_CEREMONY_SPEND_LIMIT_Q
    direct_message_cost_q: int = DEFAULT_DIRECT_MESSAGE_COST_Q
    ceremony_dual_control_multiple: int = DEFAULT_CEREMONY_DUAL_CONTROL_MULTIPLE

    @classmethod
    def from_defaults(cls, defaults: dict | None) -> MarketingPolicy:
        """Constrói a partir de ``Shop.defaults`` (chave ausente → padrão)."""
        block: dict = {}
        if isinstance(defaults, dict) and isinstance(defaults.get("marketing"), dict):
            block = defaults["marketing"]
        return cls(
            whatsapp_minimum_audience=_coerce_minimum_audience(
                block.get("whatsapp_minimum_audience")
            ),
            ceremony_audience_percent=_coerce_percent(
                block.get("ceremony_audience_percent")
            ),
            ceremony_recipient_floor=_coerce_int(
                block.get("ceremony_recipient_floor"),
                key="ceremony_recipient_floor",
                minimum=CEREMONY_RECIPIENT_FLOOR_MINIMUM,
                default=DEFAULT_CEREMONY_RECIPIENT_FLOOR,
            ),
            ceremony_spend_limit_q=_coerce_int(
                block.get("ceremony_spend_limit_q"),
                key="ceremony_spend_limit_q",
                minimum=0,
                default=DEFAULT_CEREMONY_SPEND_LIMIT_Q,
            ),
            direct_message_cost_q=_coerce_int(
                block.get("direct_message_cost_q"),
                key="direct_message_cost_q",
                minimum=0,
                default=DEFAULT_DIRECT_MESSAGE_COST_Q,
            ),
            ceremony_dual_control_multiple=_coerce_int(
                block.get("ceremony_dual_control_multiple"),
                key="ceremony_dual_control_multiple",
                minimum=CEREMONY_DUAL_CONTROL_MULTIPLE_MINIMUM,
                default=DEFAULT_CEREMONY_DUAL_CONTROL_MULTIPLE,
            ),
        )

    def ceremony_threshold(self, base_size: int) -> CeremonyThreshold:
        """Quantas pessoas até a cerimônia forte, dada a base de clientes.

        Duas contas, e vale **a que chegar primeiro** (a menor):

        - **proporção** — ``ceil(percentual × base)``. Um número absoluto só está certo
          para um tamanho de base: com 200 clientes, 50 é alto demais; com 20.000, baixo.
        - **gasto** — quantas mensagens cabem no teto de gasto, ao custo por mensagem.

        E um **piso**, que é a resposta quando a base é pequena, desconhecida ou zero.
        Ele existe para que o cálculo falhe FECHADO: base vazia não abre a porta, cai no
        piso e pede cerimônia mais cedo. Não há divisão por base em lugar nenhum.
        """
        safe_base = max(int(base_size), 0)
        from_percent = int(
            ceil((self.ceremony_audience_percent * safe_base) / Decimal(100))
        )
        from_spend = (
            self.ceremony_spend_limit_q // self.direct_message_cost_q
            if self.direct_message_cost_q > 0
            else None
        )
        first = from_percent if from_spend is None else min(from_percent, from_spend)
        typed = max(self.ceremony_recipient_floor, first)
        if first < self.ceremony_recipient_floor:
            binding = "floor"
        elif from_spend is not None and from_spend < from_percent:
            binding = "spend"
        else:
            binding = "percent"
        return CeremonyThreshold(
            typed=typed,
            dual_control=typed * self.ceremony_dual_control_multiple,
            base_size=safe_base,
            from_percent=from_percent,
            from_spend=from_spend,
            binding=binding,
        )

    def estimated_cost_q(self, recipients: int) -> int:
        """Gasto estimado de um disparo de mensagem direta, em centavos.

        Só mensagem custa. Postagem pública é mural: um post é um post, alcance não é
        fatura.
        """
        return max(int(recipients), 0) * self.direct_message_cost_q


def _coerce_minimum_audience(raw) -> int:
    # O Admin só grava inteiro >= 1; valor fora disso veio de edição crua do JSON. Cair
    # no padrão mantém a aprovação funcionando, mas grita: é uma POLÍTICA que ninguém
    # decidiu, e em silêncio o gestor veria um número e a aprovação obedeceria outro.
    if raw is None:
        return DEFAULT_WHATSAPP_MINIMUM_AUDIENCE
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < WHATSAPP_MINIMUM_AUDIENCE_FLOOR:
        logger.warning(
            "marketing_policy.whatsapp_minimum_audience_invalid type=%s",
            type(raw).__name__,
        )
        return DEFAULT_WHATSAPP_MINIMUM_AUDIENCE
    return raw


def _coerce_int(raw, *, key: str, minimum: int, default: int) -> int:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < minimum:
        logger.warning("marketing_policy.%s_invalid type=%s", key, type(raw).__name__)
        return default
    return raw


def _coerce_percent(raw) -> Decimal:
    # Guardado como string no JSON (mesmo padrão de ``production_config``): Decimal não
    # é serializável e float não representa 2,5% sem sobra.
    if raw is None:
        return DEFAULT_CEREMONY_AUDIENCE_PERCENT
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        logger.warning(
            "marketing_policy.ceremony_audience_percent_invalid type=%s",
            type(raw).__name__,
        )
        return DEFAULT_CEREMONY_AUDIENCE_PERCENT
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        logger.warning("marketing_policy.ceremony_audience_percent_unparseable")
        return DEFAULT_CEREMONY_AUDIENCE_PERCENT
    if value < 0 or value > 100:
        logger.warning("marketing_policy.ceremony_audience_percent_out_of_range")
        return DEFAULT_CEREMONY_AUDIENCE_PERCENT
    return value


def resolve_marketing_policy() -> MarketingPolicy:
    """Política de Marketing efetiva, a partir do ``Shop`` singleton."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    defaults = getattr(shop, "defaults", None) if shop else None
    return MarketingPolicy.from_defaults(defaults)
