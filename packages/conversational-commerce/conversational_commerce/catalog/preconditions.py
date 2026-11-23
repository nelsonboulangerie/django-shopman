"""As precondições do catálogo: funções puras de (situação, perfil, movimento).

Cada precondição tem um código estável, lê campos declarados da ``Situation``
(campo ``None`` → ``unknown``, sem chamar a função) e devolve ``None`` quando
passa ou o código de por que falha. Quatro são comuns a todo movimento que o
perfil governa (``GENERIC``); as demais são do movimento.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from conversational_commerce.contracts import DeploymentProfile, Known, Unknown
from conversational_commerce.profile.codes import IneligibilityCode
from conversational_commerce.profile.lines import read_line

from .levels import AUTOMATION_FORBIDDEN, at_least_identity, requires_confirmation, stricter_authority
from .situation import Situation

if TYPE_CHECKING:
    from .moves import Move

Check = Callable[[Situation, DeploymentProfile, "Move"], str | None]

# Linha do perfil que limita a iniciativa comercial não pedida por episódio (v2 4.1).
UNSOLICITED_LIMIT_LINE = "commerce.unsolicited_initiatives_per_episode"
# Regra do perfil para ``inform`` quando o fato é do cliente (A1).
PERSONAL_INFORM_RULE = "inform.personal"


@dataclass(frozen=True, slots=True)
class Precondition:
    code: str
    description: str
    reads: tuple[str, ...]
    check: Check


# ── comuns: o perfil liga o movimento, e no nível certo ──────────────────────


def _rule(profile: DeploymentProfile, move: Move):
    return profile.actions.get(move.name)


def _profile_enables(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    rule = _rule(profile, move)
    if rule is None:
        return IneligibilityCode.PROFILE_ACTION_ABSENT
    if rule.line_ref is None:
        return IneligibilityCode.PROFILE_LINE_ABSENT if move.requires_line else None
    reading = read_line(profile, rule.line_ref)
    return None if reading.usable else reading.code


def _authority(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    rule = _rule(profile, move)
    if rule is None:
        return IneligibilityCode.PROFILE_ACTION_ABSENT
    if stricter_authority(move.authority, rule.authority) == AUTOMATION_FORBIDDEN:
        return IneligibilityCode.AUTHORITY_FORBIDDEN
    return None


def _confirmation(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    rule = _rule(profile, move)
    if rule is None:
        return IneligibilityCode.PROFILE_ACTION_ABSENT
    level = stricter_authority(move.authority, rule.authority)
    if requires_confirmation(level) and not rule.confirmation:
        return IneligibilityCode.CONFIRMATION_WEAKER_THAN_LEVEL
    return None


def _identity(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    rule = _rule(profile, move)
    if rule is None:
        return IneligibilityCode.PROFILE_ACTION_ABSENT
    required = rule.min_identity.get(situation.channel)
    if required is None:
        return IneligibilityCode.IDENTITY_RULE_ABSENT
    return None if at_least_identity(situation.identity, required) else IneligibilityCode.IDENTITY_INSUFFICIENT


GENERIC: tuple[Precondition, ...] = (
    Precondition("profile_enables_move", "O perfil liga o movimento, e a linha de que ele depende está aprovada",
                 (), _profile_enables),
    Precondition("authority_permitted", "O nível efetivo (catálogo ou perfil, o mais alto) não é A5", (), _authority),
    Precondition("confirmation_matches_level", "A3 ou acima: o perfil exige confirmação", (), _confirmation),
    Precondition("identity_sufficient", "A identidade da conversa alcança o degrau que o perfil pede no canal",
                 ("identity",), _identity),
)


# ── do movimento ─────────────────────────────────────────────────────────────


def _is(field: str, expected: object, reason: str) -> Check:
    def check(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
        return None if getattr(situation, field) == expected else reason

    return check


def _facts_known_and_valid(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    if not situation.facts_needed:
        return "no_fact_to_state"
    for fact in situation.facts_needed.values():
        if isinstance(fact, Unknown):
            return IneligibilityCode.FACT_UNAVAILABLE
        if isinstance(fact, Known) and fact.valid_until is not None and fact.valid_until <= situation.now:
            return IneligibilityCode.FACT_UNAVAILABLE
    return None


def _some_fact_unknown(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    if not situation.facts_needed:
        return "no_fact_to_verify"
    for fact in situation.facts_needed.values():
        if isinstance(fact, Unknown):
            return None
        if fact.valid_until is not None and fact.valid_until <= situation.now:
            return None
    return "all_facts_known"


def _personal_fact_identity(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    if not situation.fact_is_personal:
        return None
    rule = profile.actions.get(PERSONAL_INFORM_RULE)
    if rule is None:
        return IneligibilityCode.PROFILE_ACTION_ABSENT
    required = rule.min_identity.get(situation.channel)
    if required is None:
        return IneligibilityCode.IDENTITY_RULE_ABSENT
    return None if at_least_identity(situation.identity, required) else IneligibilityCode.IDENTITY_INSUFFICIENT


def _two_readings(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return None if situation.reading_count >= 2 else "single_reading"


def _clarification_needed(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    # Campo obrigatório ausente sempre se pergunta; duas leituras só numa mudança (v2 4.2).
    if situation.missing_required_field:
        return None
    if situation.request_kind == "change" and situation.reading_count >= 2:
        return None
    return "clarification_not_needed"


def _answer_changes_decision(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    if situation.missing_required_field:
        return None  # ressalva (i) da v2 4.2: sem cálculo
    return None if situation.answer_changes_decision else "answer_does_not_change_decision"


def _staff_rule_declared(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return None if profile.staff_queue is not None else "staff_queue_absent"


def _handoff_reason(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return "no_handoff_reason" if situation.handoff_reason == "none" else None


def _commerce_can_quote(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return None if "quote" in profile.adapters.get("commerce", ()) else IneligibilityCode.CAPABILITY_MISSING


def _stable_event_identity(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return "event_identity_unstable" if situation.event_assurance == "none" else None


def _grant_bound_to_current_terms(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return None if situation.grant_terms_hash == situation.current_terms_hash else "terms_changed"


def _confirmation_after_terms(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    if not situation.confirmation_after_terms:
        return "confirmation_before_terms"
    if not situation.confirmation_same_subject:
        return "confirmation_from_other_subject"
    return None


def _one_discount_per_order(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    return None if situation.discounts_on_order == 0 else "discount_already_granted"


def _unsolicited_within_limit(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    reading = read_line(profile, UNSOLICITED_LIMIT_LINE)
    if not reading.usable:
        return reading.code
    limit = reading.value
    if isinstance(limit, bool) or not isinstance(limit, int):
        return IneligibilityCode.PROFILE_LINE_ABSENT
    return None if situation.unsolicited_initiatives_in_episode < limit else "unsolicited_limit_reached"


def _commercial_context_clear(situation: Situation, profile: DeploymentProfile, move: Move) -> str | None:
    if situation.open_problem:
        return "open_problem"
    if situation.friction_high:
        return "friction_high"
    if situation.overdue_commitment:
        return "overdue_commitment"
    return None


SPECIFIC: dict[str, Precondition] = {
    precondition.code: precondition
    for precondition in (
        Precondition("only_courtesy", "Só afirmação de cortesia", ("reply_only_courtesy",),
                     _is("reply_only_courtesy", True, "claims_beyond_courtesy")),
        Precondition("facts_known_and_valid", "Toda afirmação tem fato Known e dentro da validade",
                     ("facts_needed",), _facts_known_and_valid),
        Precondition("personal_fact_identity", "Fato do cliente pede o degrau da regra inform.personal",
                     ("fact_is_personal",), _personal_fact_identity),
        Precondition("two_readings", "Há duas leituras plausíveis", ("reading_count",), _two_readings),
        Precondition("request_is_query", "O pedido é consulta, não mudança", ("request_kind",),
                     _is("request_kind", "query", "request_is_change")),
        Precondition("requested_action_ineligible", "A ação pedida está inelegível",
                     ("requested_move_ineligible",),
                     _is("requested_move_ineligible", True, "requested_action_eligible")),
        Precondition("clarification_needed", "Campo obrigatório ausente, ou duas leituras numa mudança",
                     ("missing_required_field", "request_kind", "reading_count"), _clarification_needed),
        Precondition("answer_changes_decision", "A resposta muda o conjunto admissível",
                     ("missing_required_field", "answer_changes_decision"), _answer_changes_decision),
        Precondition("one_question_per_need", "Nenhuma pergunta já no ar para a necessidade",
                     ("question_open_for_need",), _is("question_open_for_need", False, "question_already_open")),
        Precondition("fact_unknown", "Algum fato de que a resposta depende é desconhecido ou venceu",
                     ("facts_needed",), _some_fact_unknown),
        Precondition("staff_owner_possible", "Há dono possível na equipe", ("staff_owner_possible",),
                     _is("staff_owner_possible", True, "no_staff_owner")),
        Precondition("staff_rule_declared", "O perfil declara fila, prazos e contingência", (),
                     _staff_rule_declared),
        Precondition("complaint_present", "Há ato de reclamação", ("complaint",),
                     _is("complaint", True, "no_complaint")),
        Precondition("handoff_reason", "Regra, risco ou pedido do cliente manda encaminhar", ("handoff_reason",),
                     _handoff_reason),
        Precondition("wait_is_defined", "A espera tem condição de retomada, responsável e prazo",
                     ("wait_has_condition_owner_deadline",),
                     _is("wait_has_condition_owner_deadline", True, "wait_undefined")),
        Precondition("commerce_can_quote", "A porta de comércio declara a capacidade quote", (),
                     _commerce_can_quote),
        Precondition("stable_event_identity", "O evento tem identidade estável", ("event_assurance",),
                     _stable_event_identity),
        Precondition("absolute_quantity", "A quantidade pedida é absoluta, não relativa",
                     ("quantity_is_absolute",), _is("quantity_is_absolute", True, "relative_quantity")),
        Precondition("absolute_fulfillment",
                     "Dia, modo, janela e hora do recebimento são absolutos (data ISO, hora HH:MM, modo da lista)",
                     ("fulfillment_is_absolute",),
                     _is("fulfillment_is_absolute", True, "relative_fulfillment")),
        Precondition("payment_method_offered", "A forma de pagamento pedida é uma das que o canal oferece",
                     ("payment_method_offered",),
                     _is("payment_method_offered", True, "payment_method_not_offered")),
        Precondition("change_is_reversible", "A mudança é reversível", ("change_reversible",),
                     _is("change_reversible", True, "change_not_reversible")),
        Precondition("grant_bound_to_current_terms", "A concessão está presa ao hash dos termos vigentes",
                     ("current_terms_hash", "grant_terms_hash"), _grant_bound_to_current_terms),
        Precondition("confirmation_after_terms", "Confirmação posterior aos termos e do mesmo sujeito",
                     ("confirmation_after_terms", "confirmation_same_subject"), _confirmation_after_terms),
        Precondition("ownership_epoch_current", "A época de posse esperada é a vigente",
                     ("ownership_epoch_current",), _is("ownership_epoch_current", True, "authority_revoked")),
        Precondition("within_self_service_window", "Dentro da janela de autoatendimento da porta de comércio",
                     ("within_self_service_window",),
                     _is("within_self_service_window", True, "outside_self_service_window")),
        Precondition("confirmation_bound_to_target", "A confirmação está presa ao pedido e ao novo total",
                     ("confirmation_bound_to_target",),
                     _is("confirmation_bound_to_target", True, "confirmation_required")),
        Precondition("addition_only", "A alteração só acrescenta", ("amendment_addition_only",),
                     _is("amendment_addition_only", True, "amendment_removes")),
        Precondition("one_discount_per_order", "No máximo um desconto por pedido", ("discounts_on_order",),
                     _one_discount_per_order),
        Precondition("no_open_problem", "Nenhum problema material aberto", ("open_problem",),
                     _is("open_problem", False, "open_problem")),
        Precondition("explicit_need", "A necessidade foi declarada pelo cliente", ("need_explicit",),
                     _is("need_explicit", True, "need_not_explicit")),
        Precondition("advisor_constraint", "Restrição de conselheiro satisfeita (v2 4.3)",
                     ("advisor_constraint_satisfied",),
                     _is("advisor_constraint_satisfied", True, "advisor_constraint")),
        Precondition("unsolicited_within_limit", "Iniciativa não pedida dentro do limite do perfil por episódio",
                     ("unsolicited_initiatives_in_episode",), _unsolicited_within_limit),
        Precondition("commercial_context_clear", "Sem problema aberto, atrito alto ou compromisso vencido",
                     ("open_problem", "friction_high", "overdue_commitment"), _commercial_context_clear),
        Precondition("refusal_respected", "O cliente não recusou ofertas", ("customer_declined_offers",),
                     _is("customer_declined_offers", False, "customer_declined_offers")),
    )
}
