"""A porta do concierge: receber a mensagem, rodar o turno, responder.

Duas entradas, e nenhuma delas fala com o modelo diretamente:

- ``receive_inbound``: chamado pelo webhook (External Request do ManyChat). Guarda
  a mensagem e enfileira UMA diretiva ``concierge.turn.v2``
  por conversa. Volta em milissegundos: o ManyChat corta em 10 s, e um turno com
  ferramentas não cabe nisso com folga.
- ``run_turn``: chamado pelo handler da diretiva (worker). Junta as mensagens
  ainda sem resposta, roda o agente, persiste a transcrição e envia a resposta
  pelo transporte. Se chegou mensagem nova enquanto rodava, avisa que há mais.

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
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationMessage

logger = logging.getLogger(__name__)

TURN_TOPIC = "concierge.turn.v2"


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
                operational_event("concierge.stage", stage=stage, contract_version=2,
                                  conversation_id=conversation_id, message_id=message_id,
                                  turn_fence=getattr(args[0], "turn_fence", None) if args else None,
                                  outcome=outcome, duration_ms=round((perf_counter()-started)*1000, 3))
        return execute
    return decorate

#: Sufixos que denunciam mídia: desde 04/2025 o ManyChat entrega áudio/imagem
#: como URL em ``last_input_text``. O concierge só lê texto por enquanto.
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
    if config().get("contract_version") != 2:
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


def allowed_subscribers() -> list[str]:
    return [str(v).strip() for v in (config().get("allowed_subscribers") or []) if str(v).strip()]


def is_allowed(subscriber_id: str, profile: dict | None = None) -> bool:
    """Admissão por subject explícito; lista vazia contém o canal.

    Telefone informado no payload não é prova de identidade de transporte.
    Nenhum enriquecimento remoto pertence ao ACK.
    """
    return str(subscriber_id or "").strip() in allowed_subscribers()


# ── Intake ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntakeResult:
    conversation_id: int | None
    message_id: int | None
    queued: bool
    reason: str  # queued | duplicate | handoff | disabled | not_allowed | empty


def _external_id(subscriber_id: str, text: str, external_id: str) -> str:
    # O digest cabe no índice legado, sem truncar a identidade do fornecedor.
    # O envelope conserva o valor integral para auditoria e conflito.
    return "e:" + hashlib.sha256(str(external_id).encode()).hexdigest() if external_id else ""


@_observed("intake")
def receive_inbound(
    *,
    subscriber_id: str,
    text: str,
    external_id: str = "",
    profile: dict | None = None,
    envelope: dict | None = None,
) -> IntakeResult:
    """Guarda a mensagem e enfileira o turno. Idempotente por ``external_id``."""
    if not isinstance(text, str) or not isinstance(subscriber_id, (str, int)) or isinstance(subscriber_id, bool):
        return IntakeResult(None, None, False, "invalid_input")
    subscriber_id = str(subscriber_id or "").strip()
    text = text.strip()
    if not subscriber_id or not text:
        return IntakeResult(None, None, False, "empty")
    reason = disabled_reason()
    if reason:
        logger.warning("concierge.disabled reason=%s", reason)
        return IntakeResult(None, None, False, "disabled")
    if not is_allowed(subscriber_id, profile or {}):
        logger.info("concierge.not_allowed")
        return IntakeResult(None, None, False, "not_allowed")

    if not isinstance(external_id, str):
        return IntakeResult(None, None, False, "event_id_required")
    legacy = not external_id.strip()
    if legacy and not config().get("legacy_read_handoff_enabled"):
        return IntakeResult(None, None, False, "event_id_required")
    if legacy:
        external_id = ""
    if len(external_id) > 4096 or len(text) > 16000 or len(subscriber_id) > 512:
        return IntakeResult(None, None, False, "invalid_input")
    identity = {"provider": str(config().get("provider") or "manychat"),
                "account": str(config().get("account_id") or "legacy_unverified"),
                "transport_channel": str(config().get("transport_channel") or "whatsapp")}
    if identity["account"] == "legacy_unverified":
        return IntakeResult(None, None, False, "account_required")
    envelope = dict(envelope or {})
    for key, value in identity.items():
        envelope_key = "account_id" if key == "account" else key
        if envelope_key in envelope and envelope[envelope_key] != value:
            return IntakeResult(None, None, False, "identity_conflict")
    envelope.update(version=2, event_id=external_id, subject=subscriber_id, account_id=identity["account"], provider=identity["provider"], transport_channel=identity["transport_channel"])
    envelope["input_assurance"] = "legacy_unverified" if legacy else "provider_event"
    envelope["profile"] = profile or {}
    ext = _external_id(subscriber_id, text, external_id)
    with transaction.atomic():
        conversation = _get_or_create_conversation(subscriber_id, identity)
        conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        values = {
            "role": ConversationMessage.Role.USER,
            "kind": ConversationMessage.Kind.INBOUND,
            "text": text,
            "content": [{"type": "text", "text": text}],
            "envelope": envelope,
        }
        if legacy:
            # PK identifica o recebimento local, nunca um evento do fornecedor.
            # Sem ID confiável não há dedupe de retry nem exatamente-uma-intenção.
            message = ConversationMessage.objects.create(conversation=conversation, external_id="", **values)
            created = True
        else:
            message, created = ConversationMessage.objects.get_or_create(
                conversation=conversation, external_id=ext, defaults=values,
            )
        if not created and (message.text != text or message.envelope.get("event_id") != external_id or message.envelope.get("payload_hash") != envelope.get("payload_hash")):
            return IntakeResult(conversation.pk, message.pk, False, "intent_conflict")
        if created and not legacy:
            # Recibo legado não comprova nova interação nem renova a janela.
            Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())
        if conversation.state != Conversation.State.ACTIVE:
            return IntakeResult(conversation.pk, message.pk, False, "handoff")
        # Replay repara trabalho perdido; efeito e agendamento têm o mesmo commit.
        _enqueue_turn(conversation)
    return IntakeResult(conversation.pk, message.pk, True, "legacy_read_only" if legacy else "queued" if created else "duplicate")


def _enqueue_turn(conversation: Conversation) -> None:
    from shopman.shop.directives import create_deduped

    delay = int(config().get("dispatch_delay_seconds") or 1)
    # ``available_at`` no futuro: o dispatcher por signal pula a diretiva e ela
    # fica para o worker. Sem isso o turno rodaria INLINE no request do webhook,
    # e o ManyChat cortaria a chamada em 10 s.
    create_deduped(
        TURN_TOPIC,
        payload={"conversation_id": conversation.pk, "contract_version": 2},
        dedupe_key=f"{TURN_TOPIC}:{conversation.pk}",
        available_at=timezone.now() + timedelta(seconds=max(delay, 1)),
    )


def _get_or_create_conversation(subscriber_id: str, identity: dict) -> Conversation:
    conversation, _ = Conversation.objects.get_or_create(
        subscriber_id=subscriber_id,
        **identity,
        defaults={"channel_ref": str(config().get("channel_ref") or "whatsapp")},
    )
    return conversation


def identify(conversation: Conversation, profile: dict | None = None) -> Conversation:
    """Enriquecimento pelo adapter autorizado, fora do ACK; sem promover o body."""
    from shopman.storefront.concierge import transport
    try:
        info = transport.identity_for(conversation, profile)
    except Exception:
        logger.warning("concierge.identify failed conversation=%s", conversation.pk)
        info = None
    if info is None:
        return conversation

    from shopman.guestman.services import customer as customer_service

    customer = customer_service.get_by_uuid(str(info.uuid))
    conversation.phone = (info.phone or "").strip()
    conversation.customer_name = (info.name or "").strip()
    conversation.customer_ref = getattr(customer, "ref", "") or ""
    conversation.save(update_fields=["phone", "customer_name", "customer_ref", "updated_at"])
    return conversation


# ── Turno ─────────────────────────────────────────────────────────────


@dataclass
class TurnResult:
    conversation_id: int
    replies: list[str] = field(default_factory=list)
    handoff: bool = False
    processed_message_ids: list[int] = field(default_factory=list)
    pending_more: bool = False
    fallback: str = ""  # vazio = o modelo respondeu; senão, a razão do fallback


def unanswered_inbound(conversation: Conversation) -> list[ConversationMessage]:
    """Consumo explícito: notas/saídas nunca reconhecem entradas por posição."""
    pending = conversation.messages.filter(
        kind=ConversationMessage.Kind.INBOUND, consumed_by__isnull=True,
        envelope__version=2,
    )
    if not config().get("legacy_read_handoff_enabled"):
        pending = pending.filter(_nonlegacy_input())
    return list(pending.order_by("id"))


def _nonlegacy_input():
    # Envelopes v2 anteriores à compatibilidade não têm input_assurance.
    return Q(envelope__input_assurance__isnull=True) | ~Q(envelope__input_assurance="legacy_unverified")


class TurnRevoked(Exception):
    """O claim não tem mais autoridade; conservar entradas e efeitos já registrados."""


def assert_turn_authority(conversation, *, for_mutation=True):
    from .transport import adapter_for
    current = Conversation.objects.get(pk=conversation.pk)
    if adapter_for(current) is None:
        raise TurnRevoked("transport_scope_mismatch")
    identity_fields = ("provider", "account", "transport_channel", "subscriber_id", "customer_ref", "phone", "channel_ref")
    if any(getattr(current, key) != getattr(conversation, key) for key in identity_fields):
        raise TurnRevoked("identity_changed")
    if not is_enabled() or not is_allowed(current.subscriber_id) or current.state != Conversation.State.ACTIVE:
        raise TurnRevoked("contained")
    if for_mutation and config().get("read_only"):
        raise TurnRevoked("read_only")
    if getattr(conversation, "_legacy_read_only", False):
        if for_mutation or not config().get("legacy_read_handoff_enabled"):
            raise TurnRevoked("legacy_read_only")
    fence = getattr(conversation, "_turn_fence", None)
    if for_mutation and fence is None:
        # Caller interno com objeto recarregado não pode perder a contenção
        # legada só porque os atributos transitórios do claim não estão nele.
        latest = current.messages.filter(kind=ConversationMessage.Kind.INBOUND).order_by("-pk").values_list("envelope", flat=True).first()
        if latest and latest.get("input_assurance") == "legacy_unverified":
            raise TurnRevoked("legacy_read_only")
    if fence is not None:
        if current.turn_fence != fence or not current.claim_until or current.claim_until <= timezone.now():
            raise TurnRevoked("claim_expired")
        if for_mutation and current.messages.filter(
            kind=ConversationMessage.Kind.INBOUND, envelope__version=2,
            pk__gt=conversation._inbound_max_id,
        ).exists():
            raise TurnRevoked("new_input")
    return current


def _claim(conversation_id):
    from .transport import adapter_for
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
        if adapter_for(conversation) is None:
            return conversation, []
        if not is_enabled() or not is_allowed(conversation.subscriber_id) or conversation.state != Conversation.State.ACTIVE:
            return conversation, []
        if conversation.claim_until and conversation.claim_until > timezone.now():
            return conversation, []
        inbound = unanswered_inbound(conversation)[:20]
        if not inbound:
            return conversation, []
        conversation.turn_fence += 1
        conversation.claim_until = timezone.now() + timedelta(seconds=120)
        conversation.save(update_fields=["turn_fence", "claim_until"])
        conversation._turn_fence = conversation.turn_fence
        conversation._inbound_max_id = inbound[-1].pk
        conversation._inbound_ids = [m.pk for m in inbound]
        conversation._legacy_read_only = bool(config().get("read_only")) or any(m.envelope.get("input_assurance") == "legacy_unverified" for m in inbound)
        return conversation, inbound


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


@_observed("turn")
def run_turn(conversation_id: int, *, client=None) -> TurnResult:
    """Claim curto, modelo fora de lock e consumo junto da intenção de saída."""
    conversation, inbound = _claim(conversation_id)
    result = TurnResult(conversation_id=conversation.pk)
    if not inbound:
        return result
    ids = [m.pk for m in inbound]
    from shopman.storefront.concierge import agent as agent_module
    try:
        assert_turn_authority(conversation, for_mutation=False)
        # Escape funciona mesmo sem chamada à IA.
        if any(m.text.casefold().strip(" .!?") in {
            "humano", "atendente", "quero falar com alguém", "quero falar com alguem",
            "falar com atendente", "quero atendimento humano",
        } for m in inbound):
            mark_handoff(conversation, "pedido do cliente", consumed_ids=ids)
            return TurnResult(conversation.pk, handoff=True, processed_message_ids=ids)
        if not conversation.customer_ref and not conversation._legacy_read_only:
            identify(conversation, inbound[0].envelope.get("profile") or {})
        assert_turn_authority(conversation, for_mutation=False)
        if conversation._legacy_read_only:
            # C01: somente leitura pública e escape humano; sem IA/enriquecimento.
            # Batch misto é contido integralmente, sem promover o texto legado.
            from . import tools
            reply = copy_message("CONCIERGE_LEGACY_READ_ONLY")
            menu_requests = {"menu", "cardápio", "cardapio", "oi", "olá", "ola"}
            if any(m.text.casefold().strip(" .!?") in menu_requests or m.text.casefold().startswith("#menu ") for m in inbound):
                ctx = tools.ToolContext(conversation=conversation, channel_ref=conversation.channel_ref)
                reply = tools.render_result("browse_menu", tools.browse_menu(ctx)) + "\n\n" + reply
            outcome = agent_module.AgentOutcome(reply_text=reply)
            result.fallback = "legacy_read_only"
        elif all(_looks_like_media(m.text) for m in inbound):
            outcome = agent_module.AgentOutcome(reply_text=copy_message("CONCIERGE_MEDIA_UNSUPPORTED"))
            result.fallback = "media"
        elif _bump_turn_counter(conversation) > int(config().get("max_turns_per_day") or 80):
            outcome = agent_module.AgentOutcome(reply_text=copy_message("CONCIERGE_TURN_LIMIT"))
            result.fallback = "turn_limit"
        else:
            try:
                outcome = agent_module.run_agent(
                    conversation=conversation, history=agent_module.history_for(conversation), client=client,
                )
            except TurnRevoked:
                raise
            except Exception:
                logger.error("concierge.turn_failed conversation=%s", conversation.pk)
                Conversation.objects.filter(pk=conversation.pk).update(consecutive_failures=F("consecutive_failures") + 1)
                _alert(conversation, "concierge_unavailable", "Resposta automática indisponível; contexto preservado.")
                outcome = agent_module.AgentOutcome(reply_text=copy_message("CONCIERGE_UNAVAILABLE"))
                result.fallback = "error"
        if outcome.handoff:
            mark_handoff(conversation, outcome.handoff_reason or "pedido do cliente", consumed_ids=ids)
            return TurnResult(conversation.pk, handoff=True, processed_message_ids=ids)
        from .transport import semantic_blocks
        primary = semantic_blocks(conversation, outcome.reply_text) if outcome.reply_text else []
        texts = [*primary, *[t for t in outcome.extra_replies if t and t.strip()]]
        with transaction.atomic():
            Conversation.objects.select_for_update().get(pk=conversation.pk)
            assert_turn_authority(conversation, for_mutation=False)
            _persist_outcome(conversation, outcome)
            prepared = []
            for i, text in enumerate(texts):
                prepared.append(_prepare_reply(
                    conversation, text, quote_token=getattr(outcome, "quote_token", "") if i == len(primary) - 1 else "",
                    disclosure=getattr(outcome, "disclosure", {}) if i == len(primary) - 1 else {},
                    depends_on=prepared[-1].pk if prepared else None,
                ))
            if not prepared:
                # Sem resposta útil não alegar consumo. Contenção evita loop de custo.
                _alert(conversation, "concierge_empty_output", "Entrada sem resposta útil; atendimento necessário.")
                Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.HANDOFF)
                return result
            ConversationMessage.objects.filter(pk__in=ids, consumed_by__isnull=True).update(consumed_by=conversation.turn_fence)
            Conversation.objects.filter(pk=conversation.pk).update(
                consecutive_failures=0 if not result.fallback else F("consecutive_failures"),
                input_tokens=F("input_tokens") + int(outcome.usage.get("input_tokens") or 0),
                output_tokens=F("output_tokens") + int(outcome.usage.get("output_tokens") or 0),
                cache_read_tokens=F("cache_read_tokens") + int(outcome.usage.get("cache_read_input_tokens") or 0),
                last_order_ref=outcome.order_ref or conversation.last_order_ref,
            )
        result.processed_message_ids = ids
        for message in prepared:
            _dispatch_reply(conversation, message)
        result.replies = texts
    except TurnRevoked:
        result.fallback = "revoked"
    finally:
        Conversation.objects.filter(pk=conversation.pk, turn_fence=conversation.turn_fence).update(claim_until=None)
    result.pending_more = bool(unanswered_inbound(conversation))
    return result


def _persist_outcome(conversation: Conversation, outcome) -> None:
    kinds = {
        "assistant": ConversationMessage.Kind.TOOL_CALL,
        "user": ConversationMessage.Kind.TOOL_RESULT,
    }
    for message in outcome.messages:
        role = message["role"]
        content = message["content"]
        if role == "assistant" and not any(b.get("type") == "tool_use" for b in content):
            # A resposta final é gravada por ``_send_reply`` (com o resultado do envio).
            continue
        ConversationMessage.objects.create(
            conversation=conversation,
            role=role,
            kind=kinds[role],
            content=content,
            text="",
        )


def _prepare_reply(conversation, text, *, quote_token="", disclosure=None, depends_on=None, purpose="reply"):
    return ConversationMessage.objects.create(
        conversation=conversation, role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY, text=text,
        content=[{"type": "text", "text": text}], transport_state="prepared",
        envelope={"version": 2, "turn_fence": conversation.turn_fence, "purpose": purpose,
                  "legacy_read_only": bool(getattr(conversation, "_legacy_read_only", False)),
                  "quote_token": quote_token, "disclosure": disclosure or {}, "depends_on": depends_on,
                  "inbound_max_id": getattr(conversation, "_inbound_max_id", None), "content_hash": hashlib.sha256(text.encode()).hexdigest()},
    )


@_observed("output")
def _dispatch_reply(conversation, message):
    from shopman.storefront.concierge import transport
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        message.refresh_from_db()
        if message.transport_state != "prepared":
            return message
        handoff_ack = message.envelope.get("purpose") == "handoff_ack" and current.state == Conversation.State.HANDOFF
        enabled = bool(config().get("enabled") and config().get("contract_version") == 2) if handoff_ack else is_enabled()
        if message.envelope.get("legacy_read_only") and not config().get("legacy_read_handoff_enabled"):
            enabled = False
        predecessor = message.envelope.get("depends_on")
        if predecessor and not current.messages.filter(pk=predecessor, transport_state="accepted").exists():
            message.transport_state = "not_applied"
            message.envelope = {**message.envelope, "code": "preceding_block_pending"}
        elif not enabled or not is_allowed(current.subscriber_id) or (current.state != Conversation.State.ACTIVE and not handoff_ack) or current.turn_fence != message.envelope.get("turn_fence"):
            message.transport_state = "not_applied"
            message.envelope = {**message.envelope, "code": "contained"}
        elif not transport.response_allowed(current, timezone.now()):
            message.transport_state = "not_applied"
            message.envelope = {**message.envelope, "code": "window_closed"}
        else:
            message.transport_state = "executing"
        message.save(update_fields=["transport_state", "envelope"])
    if message.transport_state != "executing":
        _alert(current, "concierge_output_blocked", "Resposta preparada e contida; verificar próxima ação de atendimento.")
        return message
    # O início desta tentativa foi autorizado sob lock. Handoff posterior contém
    # novas tentativas; esta precisa de reconciliação, nunca de repetição cega.
    try:
        outcome = transport.send_for(current, message.text)
        outcome = transport.normalize_outcome(outcome)
    except Exception as exc:
        logger.warning("concierge.dispatch.acceptance_unconfirmed conversation=%s message=%s exception_type=%s", current.pk, message.pk, type(exc).__name__)
        outcome = transport.SendOutcome("unknown", "acceptance_unconfirmed")
    message.transport_state = outcome.state
    message.envelope = {**message.envelope, "code": outcome.code}
    message.delivered = None  # Aceite não comprova chegada ao aparelho.
    message.save(update_fields=["transport_state", "envelope", "delivered"])
    if outcome.state == "accepted":
        Conversation.objects.filter(pk=current.pk).update(last_outbound_at=timezone.now())
    else:
        _alert(current, "concierge_output_pending", "Resposta com resultado " + outcome.state + "; consultar evidência antes de agir.")
    return message


def _send_reply(conversation: Conversation, text: str) -> ConversationMessage:
    return _dispatch_reply(conversation, _prepare_reply(conversation, text))


# ── Handoff ───────────────────────────────────────────────────────────


def mark_handoff(conversation: Conversation, reason: str, *, consumed_ids=()) -> bool:
    """Posse local primeiro. Espelho remoto falho nunca devolve autoridade ao bot."""
    from shopman.storefront.concierge import transport
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        current.state = Conversation.State.HANDOFF
        current.turn_fence += 1
        current.claim_until = None
        current.handoff_reason = (reason or "")[:200]
        current.handoff_at = timezone.now()
        current.handoff_sync_state = "executing"
        current.save(update_fields=["state", "turn_fence", "claim_until", "handoff_reason", "handoff_at", "handoff_sync_state", "updated_at"])
        current.messages.filter(pk__in=consumed_ids, kind=ConversationMessage.Kind.INBOUND,
                                consumed_by__isnull=True).update(consumed_by=current.turn_fence)
        ConversationMessage.objects.create(
            conversation=current, role=ConversationMessage.Role.ASSISTANT,
            kind=ConversationMessage.Kind.NOTE,
            text="Atendimento humano solicitado. Contexto preservado.",
            envelope={"version": 2, "session_key": current.session_key, "order_ref": current.last_order_ref,
                      "turn_fence": current.turn_fence},
        )
    try:
        synced = transport.handoff_for(current, True) is True
    except Exception as exc:
        logger.warning("concierge.handoff.sync_unconfirmed conversation=%s exception_type=%s", current.pk, type(exc).__name__)
        synced = False
    Conversation.objects.filter(pk=current.pk, turn_fence=current.turn_fence).update(handoff_sync_state="accepted" if synced else "unknown")
    _alert(current, "concierge_handoff", "Atendimento solicitado; sincronização " + ("aceita." if synced else "incerta; verificar ManyChat."))
    if consumed_ids:
        current._legacy_read_only = bool(getattr(conversation, "_legacy_read_only", False))
        current._inbound_max_id = max(consumed_ids)
        ack = copy_message("CONCIERGE_HANDOFF_ACK")
        if ack:
            _dispatch_reply(current, _prepare_reply(current, ack, purpose="handoff_ack"))
    conversation.refresh_from_db()
    return synced


def return_to_concierge(conversation: Conversation) -> bool:
    """G03 pendente mantém retorno desligado; falha remota mantém posse humana."""
    from shopman.storefront.concierge import transport
    if not config().get("human_return_enabled") or not is_enabled():
        return False
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if not is_allowed(current.subscriber_id) or current.state != Conversation.State.HANDOFF or current.handoff_sync_state == "executing":
            return False
        fence = current.turn_fence
        current.handoff_sync_state = "executing"
        current.save(update_fields=["handoff_sync_state", "updated_at"])
    try:
        synced = transport.handoff_for(current, False) is True
    except Exception as exc:
        logger.warning("concierge.resume.sync_unconfirmed conversation=%s exception_type=%s", current.pk, type(exc).__name__)
        synced = False
    with transaction.atomic():
        current = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if current.turn_fence != fence:
            return False
        current.handoff_sync_state = "accepted" if synced else "unknown"
        if synced and (not is_enabled() or not is_allowed(current.subscriber_id)):
            current.handoff_sync_state = "routing_mismatch"
            synced = False
        if synced:
            current.state = Conversation.State.ACTIVE
            current.turn_fence += 1
            current.handoff_reason = ""
            current.handoff_at = None
            _enqueue_turn(current)
        current.save(update_fields=["handoff_sync_state", "state", "turn_fence", "handoff_reason", "handoff_at", "updated_at"])
        if synced:
            ConversationMessage.objects.create(conversation=current, role="assistant", kind="note",
                text="Voltou para o concierge.", envelope={"version": 2, "turn_fence": current.turn_fence})
    if not synced:
        _alert(current, "concierge_handoff_sync", "Retorno não confirmado. Atendimento humano mantido.")
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
    """Recupera só envelope v2. Nunca repete envio em execução/unknown."""
    from django.db.models import Q
    from shopman.orderman.models import Directive
    now = timezone.now()
    counts = {"queued": 0, "unknown": 0}
    eligible_input = Q(kind=ConversationMessage.Kind.INBOUND, envelope__version=2, consumed_by__isnull=True, conversation__state=Conversation.State.ACTIVE)
    if not config().get("legacy_read_handoff_enabled"):
        eligible_input &= _nonlegacy_input()
    pending = ConversationMessage.objects.filter(conversation_id=OuterRef("pk")).filter(
        eligible_input | Q(transport_state__in=["prepared", "executing"])
    )
    ids = list(Conversation.objects.annotate(has_pending=Exists(pending)).filter(
        Q(claim_until__isnull=True) | Q(claim_until__lte=now),
    ).filter(Q(has_pending=True) | Q(claim_until__lte=now) | Q(handoff_sync_state="executing", updated_at__lte=now-timedelta(seconds=120))).order_by(
        "last_inbound_at", "id"
    ).values_list("id", flat=True)[:limit])
    for pk in ids:
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().get(pk=pk)
            if conversation.claim_until and conversation.claim_until > now:
                continue
            if conversation.handoff_sync_state == "executing" and conversation.updated_at <= now-timedelta(seconds=120):
                conversation.handoff_sync_state = "unknown"
                conversation.turn_fence += 1
                conversation.save(update_fields=["handoff_sync_state", "turn_fence", "updated_at"])
                _alert(conversation, "concierge_handoff_sync", "Sincronização de posse interrompida; resultado desconhecido. Verificar roteamento sem reativar o bot.")
            if conversation.claim_until:
                conversation.turn_fence += 1
                conversation.claim_until = None
                conversation.save(update_fields=["turn_fence", "claim_until"])
            unknown = conversation.messages.filter(transport_state="executing").update(transport_state="unknown")
            counts["unknown"] += unknown
            if unknown:
                _alert(conversation, "concierge_output_pending", "Processo interrompido após iniciar envio. Resultado desconhecido; não repetir.")
            # Um worker morto deixou running. Só o fence expirado permite liberar.
            Directive.objects.filter(topic=TURN_TOPIC, payload__conversation_id=pk,
                                     status="running", started_at__lt=now-timedelta(seconds=120)).update(
                status="failed", error_code="claim_expired", last_error="recovered by conversation fence")
            if is_enabled() and conversation.state == Conversation.State.ACTIVE and unanswered_inbound(conversation):
                _enqueue_turn(conversation)
                counts["queued"] += 1
            prepared = list(conversation.messages.filter(transport_state="prepared"))
            for message in prepared:
                envelope = message.envelope
                max_id = envelope.get("inbound_max_id")
                unchanged = bool(max_id) and not conversation.messages.filter(
                    kind=ConversationMessage.Kind.INBOUND, pk__gt=max_id,
                ).exists()
                quote_token = envelope.get("quote_token")
                if quote_token and quote_token != (conversation.quote or {}).get("token"):
                    unchanged = False
                if unchanged and conversation.state == Conversation.State.ACTIVE:
                    message.envelope = {**envelope, "previous_fence": envelope.get("turn_fence"),
                                        "turn_fence": conversation.turn_fence}
                    message.save(update_fields=["envelope"])

        # Persistência antes de rede: retomar bloco que comprovadamente nem começou.
        for message in prepared:
            _dispatch_reply(conversation, message)
    return counts


def retry_not_applied(conversation_id, message_id):
    """Recuperação explícita de um bloco comprovadamente não aplicado (G03)."""
    if not config().get("output_retry_enabled"):
        return False
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
        assert_turn_authority(conversation, for_mutation=False)
        message = conversation.messages.select_for_update().get(pk=message_id, kind=ConversationMessage.Kind.REPLY)
        if message.transport_state != "not_applied":
            return False
        if message.envelope.get("code") not in {"provider_rejected", "not_applied", "preceding_block_pending"}:
            return False
        max_id = message.envelope.get("inbound_max_id")
        if not max_id or conversation.messages.filter(kind=ConversationMessage.Kind.INBOUND, pk__gt=max_id).exists():
            return False
        quote_token = message.envelope.get("quote_token")
        if quote_token and quote_token != (conversation.quote or {}).get("token"):
            return False
        if message.envelope.get("legacy_read_only") and not config().get("legacy_read_handoff_enabled"):
            return False
        predecessor = message.envelope.get("depends_on")
        if predecessor and not conversation.messages.filter(pk=predecessor, transport_state="accepted").exists():
            return False
        message.transport_state = "prepared"
        message.envelope = {**message.envelope, "turn_fence": conversation.turn_fence,
                            "explicit_retry": int(message.envelope.get("explicit_retry", 0)) + 1}
        message.save(update_fields=["transport_state", "envelope"])
    _dispatch_reply(conversation, message)
    return message.transport_state == "accepted"
