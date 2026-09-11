"""Read-only inventory before any human-approved subscription consolidation."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from shopman.storefront.models import StockAlertDelivery, StockAlertSubscription


class Command(BaseCommand):
    help = "Dry-run: counts only; never changes consent, subscriptions or dispatches."

    def handle(self, *args, **options):
        active = StockAlertSubscription.objects.active()
        groups = active.values("channel_ref", "sku", "alert_type", "contact_phone").annotate(rows=Count("id"))
        duplicates = list(groups.filter(rows__gt=1).values_list("rows", flat=True))
        self.stdout.write(
            json.dumps(
                {
                    "active": active.count(),
                    "exact_contact_duplicate_groups": len(duplicates),
                    "extra_rows": sum(n - 1 for n in duplicates),
                    "paused": StockAlertSubscription.objects.filter(
                        revoked_at__isnull=True, paused_at__isnull=False
                    ).count(),
                    "queued_deliveries": StockAlertDelivery.objects.filter(status="queued").count(),
                    "indeterminate_deliveries": StockAlertDelivery.objects.filter(status="indeterminate").count(),
                    "accepted_deliveries": StockAlertDelivery.objects.filter(status="accepted").count(),
                    "legacy_notified_without_acceptance_receipt": StockAlertSubscription.objects.filter(
                        notified_at__isnull=False, dispatch_accepted_at__isnull=True
                    ).count(),
                    "mutations": 0,
                },
                sort_keys=True,
            )
        )
