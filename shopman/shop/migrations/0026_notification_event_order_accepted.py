"""O evento de notificação acompanha o status: `order_confirmed` → `order_accepted`.

O nome do evento é identificador GRAVADO em `NotificationTemplate.event`. Um sed
no Python renomeia quem dispara, mas deixa a linha do banco com o nome velho — e
aí o disparo não encontra template e a notificação some em silêncio.
"""

from django.db import migrations


def _renomear(apps, *, de: str, para: str) -> None:
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(event=de).update(event=para)


def para_accepted(apps, schema_editor):
    _renomear(apps, de="order_confirmed", para="order_accepted")


def voltar(apps, schema_editor):
    _renomear(apps, de="order_accepted", para="order_confirmed")


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0025_shop_realtime_cadence"),
    ]

    operations = [
        migrations.RunPython(para_accepted, voltar),
    ]
