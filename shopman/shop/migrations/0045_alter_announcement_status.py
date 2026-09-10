from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0044_merge_marketing_excellence")]

    operations = [
        migrations.AlterField(
            model_name="announcement",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "rascunho"),
                    ("pending_review", "aguardando aprovação"),
                    ("approved", "aprovado"),
                    ("publishing", "publicando"),
                    ("settled", "execução encerrada"),
                    ("published", "publicado"),
                    ("failed", "falhou"),
                    ("rejected", "recusado"),
                    ("expired", "expirado"),
                    ("cancelled", "cancelado"),
                    ("superseded", "Substituído"),
                ],
                default="draft",
                max_length=16,
                verbose_name="situação",
            ),
        ),
    ]
