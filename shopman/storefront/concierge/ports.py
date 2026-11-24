"""As portas da Nice para o framework de comércio conversacional: canal, modelo e posse (N4).

- ``NiceChannel`` (``ChannelPort``): fachada sobre o ``ConversationAdapter`` da conexão do
  WhatsApp. ``normalize`` traduz o envelope de entrada da Concierge (``InboundEvent.as_envelope``)
  em ``InteractionEvent``; ``capabilities()`` traduz as ``ChannelCapabilities`` da conexão. No
  alpha a identidade do evento **não** é verificada (``stable_event_identity_verified=false``),
  e a porta diz isso: o evento sai ``provider_claimed``, nunca ``verified``. Enviar, consultar a
  entrega e pedir transferência estão declarados e **não suportados** aqui: o envio da Nice
  segue pelo caminho legado até o N9, e a sombra (N5) nunca envia.
- ``LocalReader`` (``ModelPort``): o leitor local por regra da Concierge
  (``intents.local_acts``), o mesmo do ``--reader local`` do placar. Nenhuma chamada a modelo,
  custo ``Unavailable`` (nunca zero). ``draft`` e ``score`` não existem (corte C1).
- ``ConversationOwnership`` (``Ownership`` do comércio): o sujeito do contexto confiável é a
  conversa (``conversation:<pk>``); a sacola, o cliente e os pedidos são os dela.

O texto do cliente não passa por aqui: o evento leva só a referência (``message:<pk>``), e o
leitor resolve a referência do lado do Shopman (N23).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from conversational_commerce.contracts import ExposureEvent, InteractionEvent, Producer, Understanding, sha256_hash
from conversational_commerce.ports import Capabilities, Consumption, PortError, TrustedContext
from conversational_commerce.ports.channel import OPERATIONS as CHANNEL_OPERATIONS
from conversational_commerce.ports.model import OPERATIONS as MODEL_OPERATIONS

from shopman.shop.conversational.commerce_read import instant

SUBJECT_PREFIX = "conversation:"
MESSAGE_PREFIX = "message:"
TEXT_PREFIX = "text:"
READER = Producer(name="concierge-local-rules", version="2")
UNAVAILABLE = {"status": "unavailable", "reason": "no_calibration"}

# Ato da Concierge (``intents``) → ato da lista fechada do framework. O que não tem par vira
# ``unknown``: o núcleo nunca recebe ato fora da lista dele (K05).
ACT_MAP = {
    "greet": "greet",
    "thanks": "thank",
    "product_question": "ask_item",
    "order": "change_quantity",
    "hours_delivery": "ask_hours",
    "complaint": "complain",
    "cancel_order": "cancel_order",
    "human": "request_human",
}


def subject_of(conversation_id: int | str) -> str:
    return f"{SUBJECT_PREFIX}{conversation_id}"


#: A sacola que a conversa ainda não tem: o alvo do primeiro pedido pelo motor. Nasce no efeito.
NEW_CART_PREFIX = "new-cart:"


def new_cart_ref(conversation_id: int | str) -> str:
    return f"{NEW_CART_PREFIX}{subject_of(conversation_id)}"


def _conversation(ctx: TrustedContext):
    from shopman.shop.models import Conversation

    subject = ctx.subject or ""
    if not subject.startswith(SUBJECT_PREFIX):
        return None
    try:
        return Conversation.objects.filter(pk=int(subject[len(SUBJECT_PREFIX):])).first()
    except ValueError:
        return None


class ConversationOwnership:
    """A sacola, o cliente e os pedidos da conversa do contexto confiável; de mais ninguém."""

    def cart(self, ctx: TrustedContext) -> str | None:
        conversation = _conversation(ctx)
        return (conversation.session_key or None) if conversation is not None else None

    def new_cart(self, ctx: TrustedContext) -> str | None:
        """A sacola nova da conversa, enquanto ela não tem nenhuma (nasce no efeito, nunca na leitura)."""
        conversation = _conversation(ctx)
        if conversation is None or conversation.session_key:
            return None
        return new_cart_ref(conversation.pk)

    def customer(self, ctx: TrustedContext) -> str | None:
        conversation = _conversation(ctx)
        return (conversation.customer_ref or None) if conversation is not None else None

    def owns_order(self, ctx: TrustedContext, order_ref: str) -> bool:
        """O mesmo filtro de identidade que o ``order_status`` da Concierge usa."""
        from shopman.orderman.models import Order

        from shopman.shop.services.customer_orders import customer_identity_filter

        conversation = _conversation(ctx)
        if conversation is None or not order_ref:
            return False
        identity = customer_identity_filter(customer_ref=conversation.customer_ref or None,
                                            phone=conversation.phone or None)
        if identity is None:
            return False
        return Order.objects.filter(identity).filter(ref__iexact=order_ref).exists()


#: O estado do envio da Concierge (``OutboundAttempt.State``) no vocabulário da exposição.
EXPOSURE_STATE = {"prepared": "prepared", "executing": "submitted", "accepted": "accepted",
                  "not_applied": "not_applied", "unknown": "unknown", "delivered": "delivered", "read": "read"}
EXPOSURE_PREFIX = "exp-msg-"
REALIZER = Producer(name="concierge-channel", version="1")


@dataclass
class NiceChannel:
    """``ChannelPort`` sobre o adaptador da conexão da Concierge.

    O envio (decisão de 22/11/2026, "o motor fala") passa pelo MESMO caminho da resposta de
    hoje: ``service.send_out_of_turn`` prepara com as regras da casa e a prova de janela, e o
    ``_dispatch_reply`` envia. O texto vem de ``bodies`` (o ``Engine.bodies`` do turno, pelo
    ``body_ref``). A exposição diz o que de fato aconteceu: o hash é o do texto que saiu (as
    regras da casa podem consertar a frase) e o estado é o do transporte.
    """

    adapter: Any
    bodies: Mapping[str, str] | None = None
    #: Os pedidos de transferência do turno (``request_handoff``). A entrega à equipe é a de hoje
    #: (``service.mark_handoff``), feita DEPOIS que o turno do motor fecha: ela sobe a cerca do turno e tira a
    #: conversa da Concierge, e no meio do turno revogaria a resposta que diz ao cliente que a equipe vem.
    handoffs: list[str] | None = None
    PORT = "channel"

    def capabilities(self) -> Capabilities:
        caps = self.adapter.capabilities
        window = caps.response_window
        return Capabilities(
            port="channel", operations=CHANNEL_OPERATIONS,
            unsupported=("request_handoff",),
            guarantees={"stable_event_identity_verified": bool(caps.stable_event_identity_verified),
                        "read_receipts": False, "delivery_receipts": bool(caps.delivery_receipts),
                        "supports_handoff": bool(caps.supports_handoff),
                        "response_window_seconds": int(window.total_seconds()) if window else None,
                        "max_text_chars": int(caps.max_text_chars)})

    def normalize(self, ctx: TrustedContext, raw: Mapping[str, Any], received_at: str) -> InteractionEvent:
        """O envelope da Concierge (``InboundEvent.as_envelope``), com ``message_ref`` opcional."""
        event_id = str(raw.get("event_id") or "")
        verified = bool(self.adapter.capabilities.stable_event_identity_verified)
        # Sem verificação da conexão, o id do provedor é só alegado; sem id, não há identidade.
        identity = ({"id": event_id, "assurance": "verified" if verified and raw.get("event_identity_assurance")
                     == "verified" else "provider_claimed"} if event_id else {"assurance": "none"})
        subject = str(raw.get("subject") or "")
        message_ref = raw.get("message_ref")
        return InteractionEvent(
            id=f"evt-{raw.get('connection_key', 'conn')}-{event_id or raw.get('payload_hash') or received_at}",
            tenant=ctx.tenant, environment=ctx.environment, trace_id=f"trace-{event_id or received_at}",
            occurred_at=_iso_instant(raw.get("occurred_at")) or received_at,
            producer={"name": "concierge-channel", "version": "1"},
            channel_binding={"channel": str(raw.get("transport_channel") or "whatsapp"),
                             "conversation_ref": subject or "unknown"},
            actor="customer", event_identity=identity, type="message",
            content_ref=f"{MESSAGE_PREFIX}{message_ref}" if message_ref else None,
            # O telefone do WhatsApp só é transportado; nada promove identidade aqui (P03).
            identity_evidence=[{"kind": "channel_identity", "ref": subject, "assurance": "transported"}]
            if subject else [])

    def send(self, ctx, prepared, idempotency_key):
        from .service import send_out_of_turn

        conversation = _conversation(ctx)
        if conversation is None:
            raise PortError("object_forbidden", "o contexto não é uma conversa da Concierge")
        text = (self.bodies or {}).get(prepared.body_ref)
        if not text:
            raise PortError("invalid_content", f"sem o texto de {prepared.body_ref}: nada foi enviado")
        message = send_out_of_turn(conversation, text, send_key=idempotency_key)
        if message is None:
            raise PortError("provider_unavailable", "a conversa não tem entrada por vínculo ativo: nada foi enviado")
        return self._exposure(ctx, message, decision_id=prepared.decision_id, recipient=prepared.recipient)

    def delivery_status(self, ctx, exposure_id):
        from shopman.shop.models import ConversationMessage

        conversation = _conversation(ctx)
        ref = exposure_id[len(EXPOSURE_PREFIX):].split("-", 1)[0] if exposure_id.startswith(EXPOSURE_PREFIX) else ""
        message = (ConversationMessage.objects.filter(pk=int(ref), conversation=conversation).first()
                   if ref.isdigit() and conversation is not None else None)
        if message is None:
            raise PortError("object_forbidden", f"exposição que não é desta conversa: {exposure_id}")
        envelope = message.envelope or {}
        return self._exposure(ctx, message, decision_id=str(envelope.get("decision_id") or ""),
                              recipient=str(envelope.get("recipient") or ""))

    def _exposure(self, ctx, message, *, decision_id: str, recipient: str) -> ExposureEvent:
        if decision_id and recipient and not (message.envelope or {}).get("decision_id"):
            message.envelope = {**(message.envelope or {}), "decision_id": decision_id, "recipient": recipient}
            message.save(update_fields=["envelope"])
        state = EXPOSURE_STATE.get(str(message.transport_state or ""), "unknown")
        attempts = max(1, message.outbound_attempts.count())
        return ExposureEvent(
            id=f"{EXPOSURE_PREFIX}{message.pk}-{state}", tenant=ctx.tenant, environment=ctx.environment,
            trace_id=f"trace-{decision_id or message.pk}", occurred_at=instant(datetime.now(UTC)),
            producer=REALIZER, decision_id=decision_id or f"message-{message.pk}",
            content_hash=sha256_hash({"text": message.text}), realizer=REALIZER,
            recipient=recipient or "unknown", attempt=attempts, state=state)

    def request_handoff(self, ctx, request):
        """Anota o pedido de transferência; quem transfere é o serviço, ao fechar o turno (``handoffs``)."""
        if self.handoffs is None:
            raise PortError("capability_missing", "canal sem turno do motor: a transferência segue pelo caminho de hoje")
        self.handoffs.append(str(request.reason or "customer_request"))


def _cart_fields(act, conversation, text: str) -> dict:
    """O que o ``change_cart`` do framework pede: o produto (SKU) e a quantidade, com a relatividade.

    O produto sai da MESMA busca da sacola na conversa (``intents.read_cart_item``), sem modelo:
    empate entre produtos fica sem ``item`` e o framework pergunta. A quantidade é a da fala;
    "mais 2" vai como ``relative`` (o framework não trata relativa como absoluta), e "tira" é 0.
    """
    from .intents import _order_qty, read_cart_item
    from .tools import ToolContext

    qty, relative = _order_qty(act)
    fields: dict = {}
    if conversation is not None:
        def context(query: str) -> ToolContext:
            return ToolContext(conversation=conversation, channel_ref=conversation.channel_ref or "whatsapp",
                               customer_text=query or text)

        reading = read_cart_item(act, conversation=conversation, context=context)
        if reading is not None and len(reading.items) == 1 and reading.items[0].get("sku"):
            fields["item"] = str(reading.items[0]["sku"])
            if reading.removing:
                return {**fields, "quantity": "0"}
    if qty:
        fields["quantity"] = str(qty)
        if relative:
            fields["relative"] = True
    return fields


class LocalReader:
    """``ModelPort`` pelo leitor local por regra da Concierge: sem modelo, sem custo inventado."""

    PORT = "model"

    def capabilities(self) -> Capabilities:
        return Capabilities(port="model", operations=MODEL_OPERATIONS, unsupported=("draft", "score"),
                            guarantees={"priced": False, "calls_model": False})

    def interpret(self, ctx: TrustedContext, request) -> tuple[Understanding, Consumption]:
        from .intents import local_acts

        if request.request.data_class == "personal":
            raise PortError("object_forbidden", "dado pessoal não vai ao leitor")
        text = resolve_text(request.content_ref)
        allowed = set(request.allowed_acts)
        acts = []
        conversation = _conversation(ctx)
        for act in local_acts(text):
            name = ACT_MAP.get(act.act, "unknown")
            if allowed and name not in allowed:
                name = "unknown"
            fields = _cart_fields(act, conversation, text) if name == "change_quantity" else {}
            acts.append({"act": name, "fields": fields, "confidence": UNAVAILABLE})
        now = instant(datetime.now(UTC))
        understanding = Understanding(
            id=f"und-{request.event_id}", tenant=ctx.tenant, environment=ctx.environment,
            trace_id=f"trace-{request.event_id}", occurred_at=now, producer=READER, event_id=request.event_id,
            acts=acts or [{"act": "unknown", "fields": {}, "confidence": UNAVAILABLE}],
            signals={"friction": "unknown", "risk": "unknown"}, reader=READER)
        return understanding, Consumption(model=READER, calls=0, cost={"status": "unavailable",
                                                                       "reason": "no_model_call"})

    def draft(self, ctx, request, plan):
        raise PortError("capability_missing", "a Nice não redige por modelo (corte C1)")

    def score(self, ctx, request):
        raise PortError("capability_missing", "o leitor local não pontua")


def resolve_text(content_ref: str | None) -> str:
    """A referência protegida do conteúdo: ``message:<pk>`` (a mensagem gravada) ou ``text:`` (teste)."""
    from shopman.shop.models import ConversationMessage

    if not content_ref:
        return ""
    if content_ref.startswith(TEXT_PREFIX):
        return content_ref[len(TEXT_PREFIX):]
    if content_ref.startswith(MESSAGE_PREFIX):
        try:
            message = ConversationMessage.objects.filter(pk=int(content_ref[len(MESSAGE_PREFIX):])).first()
        except ValueError:
            return ""
        return message.text if message is not None else ""
    return ""


def shared_location_of(content_ref: str | None) -> bool:
    """A fala é a localização enviada pelo WhatsApp (o pin): o endereço sai dela, nunca de texto digitado."""
    from shopman.shop.models import ConversationMessage

    if not content_ref or not content_ref.startswith(MESSAGE_PREFIX):
        return False
    try:
        message = ConversationMessage.objects.filter(pk=int(content_ref[len(MESSAGE_PREFIX):])).first()
    except ValueError:
        return False
    return message is not None and (message.envelope or {}).get("message_type") == "location"


def _iso_instant(value: Any) -> str | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return instant(moment)


def nice_channel() -> NiceChannel | None:
    """A porta de canal sobre a conexão ativa do WhatsApp, ou ``None`` sem conexão."""
    from .transport import adapter_for_connection, configured_connections

    for connection in configured_connections():
        if connection.channel == "whatsapp":
            adapter = adapter_for_connection(connection)
            if adapter is not None:
                return NiceChannel(adapter)
    return None
