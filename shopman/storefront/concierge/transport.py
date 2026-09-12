"""Capacidades e adaptação do transporte; domínio conserva fatos e autoridade.

O ManyChat traduz WhatsApp pelo adapter transacional existente. Outros
transportes exigem implementação explícita e gates próprios; o segundo adapter
usado na suíte é exclusivamente fake. Nenhum resultado técnico comprova entrega
sem receipt verificável. Janela é revalidada na execução, nunca presumida no ACK.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


def _config() -> dict:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


@dataclass(frozen=True)
class SendOutcome:
    state: str
    code: str = ""


def normalize_outcome(value):
    if isinstance(value, SendOutcome):
        return value
    # Fakes antigos podem afirmar aceite. False perdeu certeza: nunca inferir
    # não aplicação a partir da fronteira booleana legada.
    return SendOutcome("accepted" if value is True else "unknown", "legacy_boolean")


def send_text(subscriber_id: str, text: str) -> SendOutcome:
    """Resultado semântico do adapter, sem truncamento nem retry automático."""
    from shopman.shop.adapters import notification_manychat

    try:
        result = notification_manychat.send_text_result(subscriber_id, text)
    except Exception as exc:
        logger.warning("concierge.transport.acceptance_unconfirmed exception_type=%s", type(exc).__name__)
        return SendOutcome("unknown", "acceptance_unconfirmed")
    state = "accepted" if result.get("success") else "unknown" if result.get("outcome_unknown") else "not_applied"
    return SendOutcome(state, str(result.get("error") or ""))


def set_handoff(subscriber_id: str, on: bool) -> bool:
    """Grava o campo de handoff no assinante (``"1"`` ligado, ``""`` desligado)."""
    field = str(_config().get("handoff_field") or "concierge_handoff")
    from shopman.shop.adapters import notification_manychat

    try:
        return bool(notification_manychat.set_custom_field(str(subscriber_id), field, "1" if on else ""))
    except Exception:
        logger.warning("concierge.transport.handoff_unconfirmed")
        return False


@dataclass(frozen=True)
class ChannelCapabilities:
    max_text_chars: int
    response_window: timedelta
    supports_text: bool = True
    supports_postback: bool = False
    supports_media: bool = False
    stable_event_identity_verified: bool = False
    supports_buttons: bool = False
    delivery_receipts: bool = False
    supports_handoff: bool = False
    identity_strength: str = "transport_subject"


class ConversationAdapter(Protocol):
    provider: str
    channel: str
    capabilities: ChannelCapabilities

    def send_text(self, subject: str, text: str) -> SendOutcome: ...
    def set_handoff(self, subject: str, on: bool) -> bool: ...
    def identify(self, subject: str, profile: dict): ...


class ManyChatAdapter:
    provider = "manychat"
    channel = "whatsapp"
    capabilities = ChannelCapabilities(
        max_text_chars=4000,
        response_window=timedelta(hours=24),
        supports_handoff=True,
        identity_strength="channel_asserted",
    )

    def send_text(self, subject, text):
        return send_text(subject, text)

    def set_handoff(self, subject, on):
        return set_handoff(subject, on)

    def identify(self, subject, profile):
        from shopman.guestman.adapters.auth import CustomerResolver

        # Perfil informado pelo body não promove identidade. O resolver lê o
        # contato do fornecedor configurado; G04 habilita esse uso explicitamente.
        return CustomerResolver().upsert_manychat_subscriber({"id": subject})


def adapter_for(conversation) -> ConversationAdapter | None:
    """Conta e transporte configurados cercam até referências persistidas antigas."""
    config = _config()
    expected = (
        str(config.get("provider") or "manychat"),
        str(config.get("account_id") or "legacy_unverified"),
        str(config.get("transport_channel") or "whatsapp"),
    )
    actual = (conversation.provider, conversation.account, conversation.transport_channel)
    if config.get("contract_version") != 2 or expected[1] == "legacy_unverified" or actual != expected:
        return None
    try:
        adapter = import_string(config["adapter_path"])() if config.get("adapter_path") else ManyChatAdapter()
    except (ImportError, AttributeError, TypeError):
        logger.error("concierge.transport.adapter_unavailable")
        return None
    if (adapter.provider, adapter.channel) != (actual[0], actual[2]):
        return None
    return adapter


def whatsapp_interaction_at(envelope, now):
    """Campo de última interação WA, opt-in por conta; nunca é ID do evento.

    O dono do flow confirma a origem do campo e o fuso antes de configurar.
    Retry conserva o instante original; timestamp inválido não abre janela.
    """
    config = _config()
    zone = config.get("whatsapp_interaction_timezone")
    if not zone or envelope.get("authentication") != "api_key":
        return None
    if (envelope.get("provider"), envelope.get("transport_channel"), envelope.get("account_id")) != (
        "manychat", "whatsapp", config.get("account_id")
    ):
        return None
    raw = envelope.get("provider_timestamp")
    if not isinstance(raw, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", raw
    ):
        return None
    try:
        local_zone = ZoneInfo(zone)
        instant = datetime.fromisoformat(raw)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=local_zone)
        instant = instant.astimezone(UTC)
    except (ValueError, TypeError, OverflowError, ZoneInfoNotFoundError):
        return None
    return instant if timedelta(0) <= now - instant < ManyChatAdapter.capabilities.response_window else None


def response_allowed(conversation, now) -> bool:
    adapter = adapter_for(conversation)
    received = conversation.last_inbound_at
    if not adapter:
        return False
    if received and timedelta(0) <= now - received < adapter.capabilities.response_window:
        return True
    zone = _config().get("whatsapp_interaction_timezone")
    if not zone or not _config().get("legacy_read_handoff_enabled"):
        return False
    # Evidência nasce no ingresso autenticado, sem backfill da transcrição.
    # Fonte separada preserva last_inbound_at e permite revogar o opt-in.
    envelope = conversation.messages.filter(
        kind="inbound", envelope__input_assurance="legacy_unverified",
        envelope__window_evidence__source="manychat_whatsapp_last_interaction",
        envelope__window_evidence__timezone=zone,
    ).order_by("-envelope__window_evidence__at").values_list("envelope", flat=True).first()
    if not envelope:
        return False
    instant = whatsapp_interaction_at(envelope, now)
    return bool(instant and envelope["window_evidence"].get("at") == instant.isoformat())


def send_for(conversation, text) -> SendOutcome:
    adapter = adapter_for(conversation)
    if adapter is None:
        return SendOutcome("not_applied", "transport_scope_mismatch")
    if not isinstance(text, str) or not text.strip():
        return SendOutcome("not_applied", "empty_text")
    if len(text) > adapter.capabilities.max_text_chars:
        # Bloco essencial indivisível: jamais cortar Pix, CTA, valor ou prazo.
        return SendOutcome("not_applied", "essential_block_too_large")
    return normalize_outcome(adapter.send_text(conversation.subscriber_id, text))


def handoff_for(conversation, on) -> bool:
    adapter = adapter_for(conversation)
    return bool(
        adapter
        and adapter.capabilities.supports_handoff
        and adapter.set_handoff(conversation.subscriber_id, on) is True
    )


def identity_for(conversation, profile=None):
    adapter = adapter_for(conversation)
    if not adapter or not _config().get("identity_link_enabled"):
        return None
    return adapter.identify(conversation.subscriber_id, profile or {})


def semantic_blocks(conversation, text: str) -> list[str]:
    """Particiona em fronteiras de linha sem cortar unidade essencial.

    Linha acima da capacidade permanece inteira: send_for recusa explicitamente.
    Não usa espaços para quebrar Pix, URL, prazo ou decisão em duas mensagens.
    """
    if not text:
        return []
    adapter = adapter_for(conversation)
    if adapter is None:
        return [text]
    limit = adapter.capabilities.max_text_chars
    blocks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            blocks.append(current)
            current = ""
        if len(line) > limit:
            blocks.append(line)
        else:
            current += line
    if current:
        blocks.append(current)
    return blocks
