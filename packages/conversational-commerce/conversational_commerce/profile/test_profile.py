"""O perfil de teste: liga todos os movimentos, com os padrões do plano (decisão 5).

São valores do perfil **de teste**, não de casa nenhuma. Toda linha está
``approved``, com dono ``framework`` e data fixa, para que o teste seja
determinístico. Um perfil real começa com as linhas que o dono não decidiu
``absent`` e as ações que dependem delas inelegíveis (K39).

Durações em segundos, inteiros (sem float, F1).
"""

from __future__ import annotations

from typing import Any

from conversational_commerce.contracts import DeploymentProfile, Producer

from ..catalog.moves import CATALOG
from ..catalog.preconditions import PERSONAL_INFORM_RULE, UNSOLICITED_LIMIT_LINE

DECIDED_AT = "2026-11-18T00:00:00.000000Z"
CHANNEL = "test-channel"

# (id, valor, por quê). O porquê é o da tabela "Perfil de teste" do plano.
TEST_LINES: tuple[tuple[str, Any, str], ...] = (
    ("episode.inactivity_window_seconds", 24 * 3600, "abre episódio novo depois de um dia parado"),
    ("effect.idempotency_retention_seconds", 7 * 24 * 3600, "cobre a janela de reconciliação com folga (K16)"),
    ("effect.reconciliation_deadline_seconds", 15 * 60, "pendente ou desconhecido não espera para sempre"),
    ("effect.reconciliation_fallback", "person", "vencido o prazo, pessoa"),
    ("staff.accept_within_seconds", 10 * 60, "padrão genérico de verificação com a equipe"),
    ("staff.respond_within_seconds", 30 * 60, "padrão genérico de verificação com a equipe"),
    ("terms.validity_seconds", 30 * 60, "termos velhos pedem cotação nova"),
    ("grant.validity_seconds", 10 * 60, "curta de propósito (K15)"),
    (UNSOLICITED_LIMIT_LINE, 1, "v2 4.1"),
    ("dialogue.open_question_expiry", "event", "vence por evento, não por relógio (v2 6.1)"),
    ("policy.seeded_selection", True, "K32 e K40 no D1, só no perfil de teste (plano 3.5)"),
    ("commerce.cancel_order", True, "liga o cancelamento no perfil de teste"),
    ("commerce.amend_order", True, "liga a alteração no perfil de teste"),
    ("commerce.discount_cap_minor", 500, "teto do desconto no perfil de teste"),
)

# Movimento → linha de que ele depende.
LINE_OF_MOVE = {
    "cancel_order": "commerce.cancel_order",
    "amend_order": "commerce.amend_order",
    "grant_discount": "commerce.discount_cap_minor",
}

# Degrau mínimo por nível no canal de teste (v2 5.6: A0 anônimo; A1 e A2 verificada; A3+ verificada).
MIN_IDENTITY_BY_LEVEL = {
    "A0": "anonymous",
    "A1": "weak_verified",
    "A2": "weak_verified",
    "A3": "weak_verified",
    "A4": "weak_verified",
}


def _action(level: str, *, line_ref: str | None = None) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "authority": level,
        "min_identity": {CHANNEL: MIN_IDENTITY_BY_LEVEL[level]},
        "confirmation": level in ("A3", "A4"),
    }
    if line_ref is not None:
        rule["line_ref"] = line_ref
    return rule


def build_test_profile(*, tenant: str = "tenant-test", **overrides: Any) -> DeploymentProfile:
    """O perfil de teste. ``overrides`` troca campos do perfil inteiro (para os testes de K39)."""
    actions = {move.name: _action(move.authority, line_ref=LINE_OF_MOVE.get(move.name)) for move in CATALOG}
    actions[PERSONAL_INFORM_RULE] = _action("A1")
    fields: dict[str, Any] = {
        "id": "profile-test",
        "tenant": tenant,
        "environment": "test",
        "trace_id": "trace-profile-test",
        "occurred_at": DECIDED_AT,
        "producer": Producer(name="conversational-commerce", version="test-profile"),
        "version": "1",
        "adapters": {
            "commerce": ("search", "read_item", "promise", "quote", "execute", "locate", "reconcile"),
            "channel": ("send", "delivery_status", "request_handoff"),
            "staff": ("ask", "assign", "record_acceptance"),
        },
        "catalog_version": "1",
        "policy_version": "1",
        "actions": actions,
        "lines": tuple(
            {"id": line_id, "setting": {"status": "set", "value": value}, "owner": "framework",
             "decided_at": DECIDED_AT, "state": "approved"}
            for line_id, value, _ in TEST_LINES
        ),
        "fact_sources": {"catalog": {"source": "commerce", "validity_rule": "per_read"}},
        "staff_queue": {"role": "attendant", "nominal_acceptance": True, "accept_within_seconds": 600,
                        "respond_within_seconds": 1800, "after_hours_contingency": "inform_and_wait"},
        "limits": {"max_steps": 6, "max_seconds": 20, "max_queries": 10, "max_model_calls": 0,
                   "max_spend": {"amount_minor": 0, "currency": "XXX"}},
        "privacy": {"purposes": ("service",), "retention_days": {"transcript": 30}, "fields_by_recipient": {}},
    }
    fields.update(overrides)
    return DeploymentProfile(**fields)
