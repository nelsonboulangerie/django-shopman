"""O turno: os dez passos da v2 5.3 sobre as portas.

1. **Receber.** Grava e deduplica antes de qualquer trabalho; liga ao episódio.
2. **Portão sem modelo.** Cortesia pura não chama modelo. A regra local de risco
   já soma os atos dela aqui.
3. **Entender.** A porta de modelo, se há orçamento e ela responde; senão, regra
   local. Ato fora da lista vira ``unknown`` e a queda é registrada.
4. **Montar o snapshot.** Necessidades, pergunta no ar e fatos lidos ao vivo, com
   teto de passos. Nada fica aberto enquanto se chama modelo ou porta: a única
   gravação é a do passo 8.
5. **Decidir.** ``policy.decide`` sobre as propostas dos movimentos registrados.
6. **Autorizar e executar** (F8). Para o movimento de efeito escolhido: a
   concessão (o núcleo emite, nunca o modelo), o comando gravado junto com a
   intenção de execução na caixa de saída (N13), a execução pela guarda do
   ponto de efeito e o recibo. Recusado no ponto de efeito, decide-se de novo,
   numa decisão nova ligada à primeira (N14).
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
    AuthorizationGrant,
    Commitment,
    ContextSnapshot,
    DecisionRecord,
    DeploymentProfile,
    Episode,
    ExposureEvent,
    InteractionEvent,
    Known,
    Producer,
    Understanding,
    Unknown,
    Wait,
    seal,
    sha256_hash,
)
from conversational_commerce.ledger import ReceiptLedger, Settled, Settler
from conversational_commerce.policy import DecisionInput, decide
from conversational_commerce.ports import (
    Budget,
    InterpretRequest,
    ModelRequest,
    PortError,
    PreparedMessage,
    Transition,
    TrustedContext,
    WorkItem,
)
from conversational_commerce.profile import read_line
from conversational_commerce.reply import Composed, Evidence, compose
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

from .acts import ACTS, ANSWER_ACTS, TEST_RULES, LocalRules, only_courtesy, validate
from .budget import TurnBudget
from .format import DEFAULT_FORMATTERS
from .moves import registry, templates
from .state import NeedSpec, Subject, TurnState

PRODUCER = Producer(name="conversational-commerce", version="engine-1")
LOCAL_READER = Producer(name="local-rules", version="1")
FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
INACTIVITY_LINE = "episode.inactivity_window_seconds"

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
    resolve_content: Callable[[str | None], str] = text_of
    # O adaptador diz quem fala e qual é o carrinho dele, do contexto confiável (nunca do texto).
    subject_of: Callable[[TrustedContext, InteractionEvent], Subject] = default_subject
    revocations: Revocations = field(default_factory=Revocations)
    ledger: ReceiptLedger = field(default_factory=ReceiptLedger)
    _turns: int = 0

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
                             inactivity_seconds=inactivity)
        if decision.action == "continue" and latest is not None:
            return latest
        episode = open_episode(record_id=self.ports.clock.new_id("eprec"), episode_id=self.ports.clock.new_id("ep"),
                               tenant=ctx.tenant, environment=ctx.environment, trace_id=trace_id,
                               at=self.ports.clock.now(), producer=PRODUCER, subject=subject)
        return self.ports.store.commit_transition(ctx, Transition(episode=episode, expected_version=0), (episode,), ())

    # ── passos 2 e 3 ────────────────────────────────────────────────────────
    def _understand(self, ctx: TrustedContext, event: InteractionEvent, episode: Episode, trace_id: str,
                    budget: TurnBudget, fallbacks: list[str]) -> Understanding:
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
                event_id=event.id, content_ref=event.content_ref, allowed_acts=ACTS)
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

    def _quote(self, ctx: TrustedContext, state: TurnState, budget: TurnBudget) -> None:
        """Cota o carrinho quando alguma necessidade pede termos. Cotação é leitura, com passo do teto."""
        target = state.subject.cart_ref
        if target is None or target in state.terms or not any(state.wants_terms(n) for n in state.needs):
            return
        key = state.terms_key(target)
        if not budget.take_step(f"read:{key}"):
            state.facts[key] = Unknown(reason="source_failed")
            return
        try:
            terms = self.ports.commerce_read.quote(ctx, target)
        except PortError:
            state.facts[key] = Unknown(reason="source_failed")
            return
        state.terms[target] = terms
        state.facts[key] = Known(value={"total": {"price_minor": terms.total.amount_minor,
                                                  "currency": terms.total.currency},
                                        "terms_id": terms.terms_id},
                                 source="commerce-quote", observed_at=state.now, valid_until=terms.valid_until,
                                 source_version=terms.hash)

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
        """Autoriza e executa o movimento de efeito escolhido. Devolve o episódio como ficou gravado.

        Um efeito por turno: o segundo movimento de efeito escolhido fica recusado
        (``one_effect_per_turn``) e a decisão refeita diz a limitação.
        """
        clock, store, moves = self.ports.clock, self.ports.store, registry()
        chosen = [decision.candidates[i] for i in decision.chosen if getattr(moves[decision.candidates[i].move],
                                                                             "EFFECT", False)]
        if not chosen:
            return episode
        if ctx.environment == "shadow":
            fallbacks.extend(f"shadow:effect_not_executed:{c.move}" for c in chosen)
            return episode
        for extra in chosen[1:]:
            state.refused[extra.need_id] = "one_effect_per_turn"
        candidate = chosen[0]
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
            return episode
        command = build_command(record=self._envelope(ctx, "cmd", episode.episode_id, trace_id, grant.id),
                                command_id=clock.new_id("command"), decision_id=decision.decision_id, grant=grant,
                                parameters=plan.parameters, expected_versions=plan.expected_versions,
                                ownership_epoch=epoch, scope=ctx.tenant, now=now)
        self.ledger.register(command)
        # N13: concessão, comando e intenção de execução gravados juntos, com o episódio esperando o efeito.
        steps = self._to_active(episode, offer_confirmed=plan.basis == "confirmation")
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
            return episode
        effects["receipts"].append(receipt)
        state.receipts[need.need_id] = receipt
        if receipt.status in ("success", "failure"):
            store.complete_work(ctx, work.work_id)
        if receipt.status == "failure":
            state.refused[need.need_id] = receipt.error.code
        elif receipt.status in ("pending", "unknown"):
            commitment = self._reconciliation_commitment(ctx, receipt, trace_id)
            state.commitments[commitment.commitment_id] = commitment
            unwritten.append(commitment)
        return episode

    def _reconciliation_commitment(self, ctx: TrustedContext, receipt: ActionReceipt, trace_id: str) -> Commitment:
        from .moves._effects import commitment_id

        return Commitment(**self._envelope(ctx, "cmt", receipt.episode_id, trace_id, receipt.id),
                          commitment_id=commitment_id(receipt.command_id), type="promise",
                          obligation="confirm the outcome of the action", owner=receipt.reconciliation.owner,
                          deadline={"status": "set", "at": receipt.reconciliation.deadline,
                                    "rule_ref": "effect.reconciliation_deadline_seconds"},
                          fulfillment_criterion="a terminal receipt for the command", state="open")

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
        for kind, wait in steps:
            current = transition(current, EpisodeEvent(kind=kind, at=now, cause_id=cause_id, wait=wait),
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

        understanding = self._understand(ctx, event, episode, trace_id, budget, fallbacks)
        needs, answered_question = self._needs(understanding, previous_dialogue, epoch)
        state = TurnState(now=clock.now(), channel=event.channel_binding.channel,
                          identity=strongest_identity(subject.identity_evidence), profile=self.profile,
                          needs=needs, event_assurance=event.event_identity.assurance, subject=subject, offer=offer)
        for need in needs:
            if state.answers_offer(need):
                state.confirmation_problems[need.need_id] = confirmation_problem(
                    offer, self._confirmation(ctx, event, subject, epoch), state.now)
        self._read_facts(ctx, state, budget)
        self._quote(ctx, state, budget)
        dialogue = answered(previous_dialogue) if answered_question else previous_dialogue
        answered_offer = offer is not None and answered_question == offer.question_id
        if answered_offer:
            dialogue.pop(OFFER_KEY, None)

        snapshot = self._snapshot(ctx, episode, trace_id, event.id, state, dialogue)
        decision = self._decide(state, needs, snapshot, trace_id)
        decisions, snapshots = [decision], [snapshot]
        by_need = {need.need_id: need for need in needs}

        # Passo 6: autorizar e executar. Recusado no ponto de efeito, decide-se de novo, ligado à anterior.
        unwritten: list = [event, understanding, snapshot, decision]
        effects: dict[str, list] = {"grants": [], "commands": [], "receipts": [], "settled": []}
        episode = self._execute(ctx, state, decision, by_need, event, episode, trace_id, unwritten, fallbacks,
                                effects)
        if state.refused:
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
        specs = [moves[c.move].reply(state, by_need[c.need_id]) for c in chosen]
        reply = None
        if specs:
            receipts = {receipt.command_id: receipt for receipt in state.receipts.values()}
            reply = compose(specs=specs, templates=templates(), formatters=self.formatters,
                            evidence=Evidence(now=state.now, facts=state.facts, fact_facets=state.fact_facets,
                                              receipts=receipts, commitments=state.commitments),
                            decision_id=decision_id,
                            record=self._envelope(ctx, "reply", episode.episode_id, trace_id, decision.id))
        held = reply is None or reply.verification.result == "hold"

        # Estado do episódio, pergunta no ar e os termos que esperam confirmação.
        asked = next((c for c in chosen if c.move == "ask_clarification"), None)
        presented = next((c for c in chosen if c.move == "present_terms"), None)
        terms_wait = None
        if asked is not None:
            dialogue = ask(dialogue, question_id=clock.new_id("q"), need_id=asked.need_id, epoch=epoch)
        if presented is not None and not held:
            # Termos que o cliente não viu (mensagem segurada) não esperam confirmação.
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
        after = None
        if dialogue != dict(snapshot.dialogue_state):
            # O estado de diálogo DEPOIS do turno: é o que o próximo turno lê (a pergunta no ar).
            after = seal(dataclasses.replace(snapshot, dialogue_state=dialogue, hash=None, id=clock.new_id("snap"),
                                             cause_id=decision.id))
        post = []
        for receipt in effects["receipts"]:
            if receipt.status in ("success", "failure"):
                post.append(("receipt_terminal", None))
            else:
                post.append(("receipt_open", Wait(condition="reconciliation returns a terminal receipt",
                                                  owner="core", deadline=receipt.reconciliation.deadline)))
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
        try:
            exposure = self.ports.channel.send(ctx, prepared, f"send:{decision_id}")
        except PortError as error:
            # Nada se sabe enviado; o trabalho de envio segue na caixa de saída, com a mesma chave.
            return TurnResult("answered", **{**result, "fallbacks": (*result["fallbacks"],
                                                                     f"send_failed:{error.code.value}")})
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

    def _due(self, episode: Episode) -> tuple[Wait, ...]:
        now = self.ports.clock.now()
        return tuple(wait for wait in episode.waits if wait.deadline <= now)

    def observe_delivery(self, ctx: TrustedContext, exposure_id: str) -> ExposureEvent:
        """Consulta a entrega. Entregue não é lida; canal sem leitura nunca diz "lida" (K18)."""
        return self.ports.channel.delivery_status(ctx, exposure_id)


def fact_value(fact: Any) -> Any:
    return fact.value if isinstance(fact, Known) else None
