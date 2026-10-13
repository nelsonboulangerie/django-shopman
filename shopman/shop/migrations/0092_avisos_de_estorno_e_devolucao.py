"""Os avisos de estorno e de devolução ao cliente (P1-9, cenários de pedido).

``payment_refunded`` passa a dizer o valor DESTE estorno, por onde ele volta e que
pode demorar conforme o banco; ``order_returned`` ganha texto (era emitido sem
nenhum). A fonte é ``shopman/shop/notification_copy.py``.

Mesmo padrão da ``0078``: o estorno só troca o texto que ainda está **exatamente**
como a ``0079`` (e o seed) gravou; texto reescrito no Admin fica. A
devolução só nasce onde não existe linha.
"""

from django.db import migrations

REFUND_EVENT = "payment_refunded"
#: O texto de fábrica que a 0079 deixou (e que o seed gravava).
REFUND_OLD_SUBJECT = "Reembolso do pedido {order_ref_short} processado"
REFUND_OLD_BODY = (
    "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de "
    "*{order_total_display}*, foi processado. Qualquer dúvida, estamos à disposição."
)
REFUND_SUBJECT = "Pedido {order_ref_short}: valor devolvido"
REFUND_BODY = (
    "Oi{customer_name_greeting}! Devolvemos *{refund_amount_display}* do seu pedido *{order_ref_short}*. "
    "{status_note}. Qualquer dúvida, estamos à disposição."
)

# (evento, assunto antigo, assunto novo, corpo antigo, corpo novo): o formato das
# migrações de texto (0075, 0078, 0079), que a trava da voz encadeia até o seed.
TEXTS = [(REFUND_EVENT, REFUND_OLD_SUBJECT, REFUND_SUBJECT, REFUND_OLD_BODY, REFUND_BODY)]

RETURN_EVENT = "order_returned"
RETURN_SUBJECT = "Pedido {order_ref_short} devolvido"
RETURN_BODY = (
    "Oi{customer_name_greeting}. Registramos a devolução de todos os itens do seu pedido *{order_ref_short}*. "
    "{status_note}. Qualquer dúvida, estamos à disposição.\n"
    "Veja os detalhes: {tracking_url}"
)


def _swap(apps, *, forward: bool) -> None:
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for event, old_subject, new_subject, old_body, new_body in TEXTS:
        source_subject, target_subject = (old_subject, new_subject) if forward else (new_subject, old_subject)
        source_body, target_body = (old_body, new_body) if forward else (new_body, old_body)
        for row in NotificationTemplate.objects.filter(event=event):
            changed = []
            if row.subject == source_subject:
                row.subject = target_subject
                changed.append("subject")
            if row.body == source_body:
                row.body = target_body
                changed.append("body")
            if changed:
                row.save(update_fields=changed)


def forwards(apps, schema_editor):
    _swap(apps, forward=True)
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.get_or_create(
        event=RETURN_EVENT,
        defaults={"subject": RETURN_SUBJECT, "body": RETURN_BODY, "is_active": True},
    )


def backwards(apps, schema_editor):
    _swap(apps, forward=False)
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    NotificationTemplate.objects.filter(
        event=RETURN_EVENT, subject=RETURN_SUBJECT, body=RETURN_BODY, whatsapp_flow_ns=""
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0091_digital_do_dispositivo_do_operador")]

    operations = [migrations.RunPython(forwards, backwards)]
