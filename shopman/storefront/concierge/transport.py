"""Registry canônico dos transportes do concierge.

O núcleo conhece somente ``ConversationBinding`` e contratos normalizados. Cada
connection fixa provider, conta, canal e adapter. Nenhum campo do payload escolhe
esse escopo e nenhum provider recebe tratamento especial no registry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils.module_loading import import_string

from .contracts import (
    ChannelCapabilities,
    ConversationAdapter,
    HandoffOutcome,
    IdentityResolution,
    InboundEvent,
    IngressRejected,
    ResponseAuthorization,
    SendOutcome,
    TransportConnection,
    TransportScope,
    WindowEvidence,
)

logger = logging.getLogger(__name__)

AUTHENTICATED_INGRESS_SOURCE = "authenticated_ingress_received_at"
PROVIDER_ENFORCED_ATTEMPT = "provider_enforced_attempt"


def _config() -> Mapping[str, Any]:
    return getattr(settings, "SHOPMAN_CONCIERGE", {}) or {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def configured_connections(config: Mapping[str, Any] | None = None) -> tuple[TransportConnection, ...]:
    """Carrega somente o registry explícito ``connections``."""
    root = config if config is not None else _config()
    raw = root.get("connections") if isinstance(root, Mapping) else None
    if not isinstance(raw, Mapping):
        logger.error("concierge.transport.connections_missing")
        return ()
    connections: list[TransportConnection] = []
    for key, value in raw.items():
        if not isinstance(value, Mapping) or value.get("active") is not True:
            continue
        options = value.get("options", {})
        if not isinstance(options, Mapping):
            logger.error("concierge.transport.connection_invalid key=%s", _clean(key) or "missing")
            continue
        connection = TransportConnection(
            key=_clean(key),
            provider=_clean(value.get("provider")),
            account=_clean(value.get("account")),
            channel=_clean(value.get("channel")),
            adapter_path=_clean(value.get("adapter_path")),
            options=dict(options),
        )
        if not all((connection.key, connection.provider, connection.account, connection.channel, connection.adapter_path)):
            logger.error("concierge.transport.connection_invalid key=%s", connection.key or "missing")
            continue
        connections.append(connection)
    scope_counts = Counter(
        (connection.provider, connection.account, connection.channel)
        for connection in connections
    )
    ambiguous = {scope for scope, count in scope_counts.items() if count > 1}
    if ambiguous:
        logger.error("concierge.transport.connection_scope_ambiguous")
    return tuple(
        connection
        for connection in connections
        if (connection.provider, connection.account, connection.channel) not in ambiguous
    )


def scope_for(binding) -> TransportScope:
    """Extrai o contrato obrigatório de ``ConversationBinding``."""
    return TransportScope(
        provider=_clean(binding.provider),
        account=_clean(binding.account),
        channel=_clean(binding.transport_channel),
        subject=_clean(binding.subject),
        connection_key=_clean(binding.connection_key),
    )


def connection_for(binding) -> TransportConnection | None:
    """Resolve por chave e confirma o escopo persistido integralmente."""
    scope = scope_for(binding)
    connection = connection_for_key(scope.connection_key)
    if connection is None:
        return None
    if (connection.provider, connection.account, connection.channel) != (
        scope.provider,
        scope.account,
        scope.channel,
    ):
        logger.error("concierge.transport.binding_scope_mismatch")
        return None
    return connection


def connection_for_key(connection_key: str) -> TransportConnection | None:
    """Resolve a connection escolhida pela rota confiável."""
    matches = [connection for connection in configured_connections() if connection.key == _clean(connection_key)]
    return matches[0] if len(matches) == 1 else None


def adapter_for_connection(connection: TransportConnection) -> ConversationAdapter | None:
    """Instancia um adapter a partir da connection já resolvida."""
    try:
        adapter_class = import_string(connection.adapter_path)
        if getattr(adapter_class, "single_account_gateway", False):
            accounts = {
                configured.account
                for configured in configured_connections()
                if configured.adapter_path == connection.adapter_path
            }
            if accounts and accounts != {connection.account}:
                logger.error("concierge.transport.adapter_account_ambiguous")
                return None
        adapter = adapter_class(connection=connection)
    except (ImportError, AttributeError, TypeError, ValueError):
        logger.error("concierge.transport.adapter_unavailable", exc_info=True)
        return None
    if (
        getattr(adapter, "provider", None),
        getattr(adapter, "channel", None),
    ) != (connection.provider, connection.channel) or not isinstance(
        getattr(adapter, "capabilities", None), ChannelCapabilities
    ):
        logger.error("concierge.transport.adapter_scope_mismatch")
        return None
    return adapter


def adapter_for(binding) -> ConversationAdapter | None:
    """Instancia o adapter registrado para o binding exato."""
    connection = connection_for(binding)
    if connection is None:
        return None
    return adapter_for_connection(connection)


def window_evidence_for(binding, envelope: Mapping[str, Any], now: datetime) -> WindowEvidence | None:
    adapter = adapter_for(binding)
    return adapter.window_evidence(envelope, now) if adapter else None


def response_authorization(
    binding,
    evidence: WindowEvidence | Mapping[str, Any] | None,
    now: datetime,
    *,
    purpose: str = "reply",
) -> ResponseAuthorization:
    adapter = adapter_for(binding)
    if adapter is None:
        return ResponseAuthorization(False, "transport_scope_mismatch")
    decision = adapter.authorize_response(evidence, now, purpose=purpose)
    if not isinstance(decision, ResponseAuthorization):
        return ResponseAuthorization(False, "invalid_adapter_authorization")
    return decision


def send_for(binding, text: str) -> SendOutcome:
    adapter = adapter_for(binding)
    if adapter is None:
        return SendOutcome("not_applied", "transport_scope_mismatch")
    if not isinstance(text, str) or not text.strip():
        return SendOutcome("not_applied", "empty_text")
    if len(text) > adapter.capabilities.max_text_chars:
        return SendOutcome("not_applied", "essential_block_too_large")
    outcome = adapter.send_text(scope_for(binding).subject, text)
    if not isinstance(outcome, SendOutcome) or outcome.state not in {
        "accepted",
        "not_applied",
        "unknown",
    }:
        return SendOutcome("unknown", "invalid_adapter_outcome")
    receipt = _clean(outcome.provider_receipt_ref)
    if len(receipt) > 512:
        return SendOutcome("unknown", "invalid_provider_receipt")
    return SendOutcome(outcome.state, _clean(outcome.code)[:80], receipt)


def handoff_for(binding, on: bool) -> HandoffOutcome:
    adapter = adapter_for(binding)
    if adapter is None:
        return HandoffOutcome("not_applied", "transport_scope_mismatch")
    if not adapter.capabilities.supports_handoff:
        return HandoffOutcome("not_applied", "handoff_not_supported")
    outcome = adapter.set_handoff(scope_for(binding).subject, on)
    if not isinstance(outcome, HandoffOutcome) or outcome.state not in {
        "accepted",
        "not_applied",
        "unknown",
    }:
        return HandoffOutcome("unknown", "invalid_adapter_outcome")
    receipt = _clean(outcome.provider_receipt_ref)
    if len(receipt) > 512:
        return HandoffOutcome("unknown", "invalid_provider_receipt")
    return HandoffOutcome(outcome.state, _clean(outcome.code)[:80], receipt)


def identity_for(binding, profile: Mapping[str, Any] | None = None):
    connection = connection_for(binding)
    adapter = adapter_for(binding)
    if connection is None or adapter is None or connection.options.get("identity_link_enabled") is not True:
        return None
    return adapter.identify(scope_for(binding).subject, profile or {})


def semantic_blocks(binding, text: str) -> list[str]:
    if not text:
        return []
    adapter = adapter_for(binding)
    if adapter is None:
        return [text]
    limit = adapter.capabilities.max_text_chars
    blocks: list[str] = []
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


class ManyChatWhatsAppAdapter:
    """Connection ManyChat/WhatsApp atual implementando o contrato comum."""

    provider = "manychat"
    channel = "whatsapp"
    single_account_gateway = True
    _default_capabilities = ChannelCapabilities(
        max_text_chars=4000,
        response_window=timedelta(hours=24),
        supports_handoff=True,
        provider_enforces_response_window=True,
    )

    def __init__(self, *, connection: TransportConnection):
        self.connection = connection
        if (connection.provider, connection.channel) != (self.provider, self.channel):
            raise ValueError("ManyChatWhatsAppAdapter recebeu escopo incompatível")
        window = self._window_config()
        duration = int(window.get("duration_seconds") or 24 * 60 * 60)
        self.capabilities = replace(
            self._default_capabilities,
            max_text_chars=max(int(connection.options.get("max_text_chars") or 4000), 1),
            response_window=timedelta(seconds=max(duration, 1)),
            stable_event_identity_verified=connection.options.get("stable_event_identity_verified") is True,
            delivery_receipts=connection.options.get("delivery_receipts") is True,
        )

    def _window_config(self) -> Mapping[str, Any]:
        value = self.connection.options.get("response_window")
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _depth_ok(value: Any, level: int = 0) -> bool:
        if level > 8:
            return False
        children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
        return all(ManyChatWhatsAppAdapter._depth_ok(child, level + 1) for child in children)

    @staticmethod
    def _looks_unrendered(value: str) -> bool:
        return "{{" in value

    def _authenticate(self, request) -> str:
        authentication = self.connection.options.get("authentication")
        authentication = authentication if isinstance(authentication, Mapping) else {}
        keys = authentication.get("keys")
        keys = [_clean(key) for key in keys] if isinstance(keys, (list, tuple)) else []
        keys = [key for key in keys if key]
        if authentication.get("scheme") != "api_key" or not keys:
            raise IngressRejected(503, "authentication_unconfigured", "Connection não configurada")
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        provided = (
            auth_header[7:].strip()
            if auth_header.startswith("Bearer ")
            else _clean(request.META.get("HTTP_X_API_KEY"))
        )
        valid = False
        for key in keys:
            valid |= secrets.compare_digest(provided.encode(), key.encode())
        if not provided or not valid:
            raise IngressRejected(401, "unauthorized", "Não autorizado")
        return "api_key"

    def authenticate_and_normalize(self, request, received_at: datetime) -> InboundEvent:
        """Autentica o External Request e fotografa os campos deste disparo."""
        authentication = self._authenticate(request)
        try:
            data = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
            raise IngressRejected(400, "invalid_json", "JSON inválido") from exc
        if not isinstance(data, dict):
            raise IngressRejected(400, "invalid_shape", "Corpo precisa ser um objeto JSON")
        if not self._depth_ok(data):
            raise IngressRejected(400, "payload_too_deep", "JSON profundo demais")

        subject_value = data.get("subscriber_id")
        if isinstance(subject_value, bool) or not isinstance(subject_value, (str, int)):
            raise IngressRejected(400, "subject_required", "subscriber_id obrigatório", field="subscriber_id")
        subject = _clean(subject_value)
        if not subject or len(subject) > 512 or self._looks_unrendered(subject):
            raise IngressRejected(400, "subject_required", "subscriber_id obrigatório", field="subscriber_id")

        text_value = data.get("text", "")
        if not isinstance(text_value, str):
            raise IngressRejected(400, "invalid_content", "Conteúdo inválido", field="text")
        text = "" if self._looks_unrendered(text_value) else text_value.strip()
        prefixes = self.connection.options.get("pilot_prefixes")
        if isinstance(prefixes, (list, tuple)):
            lowered = text.casefold()
            for value in sorted((_clean(item) for item in prefixes), key=len, reverse=True):
                if value and lowered == value.casefold():
                    text = _clean(self.connection.options.get("pilot_entry_text")) or "oi"
                    break
                if value and lowered.startswith(value.casefold() + " "):
                    text = text[len(value):].strip()
                    break
        if len(text) > 16000:
            raise IngressRejected(413, "text_too_large", "Texto muito grande", field="text")

        event_value = data.get("event_id", "")
        if isinstance(event_value, bool) or not isinstance(event_value, (str, int)):
            raise IngressRejected(400, "invalid_event_id", "Identidade de evento inválida", field="event_id")
        event_id = _clean(event_value)
        if len(event_id) > 4096:
            raise IngressRejected(400, "invalid_event_id", "Identidade de evento inválida", field="event_id")

        message_type = data.get("message_type", "text")
        if message_type not in ("text", "audio", "image", "video", "file"):
            raise IngressRejected(400, "invalid_message_type", "Tipo de mensagem inválido", field="message_type")
        correlation_ref = data.get("correlation_ref", "")
        if not isinstance(correlation_ref, str) or len(correlation_ref) > 256:
            raise IngressRejected(400, "invalid_metadata", "Metadado inválido", field="correlation_ref")

        profile: dict[str, str] = {}
        for key in ("first_name", "last_name"):
            value = data.get(key)
            if isinstance(value, str) and value.strip() and not self._looks_unrendered(value):
                profile[key] = value.strip()
        scope = TransportScope(
            provider=self.connection.provider,
            account=self.connection.account,
            channel=self.connection.channel,
            subject=subject,
            connection_key=self.connection.key,
        )
        envelope = {
            "provider": scope.provider,
            "account_id": scope.account,
            "transport_channel": scope.channel,
            "authentication": authentication,
            **{key: data[key] for key in ("provider_timestamp",) if key in data},
        }
        evidence = self.window_evidence(envelope, received_at)
        assurance = "verified" if event_id and self.capabilities.stable_event_identity_verified else "unverified" if event_id else "unavailable"
        semantic_payload = {
            "subject": subject,
            "event_id": event_id,
            "message_type": str(message_type),
            "text": text,
        }
        return InboundEvent(
            scope=scope,
            text=text,
            message_type=str(message_type),
            received_at=received_at,
            event_id=event_id,
            event_identity_assurance=assurance,
            profile=profile,
            correlation_ref=correlation_ref,
            authentication_assurance=authentication,
            payload_hash=hashlib.sha256(
                json.dumps(
                    semantic_payload,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            window_evidence=evidence,
        )

    def window_evidence(self, envelope: Mapping[str, Any], now: datetime) -> WindowEvidence | None:
        config = self._window_config()
        field = _clean(config.get("field"))
        timezone_name = _clean(config.get("timezone"))
        source = _clean(config.get("source"))
        policy = _clean(config.get("policy"))
        authentication = _clean(config.get("authentication"))
        if not all((field, timezone_name, source, policy, authentication)):
            return None
        if envelope.get("authentication") != authentication:
            return None
        if (
            envelope.get("provider"),
            envelope.get("account_id"),
            envelope.get("transport_channel"),
        ) != (self.connection.provider, self.connection.account, self.connection.channel):
            return None
        try:
            local_zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            return None
        duration = self.capabilities.response_window
        if duration is None:
            return None
        raw = envelope.get(field)
        if isinstance(raw, str) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?",
            raw,
        ):
            try:
                observed_at = datetime.fromisoformat(raw)
                if observed_at.tzinfo is None:
                    observed_at = observed_at.replace(tzinfo=local_zone)
                observed_at = observed_at.astimezone(UTC)
            except (ValueError, TypeError, OverflowError):
                observed_at = None
            if observed_at is not None and timedelta(0) <= now - observed_at < duration:
                return WindowEvidence(
                    policy=policy,
                    source=source,
                    observed_at=observed_at,
                    valid_until=observed_at + duration,
                    assurance="provider_window",
                )
        if not self.capabilities.provider_enforces_response_window:
            return None
        # A recepcao autenticada autoriza somente uma tentativa imediata. Ela nao
        # afirma quando o cliente falou nem que a janela esta aberta: o provider
        # continua sendo a barreira final e seu resultado fica no OutboundAttempt.
        return WindowEvidence(
            policy=policy,
            source=AUTHENTICATED_INGRESS_SOURCE,
            observed_at=now,
            valid_until=now + duration,
            assurance=PROVIDER_ENFORCED_ATTEMPT,
        )

    def authorize_response(
        self,
        evidence: WindowEvidence | Mapping[str, Any] | None,
        now: datetime,
        *,
        purpose: str,
    ) -> ResponseAuthorization:
        config = self._window_config()
        required = ("policy", "source", "field", "timezone", "authentication")
        if any(not _clean(config.get(key)) for key in required):
            return ResponseAuthorization(False, "window_policy_unconfigured")
        evidence = WindowEvidence.from_value(evidence)
        purposes = config.get("purposes")
        allowed_purposes = set(purposes) if isinstance(purposes, (list, tuple, set)) else set()
        if purpose not in allowed_purposes:
            return ResponseAuthorization(False, "purpose_not_allowed")
        if evidence is None:
            return ResponseAuthorization(False, "window_evidence_missing")
        provider_window = (
            evidence.source == _clean(config.get("source"))
            and evidence.assurance == "provider_window"
        )
        provider_enforced_attempt = (
            self.capabilities.provider_enforces_response_window
            and evidence.source == AUTHENTICATED_INGRESS_SOURCE
            and evidence.assurance == PROVIDER_ENFORCED_ATTEMPT
        )
        if evidence.policy != _clean(config.get("policy")) or not (
            provider_window or provider_enforced_attempt
        ):
            return ResponseAuthorization(False, "window_policy_mismatch")
        if evidence.observed_at > now or evidence.valid_until <= now:
            return ResponseAuthorization(False, "window_closed")
        return ResponseAuthorization(
            True,
            "provider_window_evidence" if provider_window else PROVIDER_ENFORCED_ATTEMPT,
            evidence.valid_until,
        )

    def send_text(self, subject: str, text: str) -> SendOutcome:
        from shopman.shop.adapters import notification_manychat

        try:
            result = notification_manychat.send_text_result(subject, text)
        except Exception as exc:
            logger.warning("concierge.transport.acceptance_unconfirmed exception_type=%s", type(exc).__name__)
            return SendOutcome("unknown", "acceptance_unconfirmed")
        state = "accepted" if result.get("success") else "unknown" if result.get("outcome_unknown") else "not_applied"
        receipt = result.get("message_id") or result.get("provider_receipt_ref") or ""
        return SendOutcome(state, _clean(result.get("error")), _clean(receipt))

    def set_handoff(self, subject: str, on: bool) -> HandoffOutcome:
        from shopman.shop.adapters import notification_manychat

        field_name = _clean(self.connection.options.get("handoff_field"))
        if not field_name:
            return HandoffOutcome("not_applied", "handoff_not_configured")
        try:
            accepted = notification_manychat.set_custom_field(subject, field_name, "1" if on else "")
        except Exception as exc:
            logger.warning("concierge.transport.handoff_unconfirmed exception_type=%s", type(exc).__name__)
            return HandoffOutcome("unknown", "acceptance_unconfirmed")
        if accepted is not True:
            return HandoffOutcome("unknown", "acceptance_unconfirmed")
        return HandoffOutcome("accepted")

    def identify(self, subject: str, profile: Mapping[str, Any]):
        from shopman.guestman.adapters.auth import CustomerResolver

        info = CustomerResolver().upsert_manychat_subscriber({"id": subject})
        if info is None:
            return None
        return IdentityResolution(
            customer_uuid=info.uuid,
            assurance="verified_customer",
            phone=info.phone or "",
            name=info.name or "",
        )
