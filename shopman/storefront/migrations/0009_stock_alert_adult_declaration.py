from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("storefront", "0008_quarantine_unverified_web_alerts"),
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
