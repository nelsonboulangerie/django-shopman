"""O perfil de implantação da Nice no framework de comércio conversacional (N3).

Monta o ``DeploymentProfile`` do ``conversational_commerce`` com as 21 linhas do plano do
adaptador (seção 2) e a P22 (a validade da concessão, #3380), a partir dos valores que já existem:

- o teto do desconto (P09) do ``ChannelConfig`` do canal da Concierge, pelo mesmo
  acessor que o desconto usa (``discount.max_percent``), nunca de constante;
- o canal, a identidade e o modo do app vivo (P02, P03, P21) do ``service.config()``;
- as regras da casa (P06) de ``house_rules.RULES``, por referência, sem copiar;
- o dono, a data e o estado de cada linha de ``profile_lines``.

Nada aqui lê ``settings`` direto (ADR-042): o perfil passa pelos acessores que a
Concierge já usa. Até o N9 o perfil não governa a Nice, que segue no caminho legado; ele
governa só a decisão em sombra (N5). Linha sem decisão fica ausente, com motivo, e a
ação que depende dela fica inelegível com o código da linha (K39); ``inform_limitation`` e
``handoff`` seguem possíveis.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from conversational_commerce.catalog.preconditions import PERSONAL_INFORM_RULE
from conversational_commerce.contracts import DeploymentProfile, Producer

from . import profile_lines
from .profile_lines import LINES, LineState

PRODUCER = Producer(name="shopman-concierge", version="profile-1")
PROFILE_VERSION = "1"
CATALOG_VERSION = "1"
POLICY_VERSION = "1"
CHANNEL = "whatsapp"
#: Uma leitura pela IA do perfil por turno (P04, D-040): o portão do Jev e a cortesia não contam,
#: e o gasto passa pelo freio da casa (``ai_governor``). Estouro cai para a regra local.
MODEL_CALLS_PER_TURN = 1

# P07: o que a Nice faz hoje. ``verify_with_staff`` entra com o WP-05 da Concierge.
ENABLED_MOVES = ("acknowledge", "inform", "cover_readings", "inform_limitation", "ask_clarification", "handoff")
# P08: o pedido na conversa, em validação até o WP-14 da Concierge.
ORDER_MOVES = ("present_terms", "change_cart", "set_fulfillment", "set_delivery_address", "set_payment",
               "commit_order")
# Movimento → a linha de que depende (P08 a P13).
LINE_OF_MOVE = {
    **dict.fromkeys(ORDER_MOVES, "commerce.order_in_conversation"),
    "grant_discount": "commerce.discount_cap_percent",
    "cancel_order": "commerce.cancel_order",
    "amend_order": "commerce.amend_order",
    "recommend": "commerce.recommend",
}
LEVEL_OF_MOVE = {"acknowledge": "A0", "inform": "A0", "cover_readings": "A0", "inform_limitation": "A0",
                 "ask_clarification": "A0", "handoff": "A0", "present_terms": "A1", "change_cart": "A2",
                 "set_fulfillment": "A2", "set_delivery_address": "A2", "set_payment": "A2",
                 "commit_order": "A3", "cancel_order": "A3", "amend_order": "A3", "grant_discount": "A4",
                 "recommend": "A0"}
# P03: o telefone do WhatsApp é identidade transportada. É com ela que a Nice atende,
# cancela e acrescenta hoje (o cliente é o dono do número); o vínculo verificado
# (``weak_verified``) é o que o fato pessoal pede, e está desligado no alpha.
TRANSPORTED = "transported"


def _concierge_config() -> Mapping[str, Any]:
    from . import service

    return service.config()


def channel_ref() -> str:
    """O canal de venda da Concierge (``Channel.ref``), de onde sai o teto do desconto."""
    return str(_concierge_config().get("channel_ref") or CHANNEL)


def _connection(config: Mapping[str, Any]) -> Mapping[str, Any]:
    for connection in (config.get("connections") or {}).values():
        if isinstance(connection, Mapping) and connection.get("channel") == CHANNEL:
            return connection
    return {}


def _tenant() -> str:
    from django.utils.text import slugify

    from shopman.shop.models import Shop

    shop = Shop.load()
    return slugify(shop.name) if shop is not None and shop.name else "shop"


def discount_cap_percent(ref: str | None = None) -> str:
    """O teto do desconto (P09), em %, como texto decimal: o contrato não aceita float."""
    from .discount import max_percent

    value = max_percent(ref or channel_ref())
    return format(value.normalize(), "f")


def house_rule_ids() -> tuple[str, ...]:
    from .house_rules import RULES

    return tuple(rule.id for rule in RULES)


def values(config: Mapping[str, Any] | None = None, *, environment: str = "shadow") -> dict[str, Any]:
    """O valor de cada linha ``set``, lido de onde já vive. Uma chamada, uma fotografia."""
    from .handler import MAX_LOOPS

    config = config if config is not None else _concierge_config()
    options = _connection(config).get("options") or {}
    observation = options.get("observation") if isinstance(options.get("observation"), Mapping) else {}
    return {
        "deployment.tenant_environment": {"tenant": _tenant(), "environment": environment},
        "channel.capabilities": {
            "channel": CHANNEL, "provider": str(_connection(config).get("provider") or ""),
            "window_hours": 24, "supports_handoff": True,
            "stable_event_identity_verified": options.get("stable_event_identity_verified") is True,
            "delivery_receipts": options.get("delivery_receipts") is True,
        },
        "identity.by_channel": {CHANNEL: TRANSPORTED,
                                "identity_link_enabled": options.get("identity_link_enabled") is True},
        "model.reader": {"first": "local_rules", "gate": "jev", "extraction": "deepseek",
                         "data_class": "redacted", "connection": "customer_text_approved"},
        "model.spend": {"governor": "shopman.shop.ai_governor"},
        "house_rules": list(house_rule_ids()),
        "moves.enabled": list(ENABLED_MOVES),
        "commerce.order_in_conversation": list(ORDER_MOVES),
        "commerce.discount_cap_percent": discount_cap_percent(str(config.get("channel_ref") or CHANNEL)),
        "commerce.cancel_order": "self_service_window",
        "commerce.amend_order": "addition_only",
        "facts.sources": {"price": "offerman", "promise": "stockman", "order": "orderman",
                          "hours": "shop", "allergens": "concierge.allergens"},
        "staff.queue": {"queue": "operator_alert", "nominal_acceptance": True,
                        "accept_within_seconds": profile_lines.STAFF_ACCEPT_WITHIN_SECONDS,
                        "respond_within_seconds": profile_lines.STAFF_RESPOND_WITHIN_SECONDS},
        "turn.limits": {"max_loops": MAX_LOOPS, "claim_seconds": 120},
        "grant.validity_seconds": profile_lines.GRANT_VALIDITY_SECONDS,
        "privacy": {"text": "redacted", "sensitive_leaves": False,
                    "observation_retention_days": str(observation.get("retention_days") or "")},
        "live.mode": {"operation_mode": str(config.get("operation_mode") or "assist"),
                      "read_only": config.get("read_only") is True,
                      "transfer_enabled": config.get("transfer_enabled") is True,
                      "human_return_enabled": config.get("human_return_enabled") is True},
    }


def _line(state: LineState, value: Any) -> dict[str, Any]:
    if state.state == "absent":
        return {"id": state.line_id, "setting": {"status": "absent", "reason": state.absent_reason},
                "owner": state.owner, "decided_at": None, "state": "proposed"}
    return {"id": state.line_id, "setting": {"status": "set", "value": value}, "owner": state.owner,
            "decided_at": state.decided_at, "state": state.state}


def _action(move: str) -> dict[str, Any]:
    level = LEVEL_OF_MOVE[move]
    rule: dict[str, Any] = {"authority": level, "min_identity": {CHANNEL: TRANSPORTED},
                            "confirmation": level in ("A3", "A4")}
    if move in LINE_OF_MOVE:
        rule["line_ref"] = LINE_OF_MOVE[move]
    if move == "grant_discount":
        rule["caps"] = ("commerce.discount_cap_percent",)
    return rule


def build_profile(*, environment: str = "shadow", config: Mapping[str, Any] | None = None,
                  occurred_at: str | None = None) -> DeploymentProfile:
    """O perfil da Nice, validado pelo contrato estrito do framework."""
    from django.utils import timezone

    measured = values(config, environment=environment)
    moves = (*ENABLED_MOVES, *ORDER_MOVES, "grant_discount", "cancel_order", "amend_order", "recommend")
    actions = {move: _action(move) for move in moves}
    # O fato do próprio cliente (pedido, endereço) pede o vínculo verificado, desligado no alpha.
    actions[PERSONAL_INFORM_RULE] = {"authority": "A1", "min_identity": {CHANNEL: "weak_verified"},
                                     "confirmation": False}
    at = occurred_at or timezone.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    tenant = measured["deployment.tenant_environment"]["tenant"]
    return DeploymentProfile(
        id=f"profile-nice-{environment}", tenant=tenant, environment=environment,
        trace_id=f"trace-profile-nice-{environment}", occurred_at=at, producer=PRODUCER,
        version=PROFILE_VERSION,
        adapters={"commerce": ("search", "read_item", "promise", "quote"),
                  "channel": ("normalize", "send", "delivery_status", "request_handoff"),
                  "staff": ()},
        catalog_version=CATALOG_VERSION, policy_version=POLICY_VERSION,
        house_rules_ref="shopman.storefront.concierge.house_rules.RULES",
        actions=actions,
        lines=tuple(_line(state, measured.get(state.line_id)) for state in LINES),
        fact_sources={"price": {"source": "offerman", "validity_rule": "per_turn"},
                      "promise": {"source": "stockman", "validity_rule": "per_turn"},
                      "order": {"source": "orderman", "validity_rule": "per_turn"},
                      "hours": {"source": "shop", "validity_rule": "per_turn"},
                      "allergens": {"source": "concierge.allergens", "validity_rule": "per_turn"}},
        staff_queue={"role": "operator_on_duty", "nominal_acceptance": True,
                     "accept_within_seconds": profile_lines.STAFF_ACCEPT_WITHIN_SECONDS,
                     "respond_within_seconds": profile_lines.STAFF_RESPOND_WITHIN_SECONDS,
                     "after_hours_contingency": "inform_when_team_returns"},
        limits={"max_steps": _max_steps(), "max_seconds": 120, "max_queries": 10, "max_model_calls": MODEL_CALLS_PER_TURN,
                "max_spend": {"amount_minor": 0, "currency": "BRL"}},
        privacy={"purposes": ("service",), "retention_days": _retention(measured), "fields_by_recipient": {}},
    )


def _retention(measured: Mapping[str, Any]) -> dict[str, int]:
    """A retenção da observação, se válida. Inválida, fica fora: a observação não liga
    (``service.observation_policy`` recusa), e desconhecido não vira zero."""
    try:
        days = int(measured["privacy"]["observation_retention_days"])
    except (TypeError, ValueError):
        return {}
    return {"observation": days} if 1 <= days <= 30 else {}


def _max_steps() -> int:
    """O teto de passos do turno do framework: o ``MAX_LOOPS`` do handler (P16)."""
    from .handler import MAX_LOOPS

    return int(MAX_LOOPS)
