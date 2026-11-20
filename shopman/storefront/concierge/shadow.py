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


def pending():
    """As entradas do cliente ainda sem decisão, da mais antiga para a mais nova (sem teto: quem corta é o ciclo)."""
    from shopman.shop.models import ConversationMessage

    return (ConversationMessage.objects.select_related("conversation", "binding")
            .filter(role="user", kind="inbound", conversational_decision__isnull=True)
            .order_by("created_at", "pk"))


def identity_of(message) -> str:
    """O degrau da escada de identidade da entrada (P03): a identidade do canal é transportada.

    A ligação do canal (``binding.subject``) é o id do assinante no provedor (ManyChat), não o
    telefone: identifica quem fala no canal, e por isso a entrada é ``transported`` mesmo quando
    a conversa ainda não guardou o telefone. Esse id não acha pedido (o pedido guarda o telefone,
    medido em produção em 20/11/2026). Sem telefone e sem ligação, é anônima, e então o snapshot
    não leva ``subject_ref`` (o contrato recusa sujeito em identidade anônima).
    """
    binding = getattr(message, "binding", None)
    return "transported" if (message.conversation.phone or (binding is not None and binding.subject)) else "anonymous"


#: O provedor da ligação cujo ``subject`` é o id do assinante (ManyChat).
MANYCHAT = "manychat"


def _subscriber_links():
    """Os assinantes do ManyChat ligados a um cliente ativo (``CustomerIdentifier``, gravado pela
    sincronização do assinante no guestman): ``identifier_value`` → cliente."""
    from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType

    return CustomerIdentifier.objects.filter(identifier_type=IdentifierType.MANYCHAT, customer__is_active=True)


def customer_ref_of(conversation_id: int) -> str:
    """O cliente da conversa, por um caminho verificável até ele, ou vazio (#2853).

    1. o ``customer_ref`` que a Concierge gravou na conversa;
    2. o assinante do ManyChat da ligação da conversa (``binding.subject``) já ligado a um
       cliente ativo pelo guestman (``CustomerIdentifier`` do tipo ``manychat``).

    Dois clientes possíveis é ambíguo, e então vazio: a sombra mede, não adivinha. O id do
    assinante nunca é comparado com telefone (não é telefone: medido em produção em 20/11/2026).
    """
    from shopman.shop.models import Conversation, ConversationBinding

    own = Conversation.objects.filter(pk=conversation_id).values_list("customer_ref", flat=True).first()
    if own:
        return own
    subjects = ConversationBinding.objects.filter(conversation_id=conversation_id, provider=MANYCHAT).values("subject")
    refs = set(_subscriber_links().filter(identifier_value__in=subjects).values_list("customer__ref", flat=True))
    return refs.pop() if len(refs) == 1 else ""


def _identity_path():
    """Para ``pending_outcomes``: a conversa da decisão tem hoje um caminho até o cliente."""
    from django.db.models import Exists, OuterRef, Q

    from shopman.shop.models import Conversation, ConversationBinding

    own = Conversation.objects.filter(pk=OuterRef("conversation_id")).filter(~Q(customer_ref="") | ~Q(phone=""))
    linked = ConversationBinding.objects.filter(
        conversation_id=OuterRef("conversation_id"), provider=MANYCHAT,
        subject__in=_subscriber_links().values("identifier_value"))
    return Exists(own) | Exists(linked)


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
        now=now, channel="whatsapp", identity=identity_of(message),
        profile=profile, needs=needs, event_assurance="provider_claimed" if message.external_id else "none",
        subject=Subject(subject_ref=ctx.subject, cart_ref=conversation.session_key or None))
    _read_facts(ctx, state, commerce)
    trace_id = f"trace-{event_id}"
    envelope = {"tenant": ctx.tenant, "environment": ENVIRONMENT, "trace_id": trace_id, "cause_id": event_id,
                "occurred_at": now, "producer": PRODUCER, "episode_id": f"conversation-{conversation.pk}"}
    snapshot = seal(ContextSnapshot(
        id=f"snap-{event_id}", **envelope, episode_version=int(conversation.turn_fence),
        ownership_epoch=int(conversation.turn_fence),
        identity={"subject_ref": ctx.subject if state.identity != "anonymous" else None,
                  "assurance": state.identity},
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
    decided = failed = attempts = 0
    first_failure = None
    for message in pending().iterator():
        # O ciclo para por decisões gravadas ou por tentativas: entrada que falha sempre não
        # ocupa o lote inteiro e não impede as novas de serem decididas.
        if decided >= limit or attempts >= 2 * limit:
            break
        attempts += 1
        try:
            decision, snapshot, acts, unknown = decide_entry(message, profile=profile)
            _, created = record_decision(
                message=message, conversation_id=message.conversation_id, decision=decision,
                snapshot_hash=snapshot.hash, acts=acts, unknown_facts=unknown,
                customer_ref=customer_ref_of(message.conversation_id), entry_at=message.created_at)
            decided += int(created)
        except Exception as error:  # noqa: BLE001 - a sombra nunca derruba o ciclo; a entrada fica para o próximo
            logger.debug("concierge.shadow: decisão falhou message=%s", message.pk, exc_info=True)
            failed += 1
            first_failure = first_failure or (message.pk, error)
    if first_failure is not None:
        # Um aviso por ciclo, com a contagem e o primeiro erro; nunca um por entrada.
        logger.warning("concierge.shadow: %d entradas falharam neste ciclo; a primeira message=%s",
                       failed, first_failure[0], exc_info=first_failure[1])
    return {"enabled": 1, "decided": decided, "failed": failed}


def pending_outcomes(now: datetime):
    """As decisões que a junção ainda tem o que fazer: alguma métrica sem resultado final.

    Final é ``observed`` ou ``not_applicable``, ou ``unknown`` com a janela já fechada e a
    conversa ainda sem caminho até o cliente. Quando o caminho aparece depois (o assinante
    ligado a um cliente, #2853), o ``unknown`` volta, e a junção mede o que faltava.
    ``censored`` e ``unknown`` com a janela aberta voltam. Sem este filtro, a junção pegava sempre as mesmas decisões mais antigas
    e as novas nunca ganhavam resultado (medido em produção em 20/11/2026: 35 de 235 sem resultado).
    """
    from django.db.models import Exists, OuterRef, Q

    from shopman.shop.models import ConversationalDecision, ConversationalOutcome

    current = ConversationalOutcome.objects.filter(decision=OuterRef("pk"), superseded_by__isnull=True)
    settled = current.filter(observation__in=("observed", "not_applicable"))
    unknown_closed = current.filter(observation="unknown", window_end__lte=now)
    path = _identity_path()
    missing = Q()
    for metric, _ in WINDOWS:
        missing |= ~Exists(settled.filter(metric=metric)) & (~Exists(unknown_closed.filter(metric=metric)) | path)
    return ConversationalDecision.objects.filter(missing).order_by("decided_at", "pk")


def join_outcomes(*, now: datetime | None = None, limit: int = SWEEP_LIMIT) -> dict[str, int]:
    """Os pedidos do cliente em 24 h e em 7 dias depois de cada entrada decidida. Só telemetria (P19)."""
    from shopman.orderman.models import Order

    from shopman.shop.conversational.decision_store import current_outcome, record_outcome
    from shopman.shop.models import Conversation
    from shopman.shop.services.customer_orders import customer_identity_filter

    if not enabled():
        return {"enabled": 0, "recorded": 0}
    now = now or datetime.now(UTC)
    recorded = 0
    for decision in pending_outcomes(now)[:limit]:
        conversation = Conversation.objects.filter(pk=decision.conversation_id).first()
        customer_ref = decision.customer_ref or customer_ref_of(decision.conversation_id)
        identity = customer_identity_filter(customer_ref=customer_ref or None,
                                            phone=(conversation.phone or None) if conversation else None)
        for metric, span in WINDOWS:
            current = current_outcome(decision, metric)
            if current is not None and current.observation == "observed":
                continue  # janela fechada já observada: o resultado não muda mais
            # A janela conta da ENTRADA (quando o cliente escreveu), não da decisão: no
            # acumulado a decisão é de hoje, e a janela mediria os pedidos depois de hoje.
            start, end = decision.entry_at, decision.entry_at + span
            # O id leva o microssegundo: duas junções no mesmo segundo não colidem.
            base = {"id": f"out-{decision.decision_id}-{metric}-{int(now.timestamp() * 1_000_000)}", "tenant": "shop",
                    "environment": ENVIRONMENT, "trace_id": f"trace-{decision.decision_id}",
                    "occurred_at": instant(now), "producer": PRODUCER, "customer_ref": customer_ref or None,
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
