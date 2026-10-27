"""Durable critical email paging, debounced by type + order; unknown delivery is fenced.

Dois caminhos de saída, a mesma Directive:

- ``enqueue`` — o normal. O e-mail vira ``notification.send`` e sai pelo
  despacho da fila (signal no commit, ou o ``process_directives``).
- ``deliver_now`` — para o alerta que fala DA fila (worker parado, backlog).
  Esse não pode depender dela: quem avisa que o worker parou não pode esperar
  o worker para sair. A Directive é a mesma (trilha, debounce e cerca de
  entrega desconhecida iguais), mas o envio roda ali, no processo que mediu.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.shop.directives import NOTIFICATION_SEND
from shopman.shop.notifications import notify

logger = logging.getLogger(__name__)


def _debounce_key(alert) -> str:
    # A trava é por tipo + pedido: o segundo pedido com o mesmo problema é outro
    # aviso, e some se a chave for só o tipo. Alerta sem pedido (backend fora,
    # loja do iFood fechada) é do sistema inteiro, e fica por tipo.
    order_ref = str(getattr(alert, "order_ref", "") or "").strip()
    return f"{alert.type}:{order_ref}" if order_ref else alert.type


def enqueue(alert):
    recipient = str(getattr(settings, "SHOPMAN_ALERT_EMAIL", "") or "").strip()
    if not recipient:
        # Alerta crítico sem ninguém para receber o e-mail: só a tela sabe dele.
        # Isto é defeito de configuração, e grita (o `operator_alert.created`
        # é rastro justamente porque conta com este e-mail).
        logger.error(
            "operator_alert.external_recipient_missing: SHOPMAN_ALERT_EMAIL vazio; "
            "alerta crítico %s só na tela",
            getattr(alert, "type", ""),
        )
        return None
    with transaction.atomic():
        receipt, created = IdempotencyKey.objects.get_or_create(
            scope="operator_critical_email", key=_debounce_key(alert),
            defaults={"status": "in_progress", "expires_at": None},
        )
        receipt = IdempotencyKey.objects.select_for_update().get(pk=receipt.pk)
        now = timezone.now()
        if not created and receipt.expires_at and receipt.expires_at > now:
            return None
        task = Directive.objects.create(topic=NOTIFICATION_SEND, payload={
            "event": "operator_critical", "recipient": recipient, "backends": ["email"],
            "alert_id": alert.pk,
            # Never copy arbitrary provider errors/customer data into an email.
            "context": {"alert_type": alert.type, "order_ref": alert.order_ref},
        })
        receipt.status = "done"
        receipt.expires_at = now + timedelta(minutes=15)
        receipt.response_body = {"directive_id": task.pk}
        receipt.save(update_fields=["status", "expires_at", "response_body"])
        return task


def deliver(message):
    from shopman.shop.adapters import notification_email

    with transaction.atomic():
        task = Directive.objects.select_for_update().get(pk=message.pk)
        payload = dict(task.payload or {})
        state = payload.get("critical_delivery")
        if state == "accepted":
            return
        if state in {"started", "unknown"}:
            raise DirectiveTerminalError("critical email acceptance unconfirmed; inspect original delivery")
        if not notification_email.is_available(payload["recipient"]):
            raise DirectiveTransientError("critical email backend unavailable")
        payload["critical_delivery"] = "started"
        task.payload = payload
        task.save(update_fields=["payload", "updated_at"])
    result = notify(event="operator_critical", recipient=payload["recipient"],
                    context=payload["context"], backend="email")
    state = "accepted" if result.success else "unknown" if result.outcome_unknown else "rejected"
    with transaction.atomic():
        task = Directive.objects.select_for_update().get(pk=message.pk)
        task.payload = {**task.payload, "critical_delivery": state}
        task.save(update_fields=["payload", "updated_at"])
    if state == "unknown":
        raise DirectiveTerminalError("critical email acceptance unconfirmed; inspect original delivery")
    if state == "rejected":
        raise DirectiveTransientError("critical email rejected")


#: Prazo até a próxima tentativa quando o envio síncrono falha de forma
#: transitória. O próximo ciclo do comando de saúde tenta de novo.
INLINE_RETRY_SECONDS = 60


def _existing_task(alert):
    return (
        Directive.objects.filter(
            topic=NOTIFICATION_SEND,
            payload__event="operator_critical",
            payload__alert_id=alert.pk,
        )
        .order_by("pk")
        .first()
    )


def _run_inline(task) -> str:
    """Executa a Directive de e-mail aqui mesmo, com o mesmo claim do despacho.

    O ``UPDATE`` condicional (``queued`` → ``running``) é o que impede o envio em
    dobro quando o despacho por signal ou o worker chegam junto.
    """
    from shopman.orderman.dispatch import MAX_ATTEMPTS

    now = timezone.now()
    claimed = Directive.objects.filter(pk=task.pk, status="queued").update(
        status="running", attempts=F("attempts") + 1, started_at=now, updated_at=now,
    )
    if not claimed:
        task.refresh_from_db(fields=["status"])
        return task.status
    task.refresh_from_db()
    try:
        deliver(task)
    except DirectiveTerminalError as exc:
        status, code, error = "failed", "terminal", exc
    except Exception as exc:  # noqa: BLE001 — transitório ou inesperado: tenta no próximo ciclo
        if not isinstance(exc, DirectiveTransientError):
            logger.exception("operator_alert.inline_delivery_crashed")
        exhausted = task.attempts >= MAX_ATTEMPTS
        status = "failed" if exhausted else "queued"
        code = "terminal" if exhausted else "transient"
        error = exc
    else:
        Directive.objects.filter(pk=task.pk).update(status="done", updated_at=timezone.now())
        return "done"
    Directive.objects.filter(pk=task.pk).update(
        status=status,
        error_code=code,
        last_error=str(error)[:500],
        available_at=timezone.now() + timedelta(seconds=INLINE_RETRY_SECONDS),
        updated_at=timezone.now(),
    )
    logger.error(
        "operator_alert.inline_delivery_failed: alerta %s, directive #%s, %s",
        task.payload.get("context", {}).get("alert_type", ""), task.pk, status,
    )
    return status


def deliver_now(alert):
    """Envia o e-mail do alerta sem passar pelo worker de directives.

    Reaproveita a Directive que ``create_operator_alert`` já criou (alerta
    crítico) ou cria uma pelo ``enqueue`` (alerta de outra severidade que fala
    da fila). O debounce é o do ``enqueue``: dentro da janela, nada sai.
    Devolve o status final da Directive, ou ``None`` quando nada saiu.
    """
    if alert is None:
        return None
    task = _existing_task(alert) or enqueue(alert)
    if task is None:
        return None
    return _run_inline(task)


def deliver_pending(alert_types, *, limit: int = 5) -> int:
    """Retenta, aqui, os e-mails desses tipos que ficaram na fila.

    O alerta é debounced (15 min) e não renasce no ciclo seguinte; o e-mail que
    falhou de forma transitória fica ``queued``. Sem isto, ele esperaria o
    worker que o próprio alerta diz estar parado.
    """
    tasks = Directive.objects.filter(
        topic=NOTIFICATION_SEND,
        status="queued",
        payload__event="operator_critical",
        payload__context__alert_type__in=list(alert_types),
        available_at__lte=timezone.now(),
    ).order_by("available_at", "pk")[:limit]
    return sum(1 for task in list(tasks) if _run_inline(task) == "done")
