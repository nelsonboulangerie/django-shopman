"""
Notification handler — processa directives notification.send.

Suporta dois tipos de notificação:
- Pedido: payload com order_ref → delega para services.notification.deliver_order_notification()
- Sistema: payload com event (ex: stock.alert) → notifica operador via email/console

O handler é fino: lê o directive, obtém o pedido, delega ao service, escreve o status.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import NOTIFICATION_SEND
from shopman.shop.notifications import notify
from shopman.shop.services import notification as notification_svc
from shopman.shop.services.observability import operational_event_on_commit

logger = logging.getLogger(__name__)


def _enrich_system_context(template: str, raw_context: object) -> dict:
    """Resolve human labels at the integration boundary, keeping Stockman generic."""

    context = dict(raw_context) if isinstance(raw_context, dict) else {}
    if template != "stock_alert":
        return context

    sku = str(context.get("sku") or "").strip()
    if not sku or str(context.get("product_name") or "").strip():
        return context
    try:
        from shopman.offerman.models import Product

        product_name = (
            Product.objects.filter(sku=sku)
            .values_list("name", flat=True)
            .first()
        )
    except Exception:
        # O alerta continua útil pelo SKU se o catálogo estiver indisponível; o
        # worker registra o diagnóstico sem incluir destinatário ou conteúdo.
        logger.warning(
            "notification.system: product label unavailable for sku=%s",
            sku,
            exc_info=True,
        )
        return context
    if product_name:
        context["product_name"] = str(product_name).strip()
    return context


#: Pedido nestes estados não espera mais a data combinada: cancelado e devolvido
#: morreram; despachado, entregue e concluído já saíram. O lembrete de véspera
#: não tem mais nada a lembrar.
PREORDER_REMINDER_DEAD_STATUSES = frozenset({"cancelled", "returned", "dispatched", "delivered", "completed"})


class NotificationSendHandler:
    """Processa directives de notificação. Topic: notification.send"""

    topic = NOTIFICATION_SEND
    #: Régua própria (beta 06/11, W2): o padrão do despacho (2, 4, 8, 16 s)
    #: desistia em meio minuto, e uma queda curta do WhatsApp ou do SMS perdia o
    #: "pedido pronto" de vez. Com esta régua a última tentativa sai cerca de
    #: 9 min depois da primeira; só então o aviso vira alerta ao operador.
    retry_delays_seconds = (15, 30, 60, 120, 300)

    @property
    def max_attempts(self) -> int:
        return len(self.retry_delays_seconds) + 1

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload

        # Processo suprimido (o seed): dado sintético não notifica ninguém. O
        # adapter inerte devolve falha, e falha aqui viraria retry que o worker
        # (que NÃO é suprimido) executaria de verdade, para os telefones do seed.
        # O registro honesto é ``skipped`` com o motivo, terminal: nem
        # "entregue" (que era a mentira de antes) nem "falhou".
        from shopman.shop.adapters._external import suppressed_reason

        reason = suppressed_reason()
        if reason is not None:
            logger.info("notification.send: processo suprimido (%s), directive %s pulada", reason, message.pk)
            self._record_skip(message, f"external_suppressed:{reason}")
            return

        # Stock alert (no order_ref, has event field)
        if not payload.get("order_ref") and payload.get("event"):
            self._handle_system_notification(message)
            return

        self._handle_order_notification(message)

    def _handle_order_notification(self, message: Directive) -> None:
        """Handle order-related notifications — delega ao service."""
        from shopman.orderman.models import Order

        from shopman.shop.services import payment as payment_svc

        payload = message.payload
        order_ref = payload.get("order_ref")
        template = payload.get("template", "generic")

        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")


        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        # A fresh lock serializes worker redelivery, but never covers transport I/O.
        blocked = False
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            fresh = Directive.objects.select_for_update().get(pk=message.pk)
            payload = dict(fresh.payload or {})
            previous = payload.get("notification_delivery") or {}
            if previous.get("status") in {"accepted", "skipped"}:
                return
            if previous.get("status") in {"started", "unknown"} or (
                fresh.attempts > 1 and previous.get("outcome") != "not_applied"
            ):
                blocked = True
            else:
                # Guarda: pular reminders de pagamento se já pago
                if template == "payment.reminder":
                    payment_status = payment_svc.get_payment_status(order) or ""
                    if payment_status in ("paid", "captured", "succeeded") or order.status not in ("new", "created"):
                        self._record_skip(fresh, "payment_not_pending")
                        return

                # O lembrete de véspera espera dias na fila, e a encomenda pode
                # ter morrido (ou já saído) nesse meio-tempo: "sua encomenda é
                # amanhã" para quem cancelou é mentira dita na voz da casa.
                if template == "preorder_reminder" and order.status in PREORDER_REMINDER_DEAD_STATUSES:
                    self._record_skip(fresh, "preorder_not_awaiting")
                    return

                # O PIX pode ser confirmado enquanto esta Directive espera um
                # worker. A guarda do enqueue não basta: a última leitura antes
                # do I/O externo precisa observar Payman, cancelamento e
                # vencimento atuais para nunca enviar uma cobrança obsoleta.
                if template == notification_svc.PAYMENT_PIX_TEMPLATE:
                    refusal = notification_svc.payment_notice_refusal(order)
                    if refusal is not None and refusal.code in {
                        "payment_notice_already_paid",
                        "payment_notice_order_cancelled",
                        "payment_notice_expired",
                        "payment_link_already_paid",
                        "payment_link_order_cancelled",
                        "payment_link_expired",
                        notification_svc.PAYMENT_TAKEN_OVER_AT_COUNTER,
                    }:
                        self._record_skip(fresh, "payment_not_pending")
                        return

                # Enqueue eligibility can expire while the worker is unavailable. Reuse
                # the same canonical link guard; do not send an obsolete charge notice.
                if template == notification_svc.PAYMENT_LINK_TEMPLATE:
                    refusal = notification_svc.payment_link_resend_refusal(order, check_delivery=False)
                    if refusal is not None:
                        self._record_skip(fresh, refusal.code)
                        return

                payload["notification_delivery"] = {
                    "status": "started", "recorded_at": timezone.now().isoformat(),
                }
                fresh.payload = payload
                fresh.save(update_fields=["payload", "updated_at"])
                self._observe(fresh)
        message.payload = payload
        if blocked:
            # Alert outside the claim transaction; it must survive a
            # terminal outcome and uses the existing audience/dedupe/ack policy.
            self._observe(message, state_override="unknown")
            self._escalate(order_ref, template, None, unknown=True)
            raise DirectiveTerminalError("notification acceptance unconfirmed; automatic resend blocked")

        success, last_error = notification_svc.deliver_order_notification(order, template, payload)
        # ``deliver_order_notification`` registra aceite, skip legítimo ou a
        # última falha no dicionário recebido. Persistir antes de retornar/lançar
        # torna o resultado observável no mesmo fato que já governa retries.
        if payload.get("notification_delivery"):
            with transaction.atomic():
                fresh = Directive.objects.select_for_update().get(pk=message.pk)
                current = dict(fresh.payload or {})
                if (current.get("notification_delivery") or {}).get("status") != "accepted":
                    current["notification_delivery"] = payload["notification_delivery"]
                    fresh.payload = current
                    fresh.save(update_fields=["payload", "updated_at"])
                    self._observe(fresh)
                message.payload = fresh.payload

        if success:
            delivery = payload.get("notification_delivery") or {}
            # Aviso crítico que terminou a cadeia aceito, mas SEM comprovante em
            # canal nenhum: saiu, e ninguém sabe se chegou. Não reenviamos
            # sozinhos (seria a terceira mensagem); o operador confirma.
            if (
                delivery.get("critical")
                and delivery.get("status") == "accepted"
                and delivery.get("proof") != notification_svc.PROOF_RECEIPT
            ):
                self._escalate(order_ref, template, None, no_receipt=True)
            return
        if (payload.get("notification_delivery") or {}).get("status") in {"started", "unknown"}:
            self._escalate(order_ref, template, None, unknown=True)
            raise DirectiveTerminalError("notification acceptance unconfirmed; automatic resend blocked")

        # Todos os backends falharam: alerta só quando a régua acabou.
        if message.attempts >= self.max_attempts:
            self._escalate(order_ref, template, last_error, attempts=message.attempts)
            raise DirectiveTerminalError(last_error or f"all backends failed after {message.attempts} attempts")

        raise DirectiveTransientError(last_error or "all backends failed")

    @staticmethod
    def _observe(message: Directive, *, state_override: str | None = None) -> None:
        delivery = (message.payload or {}).get("notification_delivery") or {}
        effect_state = state_override or delivery.get("status")
        operational_event_on_commit(
            "operator.effect.state", directive_id=message.pk, topic=message.topic,
            resource_ref=(message.payload or {}).get("order_ref"),
            worker_attempt=message.attempts, effect_state=effect_state,
            external_id=delivery.get("message_id"), recorded_at=delivery.get("recorded_at"),
            unknown_reason="acceptance_unconfirmed" if effect_state == "unknown" else None,
        )

    def _escalate(
        self,
        order_ref: str,
        template: str,
        last_error: str | None,
        *,
        unknown: bool = False,
        no_receipt: bool = False,
        attempts: int | None = None,
    ) -> None:
        """Cria OperatorAlert quando entrega de notificação é exaurida.

        O texto é para o operador: o nome do aviso em português e a causa em
        palavras dele (beta 06/11, PIXEXP-08). A chave interna do template e o
        erro cru do provedor ficam no log e na Directive, nunca na tela.
        """
        try:
            from shopman.shop.adapters import alert as alert_adapter

            label = notice_label(template)
            # O nome do aviso entre aspas é o marcador do dedupe: um replay ou
            # retry manual do mesmo fato não empilha alertas idênticos.
            marker = f'"{label}"'
            if alert_adapter.recent_exists(
                "notification_failed",
                timezone.now(),
                message_contains=marker,
                order_ref=order_ref or "",
            ):
                return
            if no_receipt:
                message = (
                    f"O aviso {marker} do pedido {order_ref} foi aceito pelo provedor, mas nenhum canal "
                    "devolveu comprovante de entrega. Confirme com o cliente que ele recebeu."
                )
            elif unknown:
                message = (
                    f"Não dá para saber se o aviso {marker} chegou ao cliente do pedido {order_ref}. "
                    "Confira com o cliente pelo WhatsApp do pedido antes de mandar de novo."
                )
            else:
                cause, advice = order_failure_cause(last_error)
                message = (
                    f"O aviso {marker} não chegou ao cliente do pedido {order_ref} depois de "
                    f"{attempts or self.max_attempts} tentativas. Motivo: {cause}. {advice}"
                )
            alert_adapter.create(
                "notification_failed",
                "error",
                message,
                order_ref=order_ref or "",
            )
            logger.warning(
                "notification_escalated order=%s template=%s error=%s",
                order_ref, template, last_error,
            )
        except Exception:
            logger.exception("Failed to create OperatorAlert for notification failure")

    def _escalate_system(self, template: str, context: dict, reasons: list[str], *, attempts: int) -> None:
        """Alerta do aviso INTERNO que não saiu (estoque baixo, pedido de compra).

        Não é aviso de pedido (beta 06/11, W1): não há cliente nem pedido, e o
        texto de pedido dizia "fale com o cliente pelo WhatsApp do pedido" com
        o ref vazio. Cada evento diz o que se perdeu e o gesto que ainda serve.
        """
        try:
            from shopman.shop.adapters import alert as alert_adapter

            cause = "; ".join(dict.fromkeys(reasons)) or "o motivo não ficou registrado"
            if template == "stock_alert":
                product = str(context.get("product_label") or context.get("sku") or "um produto").strip()
                marker = f"de {product}"
                message = (
                    f"O alerta de estoque baixo {marker} não foi enviado depois de {attempts} tentativas. "
                    f"Motivo: {cause}. Confira o estoque desse produto e peça à TI para revisar o envio."
                )
            elif template == "purchase_request":
                purchase_ref = str(context.get("purchase_ref") or "").strip()
                supplier = str(context.get("supplier_name") or context.get("supplier_ref") or "").strip()
                marker = f"pedido de compra {purchase_ref}".strip()
                message = (
                    f"O {marker} não chegou ao fornecedor {supplier or 'escolhido'} depois de {attempts} "
                    f"tentativas. Motivo: {cause}. Mande o pedido pelo contato do fornecedor."
                )
            else:
                marker = f'"{notice_label(template)}"'
                message = (
                    f"O aviso interno {marker} não saiu depois de {attempts} tentativas. "
                    f"Motivo: {cause}. Peça à TI para revisar o envio."
                )
            if alert_adapter.recent_exists(
                "notification_failed", timezone.now(), message_contains=marker, order_ref="",
            ):
                return
            alert_adapter.create("notification_failed", "error", message, order_ref="")
            logger.warning("notification_escalated system template=%s reasons=%s", template, reasons)
        except Exception:
            logger.exception("Failed to create OperatorAlert for system notification failure")

    @staticmethod
    def _record_skip(message: Directive, reason: str) -> None:
        payload = dict(message.payload or {})
        payload["notification_delivery"] = {
            "status": "skipped",
            "reason": reason,
            "recorded_at": timezone.now().isoformat(),
        }
        message.payload = payload
        message.save(update_fields=["payload", "updated_at"])

    def _handle_system_notification(self, message: Directive) -> None:
        """Handle system notifications (stock alerts, etc.) — routed to operator."""
        payload = message.payload
        event = payload.get("event", "system")
        if event == "operator_critical":
            from shopman.shop.services.critical_alerts import deliver

            return deliver(message)
        context = payload.get("context", {})

        # Normalize event → template name (stock.alert.triggered → stock_alert)
        if "stock.alert" in event:
            template = "stock_alert"
            context = _stock_alert_context(context)
        else:
            template = context.get("template") or event
        context = _enrich_system_context(template, context)

        fallback_recipient = getattr(settings, "SHOPMAN_ALERT_EMAIL", None) or getattr(
            settings, "DEFAULT_FROM_EMAIL", "admin@shopman.local"
        )
        recipient = str(payload.get("recipient") or fallback_recipient)
        recipients = payload.get("recipients") if isinstance(payload.get("recipients"), dict) else {}

        result = None
        # Por que cada canal não serviu, na língua do operador. Sem isto o
        # canal pulado por falta de configuração chegava ao alerta como
        # "desconhecido" (beta 06/11, W1).
        reasons: list[str] = []
        from shopman.shop.notifications import get_backend as _get_backend

        for backend_name in _system_backends(payload):
            channel = _CHANNEL_NAMES.get(backend_name, backend_name)
            backend_recipient = str(recipients.get(backend_name) or recipient or "").strip()
            if not backend_recipient:
                reasons.append(f"{channel} sem destinatário")
                continue

            backend_module = _get_backend(backend_name)
            if backend_module is None:
                reasons.append(f"{channel} não está ligado")
                logger.debug("notification.system: backend=%s not registered, skipping", backend_name)
                continue
            if hasattr(backend_module, "is_available"):
                if not backend_module.is_available(backend_recipient):
                    reasons.append(f"{channel} não está configurado")
                    logger.debug(
                        "notification.system: backend=%s not configured, skipping",
                        backend_name,
                    )
                    continue
            result = notify(event=template, recipient=backend_recipient, context=context, backend=backend_name)
            if result.success:
                return
            reasons.append(f"{channel} recusou o envio")
            logger.info("notification.system: backend=%s failed: %s", backend_name, result.error)

        error = (result.error if result else "; ".join(reasons) or "no backend attempted")[:500]
        if message.attempts >= self.max_attempts:
            self._escalate_system(template, context, reasons, attempts=message.attempts)
            raise DirectiveTerminalError(error)

        raise DirectiveTransientError(error)


#: Nome do canal como o operador fala.
_CHANNEL_NAMES = {
    "email": "e-mail",
    "manychat": "WhatsApp",
    "sms": "SMS",
    "push": "notificação no celular",
    "webhook": "integração",
    "console": "console",
}

#: Avisos cujo nome não está no catálogo do WhatsApp do Marketing.
_EXTRA_NOTICE_LABELS = {
    "order_ready": "Pedido pronto",
    "payment.reminder": "Lembrete de pagamento",
    "stock_alert": "Alerta de estoque baixo",
}

#: Erro gravado pela cadeia de avisos (``services/notification.py``) → causa e
#: gesto para o operador. O que não está aqui é erro do provedor, em inglês e
#: sem utilidade na tela: vira "o canal recusou o envio".
_ORDER_FAILURE_CAUSES = {
    "no active notification backend available": (
        "nenhum canal de envio está ligado",
        "Se for importante, fale com o cliente pelo WhatsApp do pedido.",
    ),
    "no active notification channel available": (
        "nenhum canal de envio está ligado",
        "Se for importante, fale com o cliente pelo WhatsApp do pedido.",
    ),
    "no active notification recipient available": (
        "o pedido não tem contato do cliente",
        "Se for importante, procure o contato no cadastro do cliente.",
    ),
    "notification customer identity unavailable": (
        "não deu para consultar o cadastro do cliente",
        "Se for importante, fale com o cliente pelo WhatsApp do pedido.",
    ),
    "notification preferences unavailable": (
        "não deu para consultar as preferências de aviso do cliente",
        "Se for importante, fale com o cliente pelo WhatsApp do pedido.",
    ),
}


def notice_label(template: str) -> str:
    """Nome do aviso em português; nunca a chave interna."""
    from shopman.shop.services.marketing_platform_configuration import WHATSAPP_EVENT_LABELS

    key = str(template or "").strip()
    return WHATSAPP_EVENT_LABELS.get(key) or _EXTRA_NOTICE_LABELS.get(key) or "aviso ao cliente"


def order_failure_cause(last_error: str | None) -> tuple[str, str]:
    """(causa, gesto) do aviso de pedido que esgotou as tentativas."""
    error = str(last_error or "").strip()
    if error in _ORDER_FAILURE_CAUSES:
        return _ORDER_FAILURE_CAUSES[error]
    cause = "o canal recusou o envio" if error else "o motivo não ficou registrado"
    return cause, "Se for importante, fale com o cliente pelo WhatsApp do pedido."


def _system_backends(payload: dict) -> list[str]:
    raw = payload.get("backends") or ["email", "console"]
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",")]
    if not isinstance(raw, list):
        return ["email", "console"]
    backends = [str(item).strip() for item in raw if str(item).strip()]
    return backends or ["email", "console"]


def _stock_alert_context(context: dict) -> dict:
    """Nome humano + SKU para o alerta operacional de estoque.

    Stockman permanece agnóstico ao catálogo e publica apenas o SKU. A borda
    orquestradora enriquece antes de escolher o canal; assim e-mail, console e
    futuros adapters recebem a mesma descrição sem acoplar o kernel de estoque
    ao Offerman.
    """
    enriched = dict(context or {})
    sku = str(enriched.get("sku") or "").strip()
    product_name = str(enriched.get("product_name") or "").strip()
    if sku and not product_name:
        try:
            from shopman.shop.projections import catalog_context

            product = catalog_context.get_product(sku)
            product_name = str(getattr(product, "name", "") or "").strip()
        except Exception:  # silêncio-deliberado: o alerta degrada para o SKU já presente
            logger.debug(
                "notification.system: product lookup failed for stock alert sku=%s",
                sku,
                exc_info=True,
            )
    enriched["product_name"] = product_name or sku
    enriched["product_label"] = (
        f"{product_name} ({sku})" if product_name and product_name != sku else sku
    )
    return enriched


__all__ = ["NotificationSendHandler"]
