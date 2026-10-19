from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0101_confirmado_diz_a_data_da_encomenda")]

    operations = [
        migrations.CreateModel(
            name="CatalogImageUpload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel_ref", models.CharField(db_index=True, max_length=32)),
                ("merchant_id", models.CharField(max_length=64)),
                ("sha256", models.CharField(max_length=64)),
                ("image_path", models.CharField(blank=True, max_length=512)),
                ("content_type", models.CharField(blank=True, max_length=32)),
                ("size", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "upload de imagem do catálogo",
                "verbose_name_plural": "uploads de imagem do catálogo",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("channel_ref", "merchant_id", "sha256"),
                        name="uniq_catalog_image_channel_merchant_hash",
                    ),
                ],
            },
        ),
    ]
