from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0088_kitchensink_permission"),
    ]

    operations = [
        migrations.AddField(
            model_name="operatoralert",
            name="respond_by",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Prazo em que a causa decide sozinha (ex.: o iFood aplica a ação de prazo). "
                    "Com prazo e sem Visto, a superfície interrompe a tela até alguém ver."
                ),
                null=True,
                verbose_name="responder até",
            ),
        ),
    ]
