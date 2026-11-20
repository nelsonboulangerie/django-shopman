"""Os três avisos do "Avisar o cliente" (WP-G07) no Admin de cada loja.

Texto aprovado pelo dono em 20/11/2026. A fonte é
``notification_copy.CUSTOMER_COPY``; o texto fica copiado aqui porque a migração é
história e não pode mudar quando a fonte mudar. Linha já curada no Admin nunca é
sobrescrita.
"""

from django.db import migrations

TEMPLATES = {
    "order_delayed": (
        "Pedido {order_ref_short}: nova previsão",
        "Oi{customer_name_greeting}! Aqui é da {shop_name} 💛 Seu pedido *{order_ref_short}* "
        "vai atrasar um pouco: a nova previsão é {status_note}, e sinto muito por isso. "
        "Qualquer dúvida, é só responder aqui.\n"
        "Acompanhe por aqui: {tracking_url}",
    ),
    "order_item_missing": (
        "Pedido {order_ref_short}: item em falta",
        "Oi{customer_name_greeting}! Aqui é da {shop_name} 💛 No seu pedido *{order_ref_short}*, "
        "vai faltar o item {status_note}, e sinto muito por isso. Posso trocar por outro "
        "produto ou devolver esse valor. Me responde aqui como fica melhor para você.\n"
        "Acompanhe por aqui: {tracking_url}",
    ),
    "order_reschedule_needed": (
        "Pedido {order_ref_short}: precisamos remarcar",
        "Oi{customer_name_greeting}! Aqui é da {shop_name} 💛 Não vamos conseguir aprontar "
        "seu pedido *{order_ref_short}* para {status_note}, como combinamos, e sinto muito "
        "por isso. Posso remarcar para outro dia ou cancelar e devolver o valor. Me responde "
        "aqui como fica melhor para você.\n"
        "Acompanhe por aqui: {tracking_url}",
    ),
}


def forwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for event, (subject, body) in TEMPLATES.items():
        NotificationTemplate.objects.get_or_create(
            event=event, defaults={"subject": subject, "body": body, "is_active": True}
        )


def backwards(apps, schema_editor):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for event, (subject, body) in TEMPLATES.items():
        NotificationTemplate.objects.filter(
            event=event, subject=subject, body=body, is_active=True, whatsapp_flow_ns="", version=1
        ).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0126_armazenamento_conversacional")]

    operations = [migrations.RunPython(forwards, backwards)]
