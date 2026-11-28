"""O próximo lote diz quando o item fica disponível (dono, 24/11/2026).

A folha de quando o item acaba e há próximo lote dizia "Já vem quentinho. Fica pronto
no próximo lote, fresquinho. Quer garantir o seu?". Passa a dizer "Disponível a partir
das 15h" (``{when}`` é a hora do próximo lote) e oferece "Reservar". O dono autorizou
trocar também o texto gravado no Admin, se houver: toda linha da chave passa ao texto
novo, editada ou não.
"""

from django.db import migrations

KEY = "KINTSUGI_PLANNED_OFFER"
TITLE = "Disponível {when}"


def forwards(apps, schema_editor):
    OmotenashiCopy = apps.get_model("shop", "OmotenashiCopy")
    OmotenashiCopy.objects.filter(key=KEY).update(title=TITLE, message="")


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0139_paleta_cor_da_promocao"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
