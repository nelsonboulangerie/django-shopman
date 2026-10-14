"""Pix vencido manda um aviso só (P1-9, 14/10/2026).

O evento ``payment_expired`` deixou de existir: o vencimento do prazo de
pagamento sai pelo ``order_cancelled``, com a frase do prazo vencido no
``status_note``. A linha do Admin (``NotificationTemplate``) que o seed criou
para o evento aposentado não tem mais quem a use; pré go-live o dado é
sintético, então ela é apagada, não arquivada. O reverse é inerte: o seed não
recria o evento.
"""

from django.db import migrations

RETIRED_EVENT = "payment_expired"


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(event=RETIRED_EVENT).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0094_loja_online_paga_ao_pedir"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
