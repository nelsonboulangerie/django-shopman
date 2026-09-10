from django.db import migrations
from django.db.models import F
from django.utils import timezone


def resolve_historical_low_yield(apps, schema_editor):
    OperatorAlert = apps.get_model("backstage", "OperatorAlert")
    OperatorAlert.objects.filter(
        type="production_low_yield",
        resolved_at__isnull=True,
    ).update(
        acknowledged=True,
        resolved_at=timezone.now(),
        resolved_by="system:migration-production-outcome-recorded",
        rev=F("rev") + 1,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0053_backfill_production_stock_shortfall_audience"),
    ]

    operations = [
        migrations.RunPython(
            resolve_historical_low_yield,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
