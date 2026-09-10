from django.db import migrations

PRODUCTION_TYPES = {
    "production_stock_shortfall",
    "production_forgotten",
    "production_unfinished",
    "production_batch_traceability",
}


def backfill_production_alert_audience(apps, schema_editor):
    operator_alert = apps.get_model("backstage", "OperatorAlert")
    operator_alert.objects.filter(
        type__in=PRODUCTION_TYPES,
        audience="operations",
    ).update(audience="production")


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0052_operatoralert_ack_audit"),
    ]

    operations = [
        migrations.RunPython(
            backfill_production_alert_audience,
            migrations.RunPython.noop,
        ),
    ]
