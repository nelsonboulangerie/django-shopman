"""Reentrega do que o ManyChat recebeu e não chegou aqui (#2943).

O External Request do ManyChat não reenvia quando a nossa ponta falha: medido em
21/11/2026, o "oi" do dono chegou ao ManyChat às 02h54Z, o container do ``web-operator``
reiniciou na mesma hora (sem deploy), e a mensagem se perdeu em silêncio. Esta varredura
pergunta ao ManyChat (``getInfo`` do assinante) pela última entrada de quem conversa com a
Concierge e reingere o que for mais novo que o nosso ``last_inbound_at``.

Limites (coordenação, 21/11/2026):

- só vínculo ManyChat ativo, de conversa com a Concierge (a que está com a equipe vai ao
  Live Chat por desenho, e reingerir dispararia o aviso de "escreveu de novo") e liberada;
- só entrada dentro da janela de 24 horas do WhatsApp (fora dela não há o que responder);
- no máximo ``MAX_PER_ROUND`` contatos por rodada, os conferidos há mais tempo primeiro,
  para não martelar a API do ManyChat;
- **idempotente**: a chave (contato, hora, texto) fica na conversa, e nada é reingerido se
  já houver uma entrada com o mesmo texto desde aquela hora. Não responde duas vezes.

A entrada reingerida passa pelo mesmo ``service.receive_inbound`` do webhook, com a hora
que o ManyChat diz que o cliente escreveu, e o turno é agendado como sempre.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_PER_ROUND = 25
#: O provedor que entrega pelo External Request, sem reenvio.
PROVIDER = "manychat"
FLAG_KEY = "inbound_sweep"
WINDOW = timedelta(hours=24)
#: Folga entre o relógio do ManyChat e o nosso: entrada até aqui é a mesma que já temos.
SKEW = timedelta(seconds=60)


def _subscriber_info(subject: str) -> dict | None:
    from shopman.guestman.contrib.manychat.resolver import ManychatSubscriberResolver

    return ManychatSubscriberResolver.fetch_subscriber_info(subject)


def _parse(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _key(subject: str, at: datetime, text: str) -> str:
    return hashlib.sha256(f"{subject}|{at.isoformat()}|{text}".encode()).hexdigest()[:24]


def candidates(limit: int = MAX_PER_ROUND) -> list:
    """Os vínculos a conferir nesta rodada: os conferidos há mais tempo primeiro."""
    from shopman.shop.models import Conversation, ConversationBinding

    from . import service

    rows = (
        ConversationBinding.objects.filter(
            provider=PROVIDER,
            status=ConversationBinding.Status.ACTIVE,
            conversation__state=Conversation.State.ACTIVE,
        )
        .select_related("conversation")
        .order_by("pk")
    )
    allowed = [binding for binding in rows if service.is_allowed(binding)]
    allowed.sort(key=lambda b: str(((b.conversation.flags or {}).get(FLAG_KEY) or {}).get("checked_at") or ""))
    return allowed[:limit]


def _mark(conversation, **values) -> None:
    from shopman.shop.models import Conversation

    flags = dict(Conversation.objects.filter(pk=conversation.pk).values_list("flags", flat=True).first() or {})
    flags[FLAG_KEY] = {**(flags.get(FLAG_KEY) or {}), **values}
    Conversation.objects.filter(pk=conversation.pk).update(flags=flags)


def _event(binding, text: str, written_at: datetime):
    """O mesmo evento que o webhook monta, com a hora que o ManyChat diz que o cliente escreveu."""
    from . import transport
    from .contracts import InboundEvent, TransportScope

    adapter = transport.adapter_for(binding)
    connection = transport.connection_for(binding)
    if adapter is None or connection is None:
        return None
    window = connection.options.get("response_window") if isinstance(connection.options.get("response_window"), dict) else {}
    authentication = str(window.get("authentication") or "api_key")
    envelope = {
        "provider": connection.provider,
        "account_id": connection.account,
        "transport_channel": connection.channel,
        "authentication": authentication,
    }
    field = str(window.get("field") or "")
    if field:
        envelope[field] = written_at.isoformat()
    scope = TransportScope(
        provider=connection.provider, account=connection.account, channel=connection.channel,
        subject=binding.subject, connection_key=connection.key,
    )
    payload = {"subject": binding.subject, "event_id": "", "message_type": "text", "text": text}
    return InboundEvent(
        scope=scope,
        text=text,
        message_type="text",
        received_at=timezone.now(),
        event_identity_assurance="unavailable",
        occurred_at=written_at,
        occurred_at_assurance="provider_api",
        correlation_ref="inbound_sweep",
        authentication_assurance=authentication,
        payload_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest(),
        window_evidence=adapter.window_evidence(envelope, timezone.now()),
    )


def sweep(*, now: datetime | None = None, limit: int = MAX_PER_ROUND) -> dict[str, int]:
    """Uma rodada. Nunca levanta: erro de um contato não para os outros."""
    from shopman.shop.models import ConversationMessage

    from . import service

    now = now or timezone.now()
    counts = {"checked": 0, "reingested": 0, "skipped": 0, "errors": 0}
    for binding in candidates(limit):
        conversation = binding.conversation
        counts["checked"] += 1
        try:
            info = _subscriber_info(binding.subject) or {}
            text = str(info.get("last_input_text") or "").strip()
            written_at = _parse(info.get("last_interaction"))
            _mark(conversation, checked_at=now.isoformat())
            ours = binding.last_inbound_at
            if not text or written_at is None or now - written_at > WINDOW or (ours and written_at <= ours + SKEW):
                counts["skipped"] += 1
                continue
            key = _key(binding.subject, written_at, text)
            already = ((conversation.flags or {}).get(FLAG_KEY) or {}).get("last_key") == key or ConversationMessage.objects.filter(
                binding=binding, kind=ConversationMessage.Kind.INBOUND, text=text, created_at__gte=written_at - SKEW,
            ).exists()
            if already:
                counts["skipped"] += 1
                continue
            event = _event(binding, text, written_at)
            if event is None:
                counts["skipped"] += 1
                continue
            result = service.receive_inbound(event)
            _mark(conversation, last_key=key, reingested_at=now.isoformat())
            logger.warning(
                "concierge.inbound_sweep.reingested conversation=%s reason=%s", conversation.pk, result.reason
            )
            counts["reingested"] += 1
        except Exception:
            logger.warning("concierge.inbound_sweep.failed conversation=%s", conversation.pk, exc_info=True)
            counts["errors"] += 1
    return counts
