"""O que o turno sabe enquanto decide e responde: necessidades, fatos e a situação comum."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from conversational_commerce.catalog import Situation
from conversational_commerce.contracts import DeploymentProfile
from conversational_commerce.contracts.common import Fact

from .acts import CHANGE_ACTS, QUERY_ACTS


@dataclass(frozen=True, slots=True)
class NeedSpec:
    need_id: str
    act: str
    # Uma entrada por leitura plausível (a principal primeiro). Cada uma com os campos do ato.
    readings: tuple[Mapping[str, Any], ...] = ({},)
    # A pergunta no ar a que esta necessidade responde, se for resposta.
    answers_question: str | None = None

    @property
    def request_kind(self) -> str:
        return "change" if self.act in CHANGE_ACTS else "query"

    @property
    def is_query(self) -> bool:
        return self.act in QUERY_ACTS


@dataclass
class TurnState:
    now: str
    channel: str
    identity: str
    profile: DeploymentProfile
    needs: tuple[NeedSpec, ...] = ()
    facts: dict[str, Fact] = field(default_factory=dict)
    fact_facets: dict[str, str] = field(default_factory=dict)
    # Necessidades que já têm pergunta no ar (uma por necessidade).
    open_question_needs: frozenset[str] = frozenset()

    def fact_keys_for(self, need: NeedSpec) -> tuple[str, ...]:
        if need.act == "ask_hours":
            return ("hours",)
        return tuple(f"item.{reading['item']}" for reading in need.readings if reading.get("item"))

    def situation(self, need: NeedSpec, **fields: Any) -> Situation:
        """A situação comum a toda proposta da necessidade, mais o que o movimento acrescenta."""
        keys = self.fact_keys_for(need)
        base: dict[str, Any] = {
            "now": self.now,
            "channel": self.channel,
            "identity": self.identity,
            "event_assurance": "provider_claimed",
            "reading_count": len(need.readings),
            "request_kind": need.request_kind,
            "missing_required_field": need.act == "unknown" or (need.is_query and need.act != "ask_hours"
                                                                and not keys),
            "answer_changes_decision": True,
            "question_open_for_need": need.need_id in self.open_question_needs,
            "requested_move_ineligible": False,
            "reply_only_courtesy": False,
            "facts_needed": {key: self.facts[key] for key in keys if key in self.facts} or None,
            "fact_is_personal": False,
        }
        base.update(fields)
        return Situation(**base)
