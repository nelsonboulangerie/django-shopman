"""Alert operators about stock-alert deliveries that exceeded their SLA."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Checks stock-alert queue SLA and creates debounced operator alerts."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=10)

    def handle(self, *args, **options):
        from shopman.shop.services.observability import create_operator_alert
        from shopman.storefront.models import StockAlertDelivery

        minutes = max(1, int(options["minutes"]))
        cutoff = timezone.now() - timedelta(minutes=minutes)
        stuck = StockAlertDelivery.objects.filter(
            status__in=[
                StockAlertDelivery.Status.QUEUED,
                StockAlertDelivery.Status.CLAIMED,
                StockAlertDelivery.Status.RETRYABLE,
                StockAlertDelivery.Status.INDETERMINATE,
            ],
            updated_at__lte=cutoff,
        )
        counts = {status: stuck.filter(status=status).count() for status, _ in StockAlertDelivery.Status.choices}
        total = sum(counts.values())
        if total:
            create_operator_alert(
                type="stock_alert_delivery_stuck",
                severity="warning",
                message=(
                    f"{total} aviso(s) excederam {minutes} min; estados={counts}; "
                    "runbook=docs/runbooks/stock-alert-delivery.md"
                ),
                dedupe_key="stock-alert-delivery-sla",
            )
        self.stdout.write(f"stuck={total} counts={counts}")
