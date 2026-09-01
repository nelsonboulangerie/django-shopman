"""Production alert handlers for operator surfaces."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from shopman.shop.adapters import alert as alert_adapter
from shopman.shop.directives import PRODUCTION_LATE_CHECK
from shopman.shop.handlers._resilient import resilient_receiver
from shopman.shop.production_config import ProductionConfig

logger = logging.getLogger(__name__)

# Marcador durável em ``WorkOrder.meta`` (mesmo padrão dos carimbos
# ``stock_consumed_at``/``stock_realized_at`` da ponte craftsman→stockman):
# uma WO iniciada cuja data passou gera UM alerta, para sempre. Dedup por
# janela (12h, como os demais alertas) re-alertaria a mesma fornada todo
# turno até alguém agir — a WO fica ``started`` até o operador decidir, e a
# decisão (concluir tarde ou cancelar) é dele, não do relógio.
UNFINISHED_ALERTED_KEY = "unfinished_alerted_at"


def connect() -> None:
    """Connect production alert receivers to Craftsman lifecycle signals."""
    from shopman.craftsman.signals import production_changed

    production_changed.connect(
        on_production_changed,
        dispatch_uid="shopman.shop.handlers.production_alerts.on_production_changed",
        weak=False,
    )


@resilient_receiver
def on_production_changed(sender, product_ref, date, action, work_order, **kwargs):
    """Create operator alerts for production lifecycle events.

    Não-crítico: um alerta que falha não pode derrubar o ``finish`` da fornada
    nem abortar o sync de pedido, que roda logo em seguida (ver
    :func:`shopman.shop.handlers._resilient.resilient_receiver`).
    """
    ensure_late_check_scheduled()
    if action == "finished":
        maybe_create_low_yield_alert(work_order)


def ensure_late_check_scheduled() -> bool:
    """Arma o heartbeat ``production.late_check`` se não houver um vivo.

    Chamado em qualquer ``production_changed``: loja com produção ativa sempre
    tem o heartbeat armado — nenhuma tela precisa estar aberta para o operador
    ser avisado de atraso ou esquecimento. Cadence 0 desliga.
    """
    cadence = _alerts_config().late_check_cadence_minutes
    if cadence <= 0:
        return False

    from shopman.orderman.models import Directive

    if Directive.objects.filter(
        topic=PRODUCTION_LATE_CHECK, status__in=("queued", "running")
    ).exists():
        return False

    Directive.objects.create(
        topic=PRODUCTION_LATE_CHECK,
        payload={},
        available_at=timezone.now() + timedelta(minutes=cadence),
    )
    return True


class ProductionLateCheckHandler:
    """Heartbeat de alertas de produção. Topic: production.late_check

    Auto-reagendável: roda as varreduras (started além da janela, planned
    esquecida, started com a data vencida sem conclusão) e reenfileira a si
    mesmo no cadence do ``ProductionConfig``,
    zerando ``attempts`` — um heartbeat perpétuo nunca esgota retries. Falha
    transitória segue o retry/backoff padrão do worker; se o heartbeat morrer
    (max attempts), o próximo ``production_changed`` rearma.

    Cadence 0 = desligado: conclui sem reagendar. Duplicatas colapsam
    mantendo a mais antiga viva.
    """

    topic = PRODUCTION_LATE_CHECK

    def handle(self, *, message, ctx: dict) -> None:
        from shopman.orderman.models import Directive

        if (
            Directive.objects.filter(
                topic=self.topic, status__in=("queued", "running"), pk__lt=message.pk
            )
            .exclude(pk=message.pk)
            .exists()
        ):
            return  # duplicata — o worker marca done; a mais antiga segue viva

        cadence = _alerts_config().late_check_cadence_minutes
        if cadence <= 0:
            return  # desligado — o worker marca done; production_changed rearma

        late = check_late_started_orders()
        forgotten = check_forgotten_planned_orders()
        unfinished = check_unfinished_started_orders()
        if late or forgotten or unfinished:
            logger.info(
                "production.late_check: %d atrasada(s), %d esquecida(s), %d sem conclusão",
                late,
                forgotten,
                unfinished,
            )

        message.status = "queued"
        message.attempts = 0
        message.available_at = timezone.now() + timedelta(minutes=cadence)
        message.save(update_fields=["status", "attempts", "available_at", "updated_at"])


def maybe_create_low_yield_alert(work_order) -> bool:
    """Create a low-yield alert when finished quantity is below threshold."""
    if work_order.finished is None:
        return False

    base_qty = work_order.started_qty or work_order.quantity
    if not base_qty:
        return False

    yield_rate = work_order.finished / base_qty
    if yield_rate >= _alerts_config().low_yield_threshold_decimal:
        return False

    message = (
        f"Produção {work_order.ref} ({work_order.output_sku}) fechou com "
        f"yield de {int(yield_rate * 100)}%."
    )
    if _recent_exists("production_low_yield", work_order.ref):
        return False
    alert_adapter.create(
        "production_low_yield",
        "warning",
        message,
        order_ref=work_order.ref,
    )
    _notify_operator(
        "production_low_yield",
        severity="warning",
        context={
            "message": message,
            "work_order_ref": work_order.ref,
            "output_sku": work_order.output_sku,
            "yield_percent": int(yield_rate * 100),
        },
    )
    return True


def check_late_started_orders(*, selected_date=None) -> int:
    """Create alerts for started work orders beyond their target window."""
    from shopman.craftsman.models import WorkOrder

    qs = WorkOrder.objects.filter(status=WorkOrder.Status.STARTED).select_related("recipe")
    if selected_date is not None:
        qs = qs.filter(target_date=selected_date)

    created = 0
    now = timezone.now()
    for work_order in qs:
        started_at = work_order.started_at or work_order.created_at
        target_minutes = _target_minutes(work_order)
        if started_at > now - timedelta(minutes=target_minutes):
            continue
        if _recent_exists("production_late", work_order.ref):
            continue
        elapsed_minutes = int((now - started_at).total_seconds() // 60)
        message = (
            f"Produção {work_order.ref} ({work_order.output_sku}) está há "
            f"{elapsed_minutes} min em andamento."
        )
        alert_adapter.create(
            "production_late",
            "warning",
            message,
            order_ref=work_order.ref,
        )
        _notify_operator(
            "production_late",
            severity="warning",
            context={
                "message": message,
                "work_order_ref": work_order.ref,
                "output_sku": work_order.output_sku,
                "elapsed_minutes": elapsed_minutes,
                "target_minutes": target_minutes,
            },
        )
        created += 1
    return created


def check_forgotten_planned_orders(*, today=None) -> int:
    """Create alerts for planned work orders whose target date has passed."""
    from shopman.craftsman.models import WorkOrder

    today = today or timezone.localdate()
    qs = (
        WorkOrder.objects.filter(status=WorkOrder.Status.PLANNED, target_date__lt=today)
        .select_related("recipe")
    )

    created = 0
    for work_order in qs:
        if _recent_exists("production_forgotten", work_order.ref):
            continue
        message = (
            f"Produção {work_order.ref} ({work_order.output_sku}) planejada para "
            f"{work_order.target_date:%d/%m} nunca foi iniciada."
        )
        alert_adapter.create(
            "production_forgotten",
            "warning",
            message,
            order_ref=work_order.ref,
        )
        _notify_operator(
            "production_forgotten",
            severity="warning",
            context={
                "message": message,
                "work_order_ref": work_order.ref,
                "output_sku": work_order.output_sku,
                "target_date": work_order.target_date.isoformat(),
            },
        )
        created += 1
    return created


def check_unfinished_started_orders(*, today=None) -> int:
    """Create ONE alert per started work order whose target date has passed.

    O trio de estagnação: ``production_late`` cobre a fornada que passou da
    janela de MINUTOS no mesmo dia; ``production_forgotten`` cobre a planejada
    cuja data passou sem nunca iniciar; este cobre a INICIADA cuja data passou
    sem conclusão. É o caso que promete estoque fantasma — o quant
    ``batch='started'`` conta como ``in_production`` no ``total_promisable``
    até a shelf-life vencer, e nenhuma varredura automática pode zerá-lo
    enquanto a WO vive (concluir tarde precisa do quant lá). Só o operador
    resolve: concluir com a quantidade real (a expedição aceita fornada de
    ontem) ou cancelar, o que dispara a baixa via ``production_changed``.

    Idempotente por WO via marcador ``unfinished_alerted_at`` em
    ``WorkOrder.meta`` — ver o comentário do :data:`UNFINISHED_ALERTED_KEY`.
    """
    from shopman.craftsman.models import WorkOrder

    today = today or timezone.localdate()
    qs = (
        WorkOrder.objects.filter(status=WorkOrder.Status.STARTED, target_date__lt=today)
        .exclude(meta__has_key=UNFINISHED_ALERTED_KEY)
        .select_related("recipe")
    )

    created = 0
    for work_order in qs:
        if _recent_exists("production_unfinished", work_order.ref):
            # Guarda de corrida entre dois heartbeats: o marcador é gravado
            # depois do alerta, então a janela curta ainda pede dedup.
            _stamp_meta(work_order, UNFINISHED_ALERTED_KEY)
            continue
        message = (
            f"Produção {work_order.ref} ({work_order.output_sku}) iniciada para "
            f"{work_order.target_date:%d/%m} nunca foi concluída. Conclua com a "
            f"quantidade real ou cancele para liberar o estoque em produção."
        )
        alert_adapter.create(
            "production_unfinished",
            "warning",
            message,
            order_ref=work_order.ref,
        )
        _stamp_meta(work_order, UNFINISHED_ALERTED_KEY)
        _notify_operator(
            "production_unfinished",
            severity="warning",
            context={
                "message": message,
                "work_order_ref": work_order.ref,
                "output_sku": work_order.output_sku,
                "target_date": work_order.target_date.isoformat(),
            },
        )
        created += 1
    return created


def _stamp_meta(work_order, key: str) -> None:
    """Carimba ``WorkOrder.meta[key]`` durável, sem tocar em mais nada.

    ``update()`` de propósito, como ``_stamp_leg`` na ponte craftsman→stockman:
    ``save()`` dispararia ``auto_now`` no ``updated_at`` (que as telas de
    operação leem como "mexeu agora") e reescreveria o objeto inteiro por cima
    de quem estiver editando o meta em paralelo.
    """
    from shopman.craftsman.models import WorkOrder

    meta = dict(work_order.meta or {})
    if meta.get(key):
        return
    meta[key] = timezone.now().isoformat()
    work_order.meta = meta
    WorkOrder.objects.filter(pk=work_order.pk).update(meta=meta)


def create_batch_traceability_alert(*, work_order_ref: str, output_sku: str, error: str) -> None:
    """Alerta quando a fornada fechou mas os LOTES não foram gravados.

    Era um WARNING de log (best-effort); com a partição (ADR-017) a falha
    silenciosa ficou mais cara — N lotes carregam desconto e validade, e lote
    não gravado é preço cheio indevido e rastreabilidade perdida. O finish não
    desfaz (a fornada FOI produzida); o operador precisa saber e regravar.
    """
    if _recent_exists("production_batch_traceability", work_order_ref):
        return
    message = (
        f"Produção {work_order_ref} ({output_sku}) concluiu mas os lotes não foram "
        f"gravados: {error}"
    )
    alert_adapter.create(
        "production_batch_traceability",
        "error",
        message,
        order_ref=work_order_ref,
    )
    _notify_operator(
        "production_batch_traceability",
        severity="error",
        context={
            "message": message,
            "work_order_ref": work_order_ref,
            "output_sku": output_sku,
            "error": error,
        },
    )


def create_stock_short_alert(*, work_order_ref: str, output_sku: str, error: str) -> None:
    """Create an alert for a failed finish caused by stock/inventory shortage."""
    if _recent_exists("production_stock_short", work_order_ref):
        return
    message = f"Produção {work_order_ref} ({output_sku}) falhou por estoque insuficiente: {error}"
    alert_adapter.create(
        "production_stock_short",
        "error",
        message,
        order_ref=work_order_ref,
    )
    _notify_operator(
        "production_stock_short",
        severity="error",
        context={
            "message": message,
            "work_order_ref": work_order_ref,
            "output_sku": output_sku,
            "error": error,
        },
    )


def _notify_operator(event: str, *, severity: str, context: dict) -> bool:
    """Enfileira ``notification.send`` de sistema quando a config permite.

    O par tela+notificação: todo alerta de produção vira ``OperatorAlert``
    incondicionalmente; a notificação ativa (email→console, via directive com
    retry) é opt-in por ``production.notifications`` — ``enabled`` liga,
    ``severities`` filtra. A dedup fica no alerta (quem chega aqui já passou).
    """
    try:
        config = ProductionConfig.load().notifications
    except Exception:
        logger.debug("production_alerts.notifications_config_failed", exc_info=True)
        return False
    if not (config.enabled and severity in config.severities):
        return False

    from shopman.orderman.models import Directive

    from shopman.shop.directives import NOTIFICATION_SEND

    Directive.objects.create(
        topic=NOTIFICATION_SEND,
        payload={"event": event, "context": context},
    )
    return True


def _target_minutes(work_order) -> int:
    try:
        raw = (work_order.recipe.meta or {}).get("max_started_minutes")
        if raw not in (None, ""):
            value = int(raw)
            if value > 0:
                return value
    except Exception:
        logger.debug("production_alerts.invalid_target_minutes work_order=%s", work_order.pk, exc_info=True)
    return _alerts_config().default_max_started_minutes


def _alerts_config() -> ProductionConfig.Alerts:
    try:
        return ProductionConfig.load().alerts
    except Exception:
        logger.debug("production_alerts.config_load_failed", exc_info=True)
        return ProductionConfig.Alerts()


def _recent_exists(alert_type: str, work_order_ref: str) -> bool:
    return alert_adapter.recent_exists(
        alert_type,
        timezone.now() - timedelta(hours=12),
        message_contains=work_order_ref,
    )
