"""iFood status callback handler + signal receiver (WP-4).

When an iFood-channel order changes status, we must tell iFood. This uses the
same durable pattern as catalog projection: a signal receiver enqueues a
``ifood.status_callback`` Directive (deduped per order+status), and a handler
calls the iFood order-action API with retry semantics.

Directive over synchronous call: the callback crosses the network and iFood may
be briefly unavailable — a Directive gives at-least-once delivery with backoff,
per ADR-003.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import IFOOD_STATUS_CALLBACK
from shopman.shop.services import ifood_accept_sync, ifood_callbacks, ifood_cancellation, ifood_ingest

logger = logging.getLogger(__name__)


class IFoodStatusCallbackHandler:
    topic = IFOOD_STATUS_CALLBACK

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        order_id = payload.get("ifood_order_id") or payload.get("external_ref")
        status = payload.get("status", "")
        if not order_id:
            logger.warning("ifood_status: directive without ifood_order_id: %s", payload)
            return

        cancellation_request = bool(payload.get("cancellation_request_id"))
        if cancellation_request and not ifood_cancellation.should_send(payload):
            return
        # Older directives contain only refs and status. Recover their workflow
        # from the persisted order instead of assuming merchant delivery.
        from shopman.orderman.models import Order

        lookup = {"ref": payload["order_ref"]} if payload.get("order_ref") else {"external_ref": order_id}
        order = Order.objects.filter(channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, **lookup).first()
        context = {
            "fulfillment_type": payload.get("fulfillment_type", ""),
            "delivered_by": payload.get("delivered_by", ""),
        }
        if order is not None:
            context = ifood_callbacks.workflow_context(order)
            if status in {"accepted", "preparing", "ready", "dispatched"} and order.status in Order.TERMINAL_STATUSES:
                # A delayed progress callback cannot reopen a completed order.
                # Keep legacy cancellation requests on their separate path.
                return
            # Persistent remote evidence also covers callbacks queued before
            # CAN/CFM/DSP. Transitions reflected from iFood never echo back.
            if (order.data or {}).get("ifood_cancelled") or ifood_callbacks.remote_status_observed(order, status):
                return

        try:
            sent = ifood_callbacks.send_for_status(
                order_id,
                status,
                cancellation_reason=payload.get("cancellation_reason", ""),
                cancellation_code=payload.get("cancellation_code", ""),
                **context,
            )
        except ifood_callbacks.IFoodCallbackError as exc:
            if cancellation_request:
                ifood_cancellation.record_result(payload, state="error", retryable=exc.retryable)
                error = DirectiveTransientError if exc.retryable else DirectiveTerminalError
                raise error("Falha no envio da solicitação de cancelamento ao iFood.") from exc
            if status == ifood_accept_sync.ACCEPT_STATUS and order is not None:
                # O aceite não chegou: a cozinha trabalha e o iFood cancela no prazo
                # dele. Aviso específico, apontando o pedido, já na primeira falha.
                ifood_accept_sync.on_attempt_failed(order, message)
            raise DirectiveTransientError(str(exc)) from exc

        if cancellation_request and sent:
            ifood_cancellation.record_result(payload, state="sent")
        if sent and status == ifood_accept_sync.ACCEPT_STATUS and order is not None:
            ifood_accept_sync.on_sent(order, message)

        if not sent:
            logger.info("ifood_status: no iFood action for status=%s (order %s)", status, order_id)

    def on_terminal_failure(self, *, message: Directive) -> None:
        """Esgotou as tentativas: o iFood ficou sem saber. Nunca em silêncio.

        O aceite tem aviso próprio desde a primeira falha (``ifood_accept_sync``).
        Os demais passos (preparo, pronto, saída) e o pedido de cancelamento
        ficavam só no log, e o pedido seguia diferente aqui e lá (16/11/2026).
        """
        payload = message.payload or {}
        if payload.get("cancellation_request_id"):
            ifood_cancellation.record_not_delivered(payload, error=message.last_error or "")
            return
        status = str(payload.get("status") or "")
        if status == ifood_accept_sync.ACCEPT_STATUS:
            return
        from shopman.orderman.models import Order

        order = Order.objects.filter(
            channel_ref=ifood_ingest.IFOOD_CHANNEL_REF, ref=payload.get("order_ref") or "",
        ).first()
        if order is None or order.status in Order.TERMINAL_STATUSES:
            return
        alert_status_not_delivered(order, status=status, error=message.last_error or "")


#: Etapa do pedido que não chegou ao iFood depois de todas as tentativas.
STATUS_NOT_DELIVERED_ALERT = "ifood_status_not_delivered"
_STEP_COPY = {
    "preparing": "o início do preparo",
    "ready": "o pedido pronto",
    "dispatched": "a saída para entrega",
}


def alert_status_not_delivered(order, *, status: str, error: str = "") -> None:
    from shopman.shop.services.observability import create_operator_alert

    display = str(((order.data or {}).get("ifood") or {}).get("display_id") or "").strip()
    name = f"{order.ref} (iFood #{display})" if display else order.ref
    step = _STEP_COPY.get(status, f"a etapa {status}")
    create_operator_alert(
        type=STATUS_NOT_DELIVERED_ALERT,
        severity="error",
        message=(
            f"O iFood não recebeu {step} do pedido {name}: o envio falhou em todas as tentativas. "
            "Aqui o pedido andou e lá não. Marque a etapa no Portal ou no widget do iFood."
        ),
        order_ref=order.ref,
        dedupe_key=f"{STATUS_NOT_DELIVERED_ALERT}:{order.ref}:{status}",
        debounce_minutes=24 * 60,
        http_error=str(error)[:200],
    )


# ── Signal receiver ────────────────────────────────────────────────────────────


def on_order_status_changed(sender, order, event_type, actor, **kwargs) -> None:
    """Pedido do iFood mudou de status: avisa o iFood e aplica o que ele já disse.

    Duas coisas, nesta ordem. O aviso (se couber) sai primeiro; depois a
    reconciliação leva o pedido até onde os fatos do iFood já autorizam — é ela
    que fecha, por exemplo, o pedido cujo CON chegou com a cozinha ainda em
    preparo, no momento em que ele finalmente sai.
    """
    if event_type != "status_changed":
        return
    if getattr(order, "channel_ref", "") != ifood_ingest.IFOOD_CHANNEL_REF:
        return
    try:
        _enqueue_callback(order, actor)
    finally:
        from shopman.shop.services import ifood_events

        ifood_events.reconcile_remote(order)


def _enqueue_callback(order, actor) -> None:
    # Cancelamento que ORIGINOU no iFood (evento CAN refletido): não chamamos
    # requestCancellation de volta para quem já cancelou. Decisão de negócio —
    # o silêncio dela custou vinte minutos de diagnóstico em 19/09/2026.
    if (order.data or {}).get("ifood_cancelled"):
        logger.info(
            "ifood_status: no callback for order %s (status=%s) — cancellation originated at iFood (ifood_cancelled)",
            order.ref,
            order.status,
        )
        return
    remote = (order.data or {}).get("ifood") or {}
    remote_markers = ",".join(m for m in ("remote_confirmed", "remote_dispatched", "remote_concluded") if remote.get(m)) or "none"
    # Transição que o PRÓPRIO iFood nos informou (ator remoto CFM/DSP): ecoar de
    # volta seria devolver ao marketplace o que veio dele. Separado da evidência
    # persistida logo abaixo porque saber QUAL dos dois fechou é o diagnóstico.
    if actor in {"system:ifood:CFM", "system:ifood:DSP"}:
        logger.info(
            "ifood_status: no callback for order %s (status=%s) — remote actor=%s (remote markers: %s)",
            order.ref,
            order.status,
            actor,
            remote_markers,
        )
        return
    # Mesma regra, evidência persistida em vez do ator: um evento remoto anterior
    # já marcou esta transição em order.data["ifood"].
    if ifood_callbacks.remote_status_observed(order, order.status):
        logger.info(
            "ifood_status: no callback for order %s (status=%s) — remote status already observed (remote markers: %s)",
            order.ref,
            order.status,
            remote_markers,
        )
        return
    context = ifood_callbacks.workflow_context(order)
    # Não existe ação no iFood para este status NESTE fluxo (ex.: despacho de uma
    # entrega que é do iFood, não da loja). Os três dados da decisão vão no log:
    # sem eles não se distingue desenho da regra de dado que faltou chegar.
    if ifood_callbacks.action_for_status(order.status, **context) is None:
        logger.info(
            "ifood_status: no callback for order %s — no iFood action for status=%s "
            "fulfillment_type=%s delivered_by=%s",
            order.ref,
            order.status,
            context["fulfillment_type"] or "(empty)",
            context["delivered_by"] or "(empty)",
        )
        return

    ifood_order_id = order.external_ref or (order.data or {}).get("external_order_code", "")
    if str(ifood_order_id).upper().startswith("IFOOD-SIM-"):
        return
    if not ifood_order_id:
        logger.warning("ifood_status: order %s has no iFood order id — cannot call back", order.ref)
        return

    # O iFood só anda para frente e não tem "desfazer pronto". Desfazer o Pronto
    # devolve o pedido ao preparo AQUI; marcar de novo não é outro aviso lá: o
    # readyToPickup (ou um passo adiante) que já saiu continua valendo, e um
    # startPreparation depois dele seria andar para trás. Só o que falhou volta
    # a sair (directive ``failed`` não conta como aviso dado).
    if _progress_already_announced(order):
        logger.info(
            "ifood_status: no callback for order %s (status=%s) — iFood already told this step or a later one",
            order.ref,
            order.status,
        )
        return

    dedupe_key = f"{IFOOD_STATUS_CALLBACK}:{order.ref}:{order.status}"
    exists = Directive.objects.filter(
        dedupe_key=dedupe_key,
        status__in=("queued", "running"),
    ).exists()
    if exists:
        return

    from shopman.shop.directives import create_deduped

    created = create_deduped(
        IFOOD_STATUS_CALLBACK,
        payload={
            "order_ref": order.ref,
            "ifood_order_id": ifood_order_id,
            "status": order.status,
            **context,
            # cancellation.cancel writes these to order.data before the signal fires.
            # O código do iFood vem do motivo da casa (``DEFAULT_REASON_CODES``).
            "cancellation_reason": (order.data or {}).get("cancellation_reason", ""),
            "cancellation_code": (order.data or {}).get("ifood_cancellation_code")
            or ifood_callbacks.resolve_cancellation_code((order.data or {}).get("cancellation_reason_key", "")),
        },
        dedupe_key=dedupe_key,
    )
    if created is None:
        return
    logger.debug("ifood_status: enqueued %s callback for order %s", order.status, order.ref)


#: Os passos de progresso do iFood, na ordem em que ele os aceita.
PROGRESS_STEPS = ("accepted", "preparing", "ready", "dispatched")


def _progress_already_announced(order) -> bool:
    """Este passo, ou um posterior, já foi (ou está sendo) avisado ao iFood?"""
    status = str(order.status or "")
    if status not in PROGRESS_STEPS:
        return False
    return Directive.objects.filter(
        topic=IFOOD_STATUS_CALLBACK,
        payload__order_ref=order.ref,
        payload__status__in=PROGRESS_STEPS[PROGRESS_STEPS.index(status):],
        status__in=("queued", "running", "done"),
    ).exists()


__all__ = ["IFoodStatusCallbackHandler", "STATUS_NOT_DELIVERED_ALERT", "alert_status_not_delivered", "on_order_status_changed"]
