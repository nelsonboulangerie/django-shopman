"""``Situation``: o que as precondições do catálogo leem.

É a fotografia, já reduzida, de que um movimento precisa para ser julgado: quem
fala, por que canal, com que identidade, e os fatos e sinais que cada
precondição consulta. Quem a monta é a política (F5), a partir do
``ContextSnapshot`` e das portas; o catálogo só a lê.

Todo campo além de ``now``, ``channel`` e ``identity`` é opcional e começa
``None``, que quer dizer **não se sabe**. Precondição que lê um campo ``None``
devolve ``unknown``, e ``unknown`` bloqueia a ação (v2 4.1: desconhecido em
requisito crítico bloqueia a ação, não o sistema). Ninguém preenche ``False``
para "não sei".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from conversational_commerce.contracts.common import (
    CONTRACT_DATACLASS,
    EventAssurance,
    Fact,
    Hash,
    Identifier,
    IdentityAssurance,
    Instant,
    NonNegativeInt,
    Value,
)


@dataclass(**CONTRACT_DATACLASS)
class Situation(Value):
    now: Instant
    channel: Identifier
    identity: IdentityAssurance

    # Evento que pede a ação.
    event_assurance: EventAssurance | None = None
    # A resposta só leva afirmação de cortesia.
    reply_only_courtesy: bool | None = None

    # Fatos de que a resposta depende, pela chave do snapshot.
    facts_needed: Mapping[str, Fact] | None = None
    # Algum desses fatos é do cliente (pedido, endereço): leitura personalizada.
    fact_is_personal: bool | None = None

    # Leituras plausíveis do pedido e o tipo dele.
    reading_count: NonNegativeInt | None = None
    request_kind: Literal["query", "change"] | None = None
    missing_required_field: bool | None = None
    answer_changes_decision: bool | None = None
    question_open_for_need: bool | None = None

    # O cliente pediu uma ação que está inelegível.
    requested_move_ineligible: bool | None = None

    # Equipe e encaminhamento.
    staff_owner_possible: bool | None = None
    complaint: bool | None = None
    handoff_reason: Literal["rule", "risk", "customer_request", "none"] | None = None
    wait_has_condition_owner_deadline: bool | None = None

    # Mudança de sacola.
    quantity_is_absolute: bool | None = None
    change_reversible: bool | None = None

    # Compromisso vinculante.
    current_terms_hash: Hash | None = None
    grant_terms_hash: Hash | None = None
    confirmation_after_terms: bool | None = None
    confirmation_same_subject: bool | None = None
    confirmation_bound_to_target: bool | None = None
    ownership_epoch_current: bool | None = None
    within_self_service_window: bool | None = None
    amendment_addition_only: bool | None = None
    discounts_on_order: NonNegativeInt | None = None

    # Contexto comercial (v2 4.1 e 4.3).
    open_problem: bool | None = None
    need_explicit: bool | None = None
    advisor_constraint_satisfied: bool | None = None
    unsolicited_initiatives_in_episode: NonNegativeInt | None = None
    friction_high: bool | None = None
    overdue_commitment: bool | None = None
    customer_declined_offers: bool | None = None
