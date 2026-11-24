"""O que o turno sabe enquanto decide e responde: necessidades, fatos e a situação comum."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from conversational_commerce.authority import Offer
from conversational_commerce.catalog import Situation
from conversational_commerce.contracts import ActionReceipt, Commitment, DeploymentProfile, IdentityEvidence
from conversational_commerce.contracts.common import Fact

from .acts import CHANGE_ACTS, QUERY_ACTS

# Recusas no ponto de efeito (ou da confirmação) que pedem termos novos e confirmação nova.
RETERM = frozenset({"terms_changed", "terms_expired", "grant_expired", "confirmation_before_terms",
                    "revision_conflict"})


#: Os atos que mudam o carrinho de forma material (a sacola, o recebimento, o pagamento): v2 4.7, propriedade 2.
MATERIAL_ACTS = frozenset({"change_quantity", "choose_fulfillment", "choose_payment", "give_address"})


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


@dataclass(frozen=True, slots=True)
class Subject:
    """Quem fala, como o adaptador o resolve a partir do contexto confiável, nunca do texto.

    ``cart_ref``: o carrinho do sujeito no sistema de registro. Sem ele, nenhuma
    mudança de carrinho nem cotação é proposta (a ação fica inelegível).
    """

    subject_ref: str | None = None
    identity_evidence: tuple[IdentityEvidence, ...] = ()
    cart_ref: str | None = None


@dataclass(frozen=True, slots=True)
class EffectPlan:
    """O que um movimento de efeito pede: a ação, o alvo, os parâmetros e a base da concessão."""

    action: str
    target: str
    parameters: Mapping[str, Any]
    expected_versions: Mapping[str, int]
    basis: Literal["confirmation", "line"]


@dataclass(frozen=True, slots=True)
class CommitmentPlan:
    """O que um movimento de compromisso pede: promessa ou caso, a operação da equipe e a janela do prazo.

    ``operation``: ``ask`` (perguntar à equipe, devolve um tíquete) ou
    ``open_or_update`` (abrir o caso na equipe). ``handoff``: a posse do episódio
    sai da automação (``handoff_requested``).
    """

    type: Literal["promise", "case"]
    obligation: str
    criterion: str
    operation: Literal["ask", "open_or_update"]
    window: Literal["respond", "accept"]
    question: str | None = None
    problem_code: str | None = None
    requested_resolution: str | None = None
    handoff: bool = False


def _without_required(need: NeedSpec) -> bool:
    """O ato tem campo obrigatório (``acts.REQUIRED_FIELDS``) e nenhuma leitura o traz."""
    from .acts import REQUIRED_FIELDS

    field = REQUIRED_FIELDS.get(need.act)
    return field is not None and not any(dict(reading).get(field) for reading in need.readings)


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
    event_assurance: str = "provider_claimed"
    subject: Subject = field(default_factory=Subject)
    # Os termos apresentados, se a pergunta que pede a confirmação deles está no ar nesta época.
    offer: Offer | None = None
    # O fechamento pediu uma condição obrigatória no turno anterior (``present_terms.needs_*``): a resposta
    # que muda o carrinho volta aos termos, sem o cliente repetir "pode fechar".
    closing: bool = False
    # A referência protegida do conteúdo do evento (spec 01): o endereço se lê por ela, nunca pelo texto.
    content_ref: str | None = None
    # A pergunta da condição de sim ou não que o fechamento fez (``turn.CONDITION_KEY``): a pergunta, o código e a
    # opção oferecida. Só deste carrinho e desta época.
    condition_question: dict | None = None
    # Algum movimento de efeito foi escolhido neste turno (executado ou não, inclusive em sombra).
    effect_chosen: bool = False
    # Necessidade que responde à oferta → por que a confirmação não autoriza (``None``: autoriza).
    confirmation_problems: dict[str, str | None] = field(default_factory=dict)
    # Termos cotados neste turno, por alvo.
    terms: dict[str, Any] = field(default_factory=dict)
    # O que aconteceu no ponto de efeito, por necessidade.
    receipts: dict[str, ActionReceipt] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)
    commitments: dict[str, Commitment] = field(default_factory=dict)
    # Necessidade → o compromisso que a casa assumiu por ela neste turno (F9).
    commitment_of: dict[str, str] = field(default_factory=dict)
    # Necessidade → o compromisso aberto sobre o qual se dá notícia (espera, prazo vencido).
    waiting: dict[str, str] = field(default_factory=dict)
    # Compromisso → a fila recebeu (``True``) ou recusou (``False``) o pedido.
    routed: dict[str, bool] = field(default_factory=dict)
    # Contexto comercial (F10): o item que atende a necessidade declarada, por necessidade, e o que trava ofertas.
    recommendations: dict[str, str] = field(default_factory=dict)
    declined_offers: bool = False
    open_problem: bool = False
    overdue_commitment: bool = False
    friction: str = "unknown"

    def fact_keys_for(self, need: NeedSpec) -> tuple[str, ...]:
        if need.act == "ask_hours":
            return ("hours",)
        return tuple(f"item.{reading['item']}" for reading in need.readings if reading.get("item"))

    def answers_offer(self, need: NeedSpec) -> bool:
        """O "sim" desta necessidade é a resposta à pergunta que pede a confirmação dos termos."""
        return (self.offer is not None and need.act == "affirm"
                and need.answers_question == self.offer.question_id)

    def declines_offer(self, need: NeedSpec) -> bool:
        """O "não" desta necessidade responde à pergunta dos termos ("deixa pra lá")."""
        return (self.offer is not None and need.act == "deny"
                and need.answers_question == self.offer.question_id)

    def declines_terms(self, need: NeedSpec) -> bool:
        """O "não" aos termos no ar, ou ao fechamento que pergunta por uma condição ("deixa pra lá").

        O "não" à condição que se responde com sim ou não ("entregamos no endereço do cadastro?") não é
        desistir: é recusar aquela opção, e o fechamento segue (``declines_condition``)."""
        return self.declines_offer(need) or (self.offer is None and self.closing and need.act == "deny"
                                             and not self.declines_condition(need) and not self._alternative(need))

    def _alternative(self, need: NeedSpec) -> bool:
        """Outra necessidade da mesma fala muda o carrinho ("não, o do trabalho"): o "não" é correção, não recusa."""
        return any(other.need_id != need.need_id and other.act in CHANGE_ACTS for other in self.needs)

    def _answers_condition_question(self, need: NeedSpec, codes) -> bool:
        """A resposta curta é À pergunta da condição que o fechamento fez (``condition_question``), do código pedido."""
        asked = self.condition_question
        if not asked or need.answers_question != asked.get("question_id"):
            return False
        if codes is not None and asked.get("code") not in codes:
            return False
        return not self._alternative(need)

    def answers_condition(self, need: NeedSpec, codes=None) -> bool:
        """O "sim" à pergunta da condição de sim ou não ("entregamos no endereço do cadastro?"): aceita a opção
        OFERECIDA naquela pergunta (``condition_question["ref"]``), nunca a que o fato diria agora.

        ``codes``: as condições do movimento que pergunta; ``None`` para quem só precisa saber se é resposta."""
        return need.act == "affirm" and self._answers_condition_question(need, codes)

    def declines_condition(self, need: NeedSpec, codes=None) -> bool:
        """O "não" à pergunta da condição: recusa a opção, e o fechamento pergunta o que falta sem ela."""
        return need.act == "deny" and self._answers_condition_question(need, codes)

    def asks_condition_options(self, need: NeedSpec, codes=None) -> bool:
        """O "outro" à pergunta da condição: nem aceita nem recusa a opção; pede as opções que o fato oferece."""
        return need.act == "ask_options" and self._answers_condition_question(need, codes)

    def has_fresh_terms(self) -> bool:
        """Os termos do carrinho cotados neste turno valem (a leitura não falhou)."""
        from conversational_commerce.contracts import Known

        target = self.subject.cart_ref
        return target in self.terms and isinstance(self.facts.get(self.terms_key(target or "")), Known)

    def changed_under_offer(self, need: NeedSpec) -> bool:
        """A mudança desta necessidade já aconteceu (recibo de sucesso) com termos no ar: pede termos novos.

        Vale também com o fechamento esperando uma condição obrigatória (``closing``): a forma de pagamento
        ou o endereço respondidos voltam aos termos, que perguntam a próxima condição ou se apresentam.

        v2 4.7, propriedade 2: mudança material gera novos termos e nova confirmação. O "sim" seguinte
        responde ao documento novo, nunca ao de antes.
        """
        if (self.offer is None and not self.closing) or not self.has_fresh_terms():
            return False
        if need.act in MATERIAL_ACTS or self.answers_condition(need):
            receipt = self.receipts.get(need.need_id)
            return receipt is not None and receipt.status == "success"
        # "Sim, e põe quatro": o "sim" do mesmo turno também pede os termos novos (as duas portas juntas).
        return self.answers_offer(need) and any(
            other.act in MATERIAL_ACTS and getattr(self.receipts.get(other.need_id), "status", "") == "success"
            for other in self.needs)

    def wants_terms(self, need: NeedSpec) -> bool:
        """Esta necessidade pede termos (novos): fechar o pedido, ou confirmação que não valeu mais."""
        if need.act == "place_order" or self.changed_under_offer(need) or self.declines_condition(need) \
                or self.asks_condition_options(need):
            return True
        if not self.answers_offer(need):
            return False
        code = self.refused.get(need.need_id) or self.confirmation_problems.get(need.need_id)
        return code in RETERM

    @staticmethod
    def terms_key(target: str) -> str:
        return f"terms.{target}"

    @staticmethod
    def order_key(ref: str) -> str:
        return f"order.{ref}"

    @staticmethod
    def requirements_key(target: str) -> str:
        return f"requirements.{target}"

    def _requirements(self) -> dict:
        from conversational_commerce.contracts import Known

        fact = self.facts.get(self.requirements_key(self.subject.cart_ref or ""))
        value = fact.value if isinstance(fact, Known) else None
        return dict(value) if hasattr(value, "get") else {}

    def conditions_known(self) -> bool:
        """O fato ``requirements`` do carrinho foi lido e é conhecido. ``Unknown`` (a fonte falhou, o teto
        acabou) ou ausente: não se sabe o que falta, e o fechamento segura (K04)."""
        from conversational_commerce.contracts import Known

        return isinstance(self.facts.get(self.requirements_key(self.subject.cart_ref or "")), Known)

    def offered(self, target: str | None, code: str) -> tuple[str, ...]:
        """As opções que o canal oferece para a condição (``commerce_read.requirements``); vazio sem o fato."""
        return tuple(self._requirements().get(code) or ())

    def missing_conditions(self) -> tuple[str, ...]:
        """As condições obrigatórias dos termos ainda ausentes (forma de pagamento, endereço…)."""
        return tuple(self._requirements().get("missing") or ())

    def situation(self, need: NeedSpec, **fields: Any) -> Situation:
        """A situação comum a toda proposta da necessidade, mais o que o movimento acrescenta."""
        keys = self.fact_keys_for(need)
        base: dict[str, Any] = {
            "now": self.now,
            "channel": self.channel,
            "identity": self.identity,
            "event_assurance": self.event_assurance,
            "reading_count": len(need.readings),
            "request_kind": need.request_kind,
            "missing_required_field": need.act == "unknown" or (need.is_query and need.act != "ask_hours"
                                                                and not keys) or _without_required(need),
            "answer_changes_decision": True,
            "question_open_for_need": need.need_id in self.open_question_needs,
            "requested_move_ineligible": False,
            "reply_only_courtesy": False,
            "facts_needed": {key: self.facts[key] for key in keys if key in self.facts} or None,
            "fact_is_personal": False,
        }
        base.update(fields)
        return Situation(**base)
