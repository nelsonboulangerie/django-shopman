"""Confirmado e lembrete "com todo carinho"; o total vira ``order_total_display``.

Decisões do dono, 25/09/2026, ao montar o primeiro template na Meta: a frase passa a
"Vamos preparar com todo carinho." nos dois avisos que a têm (confirmado e lembrete
de encomenda), e o valor formatado ganha nome que diz o que ele é
(``order_total_display``, como ``purchase_qty_display``): ``total`` era vago, e
``order_total`` já existe no ManyChat como número de outra campanha.

Mesmo padrão da ``0075``: só troca o campo que ainda está **exatamente** como o
seed gravou; texto reescrito no Admin fica como está.
"""

from django.db import migrations

# (evento, assunto antigo, assunto novo, corpo antigo, corpo novo)
TEXTS = [
    (
        "order_accepted",
        "Pedido {order_ref_short} confirmado",
        "Pedido {order_ref_short} confirmado",
        "Seu pedido *{order_ref_short}* está confirmado. O total é *{total}*. Vamos preparar tudo com muito carinho. ✨\nAcompanhe por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* está confirmado. O total é *{order_total_display}*. Vamos preparar com todo carinho. ✨\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "preorder_reminder",
        "Lembrete: pedido {order_ref_short} agendado para amanhã",
        "Lembrete: pedido {order_ref_short} agendado para amanhã",
        "Oi{customer_name_greeting}! Lembrando que seu pedido *{order_ref_short}* está agendado para amanhã. Vamos preparar tudo com muito carinho. ✨\nAcompanhe por aqui: {tracking_url}",
        "Oi{customer_name_greeting}! Lembrando que seu pedido *{order_ref_short}* está agendado para amanhã. Vamos preparar com todo carinho. ✨\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "payment_link_sent",
        "Pedido {order_ref_short}: link de pagamento",
        "Pedido {order_ref_short}: link de pagamento",
        "Oi{customer_name_greeting}! Anotamos seu pedido *{order_ref_short}* no valor de *{total}*. Pague por aqui para garantir: {checkout_url}{payment_deadline_note}",
        "Oi{customer_name_greeting}! Anotamos seu pedido *{order_ref_short}* no valor de *{order_total_display}*. Pague por aqui para garantir: {checkout_url}{payment_deadline_note}",
    ),
    (
        "payment_refunded",
        "Reembolso do pedido {order_ref_short} processado",
        "Reembolso do pedido {order_ref_short} processado",
        "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de *{total}*, foi processado. Qualquer dúvida, estamos à disposição.",
        "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de *{order_total_display}*, foi processado. Qualquer dúvida, estamos à disposição.",
    ),
]


def _swap(apps, *, forward):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for event, old_subject, new_subject, old_body, new_body in TEXTS:
        if not forward:
            old_subject, new_subject = new_subject, old_subject
            old_body, new_body = new_body, old_body
        NotificationTemplate.objects.filter(event=event, subject=old_subject).update(subject=new_subject)
        NotificationTemplate.objects.filter(event=event, body=old_body).update(body=new_body)


def forwards(apps, schema_editor):
    _swap(apps, forward=True)


def backwards(apps, schema_editor):
    _swap(apps, forward=False)


class Migration(migrations.Migration):
    dependencies = [("shop", "0078_frases_revisadas_das_notificacoes")]

    operations = [migrations.RunPython(forwards, backwards)]
