"""
Notification service.

Adapter: get_adapter("notification", channel=...) → notification_manychat / email / console

- send(): ASYNC — cria Directive para processamento posterior pelo handler.
- deliver_order_notification(): SYNC — executa a cadeia de backends diretamente.
  Chamado pelo NotificationSendHandler após resolver o pedido.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Directive
from shopman.utils.monetary import format_money

from shopman.shop.notifications import notify

logger = logging.getLogger(__name__)

TOPIC = "notification.send"

#: O aviso que leva a cobrança do pedido remoto anotado no PDV.
PAYMENT_LINK_TEMPLATE = "payment_link_sent"

#: Intervalo mínimo entre dois reenvios do MESMO aviso. Clique duplo, operador
#: ansioso e cliente que "ainda não viu" em 30 s não podem virar três mensagens.
RESEND_MIN_INTERVAL_SECONDS = 60

_ACTIVE_NOTIFICATION_TEMPLATES = frozenset(
    {
        "payment_requested",
        # Link de pagamento do pedido remoto anotado no PDV: é a cobrança inteira
        # — se não chega, a casa fica esperando um dinheiro que ninguém pediu.
        "payment_link_sent",
        "payment_expired",
        "payment_failed",
        "order_ready",
        "order_ready_pickup",
        "order_ready_delivery",
        "order_dispatched",
        "order_delivered",
        "order_cancelled",
        "order_rejected",
        # Fila de espera (WP-P2E): os dois lados do "nunca silencioso". O
        # chamado tem prazo e a saída tira a vaga — nenhum dos dois pode
        # depender de o cliente abrir a tela por conta própria.
        "waitlist_available",
        "waitlist_released",
    }
)

_BACKEND_CHANNELS = {
    "manychat": "whatsapp",
    "sms": "sms",
    "email": "email",
    "push": "push",
    "webhook": "webhook",
    "console": "console",
}

_ORIGIN_CHANNELS = {"whatsapp", "instagram", "web"}


def send(order, template: str, **extra) -> None:
    """
    Schedule a notification for the order.

    Creates a Directive with topic="notification.send". The handler that
    processes the Directive resolves the adapter, builds context, and
    executes the configured fallback chain (for example, manychat → sms → email).

    ASYNC — does not block the request.
    """
    template = _canonical_template(template)
    dedupe_key = _dedupe_key(order, template)
    existing = (
        Directive.objects.filter(
            topic=TOPIC,
            dedupe_key=dedupe_key,
            status__in=("queued", "running", "done"),
        )
        .order_by("-created_at")
        .first()
    )
    if existing:
        logger.info(
            "notification.send: skipped duplicate %s for order %s",
            template,
            order.ref,
        )
        return

    payload = {
        "order_ref": order.ref,
        "channel_ref": order.channel_ref or "",
        "template": template,
        "requires_active_notification": _requires_active_notification(template),
    }
    payload.update(extra)

    # Include origin_channel for routing
    origin = (order.data or {}).get("origin_channel")
    if origin in _ORIGIN_CHANNELS:
        payload["origin_channel"] = origin

    customer_ref = _customer_ref(order)
    if customer_ref:
        payload["customer_ref"] = customer_ref

    from shopman.shop.directives import create_deduped

    created = create_deduped(topic=TOPIC, payload=payload, dedupe_key=dedupe_key)
    if created is None:
        # Corrida no check-then-create: outro processo enfileirou a mesma
        # notificação entre o filtro acima e o INSERT. Dedupe-hit, não erro.
        logger.info(
            "notification.send: skipped duplicate %s for order %s (constraint)",
            template,
            order.ref,
        )
        return

    logger.info("notification.send: queued %s for order %s", template, order.ref)


class NotificationResendRefused(Exception):
    """Reenvio recusado por um guarda de negócio.

    ``code`` é estável (a tela decide por ele), ``message`` é a frase que o
    operador lê, ``status`` o HTTP que a view devolve. Não é erro de programa:
    é a casa dizendo por que NÃO vai mandar de novo.
    """

    def __init__(self, code: str, message: str, *, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def latest_delivery(order, template: str) -> Directive | None:
    """A última Directive deste aviso para este pedido — envio original ou reenvio."""
    return (
        Directive.objects.filter(
            topic=TOPIC,
            payload__order_ref=order.ref,
            payload__template=_canonical_template(template),
        )
        .order_by("-created_at", "-pk")
        .first()
    )


def resend(order, template: str, *, min_interval_seconds: int = RESEND_MIN_INTERVAL_SECONDS) -> Directive:
    """Enfileira de novo um aviso já enviado, apesar do dedupe de ``send``.

    Cada reenvio é UMA Directive nova, com a chave de dedupe do envio original
    mais um sufixo de tentativa (``…:resend:<n>``, ``n`` = quantas Directives
    deste pedido+template já existem + 1). Assim retry, backoff e escalada para
    ``OperatorAlert`` vêm de graça do ``NotificationSendHandler``, e o dedupe do
    envio original fica intacto — um retry do PDV continua não mandando duas.

    Dois guardas, os dois sobre a HISTÓRIA e não sobre o pedido:

    - envio anterior ainda ``queued``/``running`` → recusa ``notification_send_pending``.
      Enfileirar por cima faria o cliente receber duas mensagens quando o worker
      voltasse (ou nenhuma, pelo mesmo motivo da primeira);
    - último envio há menos de ``min_interval_seconds`` → ``notification_resend_too_soon``.

    O clique duplo no MESMO segundo passa pelos dois guardas com o mesmo ``n``;
    o UNIQUE parcial do Core recusa o segundo INSERT e devolvemos a Directive
    que o primeiro criou — nunca duas.
    """
    template = _canonical_template(template)
    history = Directive.objects.filter(topic=TOPIC, payload__order_ref=order.ref, payload__template=template)
    latest = history.order_by("-created_at", "-pk").first()
    if latest is not None:
        if latest.status in (Directive.Status.QUEUED, Directive.Status.RUNNING):
            raise NotificationResendRefused(
                "notification_send_pending",
                "O envio anterior ainda está em andamento. Aguarde um instante.",
            )
        age = (timezone.now() - latest.created_at).total_seconds()
        if age < min_interval_seconds:
            wait = max(1, int(min_interval_seconds - age))
            raise NotificationResendRefused(
                "notification_resend_too_soon",
                f"Acabamos de enviar. Aguarde {wait} s para reenviar.",
            )

    attempt = history.count() + 1
    dedupe_key = f"{_dedupe_key(order, template)}:resend:{attempt}"
    payload = {
        "order_ref": order.ref,
        "channel_ref": order.channel_ref or "",
        "template": template,
        "requires_active_notification": _requires_active_notification(template),
    }
    origin = (order.data or {}).get("origin_channel")
    if origin in _ORIGIN_CHANNELS:
        payload["origin_channel"] = origin
    customer_ref = _customer_ref(order)
    if customer_ref:
        payload["customer_ref"] = customer_ref

    from shopman.shop.directives import create_deduped

    created = create_deduped(topic=TOPIC, payload=payload, dedupe_key=dedupe_key)
    if created is None:
        # Corrida: o outro clique do mesmo segundo já enfileirou este reenvio.
        existing = Directive.objects.filter(topic=TOPIC, dedupe_key=dedupe_key).order_by("-pk").first()
        if existing is None:  # pragma: no cover — a constraint garante que existe
            raise NotificationResendRefused("notification_send_pending", "Reenvio já em andamento.")
        logger.info("notification.resend: joined in-flight resend %s for order %s", template, order.ref)
        return existing

    logger.info("notification.resend: queued %s #%d for order %s", template, attempt, order.ref)
    return created


def payment_link_resend_refusal(order) -> NotificationResendRefused | None:
    """Por que este pedido NÃO aceita reenvio do link — ou ``None`` se aceita.

    Só o que é do PEDIDO (forma, URL, cancelamento, captura, vencimento). Os
    guardas de cadência (envio em andamento, cedo demais) são de ``resend`` e
    só se decidem na hora do gesto. A projection do gestor usa esta função
    para mostrar ou esconder o botão; ``resend_payment_link`` usa a mesma para
    recusar — um dono só para a regra, e a tela nunca oferece o que o servidor
    vai negar.

    Reenvio manda a MESMA URL enquanto ela vale. Não existe regenerar: link
    vencido é pedido que a máquina de timeout cancela, e o caminho é refazer a
    venda.
    """
    payment = (order.data or {}).get("payment") or {}
    if str(payment.get("method") or "").strip().lower() != "link" or not payment.get("checkout_url"):
        return NotificationResendRefused("payment_link_unavailable", "Este pedido não tem link de pagamento.")
    if order.status == "cancelled":
        return NotificationResendRefused(
            "payment_link_order_cancelled",
            "Pedido cancelado: o link não vale mais. Refaça a venda para cobrar de novo.",
        )

    from shopman.shop.services import payment as payment_svc

    if payment_svc.has_sufficient_captured_payment(order):
        return NotificationResendRefused("payment_link_already_paid", "O cliente já pagou este pedido.")

    expires_at = _parse_expires_at(payment.get("expires_at"))
    if expires_at is not None and expires_at <= timezone.now():
        return NotificationResendRefused(
            "payment_link_expired",
            "O link venceu. Refaça a venda para gerar um novo.",
        )
    return None


def resend_payment_link(order) -> Directive:
    """Reenvia o aviso ``payment_link_sent`` — o gesto do operador quando o cliente diz "não chegou".

    Guardas do pedido (``payment_link_resend_refusal``) e de cadência
    (``resend``); as recusas de cadência ganham o prefixo do link para a tela
    falar um vocabulário só (``payment_link_send_pending``,
    ``payment_link_resend_too_soon``).
    """
    refusal = payment_link_resend_refusal(order)
    if refusal is not None:
        raise refusal
    try:
        return resend(order, PAYMENT_LINK_TEMPLATE)
    except NotificationResendRefused as exc:
        raise NotificationResendRefused(
            exc.code.replace("notification_", "payment_link_", 1), exc.message, status=exc.status
        ) from exc


def _parse_expires_at(raw) -> datetime | None:
    if not raw:
        return None
    try:
        value = parse_datetime(str(raw))
    except (TypeError, ValueError):
        return None
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


def deliver_order_notification(order, template: str, payload: dict) -> tuple[bool, str | None]:
    """
    Entrega uma notificação de pedido para o cliente via cadeia de backends.

    Tenta cada backend na cadeia configurada pelo canal até um ter sucesso.
    Retorna (True, None) no sucesso ou (False, last_error) se todos falharem.

    SYNC — chamado pelo NotificationSendHandler durante o processamento de directives.
    """
    template = _canonical_template(template)
    backend_chain = _resolve_backend_chain(order)
    requires_active = _requires_active_notification(template, payload=payload)
    backend_chain = _filter_backend_chain(
        order,
        backend_chain,
        payload=payload,
        requires_active=requires_active,
    )

    if not backend_chain or backend_chain == ["none"]:
        if requires_active:
            return False, "no active notification channel available"
        return True, None

    context = _build_context(order, payload, template)
    template = _qualify_template(template, context)
    context["template"] = template

    last_error: str | None = None
    any_attempted = False
    for backend_name in backend_chain:
        if backend_name == "none":
            continue

        recipient = _resolve_recipient(order, backend_name)
        if not recipient:
            logger.debug("notification.deliver: no recipient for backend=%s order=%s, skipping", backend_name, order.ref)
            continue

        from shopman.shop.notifications import get_backend as _get_backend
        backend_module = _get_backend(backend_name)
        if backend_module and hasattr(backend_module, "is_available"):
            if not backend_module.is_available():
                logger.debug(
                    "notification.deliver: backend=%s not configured, skipping order=%s",
                    backend_name, order.ref,
                )
                continue

        any_attempted = True

        if backend_name == "manychat" and order.handle_type == "manychat":
            context["subscriber_id"] = order.handle_ref

        result = notify(event=template, recipient=recipient, context=context, backend=backend_name)

        if result.success:
            return True, None

        last_error = result.error or "unknown"
        logger.info(
            "notification backend %s failed for order %s, trying next in chain",
            backend_name, order.ref,
        )

    if not any_attempted:
        # No recipient for any backend — notifications not configured, not a failure.
        if requires_active:
            logger.warning(
                "notification.deliver: active notification has no recipient order=%s template=%s",
                order.ref,
                template,
            )
            return False, "no active notification recipient available"
        logger.info("notification.deliver: no recipient for any backend, skipping order=%s template=%s", order.ref, template)
        return True, None

    return False, last_error


# ── private helpers ──


def _resolve_backend_chain(order) -> list[str]:
    """Resolve a cadeia de backends via ChannelConfig cascade."""
    from shopman.shop.config import ChannelConfig

    notifications = ChannelConfig.for_channel(order.channel_ref).notifications
    backend = notifications.backend or "manychat"
    chain = notifications.fallback_chain or []
    return [backend] + [b for b in chain if b != backend]


def _filter_backend_chain(
    order,
    backend_chain: list[str],
    *,
    payload: dict,
    requires_active: bool,
) -> list[str]:
    """
    Keep notification routing aligned with customer channel preferences.

    Três estados, não dois — e confundir dois deles era o defeito:

    - **opt-in gravado** → o canal vale para tudo;
    - **opt-out gravado** (``revoked_at`` preenchido) → o canal está PROIBIDO, e
      nada o traz de volta: nem a origem do pedido, nem a natureza do aviso. Foi
      a pessoa que desligou o botão que a própria loja ofereceu;
    - **nenhum registro** (a pessoa nunca passou por Preferências) → o aviso do
      PRÓPRIO pedido sai, com base legal de execução de contrato (LGPD art. 7º
      V). "Seu pedido está pronto" não é marketing: é o combinado da compra que
      ela acabou de fazer, com o telefone que ela mesma deu para isso.

    O que estava errado, e por que os dois lados doíam:

    1. o bypass por origem (``origin == "whatsapp"``) reinstalava o WhatsApp
       DEPOIS do filtro de consentimento, sem olhar se havia opt-out. Como o
       login principal da loja é o link de acesso por WhatsApp, todo cliente
       logado carrega ``origin_channel = "whatsapp"`` — então o botão "receber
       atualizações por WhatsApp" não desligava nada. Com o ManyChat vivo em
       produção, isso é o consentimento coletado pela própria tela sendo
       ignorado, e é assim que um número vira reclamação e bloqueio no WhatsApp
       Business;
    2. na outra ponta, o consentimento só nasce em `/conta/preferencias` e nasce
       DESLIGADO nos quatro canais, e o fluxo de compra não passa por lá. Quem
       entrava por "Usar outro número" ficava com a cadeia VAZIA e não recebia
       nada — nem `order_received` — enquanto o acompanhamento promete seis
       vezes que "avisamos você". Com ``DEBUG=1`` o fallback de console
       mascarava, então a suíte nunca viu.

    Marketing continua opt-in puro: campanha não passa por aqui, monta público
    por `ConsentService.get_marketable_customers` (`services/audience.py`), que
    só devolve quem está ``opted_in``.
    """
    customer_ref = payload.get("customer_ref") or _customer_ref(order)
    if not customer_ref:
        return backend_chain

    available_channels = tuple(
        sorted(
            {
                channel
                for backend in backend_chain
                for channel in [_BACKEND_CHANNELS.get(backend)]
                if channel and channel not in {"console", "webhook"}
            }
        )
    )
    revoked_channels = _revoked_notification_channels(customer_ref, available_channels)

    # A regra inteira em uma linha: o aviso do próprio pedido sai por qualquer
    # canal configurado, MENOS os que o titular revogou. "Ausente" e "revogado"
    # deixam de ser a mesma coisa — e é `toggle_notification_consent`
    # (`services/account.py`) que garante que o desligado na tela de
    # Preferências vire um opt-out gravado, e não uma ausência.
    allowed_channels = {
        channel for channel in available_channels if channel not in revoked_channels
    }

    if not allowed_channels and _dev_console_allowed(backend_chain):
        return [backend for backend in backend_chain if backend == "console"]

    if not allowed_channels:
        return []

    filtered: list[str] = []
    for backend in backend_chain:
        channel = _BACKEND_CHANNELS.get(backend)
        if channel in allowed_channels:
            filtered.append(backend)
    return filtered


def _build_context(order, payload: dict, template: str) -> dict:
    """Constrói contexto de notificação a partir dos dados do pedido."""
    fulfillment_type = order.data.get("fulfillment_type", "pickup")

    reason = payload.get("reason")
    context = {
        "order_ref": payload.get("order_ref"),
        "template": template,
        "order_status": order.status,
        "total_q": order.total_q,
        "items": order.snapshot.get("items", []),
        "reason": reason,
        # Pre-formatted, self-suppressing reason line — templates embed `{reason_note}`
        # and it disappears cleanly when no customer-facing reason is present (same
        # pattern as `pix_suffix`). Avoids "Motivo: None"/dangling labels in flat copy.
        "reason_note": f"\n\nMotivo: {reason}" if reason else "",
        "fulfillment_type": fulfillment_type,
        "outside_business_hours": bool(order.data.get("outside_business_hours", False)),
    }

    customer_data = order.data.get("customer", {})
    if isinstance(customer_data, dict):
        context["customer_name"] = customer_data.get("name", "")
    context["customer_phone"] = (
        customer_data.get("phone", "") if isinstance(customer_data, dict) else ""
    )

    customer_uuid = customer_data.get("uuid") if isinstance(customer_data, dict) else None
    if customer_uuid:
        try:
            from uuid import UUID

            from shopman.doorman.protocols.customer import AuthCustomerInfo

            from shopman.shop.services.access_urls import (
                build_payment_access_url,
                build_reorder_access_url,
                build_tracking_access_url,
            )

            auth_customer = AuthCustomerInfo(
                uuid=UUID(str(customer_uuid)),
                name=customer_data.get("name", ""),
                phone=customer_data.get("phone"),
                email=customer_data.get("email"),
                is_active=True,
            )
            order_ref = payload.get("order_ref") or order.ref
            context["tracking_url"] = build_tracking_access_url(auth_customer, order_ref)
            context["payment_url"] = build_payment_access_url(auth_customer, order_ref)
            context["reorder_url"] = build_reorder_access_url(auth_customer, order_ref)
        except Exception:
            # ⚠️ Isto era `logger.debug` e engoliu em silêncio o defeito que chegou ao
            # cliente: sem estas URLs o template do Admin manda `{tracking_url}` cru.
            # Falhar fechado não é opção aqui (o aviso tem de sair), então falha
            # GRITANDO — e o fallback logo abaixo garante um link comum no lugar.
            logger.warning(
                "access_urls: magic link não gerado para o pedido %s; "
                "os links do aviso caem para o link comum de acompanhamento",
                order.ref,
                exc_info=True,
            )

    if order.total_q:
        # ⚠️ Era `:,.2f` cru — "R$ 38.00", ponto decimal americano, na mensagem
        # que o cliente recebe. O formatador da casa é um só.
        context["total"] = f"R$ {format_money(order.total_q)}"

    from shopman.shop.services import storefront_links

    # Destino do aviso de fidelidade: os pontos são mostrados em /conta, e um aviso
    # que anuncia saldo sem dizer onde vê-lo é promessa sem porta.
    context["account_url"] = storefront_links.account_url()

    # PAYMENT-TRACKING-MERGE: o link de pagamento é o do próprio acompanhamento
    # (o Pix/cartão vivem lá inline). Sem tela /pagamento.
    payment = order.data.get("payment")
    if payment:
        context["payment"] = payment
        context["payment_url"] = context.get("payment_url") or storefront_links.order_tracking_url(order.ref)
        copy_paste = payment.get("copy_paste")
        context["copy_paste"] = copy_paste or ""
        context["pix_suffix"] = f" Código PIX: {copy_paste}" if copy_paste else ""
        # A URL da COBRANÇA (sessão hospedada do cartão/link), distinta do
        # `payment_url`, que é o acompanhamento. O aviso do link de pagamento
        # manda o cliente para cá, não para a tela do pedido.
        context["checkout_url"] = str(payment.get("checkout_url") or "")
    else:
        context["payment_url"] = context.get("payment_url") or storefront_links.order_tracking_url(order.ref)
        context["pix_suffix"] = ""
        context["checkout_url"] = ""

    # Mesmo critério do `payment_url` acima: sem magic link (pedido da loja não grava
    # `customer.uuid`, ou a cunhagem do token falhou), o acompanhamento vira o link
    # COMUM do pedido. Sem este fallback a chave sumia do contexto e o texto do Admin
    # entregava `{tracking_url}` literal na tela do cliente — link comum é pior que
    # magic link e MUITO melhor que placeholder cru.
    context["tracking_url"] = context.get("tracking_url") or storefront_links.order_tracking_url(
        order.ref
    )

    # Gêmeas PÚBLICAS dos três links de cliente. O ManyChat recusa, por construção,
    # gravar magic link como campo personalizado do assinante (`_safe_field_value`): o
    # token viveria em texto claro no perfil dele, dentro de uma ferramenta SaaS de
    # marketing. Sem uma gêmea informada aqui, a recusa vira botão EM BRANCO no template
    # aprovado — o canal que interpola o texto na hora (SMS, e-mail) segue recebendo o
    # link pessoal, que é o bom.
    #
    # O destino público de cada um é diferente, e é por isso que quem sabe é o emissor:
    # acompanhar e pagar são a MESMA tela (PAYMENT-TRACKING-MERGE, o Pix/cartão vivem
    # inline no acompanhamento); repetir o pedido é o histórico da conta. Quem chega
    # sem sessão não bate num 404: a loja mostra "entre com seu telefone" e volta para
    # o mesmo pedido (`presentation/orderAccess.ts`).
    public_tracking = storefront_links.order_tracking_url(order.ref)
    context["tracking_url_public"] = public_tracking
    context["payment_url_public"] = public_tracking
    context["reorder_url_public"] = storefront_links.storefront_url(
        storefront_links.path_order_history()
    )

    # Corrida externa (Machine): link de rastreio do entregador, quando existe.
    # Sufixo auto-suprimível (padrão pix_suffix) — some limpo em pedidos sem
    # corrida ou antes do aceite. Distinto do tracking_url (página do pedido).
    courier_block = order.data.get("courier")
    courier_tracking = (
        str(courier_block.get("tracking_url") or "") if isinstance(courier_block, dict) else ""
    )
    context["courier_tracking_url"] = courier_tracking
    context["courier_tracking_suffix"] = (
        f"\nAcompanhe o entregador: {courier_tracking}" if courier_tracking else ""
    )

    return context


def _qualify_template(template: str, context: dict) -> str:
    """
    Qualifica o nome do template com base em atributos do pedido.

    order_ready → order_ready_pickup ou order_ready_delivery
    order_received → order_received_outside_hours (quando a flag está ativa),
        degrada silenciosamente pro `order_received` se a variante não existir.
    """
    template = _canonical_template(template)
    if template == "order_ready":
        ft = context.get("fulfillment_type", "pickup")
        suffix = "delivery" if ft == "delivery" else "pickup"
        return f"{template}_{suffix}"
    if template == "order_received" and context.get("outside_business_hours"):
        from shopman.shop.models import NotificationTemplate
        variant = "order_received_outside_hours"
        if NotificationTemplate.objects.filter(event=variant, is_active=True).exists():
            return variant
    return template


def _resolve_recipient(order, backend_name: str = "") -> str | None:
    """
    Resolve o destinatário com base no tipo de backend.

    manychat → handle_ref (subscriber_id) ou phone
    email    → email
    sms      → phone
    console  → phone ou qualquer identificador
    """
    customer_data = order.data.get("customer", {})
    if not isinstance(customer_data, dict):
        customer_data = {}

    if backend_name == "manychat":
        if order.handle_type == "manychat" and order.handle_ref:
            return order.handle_ref
        # ⚠️ O telefone vai em E.164 COM o "+". O contrato do adapter (e do
        # resolver do guestman) é: dígitos puros = `subscriber_id` do ManyChat;
        # "+55…" = telefone a resolver. O PDV grava o telefone sem o "+"
        # ("5543984049009"), e o adapter o tomava por subscriber_id — o ManyChat
        # respondia "Subscriber does not exist", a cadeia caía para o e-mail, e
        # um cliente COM WhatsApp cadastrado nunca recebia o link por lá.
        return _manychat_phone(customer_data.get("phone") or order.data.get("customer_phone"))

    if backend_name == "email":
        email = customer_data.get("email")
        return email or None

    return (
        customer_data.get("phone")
        or order.data.get("customer_phone")
        or (order.handle_ref if order.handle_type in ("customer", "phone") else None)
    )


def _manychat_phone(raw) -> str | None:
    """Telefone em E.164 com "+" para o ManyChat, ou ``None`` quando não há."""
    value = str(raw or "").strip()
    if not value:
        return None
    from shopman.utils.phone import normalize_phone

    normalized = normalize_phone(value)
    if normalized:
        return normalized
    digits = "".join(ch for ch in value if ch.isdigit())
    return f"+{digits}" if digits else None


def _canonical_template(template: str) -> str:
    return str(template or "").strip()


def _requires_active_notification(template: str, *, payload: dict | None = None) -> bool:
    if payload and payload.get("requires_active_notification") is True:
        return True
    return _canonical_template(template) in _ACTIVE_NOTIFICATION_TEMPLATES


def _dedupe_key(order, template: str) -> str:
    return f"{TOPIC}:{order.ref}:{_canonical_template(template)}"


def _customer_ref(order) -> str:
    data = order.data or {}
    customer_ref = data.get("customer_ref")
    if customer_ref:
        return str(customer_ref)

    customer_data = data.get("customer", {})
    if not isinstance(customer_data, dict):
        customer_data = {}
    if customer_data.get("ref"):
        return str(customer_data["ref"])

    customer_uuid = customer_data.get("uuid")
    if customer_uuid:
        try:
            from shopman.shop.projections import customer_context

            resolved = customer_context.customer_ref_by_uuid(customer_uuid)
            if resolved:
                return str(resolved)
        except Exception:
            logger.debug("notification.customer_ref_uuid_lookup_failed order=%s", order.ref, exc_info=True)

    phone = customer_data.get("phone") or data.get("customer_phone")
    if phone:
        try:
            from shopman.guestman.services import customer as customer_service

            customer = customer_service.get_by_phone(phone)
            if customer:
                return str(customer.ref)
        except Exception:
            logger.debug("notification.customer_ref_phone_lookup_failed order=%s", order.ref, exc_info=True)

    return ""


def _revoked_notification_channels(customer_ref: str, channels: tuple[str, ...]) -> frozenset[str]:
    """Canais que o titular DESLIGOU. Falha de leitura silencia o canal.

    O fallback é o oposto do de `enabled`: se não dá para saber, não manda. Errar
    para o lado de mandar sobre um opt-out é violar o consentimento; errar para o
    lado de não mandar é um aviso perdido, e o `requires_active` faz o handler
    reclamar alto em vez de fingir sucesso.
    """
    if not channels:
        return frozenset()
    try:
        from shopman.shop.projections import customer_context

        return customer_context.revoked_notification_channels(customer_ref, channels)
    except Exception:
        logger.warning(
            "notification.revoked_channels_failed customer=%s",
            customer_ref,
            exc_info=True,
        )
        return frozenset(channels)


def _dev_console_allowed(backend_chain: list[str]) -> bool:
    return bool(getattr(settings, "DEBUG", False) and "console" in backend_chain)
