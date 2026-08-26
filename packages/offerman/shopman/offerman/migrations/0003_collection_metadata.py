from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("offerman", "0002_alter_product_sku"),
    ]

    operations = [
        migrations.AddField(
            model_name="collection",
            name="metadata",
            field=models.JSONField(blank=True, default=dict, verbose_name="metadados"),
        ),
    ]
