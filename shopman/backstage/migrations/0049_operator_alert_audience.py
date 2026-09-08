from django.db import migrations, models

PRODUCTION_TYPES = {
    "production_late",
    "production_low_yield",
    "production_stock_short",
    "stock_discrepancy",
    "stock_low",
}
FINANCE_TYPES = {
    "payment_failed",
    "payment_insufficient",
    "payment_reconciliation_failed",
    "payment_disputed",
    "payment_after_cancel",
    "cash_shift_open_at_closing",
    "cash_sale_after_shift_close",
    "bi_cash_variance",
}
ORDER_TYPES = {
    "marketplace_rejected_unavailable",
    "marketplace_rejected_oos",
    "pos_rejected_unavailable",
    "stale_new_order",
    "lifecycle_phase_stuck",
}


def backfill_alert_audience(apps, schema_editor):
    operator_alert = apps.get_model("backstage", "OperatorAlert")
    operator_alert.objects.filter(type__in=PRODUCTION_TYPES).update(audience="production")
    operator_alert.objects.filter(type__in=FINANCE_TYPES).update(audience="finance")
    operator_alert.objects.filter(type__in=ORDER_TYPES).update(audience="orders")


class Migration(migrations.Migration):
    dependencies = [("backstage", "0048_production_capability_permissions")]

    operations = [
        migrations.AddField(
            model_name="operatoralert",
            name="audience",
            field=models.CharField(
                choices=[
                    ("production", "Produção"),
                    ("orders", "Pedidos"),
                    ("finance", "Financeiro"),
                    ("operations", "Operação geral"),
                ],
                db_index=True,
                default="operations",
                max_length=20,
                verbose_name="público operacional",
            ),
        ),
        migrations.RunPython(backfill_alert_audience, migrations.RunPython.noop),
    ]
