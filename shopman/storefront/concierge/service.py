"""Núcleo conversacional independente de provedor e canal.

O ingresso entrega um ``InboundEvent`` normalizado. O núcleo persiste a mensagem
no vínculo exato, enfileira uma diretiva por ``(conversation, binding)`` e devolve
o ACK sem chamar modelo ou fornecedor. O worker preserva a memória lógica da
conversa, mas envia a resposta pelo mesmo vínculo causal que recebeu a entrada.

Tudo que é política de conversa e não é regra de pedido mora aqui: teto diário
de turnos, o que fazer com áudio, o que dizer quando o modelo cai, quando
chamar a equipe. As respostas dessas situações saem do registro de copy
(``OmotenashiCopy``), como toda copy de cliente da casa.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from functools import wraps
from time import perf_counter

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, Max, OuterRef, Q
from django.utils import timezone

from shopman.shop.models import (
    Conversation,
    ConversationBinding,
    ConversationMessage,
    OutboundAttempt,
)

from .contracts import InboundEvent

logger = logging.getLogger(__name__)

TURN_TOPIC = "concierge.turn.v3"


def _observed(stage):
    """Telemetria canônica por etapa, sem corpo, PII ou segredo."""
    def decorate(function):
        @wraps(function)
        def execute(*args, **kwargs):
            from shopman.shop.services.observability import operational_event
            started = perf_counter()
            outcome = "error"
            result = None
            try:
                result = function(*args, **kwargs)
                outcome = (getattr(result, "reason", "") or getattr(result, "transport_state", "")
                           or getattr(result, "fallback", "") or "completed")
                return result
            finally:
                conversation_id = getattr(result, "conversation_id", None)
                if conversation_id is None and args:
                    conversation_id = getattr(args[0], "pk", args[0] if isinstance(args[0], int) else None)
                message_id = getattr(result, "message_id", None)
                if stage == "output" and len(args) > 1:
                    message_id = args[1].pk
                operational_event("concierge.stage", stage=stage, contract_version=3,
                                  conversation_id=conversation_id, message_id=message_id,
                                  turn_fence=getattr(args[0], "turn_fence", None) if args else None,
                                  outcome=outcome, duration_ms=round((perf_counter()-started)*1000, 3))
        return execute
    return decorate

#: Sufixos que denunciam mídia quando um adapter textual entrega uma URL.
_MEDIA_SUFFIXES = (".ogg", ".oga", ".mp3", ".m4a", ".mp4", ".jpg", ".jpeg", ".png", ".webp", ".pdf")
_MEDIA_HOSTS = ("lookaside.fbsbx.com", "cdn.manychat", "manychat.com/", "fbcdn.net")


def config() -> dict:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


def disabled_reason() -> str:
    """Por que o concierge não atende, ou vazio quando atende.

    Duas chaves, dois motivos com nome: a chave de ligar (``SHOPMAN_CONCIERGE_ENABLED``)
    e a credencial da Anthropic (``AI_ASSIST_API_KEY``). Um ``disabled`` sem motivo
    custou uma noite: a chave estava ligada e a credencial, vazia no painel.
    """
    if config().get("contract_version") != 3:
        return "contract_gate"
    if not config().get("enabled"):
        return "switch_off"
    if not (getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip():
        return "ai_key_missing"
    return ""


def is_enabled() -> bool:
    return not disabled_reason()


# ── Copy ──────────────────────────────────────────────────────────────


def copy_message(key: str) -> str:
    """Copy de cliente do registro, no momento do dia atual. Nunca levanta."""
    from shopman.shop.omotenashi.context import OmotenashiContext
    from shopman.shop.omotenashi.copy import resolve_copy

    try:
        moment = OmotenashiContext.from_request(None).moment
    except Exception:
        logger.debug("concierge.copy_message: moment degraded", exc_info=True)
        moment = "*"
    entry = resolve_copy(key, moment=moment)
    return (entry.message or entry.title or "").strip()


# ── Piloto fechado ────────────────────────────────────────────────────


def _subject_allowed(connection, subject: str) -> bool:
    values = connection.options.get("allowed_subjects")
    if not isinstance(values, (list, tuple, set, frozenset)):
        return False
    allowed = {str(value).strip() for value in values or () if str(value).strip()}
    return subject in allowed


def is_allowed(binding: ConversationBinding) -> bool:
    """Admissão escopada pela connection; lista vazia contém a connection."""
    from . import transport

    connection = transport.connection_for(binding)
    return bool(
        connection
        and binding.status == ConversationBinding.Status.ACTIVE
        and _subject_allowed(connection, binding.subject)
    )


# ── Intake ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntakeResult:
    conversation_id: int | None
    message_id: int | None
    queued: bool
    reason: str  # queued | duplicate | handoff | disabled | not_allowed | empty


def _external_id(external_id: str) -> str:
    # O digest cabe no índice, sem truncar a identidade do fornecedor.
    # O envelope conserva o valor integral para auditoria e conflito.
    return "e:" + hashlib.sha256(str(external_id).encode()).hexdigest() if external_id else ""


@_observed("intake")
def receive_inbound(event: InboundEvent) -> IntakeResult:
    """Persiste um evento normalizado; identidade só é concedida pelo adapter."""
    if not isinstance(event, InboundEvent):
        return IntakeResult(None, None, False, "invalid_input")
    subject = event.scope.subject.strip()
    text = event.text.strip()
    if not subject or not text:
        return IntakeResult(None, None, False, "empty")
    reason = disabled_reason()
    if reason:
        logger.warning("concierge.disabled reason=%s", reason)
        return IntakeResult(None, None, False, "disabled")
    if len(event.event_id) > 4096 or len(text) > 16000 or len(subject) > 512:
        return IntakeResult(None, None, False, "invalid_input")
    from . import transport

    connection = transport.connection_for_key(event.scope.connection_key)
    if connection is None or (
        event.scope.provider,
        event.scope.account,
        event.scope.channel,
    ) != (connection.provider, connection.account, connection.channel):
        return IntakeResult(None, None, False, "scope_conflict")
    if not _subject_allowed(connection, subject):
        logger.info("concierge.not_allowed")
        return IntakeResult(None, None, False, "not_allowed")
    verified_event = event.event_identity_assurance == "verified" and bool(event.event_id)
    envelope = event.as_envelope()
    envelope["input_assurance"] = "provider_event" if verified_event else "at_least_once"
    ext = _external_id(event.event_id) if verified_event else ""
    with transaction.atomic():
        binding = _get_or_create_binding(event)
        if binding.connection_key != event.scope.connection_key:
            return IntakeResult(binding.conversation_id, None, False, "scope_conflict")
        if not is_allowed(binding):
            logger.info("concierge.not_allowed")
            return IntakeResult(binding.conversation_id, None, False, "not_allowed")
        conversation = binding.conversation
        conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        values = {
            "role": ConversationMessage.Role.USER,
            "kind": ConversationMessage.Kind.INBOUND,
            "text": text,
            "content": [{"type": "text", "text": text}],
            "envelope": envelope,
            "binding": binding,
        }
        if not verified_event:
            # Sem ID verificável, cada POST autenticado é receipt local at-least-once.
            message = ConversationMessage.objects.create(conversation=conversation, external_id="", **values)
            created = True
        else:
            message, created = ConversationMessage.objects.get_or_create(
                binding=binding,
                external_id=ext,
                defaults={"conversation": conversation, **values},
            )
        if not created and (message.text != text or message.envelope.get("event_id") != event.event_id or message.envelope.get("payload_hash") != envelope.get("payload_hash")):
            return IntakeResult(conversation.pk, message.pk, False, "intent_conflict")
        if created:
            Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=event.received_at)
            ConversationBinding.objects.filter(pk=binding.pk).update(last_inbound_at=event.received_at)
        if conversation.state != Conversation.State.ACTIVE:
            return IntakeResult(conversation.pk, message.pk, False, "handoff")
        # Replay repara trabalho perdido; efeito e agendamento têm o mesmo commit.
        _enqueue_turn(conversation, binding)
    return IntakeResult(conversation.pk, message.pk, True, "queued" if created else "duplicate")


def _enqueue_turn(conversation: Conversation, binding: ConversationBinding) -> None:
    from shopman.shop.directives import create_deduped

    delay = int(config().get("dispatch_delay_seconds") or 1)
    # ``available_at`` no futuro: o dispatcher por signal pula a diretiva e ela
    # fica para o worker. Sem isso o turno rodaria INLINE no request do webhook,
    # e o ManyChat cortaria a chamada em 10 s.
    create_deduped(
        TURN_TOPIC,
        payload={"conversation_id": conversation.pk, "binding_id": binding.pk, "contract_version": 3},
        dedupe_key=f"{TURN_TOPIC}:{conversation.pk}:{binding.pk}",
        available_at=timezone.now() + timedelta(seconds=max(delay, 1)),
    )


def _get_or_create_binding(event: InboundEvent) -> ConversationBinding:
    """Resolve identidade exata; nunca une jornadas por nome/telefone do payload."""
    scope = event.scope
    binding = ConversationBinding.objects.select_related("conversation").filter(
        provider=scope.provider,
        account=scope.account,
        transport_channel=scope.channel,
        subject=scope.subject,
    ).first()
    if binding:
        return binding
    try:
        with transaction.atomic():
            conversation = Conversation.objects.create(
                channel_ref=str(config().get("channel_ref") or "web")
            )
            return ConversationBinding.objects.create(
                conversation=conversation,
                connection_key=scope.connection_key,
                provider=scope.provider,
                account=scope.account,
                transport_channel=scope.channel,
                subject=scope.subject,
                status=ConversationBinding.Status.ACTIVE,
                identity_assurance="transport_subject",
                activated_at=event.received_at,
            )
    except IntegrityError:
        # Outro ACK venceu a corrida. A unicidade do binding escolhe o vencedor;
        # o savepoint remove também a conversa órfã desta tentativa.
        return ConversationBinding.objects.select_related("conversation").get(
            provider=scope.provider,
            account=scope.account,
            transport_channel=scope.channel,
            subject=scope.subject,
        )


def identify(
    conversation: Conversation,
    binding: ConversationBinding,
    profile: dict | None = None,
) -> Conversation:
    """Enriquece identidade pelo adapter; conflito contém a conversa."""
    from shopman.storefront.concierge import transport

    try:
        info = transport.identity_for(binding, profile)
    except Exception:
        logger.warning("concierge.identify failed conversation=%s", conversation.pk)
        info = None
    if info is None:
        return conversation

    from shopman.guestman.services import customer as customer_service

    customer = customer_service.get_by_uuid(str(info.uuid))
    proposed = (
        (info.phone or "").strip(),
        getattr(customer, "ref", "") or "",
        (info.name or "").strip(),
    )
    established = (conversation.phone, conversation.customer_ref, conversation.customer_name)
    if any(old and new and old != new for old, new in zip(established[:2], proposed[:2], strict=True)):
        Conversation.objects.filter(pk=conversation.pk).update(
            state=Conversation.State.HANDOFF,
            handoff_reason="conflito de identidade",
            handoff_at=timezone.now(),
            turn_fence=F("turn_fence") + 1,
            claim_until=None,
        )
        _alert(conversation, "concierge_identity_conflict", "Identidade divergente; atendimento humano mantido.")
        return conversation
    conversation.phone = established[0] or proposed[0]
    conversation.customer_ref = established[1] or proposed[1]
    conversation.customer_name = established[2] or proposed[2]
    conversation.save(update_fields=["phone", "customer_name", "customer_ref", "updated_at"])
    if conversation.customer_ref:
        ConversationBinding.objects.filter(pk=binding.pk).update(
            identity_assurance="verified_customer"
        )
        binding.identity_assurance = "verified_customer"
    return conversation


# ── Turno ─────────────────────────────────────────────────────────────


@dataclass
class TurnResult:
    conversation_id: int
    replies: list[str] = field(default_factory=list)
    handoff: bool = False
    processed_message_ids: list[int] = field(default_factory=list)
    pending_more: bool = False
    fallback: str = ""


def unanswered_inbound(
    conversation: Conversation, binding: ConversationBinding
) -> list[ConversationMessage]:
    """Retorna somente entradas v3 pendentes do vínculo causal."""
    return list(
        conversation.messages.filter(
            binding=binding,
            kind=ConversationMessage.Kind.INBOUND,
            consumed_by__isnull=True,
            envelope__version=3,
        ).order_by("id")
    )


class TurnRevoked(Exception):
    """O claim não tem mais autoridade; preservar entradas e efeitos."""


def assert_turn_authority(conversation, *, for_mutation=True):
    from . import transport

    binding_id = getattr(conversation, "_binding_id", None)
    fence = getattr(conversation, "_turn_fence", None)
    if not binding_id or fence is None:
        raise TurnRevoked("claim_required")
    current = Conversation.objects.get(pk=conversation.pk)
    binding = ConversationBinding.objects.filter(pk=binding_id, conversation=current).first()
    if binding is None or transport.adapter_for(binding) is None:
        raise TurnRevoked("transport_scope_mismatch")
    if (current.customer_ref, current.phone, current.channel_ref) != (
        conversation.customer_ref,
        conversation.phone,
        conversation.channel_ref,
    ):
        raise TurnRevoked("identity_changed")
    if not is_enabled() or not is_allowed(binding) or current.state != Conversation.State.ACTIVE:
        raise TurnRevoked("contained")
    if current.turn_fence != fence or not current.claim_until or current.claim_until <= timezone.now():
        raise TurnRevoked("claim_expired")
    if for_mutation and not getattr(conversation, "_commercial_authority", False):
        raise TurnRevoked("commercial_authority_missing")
    if for_mutation and current.messages.filter(
        kind=ConversationMessage.Kind.INBOUND,
        envelope__version=3,
        pk__gt=conversation._inbound_max_id,
    ).exists():
        raise TurnRevoked("new_input")
    return current


def _claim(conversation_id: int, binding_id: int):
    from . import transport

    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
        binding = ConversationBinding.objects.select_for_update().get(
            pk=binding_id, conversation=conversation
        )
        if transport.adapter_for(binding) is None:
            return conversation, binding, []
        if not is_enabled() or not is_allowed(binding) or conversation.state != Conversation.State.ACTIVE:
            return conversation, binding, []
        if conversation.claim_until and conversation.claim_until > timezone.now():
            conversation._claim_busy = True
            return conversation, binding, []
        inbound = unanswered_inbound(conversation, binding)[:20]
        if not inbound:
            return conversation, binding, []
        conversation.turn_fence += 1
        conversation.claim_until = timezone.now() + timedelta(seconds=120)
        conversation.save(update_fields=["turn_fence", "claim_until"])
        adapter = transport.adapter_for(binding)
        connection = transport.connection_for(binding)
        conversation._turn_fence = conversation.turn_fence
        conversation._binding = binding
        conversation._binding_id = binding.pk
        conversation._inbound_max_id = inbound[-1].pk
        conversation._inbound_ids = [message.pk for message in inbound]
        conversation._limited_event_assurance = bool(
            config().get("read_only")
            or (connection and connection.options.get("read_only"))
            or not adapter.capabilities.stable_event_identity_verified
            or any(message.envelope.get("input_assurance") != "provider_event" for message in inbound)
        )
        conversation._commercial_authority = bool(
            not conversation._limited_event_assurance
            and binding.identity_assurance == "verified_customer"
        )
        return conversation, binding, inbound


def _looks_like_media(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered.startswith(("http://", "https://")):
        return False
    return lowered.endswith(_MEDIA_SUFFIXES) or any(host in lowered for host in _MEDIA_HOSTS)


def _bump_turn_counter(conversation: Conversation) -> int:
    today = timezone.localdate()
    if conversation.turns_day != today:
        conversation.turns_day = today
        conversation.turns_today = 0
    conversation.turns_today += 1
    conversation.save(update_fields=["turns_day", "turns_today", "updated_at"])
    return conversation.turns_today


def _best_window_evidence(
    binding: ConversationBinding,
    inbound: list[ConversationMessage],
    *,
    purpose: str = "reply",
):
    """Escolhe a prova válida mais duradoura sem fundir evidências."""
    from . import transport

    now = timezone.now()
    candidates = []
    for message in inbound:
        evidence = (message.envelope or {}).get("window_evidence")
        decision = transport.response_authorization(
            binding, evidence, now, purpose=purpose
        )
        if decision.allowed and decision.valid_until is not None:
            candidates.append((decision.valid_until, message.pk, evidence))
    return max(candidates, default=(None, None, None))[2]


@_observed("turn")
def run_turn(conversation_id: int, binding_id: int, *, client=None) -> TurnResult:
    """Processa uma entrada pelo vínculo causal e preserva a conversa lógica."""
    conversation, binding, inbound = _claim(conversation_id, binding_id)
    result = TurnResult(
        conversation_id=conversation.pk,
        pending_more=bool(getattr(conversation, "_claim_busy", False)),
    )
    if not inbound:
        return result
    ids = [message.pk for message in inbound]
    window_evidence = _best_window_evidence(binding, inbound)
    from shopman.storefront.concierge import agent as agent_module

    try:
        assert_turn_authority(conversation, for_mutation=False)
        human_phrases = {
            "humano",
            "atendente",
            "quero falar com alguém",
            "quero falar com alguem",
            "falar com atendente",
            "quero atendimento humano",
        }
        if any(message.text.casefold().strip(" .!?") in human_phrases for message in inbound):
            mark_handoff(conversation, binding, "pedido do cliente", consumed_ids=ids)
            return TurnResult(conversation.pk, handoff=True, processed_message_ids=ids)
        if not conversation.customer_ref and not conversation._limited_event_assurance:
            identify(conversation, binding, inbound[0].envelope.get("profile") or {})
            conversation._commercial_authority = bool(
                conversation.customer_ref
                and binding.identity_assurance == "verified_customer"
            )
        assert_turn_authority(conversation, for_mutation=False)
        if conversation._limited_event_assurance:
            from . import tools

            reply = copy_message("CONCIERGE_LIMITED_ASSURANCE")
            menu_requests = {"menu", "cardápio", "cardapio", "oi", "olá", "ola"}
            if any(
                message.text.casefold().strip(" .!?") in menu_requests
                or message.text.casefold().startswith("#menu ")
                for message in inbound
            ):
                ctx = tools.ToolContext(conversation=conversation, channel_ref=conversation.channel_ref)
                reply = tools.render_result("browse_menu", tools.browse_menu(ctx)) + "\n\n" + reply
            outcome = agent_module.AgentOutcome(reply_text=reply)
            result.fallback = "limited_assurance"
        elif all(_looks_like_media(message.text) for message in inbound):
            outcome = agent_module.AgentOutcome(reply_text=copy_message("CONCIERGE_MEDIA_UNSUPPORTED"))
            result.fallback = "media"
        elif _bump_turn_counter(conversation) > int(config().get("max_turns_per_day") or 80):
            outcome = agent_module.AgentOutcome(reply_text=copy_message("CONCIERGE_TURN_LIMIT"))
            result.fallback = "turn_limit"
        else:
            try:
                outcome = agent_module.run_agent(
                    conversation=conversation,
                    history=agent_module.history_for(conversation),
                    client=client,
                )
            except TurnRevoked:
                raise
            except Exception:
                logger.error("concierge.turn_failed conversation=%s", conversation.pk)
                Conversation.objects.filter(pk=conversation.pk).update(
                    consecutive_failures=F("consecutive_failures") + 1
                )
                _alert(
                    conversation,
                    "concierge_unavailable",
                    "Resposta automática indisponível; contexto preservado.",
                )
                outcome = agent_module.AgentOutcome(reply_text=copy_message("CONCIERGE_UNAVAILABLE"))
                result.fallback = "error"
        if outcome.handoff:
            mark_handoff(
                conversation,
                binding,
                outcome.handoff_reason or "pedido do cliente",
                consumed_ids=ids,
            )
            return TurnResult(conversation.pk, handoff=True, processed_message_ids=ids)
        from .transport import semantic_blocks

        primary = semantic_blocks(binding, outcome.reply_text) if outcome.reply_text else []
        texts = [*primary, *[text for text in outcome.extra_replies if text and text.strip()]]
        with transaction.atomic():
            Conversation.objects.select_for_update().get(pk=conversation.pk)
            assert_turn_authority(conversation, for_mutation=False)
            _persist_outcome(conversation, outcome)
            prepared = []
            for index, text in enumerate(texts):
                prepared.append(
                    _prepare_reply(
                        conversation,
                        binding,
                        text,
                        quote_token=(
                            getattr(outcome, "quote_token", "")
                            if index == len(primary) - 1
                            else ""
                        ),
                        disclosure=(
                            getattr(outcome, "disclosure", {})
                            if index == len(primary) - 1
                            else {}
                        ),
                        depends_on=prepared[-1].pk if prepared else None,
                        window_evidence=window_evidence,
                    )
                )
            if not prepared:
                _alert(
                    conversation,
                    "concierge_empty_output",
                    "Entrada sem resposta útil; atendimento necessário.",
                )
                Conversation.objects.filter(pk=conversation.pk).update(
                    state=Conversation.State.HANDOFF
                )
                return result
            ConversationMessage.objects.filter(
                pk__in=ids, binding=binding, consumed_by__isnull=True
            ).update(consumed_by=conversation.turn_fence)
            Conversation.objects.filter(pk=conversation.pk).update(
                consecutive_failures=(
                    0 if not result.fallback else F("consecutive_failures")
                ),
                input_tokens=F("input_tokens") + int(outcome.usage.get("input_tokens") or 0),
                output_tokens=F("output_tokens") + int(outcome.usage.get("output_tokens") or 0),
                cache_read_tokens=F("cache_read_tokens")
                + int(outcome.usage.get("cache_read_input_tokens") or 0),
                last_order_ref=outcome.order_ref or conversation.last_order_ref,
            )
        result.processed_message_ids = ids
        for message in prepared:
            _dispatch_reply(conversation, message)
        result.replies = texts
    except TurnRevoked:
        result.fallback = "revoked"
    finally:
        Conversation.objects.filter(
            pk=conversation.pk, turn_fence=conversation.turn_fence
        ).update(claim_until=None)
    result.pending_more = bool(unanswered_inbound(conversation, binding))
    return result


def _persist_outcome(conversation: Conversation, outcome) -> None:
    kinds = {
        "assistant": ConversationMessage.Kind.TOOL_CALL,
        "user": ConversationMessage.Kind.TOOL_RESULT,
    }
    for message in outcome.messages:
        role = message["role"]
        content = message["content"]
        if role == "assistant" and not any(block.get("type") == "tool_use" for block in content):
            continue
        ConversationMessage.objects.create(
            conversation=conversation,
            role=role,
            kind=kinds[role],
            content=content,
            text="",
        )


def _prepare_reply(
    conversation,
    binding,
    text,
    *,
    quote_token="",
    disclosure=None,
    depends_on=None,
    purpose="reply",
    window_evidence=None,
):
    return ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text=text,
        content=[{"type": "text", "text": text}],
        transport_state="prepared",
        envelope={
            "version": 3,
            "connection_key": binding.connection_key,
            "turn_fence": conversation.turn_fence,
            "purpose": purpose,
            "quote_token": quote_token,
            "disclosure": disclosure or {},
            "depends_on": depends_on,
            "inbound_max_id": getattr(conversation, "_inbound_max_id", None),
            "window_evidence": window_evidence,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        },
    )


def _next_attempt_no(message: ConversationMessage) -> int:
    current = message.outbound_attempts.aggregate(value=Max("attempt_no"))["value"] or 0
    return current + 1


@_observed("output")
def _dispatch_reply(conversation, message):
    from shopman.storefront.concierge import transport

    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        message = ConversationMessage.objects.select_for_update().get(pk=message.pk)
        binding = ConversationBinding.objects.select_for_update().get(pk=message.binding_id)
        if message.transport_state != "prepared":
            return message
        purpose = message.envelope.get("purpose") or "reply"
        handoff_ack = purpose == "handoff_ack" and current.state == Conversation.State.HANDOFF
        enabled = (
            bool(config().get("enabled") and config().get("contract_version") == 3)
            if handoff_ack
            else is_enabled()
        )
        predecessor = message.envelope.get("depends_on")
        code = ""
        if predecessor and not current.messages.filter(
            pk=predecessor, transport_state="accepted"
        ).exists():
            code = "preceding_block_pending"
        elif (
            not enabled
            or not is_allowed(binding)
            or (current.state != Conversation.State.ACTIVE and not handoff_ack)
            or current.turn_fence != message.envelope.get("turn_fence")
            or message.envelope.get("connection_key") != binding.connection_key
        ):
            code = "contained"
        else:
            authorization = transport.response_authorization(
                binding,
                message.envelope.get("window_evidence"),
                timezone.now(),
                purpose=purpose,
            )
            if not authorization.allowed:
                code = authorization.code
        attempt = OutboundAttempt.objects.create(
            message=message,
            binding=binding,
            attempt_no=_next_attempt_no(message),
            state=(
                OutboundAttempt.State.NOT_APPLIED
                if code
                else OutboundAttempt.State.EXECUTING
            ),
            code=code,
            payload_hash=message.envelope.get("content_hash")
            or hashlib.sha256(message.text.encode()).hexdigest(),
            completed_at=timezone.now() if code else None,
        )
        message.transport_state = attempt.state
        message.envelope = {**message.envelope, "code": code, "attempt_no": attempt.attempt_no}
        message.save(update_fields=["transport_state", "envelope"])
    if attempt.state != OutboundAttempt.State.EXECUTING:
        _alert(
            current,
            "concierge_output_blocked",
            "Resposta preparada e contida; verificar próxima ação de atendimento.",
        )
        return message
    try:
        outcome = transport.send_for(binding, message.text)
    except Exception as exc:
        logger.warning(
            "concierge.dispatch.acceptance_unconfirmed conversation=%s message=%s exception_type=%s",
            current.pk,
            message.pk,
            type(exc).__name__,
        )
        from .contracts import SendOutcome

        outcome = SendOutcome("unknown", "acceptance_unconfirmed")
    completed_at = timezone.now()
    try:
        with transaction.atomic():
            attempt = OutboundAttempt.objects.select_for_update().get(pk=attempt.pk)
            if attempt.state == OutboundAttempt.State.EXECUTING:
                attempt.state = outcome.state
                attempt.code = outcome.code
                attempt.provider_receipt_ref = outcome.provider_receipt_ref
                attempt.completed_at = completed_at
                attempt.save(
                    update_fields=["state", "code", "provider_receipt_ref", "completed_at"]
                )
                ConversationMessage.objects.filter(pk=message.pk).update(
                    transport_state=outcome.state,
                    envelope={**message.envelope, "code": outcome.code},
                )
    except IntegrityError:
        OutboundAttempt.objects.filter(pk=attempt.pk).update(
            state=OutboundAttempt.State.UNKNOWN,
            code="provider_receipt_conflict",
            provider_receipt_ref="",
            completed_at=completed_at,
        )
        ConversationMessage.objects.filter(pk=message.pk).update(
            transport_state=OutboundAttempt.State.UNKNOWN
        )
        outcome = type(outcome)("unknown", "provider_receipt_conflict")
    message.refresh_from_db()
    if outcome.state == "accepted":
        Conversation.objects.filter(pk=current.pk).update(last_outbound_at=completed_at)
        ConversationBinding.objects.filter(pk=binding.pk).update(last_outbound_at=completed_at)
    else:
        _alert(
            current,
            "concierge_output_pending",
            f"Resposta com resultado {outcome.state}; consultar evidência antes de agir.",
        )
    return message


def _send_reply(
    conversation: Conversation, binding: ConversationBinding, text: str, *, window_evidence=None
) -> ConversationMessage:
    return _dispatch_reply(
        conversation,
        _prepare_reply(
            conversation, binding, text, window_evidence=window_evidence
        ),
    )


# ── Handoff ───────────────────────────────────────────────────────────


def _execute_handoff(binding: ConversationBinding, on: bool):
    """Sincroniza a atribuição idempotente e conserva incerteza por vínculo."""
    from shopman.storefront.concierge import transport

    ConversationBinding.objects.filter(pk=binding.pk).update(
        handoff_sync_state="executing"
    )
    try:
        outcome = transport.handoff_for(binding, on)
    except Exception as exc:
        logger.warning(
            "concierge.handoff.acceptance_unconfirmed binding=%s exception_type=%s",
            binding.pk,
            type(exc).__name__,
        )
        from .contracts import HandoffOutcome

        outcome = HandoffOutcome("unknown", "acceptance_unconfirmed")
    ConversationBinding.objects.filter(pk=binding.pk).update(
        handoff_sync_state=outcome.state
    )
    return outcome


def mark_handoff(
    conversation: Conversation,
    causal_binding: ConversationBinding,
    reason: str,
    *,
    consumed_ids=(),
) -> bool:
    """Transfere a posse local e sincroniza cada vínculo ativo."""
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        current.state = Conversation.State.HANDOFF
        current.turn_fence += 1
        current.claim_until = None
        current.handoff_reason = (reason or "")[:200]
        current.handoff_at = timezone.now()
        current.save(
            update_fields=[
                "state",
                "turn_fence",
                "claim_until",
                "handoff_reason",
                "handoff_at",
                "updated_at",
            ]
        )
        bindings = list(
            current.transport_bindings.select_for_update().filter(
                status=ConversationBinding.Status.ACTIVE
            )
        )
        ConversationBinding.objects.filter(pk__in=[item.pk for item in bindings]).update(
            handoff_sync_state="executing"
        )
        current.messages.filter(
            pk__in=consumed_ids,
            binding=causal_binding,
            kind=ConversationMessage.Kind.INBOUND,
            consumed_by__isnull=True,
        ).update(consumed_by=current.turn_fence)
        ConversationMessage.objects.create(
            conversation=current,
            role=ConversationMessage.Role.ASSISTANT,
            kind=ConversationMessage.Kind.NOTE,
            text="Atendimento humano solicitado. Contexto preservado.",
            envelope={
                "version": 3,
                "session_key": current.session_key,
                "order_ref": current.last_order_ref,
                "turn_fence": current.turn_fence,
            },
        )
    accepted = True
    for binding in bindings:
        outcome = _execute_handoff(binding, True)
        accepted &= outcome.state == "accepted"
    _alert(
        current,
        "concierge_handoff",
        "Atendimento solicitado; sincronização "
        + ("aceita em todos os vínculos." if accepted else "pendente em pelo menos um vínculo."),
    )
    if consumed_ids:
        current._inbound_max_id = max(consumed_ids)
        evidence = (
            ConversationMessage.objects.filter(pk=current._inbound_max_id)
            .values_list("envelope__window_evidence", flat=True)
            .first()
        )
        ack = copy_message("CONCIERGE_HANDOFF_ACK")
        if ack:
            _dispatch_reply(
                current,
                _prepare_reply(
                    current,
                    causal_binding,
                    ack,
                    purpose="handoff_ack",
                    window_evidence=evidence,
                ),
            )
    conversation.refresh_from_db()
    return accepted


def return_to_concierge(conversation: Conversation) -> bool:
    """Reativa somente após aceite remoto em todos os vínculos ativos."""
    if not config().get("human_return_enabled") or not is_enabled():
        return False
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        bindings = list(
            current.transport_bindings.select_for_update().filter(
                status=ConversationBinding.Status.ACTIVE
            )
        )
        if (
            current.state != Conversation.State.HANDOFF
            or not bindings
            or any(not is_allowed(binding) for binding in bindings)
            or any(binding.handoff_sync_state == "executing" for binding in bindings)
        ):
            return False
        fence = current.turn_fence
        ConversationBinding.objects.filter(pk__in=[item.pk for item in bindings]).update(
            handoff_sync_state="executing"
        )
    outcomes = []
    for binding in bindings:
        outcome = _execute_handoff(binding, False)
        outcomes.append((binding, outcome))
    synced = all(outcome.state == "accepted" for _, outcome in outcomes)
    if not synced:
        # Retorno parcial pode deixar um canal com bot e outro com humano. Repor
        # a posse humana nos vínculos já aceitos é a compensação conservadora.
        for binding, outcome in outcomes:
            if outcome.state != "accepted":
                continue
            _execute_handoff(binding, True)
    restore_after_revalidation = False
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if current.turn_fence != fence:
            return False
        bindings = list(
            current.transport_bindings.select_for_update().filter(
                status=ConversationBinding.Status.ACTIVE
            )
        )
        if synced and (not is_enabled() or any(not is_allowed(binding) for binding in bindings)):
            synced = False
            restore_after_revalidation = True
            ConversationBinding.objects.filter(pk__in=[item.pk for item in bindings]).update(
                handoff_sync_state="routing_mismatch"
            )
        if synced:
            current.state = Conversation.State.ACTIVE
            current.turn_fence += 1
            current.handoff_reason = ""
            current.handoff_at = None
            current.save(
                update_fields=[
                    "state",
                    "turn_fence",
                    "handoff_reason",
                    "handoff_at",
                    "updated_at",
                ]
            )
            ConversationMessage.objects.create(
                conversation=current,
                role=ConversationMessage.Role.ASSISTANT,
                kind=ConversationMessage.Kind.NOTE,
                text="Voltou para o concierge.",
                envelope={"version": 3, "turn_fence": current.turn_fence},
            )
            for binding in bindings:
                if unanswered_inbound(current, binding):
                    _enqueue_turn(current, binding)
    if restore_after_revalidation:
        for binding in bindings:
            _execute_handoff(binding, True)
    if not synced:
        _alert(
            current,
            "concierge_handoff_sync",
            "Retorno não confirmado em todos os vínculos. Atendimento humano mantido.",
        )
    conversation.refresh_from_db()
    return synced


def _alert(conversation: Conversation, alert_type: str, message: str) -> None:
    try:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type=alert_type,
            severity="warning",
            message=f"{message} Conversa #{conversation.pk}: /admin/shop/conversation/{conversation.pk}/change/; responsável: atendimento; consultar transcrição e próximo efeito autorizado.",
            dedupe_key=f"concierge:{conversation.pk}:{alert_type}",
            order_ref=conversation.last_order_ref,
            conversation_id=conversation.pk, owner_role="atendimento", action="inspect_conversation",

        )
    except Exception:
        logger.warning("concierge.alert_failed type=%s conversation=%s", alert_type, conversation.pk, exc_info=True)


def recover_pending(*, limit=100):
    """Recupera claims e trabalho v3 sem repetir uma saída já iniciada."""
    from shopman.orderman.models import Directive

    now = timezone.now()
    stale_at = now - timedelta(seconds=120)
    counts = {"queued": 0, "unknown": 0}
    pending = ConversationMessage.objects.filter(conversation_id=OuterRef("pk")).filter(
        Q(
            kind=ConversationMessage.Kind.INBOUND,
            envelope__version=3,
            consumed_by__isnull=True,
        )
        | Q(transport_state__in=["prepared", "executing"])
    )
    stale_handoff = ConversationBinding.objects.filter(
        conversation_id=OuterRef("pk"),
        handoff_sync_state="executing",
        updated_at__lte=stale_at,
    )
    ids = list(
        Conversation.objects.annotate(
            has_pending=Exists(pending), has_stale_handoff=Exists(stale_handoff)
        )
        .filter(Q(claim_until__isnull=True) | Q(claim_until__lte=now))
        .filter(
            Q(has_pending=True)
            | Q(has_stale_handoff=True)
            | Q(claim_until__lte=now)
        )
        .order_by("last_inbound_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    for conversation_id in ids:
        prepared = []
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
            if conversation.claim_until and conversation.claim_until > now:
                continue
            if conversation.claim_until:
                conversation.turn_fence += 1
                conversation.claim_until = None
                conversation.save(update_fields=["turn_fence", "claim_until"])
            attempts = OutboundAttempt.objects.select_for_update().filter(
                message__conversation=conversation,
                state=OutboundAttempt.State.EXECUTING,
            )
            unknown = attempts.update(
                state=OutboundAttempt.State.UNKNOWN,
                code="worker_interrupted",
                completed_at=now,
            )
            conversation.messages.filter(transport_state="executing").update(
                transport_state="unknown"
            )
            counts["unknown"] += unknown
            if unknown:
                _alert(
                    conversation,
                    "concierge_output_pending",
                    "Processo interrompido após iniciar envio. Resultado desconhecido; não repetir.",
                )
            ConversationBinding.objects.filter(
                conversation=conversation,
                handoff_sync_state="executing",
                updated_at__lte=stale_at,
            ).update(handoff_sync_state="unknown")
            Directive.objects.filter(
                topic=TURN_TOPIC,
                payload__conversation_id=conversation_id,
                status="running",
                started_at__lt=stale_at,
            ).update(
                status="failed",
                error_code="claim_expired",
                last_error="recovered by conversation fence",
            )
            if is_enabled() and conversation.state == Conversation.State.ACTIVE:
                for binding in conversation.transport_bindings.filter(
                    status=ConversationBinding.Status.ACTIVE
                ):
                    if unanswered_inbound(conversation, binding):
                        _enqueue_turn(conversation, binding)
                        counts["queued"] += 1
            prepared = list(
                conversation.messages.select_related("binding").filter(
                    transport_state="prepared", envelope__version=3
                )
            )
            for message in prepared:
                envelope = message.envelope
                max_id = envelope.get("inbound_max_id")
                unchanged = bool(max_id) and not conversation.messages.filter(
                    kind=ConversationMessage.Kind.INBOUND, pk__gt=max_id
                ).exists()
                quote_token = envelope.get("quote_token")
                if quote_token and quote_token != (conversation.quote or {}).get("token"):
                    unchanged = False
                if unchanged and conversation.state == Conversation.State.ACTIVE:
                    message.envelope = {
                        **envelope,
                        "previous_fence": envelope.get("turn_fence"),
                        "turn_fence": conversation.turn_fence,
                    }
                    message.save(update_fields=["envelope"])
                else:
                    message.transport_state = "not_applied"
                    message.envelope = {**envelope, "code": "stale_prepared_output"}
                    message.save(update_fields=["transport_state", "envelope"])
        for message in prepared:
            message.refresh_from_db()
            if message.transport_state == "prepared":
                _dispatch_reply(conversation, message)
    return counts


def retry_not_applied(conversation_id, message_id):
    """Nova tentativa somente quando o fornecedor comprovou não aplicação."""
    if not config().get("output_retry_enabled"):
        return False
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
        message = conversation.messages.select_for_update().get(
            pk=message_id, kind=ConversationMessage.Kind.REPLY
        )
        binding = ConversationBinding.objects.select_for_update().filter(
            pk=message.binding_id,
            conversation=conversation,
        ).first()
        if (
            message.transport_state != "not_applied"
            or binding is None
            or conversation.state != Conversation.State.ACTIVE
            or not is_enabled()
            or not is_allowed(binding)
        ):
            return False
        last_attempt = message.outbound_attempts.order_by("-attempt_no").first()
        if last_attempt is None or last_attempt.state != OutboundAttempt.State.NOT_APPLIED:
            return False
        max_id = message.envelope.get("inbound_max_id")
        if not max_id or conversation.messages.filter(
            kind=ConversationMessage.Kind.INBOUND, pk__gt=max_id
        ).exists():
            return False
        quote_token = message.envelope.get("quote_token")
        if quote_token and quote_token != (conversation.quote or {}).get("token"):
            return False
        predecessor = message.envelope.get("depends_on")
        if predecessor and not conversation.messages.filter(
            pk=predecessor, transport_state="accepted"
        ).exists():
            return False
        message.transport_state = "prepared"
        message.envelope = {
            **message.envelope,
            "turn_fence": conversation.turn_fence,
            "explicit_retry": int(message.envelope.get("explicit_retry", 0)) + 1,
        }
        message.save(update_fields=["transport_state", "envelope"])
    message = _dispatch_reply(conversation, message)
    return message.transport_state == "accepted"


def apply_delivery_receipt(
    binding: ConversationBinding, provider_receipt_ref: str, state: str
) -> bool:
    """Aplica callback monotônico ao recibo exato do fornecedor."""
    from shopman.storefront.concierge import transport

    ranks = {"accepted": 1, "delivered": 2, "read": 3}
    adapter = transport.adapter_for(binding)
    if (
        state not in ranks
        or not provider_receipt_ref
        or adapter is None
        or not adapter.capabilities.delivery_receipts
    ):
        return False
    with transaction.atomic():
        attempt = (
            OutboundAttempt.objects.select_for_update()
            .select_related("message")
            .filter(binding=binding, provider_receipt_ref=provider_receipt_ref)
            .first()
        )
        if attempt is None or attempt.state not in ranks or ranks[state] < ranks[attempt.state]:
            return False
        if ranks[state] == ranks[attempt.state]:
            return True
        attempt.state = state
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=["state", "completed_at"])
        attempt.message.transport_state = state
        attempt.message.save(update_fields=["transport_state"])
    return True
