"""O turno: os dez passos da v2 5.3 sobre as portas.

1. **Receber.** Grava e deduplica antes de qualquer trabalho; liga ao episódio.
2. **Portão sem modelo.** Cortesia pura não chama modelo. A regra local de risco
   já soma os atos dela aqui.
3. **Entender.** A porta de modelo, se há orçamento e ela responde; senão, regra
   local. Ato fora da lista vira ``unknown`` e a queda é registrada.
4. **Montar o snapshot.** Necessidades, pergunta no ar e fatos lidos ao vivo, com
   teto de passos; o contexto comercial (problema aberto, atrito, compromisso
   vencido, a recusa na memória declarada) e o item que atende a necessidade
   declarada (F10). Nada fica aberto enquanto se chama modelo ou porta: a única
   gravação é a do passo 8.
5. **Decidir.** ``policy.decide`` sobre as propostas dos movimentos registrados.
6. **Autorizar e executar** (F8). Para o movimento de efeito escolhido: a
   concessão (o núcleo emite, nunca o modelo), o comando gravado junto com a
   intenção de execução na caixa de saída (N13), a execução pela guarda do
   ponto de efeito e o recibo. Depois, os compromissos (F9): a promessa ou o
   caso com dono e prazo, e a equipe chamada; sem dono possível, não se promete.
   Recusado no ponto de efeito ou sem dono, decide-se de novo, numa decisão
   nova ligada à primeira (N14).
7. **Dizer e verificar.** Molde preenchido pelo lastro e verificação de saída (F6).
8. **Gravar numa transação:** o episódio novo, os registros do turno e a
   intenção de envio, com comparar e gravar.
9. **Enviar e registrar a exposição.** Em ``shadow``, nada sai e nada se escreve
   nas portas de escrita (K36). Turno revogado por fala nova não envia.
10. **Retomar esperas.** Devolve as esperas vencidas para quem agenda.

O que está no evento é dado, nunca instrução (N23): o texto do cliente só chega
ao modelo por referência protegida, e nada lido de catálogo ou da equipe entra
em pedido de modelo.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from conversational_commerce.authority import (
    Confirmation,
    CoreEffectGuard,
    GrantRefused,
    Offer,
    Revocations,
    build_command,
    confirmation_problem,
    issue_grant,
    issue_line_grant,
)
from conversational_commerce.authority.grants import OFFER_KEY
from conversational_commerce.catalog.levels import identity_rank
from conversational_commerce.contracts import (
    ActionCommand,
    ActionReceipt,
    Alternative,
    AuthorizationGrant,
    Commitment,
    ContextSnapshot,
    DecisionRecord,
    DeploymentProfile,
    Episode,
    ExposureEvent,
    InteractionEvent,
    Known,
    MemoryItem,
    Producer,
    Understanding,
    Unknown,
    Wait,
    seal,
    sha256_hash,
)
from conversational_commerce.contracts.commitment import DeadlineSet
from conversational_commerce.ledger import (
    ESCALATION_LINE,
    CommitmentLedger,
    CommitmentRefused,
    ExposureLedger,
    ReceiptLedger,
    Settled,
    Settler,
    make_commitment,
    staff_deadline,
    staff_owner,
)
from conversational_commerce.ledger.commitments import Entry, window_seconds
from conversational_commerce.memory import MemoryStore
from conversational_commerce.policy import DecisionInput, decide
from conversational_commerce.policy.advisor import adheres_to_declared_need
from conversational_commerce.ports import (
    AdjudicateRequest,
    Budget,
    HandoffRequest,
    InterpretRequest,
    ModelRequest,
    PendingQuestion,
    PortError,
    PreparedMessage,
    ReadingContext,
    RecentTurn,
    StaffQuestion,
    Transition,
    TrustedContext,
    WorkItem,
)
from conversational_commerce.profile import read_line
from conversational_commerce.reply import Composed, Evidence, PartSpec, Template, compose
from conversational_commerce.workflow import (
    EpisodeEvent,
    answer_refers_to,
    answered,
    ask,
    correlate,
    next_state,
    open_episode,
    receive,
    subject_key,
    transition,
)

from .acts import ACTS, ANSWER_ACTS, CHANGE_ACTS, DECLARATION_ACTS, TEST_RULES, LocalRules, only_courtesy, validate
from .budget import TurnBudget
from .format import DEFAULT_FORMATTERS
from .moves import expected_acts, registry, templates, yes_no_conditions
from .moves.ask_clarification import READING_REF
from .state import NeedSpec, Subject, TurnState

PRODUCER = Producer(name="conversational-commerce", version="engine-1")
LOCAL_READER = Producer(name="local-rules", version="1")
FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
INACTIVITY_LINE = "episode.inactivity_window_seconds"
# Memória declarada (F10): o cliente pediu para não receber sugestões.
OFFERS_DECLINED = "offers.declined"

Outcome = Literal["answered", "duplicate", "held", "revoked", "shadow", "superseded"]


@dataclass
class Ports:
    channel: Any
    model: Any
    commerce_read: Any
    commerce_execute: Any
    staff: Any
    store: Any
    clock: Any
    outcomes: Any

    @classmethod
    def from_world(cls, world: Any) -> Ports:
        return cls(**world.ports())


def terms_fact(terms, names: Mapping[str, str]) -> dict[str, Any]:
    """O fato dos termos: o documento canônico selado, menos o destinatário (dado pessoal).

    Os termos apresentados são o documento inteiro (v2 4.7): itens, ajustes, recebimento e condições,
    não só o total. O nome de cada item vem do fato do item (``item.<ref>``), nunca de quem formata.
    """
    def money(value) -> dict[str, Any]:
        return {"price_minor": value.amount_minor, "currency": value.currency}

    fulfillment = terms.fulfillment
    return {
        "terms_id": terms.terms_id,
        "total": money(terms.total),
        "items": [{"ref": item.ref, "quantity": item.quantity.value, "unit": item.quantity.unit,
                   "unit_price": money(item.unit_price), "line_total": money(item.line_total),
                   **({"name": names[item.ref]} if item.ref in names else {})} for item in terms.items],
        "adjustments": [{"code": adj.code, "amount": money(adj.amount)} for adj in terms.adjustments],
        "fulfillment": {key: value for key, value in (("mode", fulfillment.mode),
                                                      ("window_start", fulfillment.window_start),
                                                      ("window_end", fulfillment.window_end)) if value},
        "conditions": {condition.code: condition.value for condition in terms.conditions},
    }


#: A sequência declarada de efeitos A2 reversíveis num turno (spec 08 §5, [DECIDIDO]): o recebimento antes
#: da sacola, para a sacola medir a data combinada. ``commit_order`` (A3) nunca entra nela.
EFFECT_SEQUENCE: tuple[str, ...] = ("set_fulfillment", "set_delivery_address", "change_cart", "set_payment")
#: O fechamento que perguntou por uma condição obrigatória (``present_terms.needs_*``), no estado de diálogo:
#: ``{"cart": <carrinho>, "epoch": <época do episódio>}``. Vale só para o mesmo carrinho e a mesma época
#: (a conversa que mudou de dono não herda o fechamento), e cai com o "não" do cliente.
CLOSING_KEY = "terms_closing"


#: A pergunta da condição de sim ou não que o fechamento fez ("entregamos no endereço do cadastro?"), no estado
#: de diálogo: ``{"question_id", "code", "ref", "cart", "epoch"}``. ``ref`` é a opção OFERECIDA (a que o cliente
#: viu); o "sim" aceita essa, nunca a que o fato diria depois. Cai com o fechamento e com a resposta.
CONDITION_KEY = "terms_condition_question"


def condition_in(dialogue: dict, cart_ref: str | None, epoch: int) -> dict | None:
    """A pergunta da condição no ar, deste carrinho e desta época."""
    value = dialogue.get(CONDITION_KEY)
    if cart_ref is None or not isinstance(value, Mapping) or value.get("cart") != cart_ref \
            or value.get("epoch") != epoch:
        return None
    return dict(value)


#: As últimas falas da conversa, por referência (ADR-051): ``[{"role": "customer", "content_ref": …},
#: {"role": "agent", "template_ids": [...]}, …]``, da mais antiga à mais nova. O teto é do perfil
#: (``limits.reading_context_turns``, em turnos: cada turno são duas falas); sem teto, a chave não existe.
RECENT_KEY = "recent_turns"
#: Os atos que respondem à oferta dos termos ("Posso registrar?"): o sim e o não.
TERMS_OFFER_ACTS = ("affirm", "deny")
#: A leitura que o verificador deixou em dúvida e o agente perguntou "é isso?" (ADR-051): ``{"epoch", "acts"}``.
#: O "sim" do turno seguinte aplica ``acts``; o "não" devolve a pergunta do fechamento; outra fala a descarta.
CONFIRM_KEY = "reading_confirmation"
#: Os atos que mudam de assunto de forma legítima com uma pergunta no ar (a conferência não os julga): mudança
#: material, fechar ou cancelar, recusar, pedir a equipe ou reclamar.
RUPTURE_ACTS = CHANGE_ACTS | {"deny", "request_human", "complain"}
UNRATED = {"status": "unavailable", "reason": "conference"}


def coherence(acts, expected) -> str:
    """A leitura diante da pergunta no ar (ADR-051, peça 2): ``answers`` (algum ato a responde), ``rupture`` (o
    cliente mudou de assunto de forma legítima), ``suspect`` (só pergunta, cortesia ou ``unknown``, nada que a
    responda), ou ``free`` (nenhuma pergunta no ar). Determinística: não custa chamada."""
    names = {act.act for act in acts}
    if not expected:
        return "free"
    if names & set(expected):
        return "answers"
    if names & RUPTURE_ACTS:
        return "rupture"
    return "suspect"


@dataclass(frozen=True, slots=True)
class Conference:
    """O conflito de leitura que vai ao verificador: a classe, as candidatas (a do leitor primeiro) e os atos que
    respondem à pergunta no ar (vazio sem pergunta)."""

    found: str
    candidates: tuple[Alternative, ...]
    expected: frozenset[str]


def plan_conference(acts, alternatives, context: ReadingContext | None) -> Conference | None:
    """O que vai ao verificador (ADR-051): a leitura ``suspect`` diante da pergunta no ar, ou leitores que
    discordam em ato, com ou sem pergunta no ar. ``None``: nada a conferir, a leitura segue."""
    names = {act.act for act in acts}
    expected = frozenset(context.expected_acts) if context is not None and context.pending is not None else frozenset()
    found = coherence(acts, expected)
    differing = [alternative for alternative in alternatives if {act.act for act in alternative.acts} != names]
    if found != "suspect" and not differing:
        return None
    return Conference(found=found + (":disagreement" if differing else ""),
                      candidates=(Alternative(acts=acts, confidence=UNRATED), *differing), expected=expected)


def in_doubt(conference: Conference, *, confirmed_before: bool = False, closing: bool = False) -> dict:
    """O que o turno faz quando o verificador não escolhe (nunca chuta).

    Com pergunta no ar, a candidata que a responde vai à confirmação ("é isso?"); sem candidata que responda, a
    pergunta do fechamento volta. Sem pergunta no ar, a leitura do leitor vai à confirmação.

    ``confirmed_before``: o turno anterior já perguntou "é isso?" e a resposta deu dúvida de novo. A confirmação
    não se repete em seguida (coordenação, 24/11): com o fechamento em curso (``closing``), a pergunta dele volta;
    sem ele, o agente pede para o cliente dizer de outro jeito (``ask_clarification.more``).
    """
    if confirmed_before:
        return {"reask": True} if closing else {"more": True}
    if not conference.expected:
        chosen = conference.candidates[0].acts
    else:
        answering = next((candidate for candidate in conference.candidates
                          if {act.act for act in candidate.acts} & conference.expected), None)
        if answering is None:
            return {"reask": True}
        chosen = tuple(act for act in answering.acts if act.act in conference.expected)
    return {"confirm": {"acts": [{"act": act.act, "fields": dict(act.fields)} for act in chosen]}}


def confirmation_in(dialogue: Mapping[str, Any], epoch: int) -> Mapping[str, Any] | None:
    value = dialogue.get(CONFIRM_KEY)
    return value if isinstance(value, Mapping) and value.get("epoch") == epoch and value.get("acts") else None


def reading_context(dialogue: Mapping[str, Any], cart_ref: str | None, epoch: int,
                    offer: Offer | None) -> ReadingContext:
    """A conversa em volta da fala, para o leitor (ADR-051, peça 1): a pergunta no ar, os atos que respondem a
    ela, o que o fechamento ainda pede e as últimas falas. Só códigos e referências (P17)."""
    pending, expected, open_conditions = None, (), ()
    condition = condition_in(dict(dialogue), cart_ref, epoch)
    confirming = confirmation_in(dialogue, epoch)
    closing = dialogue.get(CLOSING_KEY) if closing_in(dict(dialogue), cart_ref, epoch) else None
    if confirming is not None:
        pending, expected = PendingQuestion(kind="clarification", code="confirm_reading"), TERMS_OFFER_ACTS
    elif condition is not None and condition.get("code"):
        code = str(condition["code"])
        pending = PendingQuestion(kind="condition_yes_no", code=code, options=(str(condition.get("ref", "")),))
        expected = expected_acts(code)
    elif closing is not None and closing.get("code"):
        code = str(closing["code"])
        pending = PendingQuestion(kind="condition", code=code,
                                  options=tuple(str(option) for option in closing.get("options") or ()))
        expected = expected_acts(code)
    elif offer is not None:
        pending, expected = PendingQuestion(kind="terms_offer", code="terms"), TERMS_OFFER_ACTS
    if closing is not None:
        open_conditions = tuple(str(code) for code in closing.get("open") or ())
    recent = tuple(RecentTurn(role=turn["role"], content_ref=turn.get("content_ref"),
                              template_ids=tuple(turn.get("template_ids") or ()))
                   for turn in dialogue.get(RECENT_KEY) or () if isinstance(turn, Mapping))
    return ReadingContext(pending=pending, expected_acts=tuple(expected), open_conditions=open_conditions,
                          recent=recent)


def with_recent(dialogue: Mapping[str, Any], content_ref: str | None, reply: Composed | None,
                turns: int) -> dict[str, Any]:
    """O estado de diálogo com a fala do cliente e a resposta deste turno no fim das recentes (teto em turnos).
    A resposta segurada não foi dita: entra só a fala do cliente."""
    state = dict(dialogue)
    if turns <= 0:
        state.pop(RECENT_KEY, None)
        return state
    recent = [dict(turn) for turn in state.get(RECENT_KEY) or () if isinstance(turn, Mapping)]
    recent.append({"role": "customer", "content_ref": content_ref})
    if reply is not None and reply.text is not None:
        recent.append({"role": "agent", "template_ids": list(reply.template_ids)})
    state[RECENT_KEY] = recent[-2 * turns:]
    return state


def closing_in(dialogue: dict, cart_ref: str | None, epoch: int) -> bool:
    """O fechamento no ar é deste carrinho e desta época."""
    value = dialogue.get(CLOSING_KEY)
    return (cart_ref is not None and isinstance(value, Mapping) and value.get("cart") == cart_ref
            and value.get("epoch") == epoch)
#: Quantas vezes o tick tenta o aviso de um prazo vencido que não saiu (segurado ou falhado) antes de desistir.
NOTIFY_ATTEMPTS = 3
#: As mudanças materiais do carrinho (v2 4.7, propriedade 2): depois de uma delas, os termos de antes não valem.
MATERIAL_CHANGES = frozenset(EFFECT_SEQUENCE)


#: A mudança da sacola com uma pergunta do fechamento no ar (#3488): os termos respondem a necessidade com a
#: próxima pergunta (``present_terms.needs_*``), que não mostra a sacola. Sem a parte do recibo, "na verdade 3"
#: mudava a sacola e ouvia só a pergunta de novo, como se nada tivesse acontecido. Diz o total novo pelos termos
#: cotados de novo; sem eles, só o efeito (o degrau de baixo).
CHANGE_TOTAL_TEMPLATE = "change_cart.done_total"
CHANGE_RECEIPT_TEMPLATE = "change_cart.done_receipt"


def _with_change_receipts(state, chosen, by_need, specs):
    """A parte do recibo da mudança antes da pergunta do fechamento que respondeu por ela."""
    from .moves._effects import known_with

    key = state.terms_key(state.subject.cart_ref) if state.subject.cart_ref else "terms.none"
    out = []
    for candidate, spec in zip(chosen, specs, strict=True):
        need = by_need[candidate.need_id]
        receipt = state.receipts.get(need.need_id)
        if candidate.move == "present_terms" and need.act == "change_quantity" and receipt is not None \
                and receipt.status == "success" and str(spec.template_id).startswith("present_terms.needs_"):
            done = {"done": ("receipt", receipt.command_id)}
            out.append(PartSpec("change_cart", CHANGE_TOTAL_TEMPLATE, {**done, "total": ("fact", key)})
                       if known_with(state, key, "total") else PartSpec("change_cart", CHANGE_RECEIPT_TEMPLATE, done))
        out.append(spec)
    return out


def _distinct(specs):
    """A mesma parte (movimento, molde e lastros iguais) sai uma vez: as linhas do mesmo comando têm uma resposta só."""
    seen, found = set(), []
    for spec in specs:
        key = (spec.move, spec.template_id, tuple(sorted(spec.bindings.items())))
        if key not in seen:
            seen.add(key)
            found.append(spec)
    return found


def default_subject(ctx: TrustedContext, event: InteractionEvent) -> Subject:
    """Sem adaptador: o sujeito do contexto confiável, a identidade que o canal transporta, nenhum carrinho."""
    return Subject(subject_ref=ctx.subject, identity_evidence=tuple(event.identity_evidence))


def strongest_identity(evidence) -> str:
    return max((item.assurance for item in evidence), key=identity_rank, default="anonymous")


@dataclass
class TurnResult:
    outcome: Outcome
    event: InteractionEvent
    episode: Episode | None = None
    understanding: Understanding | None = None
    snapshot: ContextSnapshot | None = None
    decision: DecisionRecord | None = None
    reply: Composed | None = None
    exposure: ExposureEvent | None = None
    # Quedas e tetos: o que caiu para o caminho sem modelo, e por quê.
    fallbacks: tuple[str, ...] = ()
    due_waits: tuple[Wait, ...] = ()
    # Passo 6: o que se autorizou e executou, e todas as decisões do turno (a refeita aponta a anterior).
    grants: tuple[AuthorizationGrant, ...] = ()
    commands: tuple[ActionCommand, ...] = ()
    receipts: tuple[ActionReceipt, ...] = ()
    decisions: tuple[DecisionRecord, ...] = ()

    @property
    def chosen_moves(self) -> list[str]:
        if self.decision is None:
            return []
        return [self.decision.candidates[index].move for index in self.decision.chosen]

    @property
    def text(self) -> str | None:
        return None if self.reply is None else self.reply.text


def text_of(content_ref: str | None) -> str:
    """Resolve a referência do conteúdo. Convenção dos falsos: ``text:<texto>``; o adaptador troca."""
    if content_ref and content_ref.startswith("text:"):
        return content_ref[len("text:"):]
    return ""


def _later(now: str, seconds: int) -> str:
    moment = datetime.strptime(now, FORMAT).replace(tzinfo=UTC) + timedelta(seconds=seconds)
    return moment.strftime(FORMAT)


@dataclass
class Engine:
    ports: Ports
    profile: DeploymentProfile
    rules: LocalRules = TEST_RULES
    formatters: Mapping[str, Callable[[Any], str]] = field(default_factory=lambda: dict(DEFAULT_FORMATTERS))
    # A voz e a língua da casa (spec 06, seção 2): os moldes do adaptador, pelo ``template_id``, no
    # lugar dos genéricos do pacote. Cada um troca a frase e mantém o movimento e os espaços, que é
    # o que a parte montada pelo movimento preenche; o que não trocar fica com o do pacote.
    house_templates: Mapping[str, Template] = field(default_factory=dict)
    # A casa fala SÓ com os próprios moldes: a parte por molde do pacote (o texto neutro, em inglês) segura a
    # mensagem (``template_not_in_voice``), no ar e depois do efeito, onde a sombra não vê (spec 06).
    house_voice_only: bool = False
    resolve_content: Callable[[str | None], str] = text_of
    # O adaptador diz quem fala e qual é o carrinho dele, do contexto confiável (nunca do texto).
    subject_of: Callable[[TrustedContext, InteractionEvent], Subject] = default_subject
    revocations: Revocations = field(default_factory=Revocations)
    ledger: ReceiptLedger = field(default_factory=ReceiptLedger)
    commitments: CommitmentLedger = field(default_factory=CommitmentLedger)
    memory: MemoryStore = field(default_factory=MemoryStore)
    exposures: ExposureLedger = field(default_factory=ExposureLedger)
    # O texto de cada mensagem pronta, pelo ``body_ref`` que o canal recebe (``reply:<plano>``). O
    # ``ReplyPlan`` guarda as partes e o lastro, não o texto; o canal de verdade precisa do texto
    # para enviar, e ele fica só aqui, em memória e só durante o envio, nunca num registro.
    bodies: dict[str, str] = field(default_factory=dict)
    _turns: int = 0

    def __post_init__(self) -> None:
        package = templates()
        for template_id, template in self.house_templates.items():
            base = package.get(template_id)
            if base is None:
                raise TypeError(f"molde da casa sem par no pacote: {template_id}")
            if template.template_id != template_id or template.move != base.move:
                raise TypeError(f"molde da casa {template_id}: o id e o movimento são os do pacote ({base.move})")
            if dict(template.slots) != dict(base.slots):
                raise TypeError(f"molde da casa {template_id}: os espaços (nome, lastro e faceta) são os do pacote")

    def _templates(self) -> dict[str, Template]:
        return {**templates(), **self.house_templates}

    def _voice(self) -> frozenset[str] | None:
        return frozenset(self.house_templates) if self.house_voice_only else None

    # ── envelope ────────────────────────────────────────────────────────────
    def _envelope(self, ctx: TrustedContext, prefix: str, episode_id: str | None, trace_id: str,
                  cause_id: str | None) -> dict[str, Any]:
        return {"id": self.ports.clock.new_id(prefix), "tenant": ctx.tenant, "environment": ctx.environment,
                "trace_id": trace_id, "cause_id": cause_id, "occurred_at": self.ports.clock.now(),
                "producer": PRODUCER, "episode_id": episode_id}

    # ── passo 1 ─────────────────────────────────────────────────────────────
    def _episode_for(self, ctx: TrustedContext, event: InteractionEvent, trace_id: str) -> Episode:
        binding = event.channel_binding
        subject = subject_key(verified_subject=None, channel=binding.channel, conversation_ref=binding.conversation_ref)
        latest = self.ports.store.latest_episode(ctx, subject)
        window = read_line(self.profile, INACTIVITY_LINE)
        inactivity = window.value if window.usable else 0
        decision = correlate(subject=subject, now=self.ports.clock.now(), episodes=[latest] if latest else [],
                             inactivity_seconds=inactivity,
                             open_commitments=self.commitments.open_episodes(ctx.tenant))
        if decision.action == "continue" and latest is not None:
            return latest
        episode = open_episode(record_id=self.ports.clock.new_id("eprec"), episode_id=self.ports.clock.new_id("ep"),
                               tenant=ctx.tenant, environment=ctx.environment, trace_id=trace_id,
                               at=self.ports.clock.now(), producer=PRODUCER, subject=subject)
        return self.ports.store.commit_transition(ctx, Transition(episode=episode, expected_version=0), (episode,), ())

    # ── passos 2 e 3 ────────────────────────────────────────────────────────
    def _understand(self, ctx: TrustedContext, event: InteractionEvent, episode: Episode, trace_id: str,
                    budget: TurnBudget, fallbacks: list[str], context: ReadingContext | None = None) -> Understanding:
        text = self.resolve_content(event.content_ref)
        local = self.rules.read(text)
        risk = self.rules.risk_acts(text)
        understanding: Understanding | None = None
        if only_courtesy(local) and not risk:
            fallbacks.append("gate:courtesy_without_model")
        elif event.content_ref is None:
            fallbacks.append("gate:no_content")
        elif not budget.may_call_model():
            fallbacks.append("model_budget_exhausted")
        else:
            request = InterpretRequest(
                request=ModelRequest(purpose="interpret", data_class="redacted",
                                     budget=Budget(max_calls=budget.max_model_calls - budget.model_calls,
                                                   max_spend=self.profile.limits.max_spend)),
                event_id=event.id, content_ref=event.content_ref, allowed_acts=ACTS, context=context)
            try:
                understanding, consumption = self.ports.model.interpret(ctx, request)
            except PortError as error:
                fallbacks.append(f"model_failed:{error.code.value}")
            else:
                cost = consumption.cost
                budget.record_model_call(cost.amount.amount_minor if getattr(cost, "status", "") == "known" else None)
        if understanding is None:
            understanding = Understanding(
                **self._envelope(ctx, "und", episode.episode_id, trace_id, event.id), event_id=event.id,
                acts=[{"act": act, "fields": {}, "confidence": {"status": "unavailable", "reason": "rule_reader"}}
                      for act in (local or ("unknown",))],
                signals={"friction": "unknown", "risk": "unknown"}, reader=LOCAL_READER)
        # Valida os atos; fora da lista vira unknown. O risco local SOMA, nunca é tirado.
        acts = list(understanding.acts)
        good, refused = validate(act.act for act in acts)
        if refused:
            fallbacks.append("act_outside_list:" + ",".join(refused))
            acts = [a for a in acts if a.act in ACTS] or [dataclasses.replace(acts[0], act="unknown", fields={})]
        present = {a.act for a in acts}
        for act in risk:
            if act not in present:
                acts.append(acts[0].__class__(act=act, fields={},
                                              confidence={"status": "unavailable", "reason": "local_risk_rule"}))
        return dataclasses.replace(understanding, acts=acts, id=self.ports.clock.new_id("und"),
                                   episode_id=episode.episode_id)

    def _confer(self, ctx: TrustedContext, event: InteractionEvent, understanding: Understanding,
                context: ReadingContext | None, dialogue: Mapping[str, Any], epoch: int, budget: TurnBudget,
                fallbacks: list[str]) -> tuple[Understanding, dict | None]:
        """A conferência de coerência (ADR-051, peça 2): a leitura diante da pergunta no ar.

        Devolve a leitura (a escolhida pelo verificador, ou a confirmada pelo "sim") e, quando nada se aplica,
        o que o turno faz no lugar: ``{"confirm": {"acts": [...]}}`` (perguntar "é isso?") ou ``{"reask": True}``
        (devolver a pergunta do fechamento). Desligada pelo perfil (``max_adjudications_per_turn`` zero).
        """
        acts = list(understanding.acts)
        names = {act.act for act in acts}
        confirming = confirmation_in(dialogue, epoch)
        if confirming is not None:
            if "affirm" in names:
                fallbacks.append("conference:confirmed")
                return dataclasses.replace(understanding, acts=[{**dict(act), "confidence": UNRATED}
                                                                for act in confirming["acts"]],
                                           alternatives=()), None
            if "deny" in names:
                fallbacks.append("conference:denied")
                return understanding, {"reask": True}
            # Outra resposta: a confirmação sai do ar, e a fala passa pela conferência como qualquer outra; se der
            # dúvida de novo, o "é isso?" não se repete em seguida.
        if self.profile.limits.max_adjudications_per_turn <= 0 or context is None or event.content_ref is None:
            return understanding, None
        conference = plan_conference(acts, understanding.alternatives, context)
        if conference is None:
            return understanding, None
        fallbacks.append(f"conference:{conference.found}")
        candidates = list(conference.candidates)
        choice = self._adjudicate(ctx, event, context, candidates, budget, fallbacks)
        if choice is not None:
            return dataclasses.replace(understanding, acts=list(candidates[choice].acts), alternatives=()), None
        closing = bool(context.open_conditions) or OFFER_KEY in dialogue
        return understanding, in_doubt(conference, confirmed_before=confirming is not None, closing=closing)

    def _adjudicate(self, ctx: TrustedContext, event: InteractionEvent, context: ReadingContext, candidates: list,
                    budget: TurnBudget, fallbacks: list[str]) -> int | None:
        """O verificador com o contexto escolhe uma candidata; sem porta, sem orçamento, com falha ou na dúvida,
        ``None``: nunca um chute."""
        port = self.ports.model
        if not port.capabilities().supports("adjudicate"):
            fallbacks.append("adjudicate:unsupported")
            return None
        if not budget.may_call_model():
            fallbacks.append("adjudicate:budget")
            return None
        request = AdjudicateRequest(
            request=ModelRequest(purpose="adjudicate", data_class="redacted",
                                 budget=Budget(max_calls=1, max_spend=self.profile.limits.max_spend)),
            event_id=event.id, content_ref=event.content_ref, context=context, candidates=tuple(candidates))
        try:
            adjudication = port.adjudicate(ctx, request)
        except PortError as error:
            fallbacks.append(f"adjudicate_failed:{error.code.value}")
            return None
        cost = adjudication.consumption.cost
        budget.record_model_call(cost.amount.amount_minor if getattr(cost, "status", "") == "known" else None)
        if adjudication.choice is None or adjudication.choice >= len(candidates):
            fallbacks.append("adjudicate:doubt")
            return None
        fallbacks.append(f"adjudicate:chose:{adjudication.choice}")
        return adjudication.choice

    # ── passo 4 ─────────────────────────────────────────────────────────────
    def _needs(self, understanding: Understanding, previous_dialogue: Mapping[str, Any],
               epoch: int) -> tuple[tuple[NeedSpec, ...], str | None]:
        needs, answered_question = [], None
        alternatives = understanding.alternatives
        for index, act in enumerate(understanding.acts):
            need_id = f"n{index + 1}"
            if act.act in ANSWER_ACTS:
                question = answer_refers_to(previous_dialogue, epoch)
                if question is not None:
                    answered_question = question
                needs.append(NeedSpec(need_id, act.act, answers_question=question))
                continue
            readings = [dict(act.fields)]
            for alternative in alternatives:
                for alt_act in alternative.acts:
                    if alt_act.act == act.act and dict(alt_act.fields) != readings[0]:
                        readings.append(dict(alt_act.fields))
            needs.append(NeedSpec(need_id, act.act, readings=tuple(readings)))
        return tuple(needs), answered_question

    def _read_facts(self, ctx: TrustedContext, state: TurnState, budget: TurnBudget) -> None:
        for need in state.needs:
            for key in state.fact_keys_for(need):
                if key in state.facts:
                    continue
                if not budget.take_step(f"read:{key}"):
                    state.facts[key] = Unknown(reason="source_failed")
                    continue
                try:
                    if key == "hours":
                        state.facts[key] = self.ports.clock.business_hours(state.now)
                    else:
                        state.facts[key] = self.ports.commerce_read.read_item(ctx, key.split(".", 1)[1])
                except PortError:
                    state.facts[key] = Unknown(reason="source_failed")

    def _quote(self, ctx: TrustedContext, state: TurnState, budget: TurnBudget, *, refresh: bool = False) -> None:
        """Cota o carrinho quando alguma necessidade pede termos. Cotação é leitura, com passo do teto.

        ``refresh``: depois de uma mudança material no carrinho, os termos de antes não valem (v2 4.7,
        propriedade 2); cota de novo, mesmo que ninguém peça termos, para a resposta mostrar o carrinho.
        """
        target = state.subject.cart_ref
        if target is None:
            return
        if not refresh and (target in state.terms or not any(state.wants_terms(n) for n in state.needs)):
            return
        key = state.terms_key(target)
        if refresh:
            # O documento de antes não vale depois da mudança: sai antes de ler, para que a falha da leitura
            # nunca deixe os termos velhos parecerem os de agora.
            state.terms.pop(target, None)
            state.facts.pop(key, None)
        if not budget.take_step(f"read:{key}"):
            state.facts[key] = Unknown(reason="source_failed")
            return
        try:
            terms = self.ports.commerce_read.quote(ctx, target)
        except PortError:
            state.facts[key] = Unknown(reason="source_failed")
            return
        state.terms[target] = terms
        self._requirements(ctx, state, budget)
        names = self._item_names(ctx, state, budget, terms)
        state.facts[key] = Known(value=terms_fact(terms, names), source="commerce-quote", observed_at=state.now,
                                 valid_until=terms.valid_until, source_version=terms.hash)

    def _requirements(self, ctx: TrustedContext, state: TurnState, budget: TurnBudget) -> None:
        """O que os termos do carrinho ainda exigem (``commerce_read.requirements``), lido com passo do teto."""
        target = state.subject.cart_ref
        if target is None:
            return
        key = state.requirements_key(target)
        state.facts.pop(key, None)
        if not budget.take_step(f"read:{key}"):
            state.facts[key] = Unknown(reason="source_failed")
            return
        try:
            state.facts[key] = self.ports.commerce_read.requirements(ctx, target)
        except PortError:
            state.facts[key] = Unknown(reason="source_failed")

    def _item_names(self, ctx: TrustedContext, state: TurnState, budget: TurnBudget, terms) -> dict[str, str]:
        """O nome de cada item dos termos, pelo fato do item (``item.<ref>``), lido com passo do teto."""
        names: dict[str, str] = {}
        for item in terms.items:
            key = f"item.{item.ref}"
            if key not in state.facts:
                if not budget.take_step(f"read:{key}"):
                    continue
                try:
                    state.facts[key] = self.ports.commerce_read.read_item(ctx, item.ref)
                except PortError:
                    state.facts[key] = Unknown(reason="source_failed")
            fact = state.facts[key]
            value = getattr(fact, "value", None)
            if isinstance(value, Mapping) and value.get("name"):
                names[item.ref] = str(value["name"])
        return names

    def _after_effects(self, ctx: TrustedContext, state: TurnState, event, budget: TurnBudget,
                       effects: dict) -> bool:
        """O que se lê depois do recibo de sucesso, para a resposta dizer o estado de agora.

        - mudança no carrinho: o sujeito de novo (o efeito pode ter criado o carrinho) e termos novos;
        - pedido fechado: o pedido lido pela porta, com o total dele.

        Devolve se o carrinho foi cotado de novo (termos novos neste turno).
        """
        requoted = False
        actions = {command.command_id: command.action for command in effects["commands"]}
        for receipt in effects["receipts"]:
            if receipt.status != "success":
                continue
            action = actions.get(receipt.command_id)
            if action == "change_cart":
                state.subject = self.subject_of(ctx, event)
                self._quote(ctx, state, budget, refresh=True)
                requoted = True
            elif action in ("set_payment", "set_delivery_address", "set_fulfillment"):
                # A condição mudou (o recebimento também é dos termos: o dia e o horário estão no resumo, e o
                # quando é condição para registrar): termos novos.
                self._quote(ctx, state, budget, refresh=True)
                requoted = True
            elif action == "commit_order" and receipt.domain_refs.get("effect"):
                ref = receipt.domain_refs["effect"]
                key = state.order_key(ref)
                if key in state.facts or not budget.take_step(f"read:{key}"):
                    continue
                try:
                    state.facts[key] = self.ports.commerce_read.read_order(ctx, ref)
                except PortError:
                    state.facts[key] = Unknown(reason="source_failed")
        return requoted

    def _confirmation(self, ctx: TrustedContext, event: InteractionEvent, subject: Subject,
                      epoch: int) -> Confirmation:
        return Confirmation(event_id=event.id, event_assurance=event.event_identity.assurance,
                            occurred_at=event.occurred_at, tenant=ctx.tenant, environment=ctx.environment,
                            subject_ref=subject.subject_ref, epoch=epoch,
                            identity_evidence=tuple(subject.identity_evidence))

    def _decide(self, state: TurnState, needs, snapshot: ContextSnapshot, trace_id: str,
                parent: str | None = None) -> DecisionRecord:
        clock = self.ports.clock
        proposals = [proposal for need in needs for module in registry().values()
                     if (proposal := module.propose(state, need)) is not None]
        return decide(DecisionInput(decision_id=clock.new_id("dec"), record_id=clock.new_id("decrec"),
                                    trace_id=trace_id, occurred_at=clock.now(), turn=self._turns,
                                    snapshot=snapshot, profile=self.profile, proposals=tuple(proposals),
                                    parent_decision_id=parent))

    def settler(self, ctx: TrustedContext) -> Settler:
        return Settler(self.ledger, self.ports.commerce_execute, self.ports.clock, self.profile,
                       on_receipt=lambda receipt: self.ports.store.append_receipt(ctx, receipt))

    # ── passo 6 ─────────────────────────────────────────────────────────────
    def _execute(self, ctx: TrustedContext, state: TurnState, decision: DecisionRecord, by_need, event,
                 episode: Episode, trace_id: str, unwritten: list, fallbacks: list[str], effects: dict) -> Episode:
        """Autoriza e executa os movimentos de efeito escolhidos. Devolve o episódio como ficou gravado.

        Um efeito por turno, com uma exceção declarada (spec 08 §5, [DECIDIDO]): a SEQUÊNCIA de efeitos
        A2 reversíveis na ordem de ``EFFECT_SEQUENCE`` (o recebimento antes da sacola). Cada efeito da
        sequência tem a própria concessão, o próprio comando, a intenção gravada antes (N13) e o
        próprio recibo; o recibo terminal de um devolve o episódio a ``active`` antes do próximo, e a
        sequência para no primeiro recibo que não é sucesso (``sequence_stopped``). Fora disso, o segundo
        efeito escolhido fica recusado (``one_effect_per_turn``) e a decisão refeita diz a limitação. A
        mesma mudança levada pelo primeiro (``carried_by``, as várias linhas do carrinho) é o mesmo comando,
        e o recibo dele é o dela.
        """
        moves = registry()
        chosen = [decision.candidates[i] for i in decision.chosen if getattr(moves[decision.candidates[i].move],
                                                                             "EFFECT", False)]
        if not chosen:
            return episode
        state.effect_chosen = True
        if ctx.environment == "shadow":
            fallbacks.extend(f"shadow:effect_not_executed:{c.move}" for c in chosen)
            return episode
        # A levada sem a líder escolhida nunca executa sozinha: o comando é o da líder.
        leads = [c for c in chosen if not dict(c.content).get("carried_by")]
        lead_ids = {c.need_id for c in leads}
        for orphan in [c for c in chosen if dict(c.content).get("carried_by") not in (None, *lead_ids)]:
            state.refused[orphan.need_id] = "carried_without_lead"
        chosen = [c for c in chosen if c.need_id not in state.refused]
        leads = [c for c in leads if c.need_id not in state.refused]
        if not leads:
            return episode

        def carried_by(lead):
            return [c for c in chosen if dict(c.content).get("carried_by") == lead.need_id]

        moves_of_leads = [c.move for c in leads]
        if len(leads) > 1 and all(m in EFFECT_SEQUENCE for m in moves_of_leads) \
                and len(set(moves_of_leads)) == len(moves_of_leads):
            ordered = sorted(leads, key=lambda c: EFFECT_SEQUENCE.index(c.move))
        else:
            ordered = leads[:1]
            for extra in leads[1:]:
                for refused in (extra, *carried_by(extra)):
                    state.refused[refused.need_id] = "one_effect_per_turn"
        for index, lead in enumerate(ordered):
            # O recibo terminal do efeito anterior devolve o episódio a ``active``: uma espera por vez.
            prefix = [("receipt_terminal", None)] if index else []
            episode, receipt = self._effect(ctx, state, decision, lead, carried_by(lead), by_need, event, episode,
                                            trace_id, unwritten, fallbacks, effects, prefix)
            if index:
                effects["walked"] = effects.get("walked", 0) + 1
            if receipt is None or receipt.status != "success":
                for rest in ordered[index + 1:]:
                    for refused in (rest, *carried_by(rest)):
                        state.refused[refused.need_id] = "sequence_stopped"
                break
        return episode

    def _effect(self, ctx: TrustedContext, state: TurnState, decision: DecisionRecord, candidate, carried, by_need,
                event, episode: Episode, trace_id: str, unwritten: list, fallbacks: list[str], effects: dict,
                prefix: list) -> tuple[Episode, ActionReceipt | None]:
        """Um efeito: concessão, comando, a intenção gravada antes (N13), a execução e o recibo."""
        clock, store, moves = self.ports.clock, self.ports.store, registry()
        need, module = by_need[candidate.need_id], moves[candidate.move]
        plan = module.effect(state, need)
        now, epoch = clock.now(), episode.ownership.epoch
        evidence = tuple(state.subject.identity_evidence)
        record = self._envelope(ctx, "grant", episode.episode_id, trace_id, decision.id)
        try:
            if plan.basis == "confirmation":
                grant = issue_grant(record=record, grant_id=clock.new_id("grantid"), offer=state.offer,
                                    confirmation=self._confirmation(ctx, event, state.subject, epoch),
                                    action=plan.action, profile=self.profile, now=now)
            else:
                grant = issue_line_grant(record=record, grant_id=clock.new_id("grantid"),
                                         subject=state.subject.subject_ref or episode.subject or "unknown-subject",
                                         action=plan.action, targets=(plan.target,), identity_evidence=evidence,
                                         profile=self.profile, now=now)
        except GrantRefused as refused:
            state.refused[need.need_id] = refused.code
            fallbacks.append(f"grant_refused:{refused.code}")
            if prefix:
                # O efeito anterior terminou: o episódio volta a ``active`` mesmo sem o próximo.
                episode = store.commit_transition(
                    ctx, Transition(episode=self._walk(episode, event.id, prefix), expected_version=episode.version),
                    (*unwritten,), ())
                unwritten.clear()
                # O recibo anterior andou aqui; o ``_execute`` conta a volta (``walked``) uma vez só.
            return episode, None
        command = build_command(record=self._envelope(ctx, "cmd", episode.episode_id, trace_id, grant.id),
                                command_id=clock.new_id("command"), decision_id=decision.decision_id, grant=grant,
                                parameters=plan.parameters, expected_versions=plan.expected_versions,
                                ownership_epoch=epoch, scope=ctx.tenant, now=now)
        self.ledger.register(command)
        # N13: concessão, comando e intenção de execução gravados juntos, com o episódio esperando o efeito.
        steps = [*prefix, *self._to_active(episode, offer_confirmed=plan.basis == "confirmation")]
        steps.append(("command_handed_off", Wait(condition="the executor returns a receipt", owner="core",
                                                 deadline=command.deadline)))
        work = WorkItem(work_id=f"execute:{command.command_id}", kind="execute",
                        payload={"command_id": command.command_id}, due_at=now)
        episode = store.commit_transition(
            ctx, Transition(episode=self._walk(episode, event.id, steps), expected_version=episode.version),
            (*unwritten, grant, command), (work,))
        unwritten.clear()
        effects["grants"].append(grant)
        effects["commands"].append(command)

        settled = self.settler(ctx).settle(ctx, command, CoreEffectGuard(grant, command, self.revocations))
        effects["settled"].append(settled)
        receipt = settled.receipt
        if receipt is None:
            state.refused[need.need_id] = settled.conflict or "effect_unknown"
            return episode, None
        effects["receipts"].append(receipt)
        state.receipts[need.need_id] = receipt
        for other in carried:
            state.receipts[other.need_id] = receipt  # a mesma mudança: o mesmo recibo
        if receipt.status in ("success", "failure"):
            store.complete_work(ctx, work.work_id)
        if receipt.status == "failure":
            state.refused[need.need_id] = receipt.error.code
            for other in carried:
                state.refused[other.need_id] = receipt.error.code
        elif receipt.status in ("pending", "unknown"):
            commitment = self._reconciliation_commitment(ctx, receipt, trace_id)
            state.commitments[commitment.commitment_id] = commitment
            unwritten.append(commitment)
        return episode, receipt

    def _reconciliation_commitment(self, ctx: TrustedContext, receipt: ActionReceipt, trace_id: str) -> Commitment:
        from .moves._effects import commitment_id

        return Commitment(**self._envelope(ctx, "cmt", receipt.episode_id, trace_id, receipt.id),
                          commitment_id=commitment_id(receipt.command_id), type="promise",
                          obligation="confirm the outcome of the action", owner=receipt.reconciliation.owner,
                          deadline={"status": "set", "at": receipt.reconciliation.deadline,
                                    "rule_ref": "effect.reconciliation_deadline_seconds"},
                          fulfillment_criterion="a terminal receipt for the command", state="open")

    # ── contexto comercial e memória declarada (F10) ────────────────────────
    def _commercial_context(self, ctx: TrustedContext, state: TurnState, episode: Episode,
                            understanding: Understanding, budget: TurnBudget) -> None:
        """O que trava ou permite a recomendação, e o item que atende a necessidade declarada.

        Problema aberto: caso aberto no episódio, ou reclamação nesta mensagem.
        Compromisso vencido: prazo de compromisso aberto do episódio já passado. A
        recusa vem da memória declarada. O item é o primeiro do catálogo que atende
        cada exigência declarada (restrição de conselheiro); o nome e o preço são lidos
        do item, com passo do teto.
        """
        now = state.now
        mine = [e for e in self.commitments.open_entries(ctx.tenant, ctx.environment)
                if e.commitment.episode_id == episode.episode_id]
        state.open_problem = any(e.commitment.type == "case" for e in mine) or any(
            need.act == "complain" for need in state.needs)
        state.overdue_commitment = any(isinstance(e.commitment.deadline, DeadlineSet) and e.commitment.deadline.at
                                       <= now for e in mine)
        state.declined_offers = self.memory.value(episode.subject or "unknown", OFFERS_DECLINED, now) is True
        state.friction = getattr(understanding.signals, "friction", "unknown")
        from .moves.recommend import declared_need

        for need in state.needs:
            declared = declared_need(need) if need.act == "ask_recommendation" else {}
            if not declared or not budget.take_step("read:catalog"):
                continue
            try:
                items = self.ports.commerce_read.search_catalog(ctx, "")
            except PortError:
                continue
            match = next((item for item in items if adheres_to_declared_need(
                declared, {"unit": item.unit, "ref": item.ref})), None)
            if match is None:
                continue
            key = f"item.{match.ref}"
            if key not in state.facts and budget.take_step(f"read:{key}"):
                try:
                    state.facts[key] = self.ports.commerce_read.read_item(ctx, match.ref)
                except PortError:
                    state.facts[key] = Unknown(reason="source_failed")
            if isinstance(state.facts.get(key), Known):
                state.recommendations[need.need_id] = match.ref

    def _remember(self, ctx: TrustedContext, state: TurnState, decision: DecisionRecord, by_need, event,
                  episode: Episode, trace_id: str, unwritten: list) -> None:
        """O que o cliente declarou vira memória declarada, com fonte; a mudança de ideia substitui (K28).

        Em ``shadow`` nada se guarda.
        """
        if ctx.environment == "shadow":
            return
        subject = episode.subject or "unknown"
        for need in state.needs:
            if need.act not in DECLARATION_ACTS:
                continue
            current = self.memory.recall(subject, state.now, OFFERS_DECLINED)
            item = MemoryItem(**self._envelope(ctx, "mem", episode.episode_id, trace_id, event.id),
                              memory_id=self.ports.clock.new_id("memory"), subject_ref=subject,
                              category=OFFERS_DECLINED, value=need.act == "decline_offers",
                              evidence_state="declared", source=event.id, purpose="service",
                              sensitivity="ordinary", supersedes=current[-1].memory_id if current else None)
            unwritten.append(self.memory.declare(item))

    # ── passo 6, compromissos (F9) ──────────────────────────────────────────
    def _hours(self, now: str):
        try:
            return self.ports.clock.business_hours(now)
        except PortError:
            return Unknown(reason="source_failed")

    def _promise(self, ctx: TrustedContext, state: TurnState, decision: DecisionRecord, by_need, event,
                 episode: Episode, trace_id: str, unwritten: list, fallbacks: list[str]) -> list[tuple[str, Wait]]:
        """Assume os compromissos dos movimentos escolhidos e devolve os passos do episódio (encaminhar).

        Sem dono possível, a promessa não é feita (N04): a necessidade fica recusada e
        a decisão refeita diz a limitação. A fila que recusa uma pergunta também
        tira o dono; a que recusa uma transferência deixa o compromisso com a
        automação, monitorado, com a contingência do perfil (K20). Em ``shadow``,
        a equipe não é chamada e nada entra no livro.
        """
        clock, staff, moves = self.ports.clock, self.ports.staff, registry()
        shadow = ctx.environment == "shadow"
        steps: list[tuple[str, Wait]] = []
        for candidate in (decision.candidates[i] for i in decision.chosen):
            module = moves[candidate.move]
            if not getattr(module, "COMMITS", False) or candidate.need_id in state.commitment_of:
                continue
            need = by_need[candidate.need_id]
            plan = module.commitment(state, need)
            now = clock.now()
            deadline = staff_deadline(self.profile, self._hours(now), now, plan.window)
            try:
                commitment = make_commitment(
                    record=self._envelope(ctx, "cmt", episode.episode_id, trace_id, decision.id),
                    commitment_id=clock.new_id("commitment"), type=plan.type, obligation=plan.obligation,
                    owner=staff_owner(self.profile, plan.operation), deadline=deadline, criterion=plan.criterion,
                    problem_code=plan.problem_code, requested_resolution=plan.requested_resolution)
            except CommitmentRefused as refused:
                state.refused[need.need_id] = refused.code
                fallbacks.append(f"commitment_refused:{refused.code}")
                continue
            ticket, routed = None, True
            if shadow:
                fallbacks.append(f"shadow:staff_not_called:{candidate.move}")
            else:
                respond_by = deadline.at if isinstance(deadline, DeadlineSet) else \
                    _later(now, window_seconds(self.profile, plan.window))
                try:
                    if plan.operation == "ask":
                        ticket = staff.ask(ctx, StaffQuestion(episode_id=episode.episode_id, question=plan.question,
                                                              respond_by=respond_by))
                        routed = ticket.state != "rejected"
                except PortError as error:
                    state.refused[need.need_id] = f"staff_failed:{error.code.value}"
                    fallbacks.append(f"staff_failed:{error.code.value}")
                    continue
            accept_by = _later(now, window_seconds(self.profile, "accept"))
            if not routed:
                if not plan.handoff:
                    # A fila recusou a pergunta: ninguém vai responder, e a promessa não é feita.
                    state.refused[need.need_id] = "queue_rejected"
                    fallbacks.append("commitment_refused:queue_rejected")
                    continue
                # K20: ninguém assumiu. A automação monitora, com a contingência do perfil; nada afirma aceite.
                commitment = dataclasses.replace(commitment, owner="core", deadline=DeadlineSet(
                    at=accept_by, rule_ref="staff_queue.accept_within_seconds"))
            if not shadow:
                try:
                    staff.open_or_update(ctx, commitment)
                except PortError as error:
                    state.refused[need.need_id] = f"staff_failed:{error.code.value}"
                    fallbacks.append(f"staff_failed:{error.code.value}")
                    continue
                self.commitments.open(commitment, move=candidate.move, need=need, binding=event.channel_binding,
                                      recipient=episode.subject or "unknown", identity=state.identity,
                                      ticket_id=ticket.ticket_id if ticket is not None else None)
                if not routed:
                    self.commitments.note("contingency", commitment.commitment_id, now,
                                          self.profile.staff_queue.after_hours_contingency)
            state.commitments[commitment.commitment_id] = commitment
            state.commitment_of[need.need_id] = commitment.commitment_id
            state.routed[commitment.commitment_id] = routed
            unwritten.append(commitment)
            if plan.handoff:
                steps.append(("handoff_requested", Wait(condition="a person accepts the conversation", owner="queue",
                                                        deadline=accept_by)))
                if not routed:
                    contingency = self.profile.staff_queue.after_hours_contingency
                    steps.append(("handoff_not_accepted", Wait(condition=f"contingency: {contingency}", owner="core",
                                                               deadline=accept_by)))
                elif not shadow:
                    try:
                        self.ports.channel.request_handoff(ctx, HandoffRequest(
                            binding=event.channel_binding, reason="customer_request", requested_at=now))
                    except PortError as error:
                        fallbacks.append(f"channel_handoff_failed:{error.code.value}")
        return steps

    @staticmethod
    def _to_active(episode: Episode, *, offer_confirmed: bool) -> list[tuple[str, Wait | None]]:
        if episode.state == "waiting_input":
            return [("evidence_arrived", None)]
        if episode.state == "waiting_authorization":
            return [("grant_valid" if offer_confirmed else "authorization_invalidated", None)]
        return []

    def _walk(self, episode: Episode, cause_id: str, steps) -> Episode:
        """Os passos da máquina numa gravação só: a versão sobe uma vez por gravação."""
        now = self.ports.clock.now()
        record_id = self.ports.clock.new_id("eprec")
        current = episode
        for kind, wait, *holder in steps:
            current = transition(current, EpisodeEvent(kind=kind, at=now, cause_id=cause_id, wait=wait,
                                                       holder_ref=holder[0] if holder else None),
                                 expected_version=current.version, record_id=record_id)
        return dataclasses.replace(current, version=episode.version + 1)

    # ── o turno ─────────────────────────────────────────────────────────────
    def turn(self, ctx: TrustedContext, raw: Mapping[str, Any], *,
             interrupted: Callable[[], bool] | None = None) -> TurnResult:
        clock, store = self.ports.clock, self.ports.store
        received = receive(ctx, raw, channel=self.ports.channel, store=store, clock=clock)
        event = received.event
        if not received.created:
            return TurnResult("duplicate", event)
        self._turns += 1
        trace_id = clock.new_id("trace")
        fallbacks: list[str] = []
        budget = TurnBudget.from_profile(self.profile)
        shadow = ctx.environment == "shadow"

        episode = self._episode_for(ctx, event, trace_id)
        previous = store.latest_record(ctx, episode.episode_id, ContextSnapshot.SCHEMA)
        previous_dialogue = dict(previous.dialogue_state) if previous is not None else {}
        epoch = episode.ownership.epoch
        subject = self.subject_of(ctx, event)
        offer = Offer.from_dialogue(previous_dialogue)
        if offer is not None and answer_refers_to(previous_dialogue, epoch) != offer.question_id:
            offer = None  # a pergunta dos termos não está no ar nesta época: nenhum "sim" se liga a ela

        context = reading_context(previous_dialogue, subject.cart_ref, epoch, offer)
        understanding = self._understand(ctx, event, episode, trace_id, budget, fallbacks, context)
        understanding, conference = self._confer(ctx, event, understanding, context, previous_dialogue, epoch,
                                                 budget, fallbacks)
        needs, answered_question = self._needs(understanding, previous_dialogue, epoch)
        if conference is not None:
            # A conferência não aplicou leitura nenhuma: o turno só pergunta "é isso?", ou devolve a pergunta do
            # fechamento pelos termos (a mesma frase da casa, que pede o que ainda falta).
            if "confirm" in conference:
                needs = (NeedSpec("n1", "unknown", confirm=conference["confirm"]),)
            elif "more" in conference:
                needs = (NeedSpec("n1", "unknown"),)  # "pode me dizer de outro jeito?"
            else:
                needs = (NeedSpec("n1", "place_order"),)
            answered_question = answer_refers_to(previous_dialogue, epoch)
        state = TurnState(now=clock.now(), channel=event.channel_binding.channel,
                          identity=strongest_identity(subject.identity_evidence), profile=self.profile,
                          needs=needs, event_assurance=event.event_identity.assurance, subject=subject, offer=offer,
                          closing=closing_in(previous_dialogue, subject.cart_ref, epoch),
                          content_ref=event.content_ref)
        if state.closing:
            state.condition_question = condition_in(previous_dialogue, subject.cart_ref, epoch)
        for need in needs:
            if state.answers_offer(need):
                state.confirmation_problems[need.need_id] = confirmation_problem(
                    offer, self._confirmation(ctx, event, subject, epoch), state.now)
        self._read_facts(ctx, state, budget)
        self._commercial_context(ctx, state, episode, understanding, budget)
        self._quote(ctx, state, budget)
        if any(need.act == "choose_payment" for need in needs) and state.requirements_key(
                state.subject.cart_ref or "") not in state.facts:
            self._requirements(ctx, state, budget)  # a forma pedida confere com as opções do canal
        dialogue = answered(previous_dialogue) if answered_question else previous_dialogue
        answered_offer = offer is not None and answered_question == offer.question_id
        if answered_offer:
            dialogue.pop(OFFER_KEY, None)
        if CLOSING_KEY in dialogue and (not state.closing or any(state.declines_terms(n) for n in needs)):
            # O fechamento de outro carrinho ou de outra época não vale; o "não" do cliente o encerra.
            dialogue = {key: value for key, value in dialogue.items() if key not in (CLOSING_KEY, CONDITION_KEY)}
        if CONDITION_KEY in dialogue and (state.condition_question is None or answered_question == (
                state.condition_question or {}).get("question_id")):
            # A pergunta da condição foi respondida (ou não vale mais): sai do ar.
            dialogue = {key: value for key, value in dialogue.items() if key != CONDITION_KEY}

        snapshot = self._snapshot(ctx, episode, trace_id, event.id, state, dialogue)
        decision = self._decide(state, needs, snapshot, trace_id)
        decisions, snapshots = [decision], [snapshot]
        by_need = {need.need_id: need for need in needs}

        # Passo 6: autorizar e executar. Recusado no ponto de efeito, decide-se de novo, ligado à anterior.
        unwritten: list = [event, understanding, snapshot, decision]
        effects: dict[str, list] = {"grants": [], "commands": [], "receipts": [], "settled": []}
        episode = self._execute(ctx, state, decision, by_need, event, episode, trace_id, unwritten, fallbacks,
                                effects)
        promised = self._promise(ctx, state, decision, by_need, event, episode, trace_id, unwritten, fallbacks)
        self._remember(ctx, state, decision, by_need, event, episode, trace_id, unwritten)
        requoted = self._after_effects(ctx, state, event, budget, effects)
        if offer is not None and any(r.status == "success" for r in effects["receipts"]
                                     if r.command_id in {c.command_id for c in effects["commands"]
                                                         if c.action in MATERIAL_CHANGES}):
            # O carrinho mudou: a pergunta dos termos de antes sai do ar (o "sim" seguinte nunca a confirma).
            # Se os termos novos forem apresentados neste turno, a pergunta nova a substitui.
            dialogue = dict(dialogue)
            dialogue.pop(OFFER_KEY, None)
        # Termos apresentados no mesmo turno de uma mudança: a decisão que os apresenta é refeita sobre
        # os termos novos, ligada à anterior (N14), para a decisão gravada e a pergunta no ar citarem o
        # MESMO documento.
        presents = any(decision.candidates[i].move == "present_terms" for i in decision.chosen)
        # A mudança feita com termos no ar pede termos novos (v2 4.7, propriedade 2): a decisão refeita
        # apresenta o documento novo para a confirmação nova.
        changed_under_offer = requoted and any(state.changed_under_offer(need) for need in needs)
        if state.refused or (requoted and presents) or changed_under_offer:
            self._quote(ctx, state, budget)
            snapshot = self._snapshot(ctx, episode, trace_id, decision.id, state, dialogue)
            decision = self._decide(state, needs, snapshot, trace_id, parent=decision.decision_id)
            decisions.append(decision)
            snapshots.append(snapshot)
            unwritten.extend((snapshot, decision))
        decision_id = decision.decision_id
        chosen = [decision.candidates[i] for i in decision.chosen]
        moves = registry()

        # Passo 7: dizer e verificar.
        specs = _distinct(_with_change_receipts(state, chosen, by_need,
                                                [moves[c.move].reply(state, by_need[c.need_id]) for c in chosen]))
        reply = None
        if specs:
            receipts = {receipt.command_id: receipt for receipt in state.receipts.values()}
            reply = compose(specs=specs, templates=self._templates(), formatters=self.formatters,
                            voice=self._voice(),
                            evidence=Evidence(now=state.now, facts=state.facts, fact_facets=state.fact_facets,
                                              receipts=receipts, commitments=state.commitments,
                                              readings={READING_REF.format(need_id=need.need_id): need.confirm
                                                        for need in needs if need.confirm is not None}),
                            decision_id=decision_id,
                            record=self._envelope(ctx, "reply", episode.episode_id, trace_id, decision.id))
        held = reply is None or reply.verification.result == "hold"

        # Estado do episódio, pergunta no ar e os termos que esperam confirmação.
        asked = next((c for c in chosen if c.move == "ask_clarification"), None)
        presented = next((c for c in chosen if c.move == "present_terms"), None)
        terms_wait = None
        if asked is not None:
            dialogue = ask(dialogue, question_id=clock.new_id("q"), need_id=asked.need_id, epoch=epoch)
        dialogue = {key: value for key, value in dialogue.items() if key != CONFIRM_KEY}
        confirming = next((need for need in needs if need.confirm is not None), None)
        if confirming is not None and asked is not None and asked.need_id == confirming.need_id and not held:
            dialogue[CONFIRM_KEY] = {"epoch": epoch, "acts": [dict(act) for act in confirming.confirm["acts"]]}
        if presented is not None and not held and state.missing_conditions():
            # O fechamento perguntou por uma condição: a resposta que mudar o carrinho volta aos termos.
            code = state.missing_conditions()[0]
            options = state.offered(subject.cart_ref, code)
            # O código perguntado, o que ainda falta e as opções vão junto: o próximo leitor lê a fala na
            # pergunta (ADR-051), não sozinha.
            dialogue = {**dialogue, CLOSING_KEY: {"cart": subject.cart_ref, "epoch": epoch, "code": code,
                                                  "open": list(state.missing_conditions()),
                                                  "options": [str(option) for option in options or ()]}}
            # A lista das opções ("outro") não é pergunta de sim ou não: o "sim" a ela não escolhe a primeira.
            asked_code = any(str(t).startswith(f"present_terms.needs_{code}")
                             and not str(t).endswith(("_declined", "_options")) for t in reply.template_ids)
            if code in yes_no_conditions() and options and asked_code:
                # A pergunta de sim ou não fica no ar, com a opção oferecida: o "sim" responde a ESTA pergunta.
                question_id = clock.new_id("q")
                dialogue = ask(dialogue, question_id=question_id, need_id=presented.need_id, epoch=epoch)
                dialogue[CONDITION_KEY] = {"question_id": question_id, "code": code, "ref": str(options[0]),
                                           "cart": subject.cart_ref, "epoch": epoch}
        if presented is not None and not held and not state.missing_conditions():
            dialogue = {key: value for key, value in dialogue.items() if key not in (CLOSING_KEY, CONDITION_KEY)}
            # Termos que o cliente não viu (mensagem segurada) não esperam confirmação; nem os que ainda pedem
            # uma condição obrigatória (a parte perguntou por ela, e os termos não foram apresentados).
            terms = state.terms[subject.cart_ref]
            question_id = clock.new_id("q")
            dialogue = ask(dialogue, question_id=question_id, need_id=presented.need_id, epoch=epoch)
            dialogue[OFFER_KEY] = Offer(
                terms_hash=terms.hash, terms_id=terms.terms_id, terms_version=terms.version, target=subject.cart_ref,
                subject_ref=terms.recipient.subject_ref, tenant=ctx.tenant, environment=ctx.environment,
                presented_at=clock.now(), valid_until=terms.valid_until, question_id=question_id,
                epoch=epoch).to_json()
            terms_wait = Wait(condition="the customer confirms the terms", owner="customer",
                              deadline=terms.valid_until)
        if self.profile.limits.reading_context_turns or RECENT_KEY in dialogue:
            dialogue = with_recent(dialogue, event.content_ref, reply, self.profile.limits.reading_context_turns)
        after = None
        if dialogue != dict(snapshot.dialogue_state):
            # O estado de diálogo DEPOIS do turno: é o que o próximo turno lê (a pergunta no ar).
            after = seal(dataclasses.replace(snapshot, dialogue_state=dialogue, hash=None, id=clock.new_id("snap"),
                                             cause_id=decision.id))
        post = []
        # Os recibos que a sequência já levou à máquina (o terminal de um, antes do próximo) não andam de novo.
        for receipt in effects["receipts"][effects.get("walked", 0):]:
            if receipt.status in ("success", "failure"):
                post.append(("receipt_terminal", None))
            else:
                post.append(("receipt_open", Wait(condition="reconciliation returns a terminal receipt",
                                                  owner="core", deadline=receipt.reconciliation.deadline)))
        post.extend(promised)
        executed = bool(effects["commands"])
        new_episode = self._next_episode(episode, event, asked is not None, post=post, terms_wait=terms_wait,
                                         invalidate=answered_offer and not executed)

        records = tuple(r for r in (*unwritten, reply.plan if reply else None, after) if r is not None)
        outbox = () if held or shadow else (WorkItem(work_id=f"send:{decision_id}", kind="send",
                                                     payload={"decision_id": decision_id}, due_at=clock.now()),)
        extras = {"grants": tuple(effects["grants"]), "commands": tuple(effects["commands"]),
                  "receipts": tuple(effects["receipts"]), "decisions": tuple(decisions)}
        try:
            committed = store.commit_transition(ctx, Transition(episode=new_episode, expected_version=episode.version),
                                                records, outbox)
        except PortError as conflict:
            if conflict.code.value != "revision_conflict":
                raise
            fallbacks.append("superseded:revision_conflict")
            return TurnResult("superseded", event, episode, understanding, snapshots[0], decision, reply,
                              fallbacks=tuple(fallbacks + budget.events), **extras)

        result = {"event": event, "episode": committed, "understanding": understanding, "snapshot": snapshots[0],
                  "decision": decision, "reply": reply, "due_waits": self._due(committed),
                  "fallbacks": tuple(fallbacks + budget.events), **extras}
        if shadow:
            return TurnResult("shadow", **result)
        if held:
            return TurnResult("held", **result)
        if interrupted is not None and interrupted():
            return TurnResult("revoked", **result)
        prepared = PreparedMessage(decision_id=decision_id, content_hash=sha256_hash({"text": reply.text}),
                                   recipient=episode.subject or "unknown", binding=event.channel_binding,
                                   body_ref=f"reply:{reply.plan.id}")
        self.bodies[prepared.body_ref] = reply.text
        try:
            exposure = self.exposures.record(self.ports.channel.send(ctx, prepared, f"send:{decision_id}"))
        except PortError as error:
            # Nada se sabe enviado; o trabalho de envio segue na caixa de saída, com a mesma chave.
            return TurnResult("answered", **{**result, "fallbacks": (*result["fallbacks"],
                                                                     f"send_failed:{error.code.value}")})
        finally:
            self.bodies.pop(prepared.body_ref, None)  # o texto vive só durante o envio
        return TurnResult("answered", exposure=exposure, **result)

    def _snapshot(self, ctx: TrustedContext, episode: Episode, trace_id: str, cause_id: str, state: TurnState,
                  dialogue: Mapping[str, Any]) -> ContextSnapshot:
        return seal(ContextSnapshot(
            **self._envelope(ctx, "snap", episode.episode_id, trace_id, cause_id),
            episode_version=episode.version, ownership_epoch=episode.ownership.epoch,
            identity={"subject_ref": episode.subject, "assurance": state.identity},
            needs=[{"need_id": n.need_id, "type": n.act, "state": "open"} for n in state.needs],
            facts=state.facts, unknowns=[k for k, f in state.facts.items() if isinstance(f, Unknown)],
            dialogue_state=dialogue, relationship_state={},
            profile_ref={"id": self.profile.id, "version": self.profile.version},
            policy_ref={"id": "moves", "version": "1"},
        ))

    def _next_episode(self, episode: Episode, event: InteractionEvent, asked: bool, *, post=(),
                      terms_wait: Wait | None = None, invalidate: bool = False) -> Episode:
        """Uma gravação, uma versão: a máquina (F4) anda os passos do turno, quando o estado muda.

        ``post``: o que o recibo do passo 6 fez (``receipt_terminal`` ou ``receipt_open``).
        ``terms_wait``: termos apresentados, que esperam confirmação.
        ``invalidate``: a resposta à pergunta dos termos não virou efeito (recusa, "não").
        """
        now = self.ports.clock.now()
        steps = list(post)
        state = episode.state
        for kind, _ in post:
            state = next_state(state, kind)
        wait = None
        if asked:
            window = read_line(self.profile, INACTIVITY_LINE)
            wait = Wait(condition="the customer answers the open question", owner="core",
                        deadline=_later(now, window.value if window.usable else 3600))
        if terms_wait is not None:
            if state == "waiting_input":
                steps.append(("evidence_arrived", None))
                state = "active"
            elif state == "waiting_authorization":
                steps.append(("authorization_invalidated", None))
                state = "active"
            if state == "active":
                steps.append(("terms_presented", terms_wait))
        elif asked:
            if state == "waiting_authorization":
                steps.append(("authorization_invalidated", None))
                state = "active"
            if state == "active":
                steps.append(("question_sent", wait))
        elif state == "waiting_input":
            steps.append(("evidence_arrived", None))
        elif state == "waiting_authorization" and invalidate:
            steps.append(("authorization_invalidated", None))
        if steps:
            return self._walk(episode, event.id, steps)
        # Sem mudança de estado (ou pergunta nova sobre pergunta): a versão sobe, a espera se renova.
        changes = {"id": self.ports.clock.new_id("eprec"), "cause_id": event.id, "occurred_at": now,
                   "recorded_at": None, "version": episode.version + 1}
        if wait is not None:
            changes["waits"] = (wait,)
        return dataclasses.replace(episode, **changes)

    def reconcile(self, ctx: TrustedContext, command_id: str) -> Settled:
        """Reconcilia um efeito aberto com a MESMA chave (K08, K10); vencido o prazo, vai a pessoa.

        Recibo terminal leva o episódio de ``waiting_effect`` a ``active``; prazo
        vencido, a ``awaiting_handoff`` (``reconciliation_overdue``). Nunca executa
        de novo: um efeito desconhecido não se repete.
        """
        store, clock = self.ports.store, self.ports.clock
        command = self.ledger.commands[command_id]
        settled = self.settler(ctx).settle(ctx, command, None, attempt=2)
        episode = store.load_episode(ctx, command.episode_id)
        if episode is None or episode.state != "waiting_effect":
            return settled
        receipt = settled.receipt
        if settled.to_person:
            step = ("reconciliation_overdue", Wait(condition="a person settles the effect", owner="queue",
                                                   deadline=_later(clock.now(), 3600)))
        elif receipt is not None and receipt.status in ("success", "failure"):
            store.complete_work(ctx, f"execute:{command_id}")
            step = ("receipt_terminal", None)
        else:
            return settled
        cause = receipt.id if receipt is not None else command.id
        store.commit_transition(ctx, Transition(episode=self._walk(episode, cause, [step]),
                                                expected_version=episode.version), (), ())
        return settled

    # ── retomadas de compromisso (F9) ───────────────────────────────────────
    def _resume_state(self, entry, now: str) -> TurnState:
        return TurnState(now=now, channel=entry.binding.channel, identity=entry.identity, profile=self.profile,
                         needs=(entry.need,), subject=Subject(subject_ref=entry.recipient))

    def _respond(self, ctx: TrustedContext, entry, episode: Episode, state: TurnState, *, cause_id: str,
                 only: tuple[str, ...], records: tuple = (), steps=()) -> TurnResult:
        """Decide, diz, grava e envia fora de um turno do cliente: a retomada de um compromisso.

        A mesma cadeia do turno (snapshot, decisão, molde verificado, uma gravação, envio),
        restrita aos movimentos ``only``. A mensagem vai ao vínculo de canal em que o
        compromisso nasceu, mesmo depois de a conversa ter acabado (K21).
        """
        clock, store = self.ports.clock, self.ports.store
        trace_id = clock.new_id("trace")
        previous = store.latest_record(ctx, episode.episode_id, ContextSnapshot.SCHEMA)
        dialogue = dict(previous.dialogue_state) if previous is not None else {}
        snapshot = self._snapshot(ctx, episode, trace_id, cause_id, state, dialogue)
        moves = registry()
        proposals = [proposal for need in state.needs for name in only
                     if (proposal := moves[name].propose(state, need)) is not None]
        decision = decide(DecisionInput(decision_id=clock.new_id("dec"), record_id=clock.new_id("decrec"),
                                        trace_id=trace_id, occurred_at=clock.now(), turn=self._turns,
                                        snapshot=snapshot, profile=self.profile, proposals=tuple(proposals)))
        by_need = {need.need_id: need for need in state.needs}
        chosen = [decision.candidates[i] for i in decision.chosen]
        reply = None
        if chosen:
            reply = compose(specs=[moves[c.move].reply(state, by_need[c.need_id]) for c in chosen],
                            templates=self._templates(), formatters=self.formatters, voice=self._voice(),
                            evidence=Evidence(now=state.now, facts=state.facts, fact_facets=state.fact_facets,
                                              commitments=state.commitments),
                            decision_id=decision.decision_id,
                            record=self._envelope(ctx, "reply", episode.episode_id, trace_id, decision.id))
        held = reply is None or reply.verification.result == "hold"
        new_episode = self._walk(episode, cause_id, steps) if steps else dataclasses.replace(
            episode, id=clock.new_id("eprec"), cause_id=cause_id, occurred_at=clock.now(), recorded_at=None,
            version=episode.version + 1)
        outbox = () if held else (WorkItem(work_id=f"send:{decision.decision_id}", kind="send",
                                           payload={"decision_id": decision.decision_id}, due_at=clock.now()),)
        committed = store.commit_transition(
            ctx, Transition(episode=new_episode, expected_version=episode.version),
            tuple(r for r in (snapshot, decision, *records, reply.plan if reply else None) if r is not None), outbox)
        result = {"event": None, "episode": committed, "snapshot": snapshot, "decision": decision, "reply": reply,
                  "decisions": (decision,)}
        if held:
            return TurnResult("held", **result)
        prepared = PreparedMessage(decision_id=decision.decision_id, content_hash=sha256_hash({"text": reply.text}),
                                   recipient=entry.recipient, binding=entry.binding, body_ref=f"reply:{reply.plan.id}")
        self.bodies[prepared.body_ref] = reply.text
        try:
            exposure = self.exposures.record(self.ports.channel.send(ctx, prepared, f"send:{decision.decision_id}"))
        except PortError as error:
            return TurnResult("answered", fallbacks=(f"send_failed:{error.code.value}",), **result)
        finally:
            self.bodies.pop(prepared.body_ref, None)  # o texto vive só durante o envio
        return TurnResult("answered", exposure=exposure, **result)

    def _advance(self, ctx: TrustedContext, entry, cause_id: str, **changes) -> Commitment:
        clock = self.ports.clock
        return self.commitments.advance(entry.commitment_id, record_id=clock.new_id("cmt"), at=clock.now(),
                                        cause_id=cause_id, **changes)

    def staff_answered(self, ctx: TrustedContext, commitment_id: str) -> TurnResult:
        """A equipe respondeu: a resposta entra como fato com autoria e validade, e volta ao cliente (J3).

        O compromisso se cumpre com a resposta como evidência. O fato da equipe é
        lido como qualquer fato: vencido, não se diz.
        """
        entry = self.commitments.entries[commitment_id]
        if not entry.is_open or entry.ticket_id is None:
            raise CommitmentRefused("not_open", commitment_id)
        fact = self.ports.staff.promote_answer(ctx, entry.ticket_id)
        state = self._resume_state(entry, self.ports.clock.now())
        for key in state.fact_keys_for(entry.need):
            state.facts[key] = fact
        episode = self.ports.store.load_episode(ctx, entry.commitment.episode_id)
        fulfilled = self._advance(ctx, entry, entry.ticket_id, state="fulfilled", evidence=(entry.ticket_id,))
        try:
            self.ports.staff.record_fulfillment(ctx, commitment_id, entry.ticket_id)
        except PortError:
            pass  # a equipe guarda o que guarda; o livro do núcleo já registrou o cumprimento
        return self._respond(ctx, entry, episode, state, cause_id=entry.ticket_id,
                             only=("inform", "inform_limitation"), records=(fulfilled,))

    def staff_accepted(self, ctx: TrustedContext, commitment_id: str) -> Commitment:
        """Alguém aceitou, nominalmente. Na transferência, o episódio passa à posse dessa pessoa.

        A fila que recusou não tem aceite a registrar: o erro da porta sobe, e nada
        muda (K20).
        """
        entry = self.commitments.entries[commitment_id]
        ticket = self.ports.staff.record_acceptance(ctx, entry.ticket_id)
        accepted = self._advance(ctx, entry, ticket.ticket_id, state="accepted", owner=ticket.accepted_by)
        store = self.ports.store
        episode = store.load_episode(ctx, entry.commitment.episode_id)
        steps = []
        if entry.move == "handoff" and episode.state == "awaiting_handoff":
            steps.append(("handoff_accepted", None, ticket.accepted_by))
        new_episode = self._walk(episode, ticket.ticket_id, steps) if steps else dataclasses.replace(
            episode, id=self.ports.clock.new_id("eprec"), cause_id=ticket.ticket_id,
            occurred_at=self.ports.clock.now(), recorded_at=None, version=episode.version + 1)
        store.commit_transition(ctx, Transition(episode=new_episode, expected_version=episode.version),
                                (accepted,), ())
        return accepted

    def tick(self, ctx: TrustedContext) -> tuple[TurnResult, ...]:
        """Prazos de compromisso vencidos: cada um vira evento, escala conforme o perfil e avisa o cliente UMA vez (K22).

        Escalar (linha ``commitment.escalation``): o compromisso passa ao dono que a
        linha diz, com prazo novo, e o episódio vai a pessoa (``handoff_requested``).
        Sem a linha, não se inventa a quem escalar: o prazo vencido fica registrado
        e o cliente é avisado. Prazo escalado que vence de novo quebra a promessa.
        """
        clock, store = self.ports.clock, self.ports.store
        now = clock.now()
        line = read_line(self.profile, ESCALATION_LINE)
        results = []
        # Avisos que não saíram num tick anterior (segurado ou falhado), antes que o due marque prazos novos.
        pending = [entry for entry in self.commitments.open_entries(ctx.tenant, ctx.environment)
                   if not entry.notified and "customer_notify_failed" in self.commitments.events_of(entry.commitment_id)]
        for entry in self.commitments.due(now, ctx.tenant, ctx.environment):
            cid = entry.commitment_id
            pending = [other for other in pending if other.commitment_id != cid]
            self.commitments.note("deadline_passed", cid, now, entry.commitment.deadline.at)
            episode = store.load_episode(ctx, entry.commitment.episode_id)
            records, steps = [], []
            if entry.escalated:
                records.append(self._advance(ctx, entry, cid, state="broken"))
            elif line.usable:
                deadline = staff_deadline(self.profile, self._hours(now), now, "respond")
                records.append(self._advance(ctx, entry, cid, owner=str(line.value), deadline=deadline))
                entry.escalated = True
                self.commitments.note("escalated", cid, now, str(line.value))
                if episode.state not in ("awaiting_handoff", "human_owned", "resolved"):
                    steps.append(("handoff_requested", Wait(
                        condition="a person takes over the overdue commitment", owner="queue",
                        deadline=deadline.at if isinstance(deadline, DeadlineSet) else
                        _later(now, window_seconds(self.profile, "accept")))))
            else:
                self.commitments.note("escalation_absent", cid, now, line.code)
            if entry.notified:
                if records or steps:
                    new_episode = self._walk(episode, cid, steps) if steps else dataclasses.replace(
                        episode, id=clock.new_id("eprec"), cause_id=cid, occurred_at=now, recorded_at=None,
                        version=episode.version + 1)
                    store.commit_transition(ctx, Transition(episode=new_episode, expected_version=episode.version),
                                            tuple(records), ())
                continue
            results.append(self._notify_overdue(ctx, entry, episode, now, records, steps))
        for entry in pending:
            # O prazo já foi tratado; só o aviso ao cliente não saiu da outra vez. Tenta de novo, sem reescalar.
            episode = store.load_episode(ctx, entry.commitment.episode_id)
            results.append(self._notify_overdue(ctx, entry, episode, now, [], []))
        return tuple(results)

    def _notify_overdue(self, ctx: TrustedContext, entry: Entry, episode: Episode, now: str,
                        records: list, steps: list) -> TurnResult:
        """Avisa o cliente do prazo vencido. Avisado só com o aviso enviado: segurado ou falhado, ele não soube."""
        cid = entry.commitment_id
        state = self._resume_state(entry, now)
        state.commitments[cid] = entry.commitment
        state.waiting[entry.need.need_id] = cid
        result = self._respond(ctx, entry, episode, state, cause_id=cid, only=("wait",),
                               records=tuple(records), steps=steps)
        if result.outcome == "answered" and result.exposure is not None:
            entry.notified = True
            self.commitments.note("customer_notified", cid, now)
            return result
        reason = result.fallbacks[0] if result.fallbacks else result.outcome
        if self.commitments.events_of(cid).count("customer_notify_failed") + 1 >= NOTIFY_ATTEMPTS:
            # Tentou e não saiu: para de tentar, registrado, em vez de repetir a cada tick para sempre.
            entry.notified = True
            self.commitments.note("customer_notify_failed", cid, now, reason)
            self.commitments.note("customer_notify_gave_up", cid, now, reason)
        else:
            self.commitments.note("customer_notify_failed", cid, now, reason)
        return result

    def _due(self, episode: Episode) -> tuple[Wait, ...]:
        now = self.ports.clock.now()
        return tuple(wait for wait in episode.waits if wait.deadline <= now)

    def observe_delivery(self, ctx: TrustedContext, exposure_id: str) -> ExposureEvent:
        """Consulta a entrega. Entregue não é lida; canal sem leitura nunca diz "lida" (K18)."""
        return self.exposures.record(self.ports.channel.delivery_status(ctx, exposure_id))


def fact_value(fact: Any) -> Any:
    return fact.value if isinstance(fact, Known) else None
