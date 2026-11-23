"""O estado das linhas do perfil da Nice: dono, data e estado, revisados em código.

Linha de alçada não se edita em painel (v2 9.1): muda por revisão e teste. O
**valor** de cada linha não mora aqui. Ele é lido de onde já vive (o teto do
desconto no ``ChannelConfig``, o modo do app no ``service.config()``, as regras
em ``house_rules.RULES``), e a montagem fica em ``profile.py``. Aqui só se diz quem
decidiu, quando e se a linha vale para o framework.

Fonte: ``docs/plans/COMERCIO-CONVERSACIONAL-ADAPTADOR-NICE-PLANO.md``, seção 2 (P01 a P21).

Estados do framework: ``approved`` vale; ``validating`` e ``proposed`` não valem; linha
``absent`` não tem valor, e a ação que depende dela fica inelegível com o código da linha
(K39). O plano tem um quinto estado, ``vigente`` (o comportamento existe no código legado e
não governa o framework). No contrato ele vira ``approved`` com o valor medido, e o
``plan_state`` guarda o nome do plano.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ENGINEERING = "engineering"
OWNER = "owner"

# Datas das decisões (início do dia, UTC). A reconferência do plano é de 17/11/2026.
RECHECKED = "2026-11-17T00:00:00.000000Z"
D039 = "2026-11-12T00:00:00.000000Z"  # D-039: freio e teto de gasto
D040 = "2026-11-16T00:00:00.000000Z"  # D-040: leitura por Jev e DeepSeek, só texto redigido
OBS0310 = "2026-10-03T00:00:00.000000Z"  # OBS0310-M, O e P: regras da casa e as três alçadas
DECISION_1_AND_2 = "2026-11-18T00:00:00.000000Z"  # as três alçadas no framework; aceite pelo sino
GRANT_DECIDED = "2026-11-23T00:00:00.000000Z"  # #3380: validade da concessão, decisão da coordenação

#: Quanto tempo uma concessão vale entre a decisão e o efeito (``authority.grants.GRANT_VALIDITY_LINE``).
#: Mecânica de autorização, não negócio: a coordenação decidiu 600 s, o valor do perfil de teste do pacote
#: ("curta de propósito", K15). Sem a linha, nenhuma concessão nasce e o motor não executa efeito.
GRANT_VALIDITY_SECONDS = 600

State = Literal["proposed", "validating", "approved", "absent"]


@dataclass(frozen=True, slots=True)
class LineState:
    plan_id: str
    line_id: str
    owner: str
    state: State
    decided_at: str | None
    source: str
    # Para ``absent``: por que não há valor.
    absent_reason: str | None = None
    plan_state: str | None = None


LINES: tuple[LineState, ...] = (
    LineState("P01", "deployment.tenant_environment", ENGINEERING, "approved", RECHECKED,
              "o Shop singleton; shadow no N5, live só no N9"),
    LineState("P02", "channel.capabilities", ENGINEERING, "approved", RECHECKED,
              "service.config()['connections'], conexão do WhatsApp"),
    LineState("P03", "identity.by_channel", ENGINEERING, "approved", RECHECKED,
              "telefone do WhatsApp transportado; vínculo verificado pela opção identity_link_enabled"),
    LineState("P04", "model.reader", OWNER, "approved", D040, "D-040"),
    LineState("P05", "model.spend", OWNER, "approved", D039, "D-039, item 5: shopman.shop.ai_governor"),
    LineState("P06", "house_rules", OWNER, "approved", OBS0310, "OBS0310-M (#1442): house_rules.RULES"),
    LineState("P07", "moves.enabled", OWNER, "approved", RECHECKED, "comportamento atual da Nice"),
    LineState("P08", "commerce.order_in_conversation", OWNER, "validating", D040,
              "DEV-2026-027; construído nos WP-11 a WP-14 da Concierge"),
    LineState("P09", "commerce.discount_cap_percent", OWNER, "approved", DECISION_1_AND_2,
              "OBS0310-O (#1444): ChannelConfig.pricing.concierge_discount_max_percent"),
    LineState("P10", "commerce.cancel_order", OWNER, "approved", DECISION_1_AND_2,
              "OBS0310-O (#1445): customer_orders.can_cancel"),
    LineState("P11", "commerce.amend_order", OWNER, "approved", DECISION_1_AND_2,
              "OBS0310-P (#1450): order_edit do balcão, só aumento"),
    LineState("P12", "commerce.compensation", OWNER, "absent", None, "Q4",
              absent_reason="nenhuma alçada de compensação: só com pessoa"),
    LineState("P13", "commerce.recommend", OWNER, "absent", None, "v2 15.5",
              absent_reason="a recomendação não existe na Nice: a sombra calcula a candidata, nada sai"),
    LineState("P14", "facts.sources", ENGINEERING, "approved", RECHECKED,
              "Offerman, Stockman, Orderman, Shop e concierge/allergens.py, lidos ao vivo"),
    LineState("P15", "staff.queue", OWNER, "approved", DECISION_1_AND_2,
              "sino do Gestor (OperatorAlert); aceite nominal de quem está com o Gestor aberto"),
    LineState("P16", "turn.limits", ENGINEERING, "approved", RECHECKED,
              "handler.MAX_LOOPS e o claim de 120 s do service"),
    LineState("P17", "privacy", OWNER, "approved", D040, "D-039 e D-040: texto redigido, sensitive nunca sai"),
    LineState("P18", "memory.beyond_episode", OWNER, "absent", None, "Q6",
              absent_reason="só memória declarada, ainda não decidida para a Nice"),
    LineState("P19", "outcomes.window", OWNER, "absent", None, "Q1",
              absent_reason="só telemetria, nenhuma alegação de eficácia"),
    LineState("P20", "policy.seeded_selection", OWNER, "absent", None, "Q8",
              absent_reason="nenhum sorteio de oferta"),
    LineState("P21", "live.mode", OWNER, "approved", RECHECKED, "service.config(): modo do app vivo",
              plan_state="vigente"),
    LineState("P22", "grant.validity_seconds", ENGINEERING, "approved", GRANT_DECIDED,
              "#3380, coordenação em 23/11: 600 s, como o perfil de teste do pacote (K15)"),
)

BY_PLAN_ID: dict[str, LineState] = {line.plan_id: line for line in LINES}
BY_LINE_ID: dict[str, LineState] = {line.line_id: line for line in LINES}

# Prazos da fila humana (P15), decididos pelo dono em 16/11. Ainda não existem no
# ``ChannelConfig``: entram lá com o WP-06 da Concierge, e aí o perfil passa a lê-los
# de lá (issue ficou-de-fora do N3).
STAFF_ACCEPT_WITHIN_SECONDS = 10 * 60
STAFF_RESPOND_WITHIN_SECONDS = 30 * 60
