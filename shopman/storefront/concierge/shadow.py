"""A decisão em sombra (N5, X1 da v2 11.5): o que o framework faria com cada entrada da Nice.

Uma varredura (``concierge_shadow_decisions``, no ``maintenance_worker``) pega as entradas
ainda sem decisão. Para cada uma, faz os passos 1 a 5 do turno do framework sobre as portas
do Shopman e grava o ``DecisionRecord``:

1. o contexto confiável é a conversa (``conversation:<pk>``), em ``environment=shadow``;
2. o leitor local por regra (``ports.LocalReader``) entende a mensagem, por referência
   (``message:<pk>``): nenhum modelo, nenhum texto fora do Shopman;
3. as necessidades, a situação comum e os fatos lidos ao vivo pela porta de leitura
   (``ShopmanCommerceRead``), cada um com ``observed_at``: o atraso da varredura aparece no
   registro em vez de se esconder;
4. o snapshot selado;
5. ``policy.decide`` sobre as propostas dos movimentos do framework, com o perfil da Nice.

**O que não faz** (K36): nenhuma chamada às portas de escrita, nenhum envio, nenhum
modelo, nenhum texto do cliente no registro. Até o N9 a Nice segue pelo caminho legado; a
sombra só olha.

A junção (``join_outcomes``) grava, por decisão, os pedidos do cliente em 24 horas e em 7
dias (Orderman): janela aberta é ``censored`` (K33), cliente sem identidade é ``unknown``.

Por que varredura e não gancho no turno [DECIDIDO, plano 6]: o gancho editaria
``service.py``, e uma falha da sombra nunca pode atrasar nem derrubar um turno vivo.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from conversational_commerce.contracts import ContextSnapshot, MetricRef, OutcomeEvent, Unknown, seal
from conversational_commerce.engine.acts import ACTS, ANSWER_ACTS
from conversational_commerce.engine.moves import registry
from conversational_commerce.engine.state import NeedSpec, Subject, TurnState
from conversational_commerce.policy import DecisionInput, decide
from conversational_commerce.ports import InterpretRequest, ModelRequest, TrustedContext

from shopman.shop.conversational.commerce_read import ShopmanCommerceRead, instant

from .ports import ConversationOwnership, LocalReader, subject_of

logger = logging.getLogger(__name__)

ENVIRONMENT = "shadow"
PRODUCER = {"name": "concierge-shadow", "version": "1"}
WINDOWS = (("orders_24h", timedelta(hours=24)), ("orders_7d", timedelta(days=7)))
OUTCOME_SOURCE = "orderman"
SWEEP_LIMIT = 200


def enabled() -> bool:
    """O campo da ``Shop`` que liga a sombra (ADR-042). Sem loja, desligada."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    return bool(shop is not None and shop.conversational_shadow_enabled)


def pending(limit: int = SWEEP_LIMIT):
    """As entradas do cliente ainda sem decisão, da mais antiga para a mais nova."""
    from shopman.shop.models import ConversationMessage

    return (ConversationMessage.objects.select_related("conversation")
            .filter(role="user", kind="inbound", conversational_decision__isnull=True)
            .order_by("created_at", "pk")[:limit])


def _needs(understanding) -> tuple[NeedSpec, ...]:
    needs = []
    for index, act in enumerate(understanding.acts):
        # Na sombra não há pergunta no ar a que o "sim" se ligue: ela não envia pergunta nenhuma.
        if act.act in ANSWER_ACTS:
            needs.append(NeedSpec(f"n{index + 1}", act.act))
            continue
        needs.append(NeedSpec(f"n{index + 1}", act.act, readings=(dict(act.fields),)))
    return tuple(needs)


def _read_facts(ctx: TrustedContext, state: TurnState, commerce: ShopmanCommerceRead) -> None:
    for need in state.needs:
        for key in state.fact_keys_for(need):
            if key in state.facts:
                continue
            if key == "hours":
                state.facts[key] = commerce.read_policy(ctx, "hours")
            else:
                state.facts[key] = commerce.read_item(ctx, key.split(".", 1)[1])


def decide_entry(message, *, profile, commerce: ShopmanCommerceRead | None = None,
                 reader: LocalReader | None = None):
    """``(DecisionRecord, snapshot, atos, fatos desconhecidos)`` para a entrada ``message``."""
    conversation = message.conversation
    now = instant()
    ctx = TrustedContext(tenant=profile.tenant, environment=ENVIRONMENT, subject=subject_of(conversation.pk))
    commerce = commerce or ShopmanCommerceRead(channel_ref=conversation.channel_ref or "whatsapp",
                                               ownership=ConversationOwnership())
    reader = reader or LocalReader()
    event_id = f"msg-{message.pk}"
    understanding, _ = reader.interpret(ctx, InterpretRequest(
        request=ModelRequest(purpose="interpret", data_class="redacted",
                             budget={"max_calls": 0, "max_spend": {"amount_minor": 0, "currency": "BRL"}}),
        event_id=event_id, content_ref=f"message:{message.pk}", allowed_acts=ACTS))
    needs = _needs(understanding)
    state = TurnState(
        now=now, channel="whatsapp", identity="transported" if conversation.phone else "anonymous",
        profile=profile, needs=needs, event_assurance="provider_claimed" if message.external_id else "none",
        subject=Subject(subject_ref=ctx.subject, cart_ref=conversation.session_key or None))
    _read_facts(ctx, state, commerce)
    trace_id = f"trace-{event_id}"
    envelope = {"tenant": ctx.tenant, "environment": ENVIRONMENT, "trace_id": trace_id, "cause_id": event_id,
                "occurred_at": now, "producer": PRODUCER, "episode_id": f"conversation-{conversation.pk}"}
    snapshot = seal(ContextSnapshot(
        id=f"snap-{event_id}", **envelope, episode_version=int(conversation.turn_fence),
        ownership_epoch=int(conversation.turn_fence),
        identity={"subject_ref": ctx.subject, "assurance": state.identity},
        needs=[{"need_id": n.need_id, "type": n.act, "state": "open"} for n in needs],
        facts=state.facts, unknowns=[k for k, f in state.facts.items() if isinstance(f, Unknown)],
        dialogue_state={}, relationship_state={},
        profile_ref={"id": profile.id, "version": profile.version}, policy_ref={"id": "moves", "version": "1"}))
    proposals = [proposal for need in needs for module in registry().values()
                 if (proposal := module.propose(state, need)) is not None]
    decision = decide(DecisionInput(decision_id=f"dec-{event_id}", record_id=f"decrec-{event_id}",
                                    trace_id=trace_id, occurred_at=now, turn=1, snapshot=snapshot,
                                    profile=profile, proposals=tuple(proposals)))
    unknown = {key: fact.reason for key, fact in state.facts.items() if isinstance(fact, Unknown)}
    return decision, snapshot, [act.act for act in understanding.acts], unknown


def sweep(*, limit: int = SWEEP_LIMIT) -> dict[str, int]:
    """Decide em sombra as entradas pendentes. Desligada pela ``Shop``, não toca em nada."""
    from shopman.shop.conversational.decision_store import record_decision

    from .profile import build_profile

    if not enabled():
        return {"enabled": 0, "decided": 0, "failed": 0}
    profile = build_profile(environment=ENVIRONMENT)
    decided = failed = 0
    for message in pending(limit):
        try:
            decision, snapshot, acts, unknown = decide_entry(message, profile=profile)
            _, created = record_decision(
                message=message, conversation_id=message.conversation_id, decision=decision,
                snapshot_hash=snapshot.hash, acts=acts, unknown_facts=unknown,
                customer_ref=message.conversation.customer_ref or "", entry_at=message.created_at)
            decided += int(created)
        except Exception:  # noqa: BLE001 - a sombra nunca derruba o ciclo; a entrada fica para o próximo
            failed += 1
            logger.warning("concierge.shadow: decisão falhou message=%s", message.pk, exc_info=True)
    return {"enabled": 1, "decided": decided, "failed": failed}


def join_outcomes(*, now: datetime | None = None, limit: int = SWEEP_LIMIT) -> dict[str, int]:
    """Os pedidos do cliente em 24 h e em 7 dias depois de cada decisão. Só telemetria (P19)."""
    from shopman.orderman.models import Order

    from shopman.shop.conversational.decision_store import current_outcome, record_outcome
    from shopman.shop.models import Conversation, ConversationalDecision
    from shopman.shop.services.customer_orders import customer_identity_filter

    if not enabled():
        return {"enabled": 0, "recorded": 0}
    now = now or datetime.now(UTC)
    horizon = now - WINDOWS[-1][1] - timedelta(days=1)
    recorded = 0
    for decision in ConversationalDecision.objects.filter(decided_at__gte=horizon).order_by("decided_at")[:limit]:
        conversation = Conversation.objects.filter(pk=decision.conversation_id).first()
        identity = customer_identity_filter(customer_ref=decision.customer_ref or None,
                                            phone=(conversation.phone or None) if conversation else None)
        for metric, span in WINDOWS:
            current = current_outcome(decision, metric)
            if current is not None and current.observation == "observed":
                continue  # janela fechada já observada: o resultado não muda mais
            start, end = decision.decided_at, decision.decided_at + span
            base = {"id": f"out-{decision.decision_id}-{metric}-{int(now.timestamp())}", "tenant": "shop",
                    "environment": ENVIRONMENT, "trace_id": f"trace-{decision.decision_id}",
                    "occurred_at": instant(now), "producer": PRODUCER, "customer_ref": decision.customer_ref or None,
                    "metric": MetricRef(id=metric, definition_version="1"),
                    "window": {"start": instant(start), "end": instant(end)}, "source": OUTCOME_SOURCE,
                    "decision_ids": (decision.decision_id,)}
            if end > now:
                outcome = OutcomeEvent(**base, observation="censored")
            elif identity is None:
                outcome = OutcomeEvent(**base, observation="unknown")
            else:
                count = Order.objects.filter(identity, created_at__gte=start, created_at__lt=end).distinct().count()
                outcome = OutcomeEvent(**base, observation="observed", value=count)
            recorded += int(record_outcome(decision, outcome) is not None)
    return {"enabled": 1, "recorded": recorded}
