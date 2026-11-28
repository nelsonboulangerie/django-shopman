"""O catálogo v1: os 19 movimentos, com família, nível e precondições.

Ordem das famílias (v2 4.1), da que vence para a que cede:
``protect_and_fulfill`` > ``resolve`` > ``clarify`` > ``commerce`` > ``follow_up``.
Dentro da família, a ordem do catálogo é o desempate estável (F5).

O catálogo diz o que EXISTE; o perfil diz o que fica LIGADO (plano, [DIVERGE]
da seção 3.2). ``inform_limitation`` e ``handoff`` não dependem do perfil:
informar a limitação e encaminhar seguem possíveis com qualquer linha ausente
(K39). Todo outro movimento passa pelas quatro precondições comuns
(``preconditions.GENERIC``) e pelas suas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .preconditions import GENERIC, SPECIFIC, Precondition

Family = Literal["protect_and_fulfill", "resolve", "clarify", "commerce", "follow_up"]

FAMILIES: tuple[str, ...] = ("protect_and_fulfill", "resolve", "clarify", "commerce", "follow_up")


@dataclass(frozen=True, slots=True)
class Move:
    name: str
    family: Family | None  # None: ``wait`` serve a qualquer família
    authority: str
    specific: tuple[str, ...]
    journeys: tuple[str, ...]
    # O que o movimento cria quando executado (para o F4, F8 e F9).
    creates: str | None = None
    # O perfil não governa: segue possível com qualquer linha ausente (K39).
    always_available: bool = False
    # Exige linha de perfil aprovada, além da entrada em ``actions``.
    requires_line: bool = False

    @property
    def preconditions(self) -> tuple[Precondition, ...]:
        generic = () if self.always_available else GENERIC
        return (*generic, *(SPECIFIC[code] for code in self.specific))

    def family_rank(self) -> int:
        """Posição da família na prioridade; ``wait`` fica por último."""
        return FAMILIES.index(self.family) if self.family else len(FAMILIES)


CATALOG: tuple[Move, ...] = (
    Move("acknowledge", "resolve", "A0", ("only_courtesy",), ("J1",)),
    Move("inform", "resolve", "A0", ("facts_known_and_valid", "personal_fact_identity"), ("J1",)),
    Move("cover_readings", "resolve", "A0", ("two_readings", "request_is_query", "facts_known_and_valid"), ("J2",)),
    Move("inform_limitation", "resolve", "A0", ("requested_action_ineligible",), ("K39",), always_available=True),
    Move("ask_clarification", "clarify", "A0",
         ("clarification_needed", "answer_changes_decision", "one_question_per_need"), ("J2",)),
    Move("verify_with_staff", "resolve", "A0", ("fact_unknown", "staff_owner_possible", "staff_rule_declared"),
         ("J3",), creates="promise"),
    Move("open_case", "protect_and_fulfill", "A0", ("complaint_present", "staff_owner_possible"), ("J5",),
         creates="case"),
    Move("handoff", "protect_and_fulfill", "A0", ("handoff_reason", "staff_rule_declared"), ("J3", "J5"),
         always_available=True),
    Move("wait", None, "A0", ("wait_is_defined",), ("J3",)),
    Move("present_terms", "resolve", "A1", ("commerce_can_quote", "conditions_known"), ("J4",), creates="terms"),
    Move("change_cart", "resolve", "A2", ("stable_event_identity", "absolute_quantity", "change_is_reversible"),
         ("J4",)),
    Move("set_fulfillment", "resolve", "A2",
         ("stable_event_identity", "absolute_fulfillment", "change_is_reversible"), ("J4",)),
    Move("set_payment", "resolve", "A2",
         ("stable_event_identity", "conditions_known", "payment_method_offered", "change_is_reversible"), ("J4",)),
    Move("set_delivery_address", "resolve", "A2",
         ("stable_event_identity", "address_by_reference", "change_is_reversible"), ("J4",)),
    Move("commit_order", "resolve", "A3",
         ("grant_bound_to_current_terms", "confirmation_after_terms", "ownership_epoch_current"), ("J4",)),
    Move("cancel_order", "resolve", "A3", ("within_self_service_window", "confirmation_bound_to_target"), (),
         requires_line=True),
    Move("amend_order", "resolve", "A3", ("addition_only", "confirmation_bound_to_target"), (), requires_line=True),
    Move("grant_discount", "commerce", "A4", ("one_discount_per_order", "no_open_problem"), (), requires_line=True),
    Move("recommend", "commerce", "A0",
         ("explicit_need", "advisor_constraint", "unsolicited_within_limit", "commercial_context_clear",
          "refusal_respected"), ("J6",)),
)

MOVES: dict[str, Move] = {move.name: move for move in CATALOG}
