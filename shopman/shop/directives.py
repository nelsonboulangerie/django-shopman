"""
Directives — topic constants + queue helpers.

Topic constants: canonical names for all directive topics (single source of truth).
queue(): single entry point for creating Directives across services.
create_deduped(): create com dedupe_key sob a garantia do UNIQUE parcial do
Core (orderman_directive_live_dedupe_unique) — violação é dedupe-hit, não erro.
"""

import logging

from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

# ── Topic constants ──

# Lifecycle: missing post-commit phases, dispatched by the existing worker.
ORDER_LIFECYCLE_PHASE = "order.lifecycle_phase"
LIFECYCLE_PHASE_RECEIPT_SCOPE = "lifecycle:phase"

# Notification
NOTIFICATION_SEND = "notification.send"
STOCK_ALERT_DELIVER = "stock_alert.deliver"
STOCK_ALERT_DELIVERY_RECEIPT_SCOPE = "stock_alert:delivery"

# Receipts permanentes para a identidade de entrega. O envio original e os
# reenvios vivem em scopes distintos: o primeiro nunca volta a nascer depois de
# concluído; cada gesto explícito de reenvio ganha a própria chave sufixada.
NOTIFICATION_ORIGINAL_RECEIPT_SCOPE = "notification:original"
NOTIFICATION_RESEND_RECEIPT_SCOPE = "notification:resend"

CHECKOUT_CONVENIENCE = "checkout.convenience"

# Fulfillment
FULFILLMENT_CREATE = "fulfillment.create"
FULFILLMENT_UPDATE = "fulfillment.update"
# Rede de segurança: auto-conclui um pedido em entrega após ETA + folga, se nem
# o cliente ("Recebi") nem o operador ("Marcar entregue") fecharem o loop.
DELIVERY_AUTO_COMPLETE = "delivery.auto_complete"

# Courier (logística externa — Machine)
# Despacho da corrida ao marcar "pronto" (retry/idempotência via Directive) e
# heartbeat de polling do status (fallback do webhook, auto-reagendável).
COURIER_DISPATCH = "courier.dispatch"
COURIER_CANCEL = "courier.cancel"
COURIER_SYNC = "courier.sync"

# Confirmation
CONFIRMATION_TIMEOUT = "confirmation.timeout"
ORDER_STALE_NEW_ALERT = "order.stale_new_alert"

# Piloto automático de staging (nunca em produção — ver SHOPMAN_E012)
# Dá o próximo passo do operador num pedido de staging, para o testador ver a
# cascata inteira sem ninguém no backstage.
STAGING_AUTOPILOT = "staging.autopilot"

# Payment
PAYMENT_TIMEOUT = "payment.timeout"
PAYMENT_REFUND = "payment.refund"  # retry assíncrono de estorno com backoff

# Production
# Heartbeat auto-reagendável: varre WOs started além da janela e planned
# esquecidas, criando OperatorAlerts sem depender de tela aberta.
PRODUCTION_LATE_CHECK = "production.late_check"

# Preorder (encomenda com data futura)
# O trabalho físico (KDS/baixa) de um pedido para data futura só dispara NA
# data — esta directive é o despertador (available_at = meia-noite da data).
PREORDER_ACTIVATE = "preorder.activate"


# Fiscal
FISCAL_EMIT_NFCE = "fiscal.emit_nfce"
FISCAL_CANCEL_NFCE = "fiscal.cancel_nfce"

# Accounting
ACCOUNTING_CREATE_PAYABLE = "accounting.create_payable"

# Loyalty
LOYALTY_EARN = "loyalty.earn"
LOYALTY_REDEEM = "loyalty.redeem"
LOYALTY_REVOKE = "loyalty.revoke"
LOYALTY_RESTORE = "loyalty.restore"

# Returns
RETURN_PROCESS = "return.process"

# Catalog projection
CATALOG_PROJECT_SKU = "catalog.project_sku"

# iFood status callback (push internal lifecycle → iFood order actions)
IFOOD_STATUS_CALLBACK = "ifood.status_callback"

# Campanha (marketing operacional)
# ANNOUNCEMENT_PUBLISH   — publica em plataforma externa (IG, Facebook, Google Business).
# ANNOUNCEMENT_NOTIFY — dispara a audiência direta (WhatsApp), uma onda por directive
#                    (o VIP-first vira duas, com available_at diferente).
ANNOUNCEMENT_PUBLISH = "announcement.publish"
ANNOUNCEMENT_NOTIFY = "announcement.notify"
# CAMPAIGN_OCCUR — a OCASIÃO agendada chegou; crie o anúncio agora.
#
# A vassoura de manutenção não dispara: ela ARMA esta directive com `available_at` no
# instante exato do início da janela. Quem dispara é `process_directives --watch`, que
# roda a cada ~2 segundos — então a latência de armar (até 5 min, na hora anterior) é
# irrelevante e a de disparar é de segundos. Uma relâmpago das 17h30 sai às 17h30.
CAMPAIGN_OCCUR = "campaign.occur"


# ── Queue helper ──


def queue(topic, order, **extra):
    """
    Create a Directive for async processing.

    Always includes order_ref and channel_ref. Extra kwargs are
    merged into the payload.

    Usage:
        from shopman.shop import directives
        directives.queue("notification.send", order, template="order_accepted")
    """
    payload = {"order_ref": order.ref}
    if order.channel_ref:
        payload["channel_ref"] = order.channel_ref
    payload.update(extra)
    return Directive.objects.create(topic=topic, payload=payload)


def create_deduped(topic, *, payload, dedupe_key, available_at=None):
    """Create a Directive com dedupe_key, tratando corrida como dedupe-hit.

    O check-then-create dos criadores continua como fast path (log amigável,
    zero INSERT), mas a garantia vem do UNIQUE parcial do Core: no máximo uma
    directive viva (queued/running) por (topic, dedupe_key). Sob corrida, o
    segundo INSERT viola a constraint — aqui isso vira ``None`` (dedupe-hit),
    nunca exceção.

    O ``transaction.atomic()`` interno é um savepoint: quando o caller está
    dentro de uma transação, o IntegrityError não a envenena.
    """
    from django.db import IntegrityError, transaction

    kwargs = {"topic": topic, "payload": payload, "dedupe_key": dedupe_key}
    if available_at is not None:
        kwargs["available_at"] = available_at
    try:
        with transaction.atomic():
            return Directive.objects.create(**kwargs)
    except IntegrityError:
        logger.info("directives.dedupe_hit topic=%s dedupe_key=%s", topic, dedupe_key)
        return None


def create_persistently_deduped(
    topic,
    *,
    payload,
    dedupe_key,
    receipt_scope,
    available_at=None,
):
    """Cria uma Directive uma única vez para uma identidade durável.

    A constraint parcial de :class:`Directive` protege apenas tarefas vivas. Isso
    é correto para o contrato genérico, mas insuficiente para uma notificação:
    duas requisições podem atravessar o pré-check enquanto a primeira tarefa
    termina e criar dois envios externos. ``IdempotencyKey`` fornece a identidade
    permanente e concorrente; receipt e Directive são gravados na mesma transação,
    portanto nunca sobra claim sem tarefa quando o INSERT falha.

    Uma Directive histórica anterior ao receipt também é adotada: criamos o
    receipt apontando para ela e não recriamos o efeito. Isso mantém o rollout
    compatível com filas existentes.
    """
    from django.db import transaction
    from shopman.orderman.models import IdempotencyKey

    with transaction.atomic():
        receipt, created = IdempotencyKey.objects.get_or_create(
            scope=receipt_scope,
            key=dedupe_key,
            defaults={
                "status": "done",
                "expires_at": None,
                "response_body": {"topic": topic},
            },
        )
        if not created:
            logger.info(
                "directives.persistent_dedupe_hit topic=%s dedupe_key=%s",
                topic,
                dedupe_key,
            )
            return None

        existing = (
            Directive.objects.filter(topic=topic, dedupe_key=dedupe_key)
            .order_by("pk")
            .first()
        )
        if existing is not None:
            receipt.response_body = {"topic": topic, "directive_pk": existing.pk}
            receipt.save(update_fields=["response_body"])
            return None

        kwargs = {"topic": topic, "payload": payload, "dedupe_key": dedupe_key}
        if available_at is not None:
            kwargs["available_at"] = available_at
        directive = Directive.objects.create(**kwargs)
        receipt.response_body = {"topic": topic, "directive_pk": directive.pk}
        receipt.save(update_fields=["response_body"])
        return directive
