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
6. **Autorizar e executar.** Nenhum movimento deste turno tem efeito (F8 traz).
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

from conversational_commerce.contracts import (
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
    open_episode,
    receive,
    subject_key,
    transition,
)

from .acts import ACTS, ANSWER_ACTS, TEST_RULES, LocalRules, only_courtesy, validate
from .budget import TurnBudget
from .format import DEFAULT_FORMATTERS
from .moves import registry, templates
from .state import NeedSpec, TurnState

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

        episode = self._episode_for(ctx, event, trace_id)
        previous = store.latest_record(ctx, episode.episode_id, ContextSnapshot.SCHEMA)
        previous_dialogue = dict(previous.dialogue_state) if previous is not None else {}
        epoch = episode.ownership.epoch

        understanding = self._understand(ctx, event, episode, trace_id, budget, fallbacks)
        needs, answered_question = self._needs(understanding, previous_dialogue, epoch)
        state = TurnState(now=clock.now(), channel=event.channel_binding.channel, identity="transported",
                          profile=self.profile, needs=needs)
        self._read_facts(ctx, state, budget)
        dialogue = answered(previous_dialogue) if answered_question else previous_dialogue

        snapshot = seal(ContextSnapshot(
            **self._envelope(ctx, "snap", episode.episode_id, trace_id, event.id),
            episode_version=episode.version, ownership_epoch=epoch,
            identity={"subject_ref": episode.subject, "assurance": "transported"},
            needs=[{"need_id": n.need_id, "type": n.act, "state": "open"} for n in needs],
            facts=state.facts, unknowns=[k for k, f in state.facts.items() if isinstance(f, Unknown)],
            dialogue_state=dialogue, relationship_state={},
            profile_ref={"id": self.profile.id, "version": self.profile.version},
            policy_ref={"id": "moves", "version": "1"},
        ))

        moves = registry()
        proposals = [proposal for need in needs for module in moves.values()
                     if (proposal := module.propose(state, need)) is not None]
        decision_id = clock.new_id("dec")
        decision = decide(DecisionInput(decision_id=decision_id, record_id=clock.new_id("decrec"), trace_id=trace_id,
                                        occurred_at=clock.now(), turn=self._turns, snapshot=snapshot,
                                        profile=self.profile, proposals=tuple(proposals)))
        chosen = [decision.candidates[i] for i in decision.chosen]
        by_need = {need.need_id: need for need in needs}

        # Passo 7: dizer e verificar.
        specs = [moves[c.move].reply(state, by_need[c.need_id]) for c in chosen]
        reply = None
        if specs:
            reply = compose(specs=specs, templates=templates(), formatters=self.formatters,
                            evidence=Evidence(now=state.now, facts=state.facts, fact_facets=state.fact_facets),
                            decision_id=decision_id,
                            record=self._envelope(ctx, "reply", episode.episode_id, trace_id, decision.id))

        # Estado do episódio e pergunta no ar.
        asked = next((c for c in chosen if c.move == "ask_clarification"), None)
        after = None
        if asked is not None:
            dialogue = ask(dialogue, question_id=clock.new_id("q"), need_id=asked.need_id, epoch=epoch)
        if dialogue != dict(snapshot.dialogue_state):
            # O estado de diálogo DEPOIS do turno: é o que o próximo turno lê (a pergunta no ar).
            after = seal(dataclasses.replace(snapshot, dialogue_state=dialogue, hash=None, id=clock.new_id("snap"),
                                             cause_id=decision.id))
        new_episode = self._next_episode(episode, event, asked is not None)

        held = reply is None or reply.verification.result == "hold"
        shadow = ctx.environment == "shadow"
        records = tuple(r for r in (event, understanding, snapshot, decision,
                                    reply.plan if reply else None, after) if r is not None)
        outbox = () if held or shadow else (WorkItem(work_id=f"send:{decision_id}", kind="send",
                                                     payload={"decision_id": decision_id}, due_at=clock.now()),)
        try:
            committed = store.commit_transition(ctx, Transition(episode=new_episode, expected_version=episode.version),
                                                records, outbox)
        except PortError as conflict:
            if conflict.code.value != "revision_conflict":
                raise
            fallbacks.append("superseded:revision_conflict")
            return TurnResult("superseded", event, episode, understanding, snapshot, decision, reply,
                              fallbacks=tuple(fallbacks + budget.events))

        result = {"event": event, "episode": committed, "understanding": understanding, "snapshot": snapshot,
                  "decision": decision, "reply": reply, "due_waits": self._due(committed),
                  "fallbacks": tuple(fallbacks + budget.events)}
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

    def _next_episode(self, episode: Episode, event: InteractionEvent, asked: bool) -> Episode:
        """Uma transição por turno (o episódio sobe uma versão), pela máquina quando o estado muda."""
        clock = self.ports.clock
        now = clock.now()
        record_id = clock.new_id("eprec")
        wait = None
        if asked:
            window = read_line(self.profile, INACTIVITY_LINE)
            wait = Wait(condition="the customer answers the open question", owner="core",
                        deadline=_later(now, window.value if window.usable else 3600))
        if asked and episode.state == "active":
            return transition(episode, EpisodeEvent(kind="question_sent", at=now, cause_id=event.id, wait=wait),
                              expected_version=episode.version, record_id=record_id)
        if not asked and episode.state == "waiting_input":
            return transition(episode, EpisodeEvent(kind="evidence_arrived", at=now, cause_id=event.id),
                              expected_version=episode.version, record_id=record_id)
        # Sem mudança de estado (ou pergunta nova sobre pergunta): a versão sobe, a espera se renova.
        changes = {"id": record_id, "cause_id": event.id, "occurred_at": now, "recorded_at": None,
                   "version": episode.version + 1}
        if wait is not None:
            changes["waits"] = (wait,)
        return dataclasses.replace(episode, **changes)

    def _due(self, episode: Episode) -> tuple[Wait, ...]:
        now = self.ports.clock.now()
        return tuple(wait for wait in episode.waits if wait.deadline <= now)

    def observe_delivery(self, ctx: TrustedContext, exposure_id: str) -> ExposureEvent:
        """Consulta a entrega. Entregue não é lida; canal sem leitura nunca diz "lida" (K18)."""
        return self.ports.channel.delivery_status(ctx, exposure_id)


def fact_value(fact: Any) -> Any:
    return fact.value if isinstance(fact, Known) else None
