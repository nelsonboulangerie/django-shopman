from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("storefront", "0007_stock_alerts_persist_until_cancelled"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockalertsubscription",
            name="adult_declared",
            field=models.BooleanField(
                default=False,
                db_default=False,
                verbose_name="declarou ter 18 anos ou mais",
            ),
        ),
    ]
