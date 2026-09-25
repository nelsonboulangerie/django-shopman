"""O aviso de saída para entrega perde o cumprimento (decisão do dono, 25/09/2026).

Mesma regra da voz de 24/09 (``0075_voz_dos_avisos_do_pedido``): o nome fica na
abertura do ciclo, e os passos do meio falam só do pedido. Só troca o corpo que
ainda está **exatamente** como o seed antigo gravou; o texto reescrito no Admin
fica como está.
"""

from django.db import migrations

EVENT = "order_dispatched"
OLD_BODY = "Olá{customer_name_greeting}! Seu pedido *{order_ref}* saiu para entrega!{courier_tracking_suffix}\n\nQuando receber, é só confirmar por aqui: {tracking_url}"
NEW_BODY = "Seu pedido *{order_ref}* saiu para entrega e chega logo.{courier_tracking_suffix}\nQuando receber, é só confirmar por aqui: {tracking_url}"


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(event=EVENT, body=OLD_BODY).update(body=NEW_BODY)


def backwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(event=EVENT, body=NEW_BODY).update(body=OLD_BODY)


class Migration(migrations.Migration):
    dependencies = [("shop", "0075_voz_dos_avisos_do_pedido")]

    operations = [migrations.RunPython(forwards, backwards)]
