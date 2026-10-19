"""O aviso de confirmado diz a data da encomenda (WP-DATA-E-PROMESSA, L9).

"Seu pedido A47 está confirmado" não dizia para quando: na encomenda o cliente
ficava sem a promessa escrita. O corpo ganha ``{commitment_suffix}`` logo depois
de "confirmado" (" para retirada amanhã, a partir das 9h"), que fica vazio no
pedido de hoje.

Mesmo padrão da ``0075``: só troca o corpo que ainda está **exatamente** como o
seed gravou; texto reescrito no Admin fica como está.
"""

from django.db import migrations

# (evento, assunto antigo, assunto novo, corpo antigo, corpo novo)
TEXTS = [
    (
        "order_accepted",
        "Pedido {order_ref_short} confirmado",
        "Pedido {order_ref_short} confirmado",
        "Seu pedido *{order_ref_short}* está confirmado. O total é *{order_total_display}*. Vamos preparar com todo carinho. ✨\nAcompanhe por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* está confirmado{commitment_suffix}. O total é *{order_total_display}*. Vamos preparar com todo carinho. ✨\nAcompanhe por aqui: {tracking_url}",
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
    dependencies = [("shop", "0100_shop_brand_palette")]

    operations = [migrations.RunPython(forwards, backwards)]
