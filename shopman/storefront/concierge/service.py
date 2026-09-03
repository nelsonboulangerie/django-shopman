"""A porta do concierge: receber a mensagem, rodar o turno, responder.

Duas entradas, e nenhuma delas fala com o modelo diretamente:

- ``receive_inbound``: chamado pelo webhook (External Request do ManyChat). Guarda
  a mensagem, identifica o cliente e enfileira UMA diretiva ``concierge.turn``
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

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationMessage

logger = logging.getLogger(__name__)

TURN_TOPIC = "concierge.turn"

#: Sufixos que denunciam mídia: desde 04/2025 o ManyChat entrega áudio/imagem
#: como URL em ``last_input_text``. O concierge só lê texto por enquanto.
_MEDIA_SUFFIXES = (".ogg", ".oga", ".mp3", ".m4a", ".mp4", ".jpg", ".jpeg", ".png", ".webp", ".pdf")
_MEDIA_HOSTS = ("lookaside.fbsbx.com", "cdn.manychat", "manychat.com/", "fbcdn.net")


def config() -> dict:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


def is_enabled() -> bool:
    cfg = config()
    return bool(cfg.get("enabled")) and bool((getattr(settings, "AI_ASSIST_API_KEY", "") or "").strip())


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
    """Com a lista vazia, todos entram. Com lista, só quem está nela (id ou telefone).

    Antes de qualquer escrita: quem não está na lista não ganha conversa, nem
    mensagem guardada, nem cliente sincronizado. Para comparar por telefone, o
    número vem do corpo (``whatsapp_phone``/``whatsapp_id``) ou do ``getInfo``,
    que é só leitura.
    """
    allowed = allowed_subscribers()
    if not allowed:
        return True
    subscriber_id = str(subscriber_id or "").strip()
    if subscriber_id in allowed:
        return True
    phones = {v for v in allowed if v.startswith("+")}
    if not phones:
        return False
    from shopman.utils.phone import normalize_phone

    profile = profile or {}
    candidates = [profile.get("whatsapp_phone"), profile.get("whatsapp_id"), profile.get("phone")]
    if not any(candidates):
        try:
            from shopman.guestman.adapters.auth import CustomerResolver

            candidates.append(CustomerResolver().manychat_phone(subscriber_id))
        except Exception:
            logger.debug("concierge.is_allowed: getInfo degraded", exc_info=True)
    for raw in candidates:
        if not raw:
            continue
        try:
            phone = normalize_phone(str(raw))
        except Exception:
            logger.debug("concierge.is_allowed: telefone ilegível %r", raw)
            phone = ""
        if phone and phone in phones:
            return True
    return False


# ── Intake ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IntakeResult:
    conversation_id: int | None
    message_id: int | None
    queued: bool
    reason: str  # queued | duplicate | handoff | disabled | not_allowed | empty


def _external_id(subscriber_id: str, text: str, external_id: str) -> str:
    if external_id:
        return str(external_id)[:80]
    # Sem id do ManyChat: a mesma frase, do mesmo assinante, no mesmo minuto é
    # o mesmo evento (reenvio do webhook), não uma insistência do cliente.
    bucket = timezone.now().strftime("%Y%m%d%H%M")
    digest = hashlib.sha1(f"{subscriber_id}|{text.strip()}|{bucket}".encode()).hexdigest()
    return f"h:{digest[:40]}"


def receive_inbound(
    *,
    subscriber_id: str,
    text: str,
    external_id: str = "",
    profile: dict | None = None,
) -> IntakeResult:
    """Guarda a mensagem e enfileira o turno. Idempotente por ``external_id``."""
    subscriber_id = str(subscriber_id or "").strip()
    text = (text or "").strip()
    if not subscriber_id or not text:
        return IntakeResult(None, None, False, "empty")
    if not is_enabled():
        logger.info("concierge.disabled subscriber=%s", subscriber_id)
        return IntakeResult(None, None, False, "disabled")
    if not is_allowed(subscriber_id, profile or {}):
        logger.info("concierge.not_allowed subscriber=%s", subscriber_id)
        return IntakeResult(None, None, False, "not_allowed")

    conversation = _get_or_create_conversation(subscriber_id, profile or {})

    ext = _external_id(subscriber_id, text, external_id)
    try:
        with transaction.atomic():
            message = ConversationMessage.objects.create(
                conversation=conversation,
                role=ConversationMessage.Role.USER,
                kind=ConversationMessage.Kind.INBOUND,
                text=text,
                content=[{"type": "text", "text": text}],
                external_id=ext,
            )
    except IntegrityError:
        logger.info("concierge.duplicate_inbound conversation=%s ext=%s", conversation.pk, ext)
        return IntakeResult(conversation.pk, None, False, "duplicate")

    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())

    if conversation.state == Conversation.State.HANDOFF:
        # A equipe está na conversa. A mensagem fica na transcrição, o bot cala.
        return IntakeResult(conversation.pk, message.pk, False, "handoff")

    _enqueue_turn(conversation)
    return IntakeResult(conversation.pk, message.pk, True, "queued")


def _enqueue_turn(conversation: Conversation) -> None:
    from shopman.shop.directives import create_deduped

    delay = int(config().get("dispatch_delay_seconds") or 1)
    # ``available_at`` no futuro: o dispatcher por signal pula a diretiva e ela
    # fica para o worker. Sem isso o turno rodaria INLINE no request do webhook,
    # e o ManyChat cortaria a chamada em 10 s.
    create_deduped(
        TURN_TOPIC,
        payload={"conversation_id": conversation.pk},
        dedupe_key=f"{TURN_TOPIC}:{conversation.pk}",
        available_at=timezone.now() + timedelta(seconds=max(delay, 0)),
    )


def _get_or_create_conversation(subscriber_id: str, profile: dict) -> Conversation:
    conversation, created = Conversation.objects.get_or_create(
        subscriber_id=subscriber_id,
        defaults={"channel_ref": str(config().get("channel_ref") or "whatsapp")},
    )
    if created or not conversation.phone or not conversation.customer_ref:
        identify(conversation, profile)
    return conversation


def identify(conversation: Conversation, profile: dict | None = None) -> Conversation:
    """Resolve o cliente do assinante pelo Guestman (que pergunta ao ManyChat o
    telefone quando o corpo não trouxe). Nunca levanta: sem identidade a conversa
    segue, só não pode fechar pedido."""
    from shopman.guestman.adapters.auth import CustomerResolver

    payload = {"id": conversation.subscriber_id, **{k: v for k, v in (profile or {}).items() if v}}
    try:
        info = CustomerResolver().upsert_manychat_subscriber(payload)
    except Exception:
        logger.warning("concierge.identify failed subscriber=%s", conversation.subscriber_id, exc_info=True)
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
    """Mensagens do cliente ainda sem resposta (depois da última resposta/nota)."""
    last_answer = (
        conversation.messages.filter(
            kind__in=(ConversationMessage.Kind.REPLY, ConversationMessage.Kind.NOTE)
        )
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    )
    qs = conversation.messages.filter(kind=ConversationMessage.Kind.INBOUND)
    if last_answer:
        qs = qs.filter(id__gt=last_answer)
    return list(qs.order_by("id"))


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


def run_turn(conversation_id: int, *, client=None) -> TurnResult:
    """Responde tudo que o cliente mandou desde a última resposta."""
    conversation = Conversation.objects.get(pk=conversation_id)
    result = TurnResult(conversation_id=conversation.pk)

    if conversation.state == Conversation.State.HANDOFF:
        return result

    inbound = unanswered_inbound(conversation)
    if not inbound:
        return result
    result.processed_message_ids = [m.pk for m in inbound]

    if all(_looks_like_media(m.text) for m in inbound):
        return _reply_with_copy(conversation, result, "CONCIERGE_MEDIA_UNSUPPORTED", fallback="media")

    turns = _bump_turn_counter(conversation)
    if turns > int(config().get("max_turns_per_day") or 80):
        return _reply_with_copy(conversation, result, "CONCIERGE_TURN_LIMIT", fallback="turn_limit")

    from shopman.storefront.concierge import agent as agent_module

    history = agent_module.history_for(conversation)
    try:
        outcome = agent_module.run_agent(conversation=conversation, history=history, client=client)
    except Exception:
        logger.exception("concierge.turn_failed conversation=%s", conversation.pk)
        conversation.consecutive_failures += 1
        conversation.save(update_fields=["consecutive_failures", "updated_at"])
        if conversation.consecutive_failures >= 3:
            _alert(conversation, "concierge_unavailable", "O concierge falhou três vezes seguidas nesta conversa.")
        return _reply_with_copy(conversation, result, "CONCIERGE_UNAVAILABLE", fallback="error")

    # Transcrição: cada mensagem no formato da API, na ordem em que aconteceu.
    _persist_outcome(conversation, outcome)

    conversation.consecutive_failures = 0
    conversation.input_tokens += int(outcome.usage.get("input_tokens") or 0)
    conversation.output_tokens += int(outcome.usage.get("output_tokens") or 0)
    conversation.cache_read_tokens += int(outcome.usage.get("cache_read_input_tokens") or 0)
    conversation.save(update_fields=["consecutive_failures", "input_tokens", "output_tokens", "cache_read_tokens", "updated_at"])

    replies = [outcome.reply_text] + list(outcome.extra_replies)
    replies = [r for r in replies if r and r.strip()]
    if outcome.handoff:
        mark_handoff(conversation, outcome.handoff_reason or "pedido do cliente")
        ack = copy_message("CONCIERGE_HANDOFF_ACK")
        if ack and not outcome.reply_text:
            replies.append(ack)
        result.handoff = True

    for text in replies:
        _send_reply(conversation, text)
    result.replies = replies

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


def _send_reply(conversation: Conversation, text: str) -> ConversationMessage:
    from shopman.storefront.concierge import transport

    delivered = transport.send_text(conversation.subscriber_id, text)
    message = ConversationMessage.objects.create(
        conversation=conversation,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text=text,
        content=[{"type": "text", "text": text}],
        delivered=delivered,
    )
    Conversation.objects.filter(pk=conversation.pk).update(last_outbound_at=timezone.now())
    if not delivered:
        logger.error("concierge.reply_not_delivered conversation=%s", conversation.pk)
    return message


def _reply_with_copy(conversation: Conversation, result: TurnResult, key: str, *, fallback: str) -> TurnResult:
    text = copy_message(key)
    if text:
        _send_reply(conversation, text)
        result.replies = [text]
    else:
        # Sem copy não há o que dizer; registra a nota para a fila não repetir.
        ConversationMessage.objects.create(
            conversation=conversation,
            role=ConversationMessage.Role.ASSISTANT,
            kind=ConversationMessage.Kind.NOTE,
            text=f"[{fallback}] sem copy configurada",
        )
    result.fallback = fallback
    result.pending_more = bool(unanswered_inbound(conversation))
    return result


# ── Handoff ───────────────────────────────────────────────────────────


def mark_handoff(conversation: Conversation, reason: str) -> None:
    """Passa a conversa para a equipe: estado, alerta e o campo no ManyChat."""
    from shopman.storefront.concierge import transport

    conversation.state = Conversation.State.HANDOFF
    conversation.handoff_reason = (reason or "")[:200]
    conversation.handoff_at = timezone.now()
    conversation.save(update_fields=["state", "handoff_reason", "handoff_at", "updated_at"])
    ConversationMessage.objects.create(
        conversation=conversation,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.NOTE,
        text=f"Passou para a equipe: {conversation.handoff_reason}",
    )
    who = conversation.customer_name or conversation.phone or conversation.subscriber_id
    _alert(conversation, "concierge_handoff", f"{who} pediu a equipe no WhatsApp: {conversation.handoff_reason}")
    transport.set_handoff(conversation.subscriber_id, True)


def return_to_concierge(conversation: Conversation) -> None:
    """A equipe devolve a conversa ao bot (ação do Admin)."""
    from shopman.storefront.concierge import transport

    conversation.state = Conversation.State.ACTIVE
    conversation.handoff_reason = ""
    conversation.handoff_at = None
    conversation.save(update_fields=["state", "handoff_reason", "handoff_at", "updated_at"])
    ConversationMessage.objects.create(
        conversation=conversation,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.NOTE,
        text="Voltou para o concierge.",
    )
    transport.set_handoff(conversation.subscriber_id, False)


def _alert(conversation: Conversation, alert_type: str, message: str) -> None:
    try:
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type=alert_type,
            severity="warning",
            message=message,
            dedupe_key=f"concierge:{conversation.pk}:{alert_type}",
        )
    except Exception:
        logger.warning("concierge.alert_failed type=%s conversation=%s", alert_type, conversation.pk, exc_info=True)
