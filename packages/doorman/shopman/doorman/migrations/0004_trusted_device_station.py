"""A confiança de dispositivo ganha o terceiro sujeito: a ESTAÇÃO.

Só a lista de `choices` muda — nenhuma coluna, nenhum dado. `subject_type` já é
`CharField`, e a forma foi desenhada para isto: o docstring do model reservava o
terceiro valor desde que o `display` entrou.

O que ele guarda é "de que balcão esta requisição veio". A estação confiável NÃO
ganha permissão por ser confiável; quem autoriza é a pessoa que se identifica
nela (D1, opção B, 21/08/2026).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("doorman", "0003_rotulos_em_portugues"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trusteddevice",
            name="subject_type",
            field=models.CharField(
                choices=[
                    ("customer", "cliente"),
                    ("display", "quadro"),
                    ("station", "estação"),
                ],
                db_index=True,
                default="customer",
                max_length=16,
                verbose_name="tipo de sujeito",
            ),
        ),
    ]
