"""Ensure existing shops have a row for the reschedule notification."""

from django.db import migrations

EVENT = "order_rescheduled"
SUBJECT = "Pedido {order_ref_short}: nova data"
BODY = (
    "Oi{customer_name_greeting}! Tudo certo: seu pedido *{order_ref_short}* "
    "agora está marcado para {status_note}. Qualquer dúvida, estamos à "
    "disposição. 💛\nAcompanhe por aqui: {tracking_url}"
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
    dependencies = [("shop", "0079_confirmado_com_todo_carinho")]

    operations = [migrations.RunPython(forwards, backwards)]
