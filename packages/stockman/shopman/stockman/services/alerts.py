"""
Stock alerts — check and trigger min stock alerts.

Usage:
    from shopman.stockman.services.alerts import check_alerts

    # Run periodically (celery beat, cron) or after stock changes
    triggered = check_alerts()
    # Returns list of (StockAlert, current_available) tuples
"""

import logging
from decimal import Decimal

from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from shopman.stockman.models.alert import StockAlert
from shopman.stockman.models.hold import Hold
from shopman.stockman.models.quant import Quant

logger = logging.getLogger('shopman.stockman')

_ZERO = Decimal('0')
_QUANTITY_FIELD = DecimalField(max_digits=12, decimal_places=3)


def _quant_total_subquery(physical: Q, *, at_position: bool):
    """
    Saldo físico de um alerta, como subconsulta escalar.

    at_position=False soma todas as posições (SKU); at_position=True soma a
    posição do alerta. É o mesmo par de agregados que o laço fazia por alerta,
    agora resolvido dentro da consulta que já traz os alertas.
    """
    quants = Quant.objects.filter(sku=OuterRef('sku')).filter(physical)
    if at_position:
        quants = quants.filter(position_id=OuterRef('position_id'))
        group_by = ('sku', 'position_id')
    else:
        group_by = ('sku',)
    return Coalesce(
        Subquery(
            quants.values(*group_by).annotate(total=Sum('_quantity')).values('total')[:1],
            output_field=_QUANTITY_FIELD,
        ),
        _ZERO,
        output_field=_QUANTITY_FIELD,
    )


def _hold_total_subquery(today, *, at_position: bool):
    """
    Reservas ativas de hoje de um alerta, como subconsulta escalar.

    at_position=True restringe às reservas cujo Quant está na posição do alerta
    (mesma semântica do filtro por quant__position do laço); reservas sem Quant
    (demanda) só entram no total global.
    """
    holds = Hold.objects.filter(sku=OuterRef('sku'), target_date=today).active()
    if at_position:
        holds = holds.filter(quant__position_id=OuterRef('position_id'))
        group_by = ('sku', 'quant__position_id')
    else:
        group_by = ('sku',)
    return Coalesce(
        Subquery(
            holds.values(*group_by).annotate(total=Sum('quantity')).values('total')[:1],
            output_field=_QUANTITY_FIELD,
        ),
        _ZERO,
        output_field=_QUANTITY_FIELD,
    )


def check_alerts(sku: str | None = None) -> list[tuple[StockAlert, Decimal]]:
    """
    Check all active alerts and return those that are triggered.

    An alert is triggered when available quantity < min_quantity.

    Args:
        sku: Optional SKU to check alerts for (None = all).

    Returns:
        List of (alert, current_available) tuples for triggered alerts.

    Os totais de cada alerta vêm embutidos na consulta que busca os alertas
    (subconsultas escalares), no mesmo padrão em bloco que a projeção do
    dashboard usa em _stock_alerts: o custo não cresce com o número de alertas.
    Os disparos caem num único UPDATE ao final.
    """
    qs = StockAlert.objects.filter(is_active=True)
    if sku is not None:
        qs = qs.filter(sku=sku)

    today = timezone.localdate()
    now = timezone.now()

    # Só estoque físico (sem produção planejada para o futuro).
    physical = Q(target_date__isnull=True) | Q(target_date__lte=today)

    alerts = list(
        qs.select_related('position').annotate(
            _quant_total_all=_quant_total_subquery(physical, at_position=False),
            _quant_total_at_position=_quant_total_subquery(physical, at_position=True),
            _hold_total_all=_hold_total_subquery(today, at_position=False),
            _hold_total_at_position=_hold_total_subquery(today, at_position=True),
        )
    )

    triggered = []
    for alert in alerts:
        if alert.position_id:
            total = alert._quant_total_at_position
            held = alert._hold_total_at_position
        else:
            total = alert._quant_total_all
            held = alert._hold_total_all

        available = total - held

        if available < alert.min_quantity:
            alert.last_triggered_at = now
            triggered.append((alert, available))
            logger.warning(
                "stock.alert.triggered",
                extra={
                    "alert_id": alert.pk,
                    "sku": alert.sku,
                    "min_quantity": str(alert.min_quantity),
                    "available": str(available),
                    "position": str(alert.position) if alert.position else "all",
                },
            )

    if triggered:
        # Todos os disparados recebem o mesmo now, então um UPDATE único grava
        # exatamente o que os saves individuais gravariam.
        StockAlert.objects.filter(
            pk__in=[alert.pk for alert, _ in triggered]
        ).update(last_triggered_at=now)

    return triggered
