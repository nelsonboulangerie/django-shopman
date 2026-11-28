"""Cancelamento sem repetição, revisão do dono em 06/11/2026.

Atualiza somente o padrão anterior, preservando texto personalizado no Admin.
"""

from django.db import migrations
from django.db.models import F

SUBJECT = "Pedido {order_ref_short} cancelado"
OLD_BODY = 'Oi{customer_name_greeting}. Seu pedido *{order_ref_short}* foi cancelado. {status_note} Qualquer dúvida, estamos à disposição. 😌\nVeja os detalhes: {tracking_url}'
NEW_BODY = 'Oi{customer_name_greeting}. Seu pedido *{order_ref_short}* foi cancelado{cancellation_reason_suffix} Qualquer dúvida, estamos à disposição. 😌\nVeja os detalhes: {tracking_url}'
TEXTS = [("order_cancelled", SUBJECT, SUBJECT, OLD_BODY, NEW_BODY)]


def forwards(apps, schema_editor):
    template = apps.get_model("shop", "NotificationTemplate")
    template.objects.filter(event="order_cancelled", body=OLD_BODY).update(
        body=NEW_BODY, version=F("version") + 1,
    )


def backwards(apps, schema_editor):
    template = apps.get_model("shop", "NotificationTemplate")
    template.objects.filter(event="order_cancelled", body=NEW_BODY).update(
        body=OLD_BODY, version=F("version") + 1,
    )


class Migration(migrations.Migration):
    dependencies = [("shop", "0110_cupom_em_maiusculas_e_ajudas")]
    operations = [migrations.RunPython(forwards, backwards)]
