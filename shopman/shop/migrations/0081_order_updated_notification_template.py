"""Ensure existing shops have a row for the order-edit notification (``order_updated``).

⚠️ O texto é RASCUNHO (28/09/2026): o dono revisa antes de o template ir para a
Meta. A fonte é ``notification_copy.CUSTOMER_COPY["order_updated"]``; linha já
curada no Admin nunca é sobrescrita.
"""

from django.db import migrations

EVENT = "order_updated"
SUBJECT = "Pedido {order_ref_short} atualizado"
BODY = (
    "Oi{customer_name_greeting}! Tudo certo: atualizamos seu pedido *{order_ref_short}*. "
    "{status_note}. Qualquer dúvida, estamos à disposição. 💛\n"
    "Acompanhe por aqui: {tracking_url}"
)


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.get_or_create(
        event=EVENT,
        defaults={
            "subject": SUBJECT,
            "body": BODY,
            "is_active": True,
        },
    )


def backwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(
        event=EVENT,
        subject=SUBJECT,
        body=BODY,
        is_active=True,
        whatsapp_flow_ns="",
        version=1,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0080_order_rescheduled_notification_template")]

    operations = [migrations.RunPython(forwards, backwards)]
