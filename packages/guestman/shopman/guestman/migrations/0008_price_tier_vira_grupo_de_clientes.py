from django.db import migrations, models


class Migration(migrations.Migration):
    """Decisão do dono (20/10/2026): o PriceTier se chama "grupo de clientes" em toda tela.

    Só rótulo: nenhuma coluna muda.
    """

    dependencies = [
        ("guestman", "0007_contactpoint_otp_email_verification_method"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="pricetier",
            options={
                "ordering": ["-priority", "name"],
                "verbose_name": "grupo de clientes",
                "verbose_name_plural": "grupos de clientes",
            },
        ),
        migrations.AlterField(
            model_name="pricetier",
            name="is_default",
            field=models.BooleanField(
                default=False,
                help_text="Grupo padrão para novos clientes",
                verbose_name="padrão",
            ),
        ),
        migrations.AlterField(
            model_name="pricetier",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Metadados do grupo. Ex: {"discount_percent": 10, "min_order_q": 5000}',
                verbose_name="metadados",
            ),
        ),
    ]
