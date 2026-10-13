"""Os avisos de estorno e de devolução ao cliente (P1-9, cenários de pedido).

``payment_refunded`` passa a dizer o valor DESTE estorno, por onde ele volta e que
pode demorar conforme o banco; ``order_returned`` ganha texto (era emitido sem
nenhum). A fonte é ``shopman/shop/notification_copy.py``.

Mesmo padrão da ``0078``: o estorno só troca o texto que ainda está **exatamente**
como a casa gravou (pela ``0078`` ou pelo seed); texto reescrito no Admin fica. A
devolução só nasce onde não existe linha.
"""

from django.db import migrations

REFUND_EVENT = "payment_refunded"
#: Os dois textos de fábrica que podem estar no banco: o da 0078 e o do seed.
REFUND_OLD_SUBJECT = "Reembolso do pedido {order_ref_short} processado"
REFUND_OLD_BODIES = (
    "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de *{total}*, "
    "foi processado. Qualquer dúvida, estamos à disposição.",
    "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de "
    "*{order_total_display}*, foi processado. Qualquer dúvida, estamos à disposição.",
)
REFUND_SUBJECT = "Pedido {order_ref_short}: valor devolvido"
REFUND_BODY = (
    "Oi{customer_name_greeting}! Devolvemos *{refund_amount_display}* do seu pedido *{order_ref_short}*. "
    "{status_note}. Qualquer dúvida, estamos à disposição."
)

RETURN_EVENT = "order_returned"
RETURN_SUBJECT = "Pedido {order_ref_short} devolvido"
RETURN_BODY = (
    "Oi{customer_name_greeting}. Registramos a devolução de todos os itens do seu pedido *{order_ref_short}*. "
    "{status_note}. Qualquer dúvida, estamos à disposição.\n"
    "Veja os detalhes: {tracking_url}"
)


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for row in NotificationTemplate.objects.filter(event=REFUND_EVENT):
        changed = []
        if row.subject == REFUND_OLD_SUBJECT:
            row.subject = REFUND_SUBJECT
            changed.append("subject")
        if row.body in REFUND_OLD_BODIES:
            row.body = REFUND_BODY
            changed.append("body")
        if changed:
            row.save(update_fields=changed)
    NotificationTemplate.objects.get_or_create(
        event=RETURN_EVENT,
        defaults={"subject": RETURN_SUBJECT, "body": RETURN_BODY, "is_active": True},
    )


def backwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(
        event=REFUND_EVENT, subject=REFUND_SUBJECT, body=REFUND_BODY
    ).update(subject=REFUND_OLD_SUBJECT, body=REFUND_OLD_BODIES[0])
    NotificationTemplate.objects.filter(
        event=RETURN_EVENT, subject=RETURN_SUBJECT, body=RETURN_BODY, whatsapp_flow_ns=""
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0091_digital_do_dispositivo_do_operador")]

    operations = [migrations.RunPython(forwards, backwards)]
