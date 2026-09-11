"""Read-only inventory before any human-approved subscription consolidation."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from shopman.storefront.models import StockAlertSubscription


class Command(BaseCommand):
    help = "Dry-run: counts only; never changes consent, subscriptions or dispatches."

    def handle(self, *args, **options):
        pending = StockAlertSubscription.objects.filter(notified_at__isnull=True)
        groups = pending.values("channel_ref", "sku", "alert_type", "contact_phone").annotate(rows=Count("id"))
        duplicates = list(groups.filter(rows__gt=1).values_list("rows", flat=True))
        self.stdout.write(
            json.dumps(
                {
                    "pending": pending.count(),
                    "exact_contact_duplicate_groups": len(duplicates),
                    "extra_rows": sum(n - 1 for n in duplicates),
                    "unresolved_claims": pending.filter(
                        dispatch_claimed_at__isnull=False, dispatch_accepted_at__isnull=True
                    ).count(),
                    "accepted": StockAlertSubscription.objects.filter(dispatch_accepted_at__isnull=False).count(),
                    "legacy_notified_without_acceptance_receipt": StockAlertSubscription.objects.filter(
                        notified_at__isnull=False, dispatch_accepted_at__isnull=True
                    ).count(),
                    "mutations": 0,
                },
                sort_keys=True,
            )
        )
