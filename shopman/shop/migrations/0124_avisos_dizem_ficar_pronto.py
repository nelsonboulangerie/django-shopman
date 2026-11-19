"""Os avisos da fila e da fornada dizem "ficar pronto", nunca "sair do forno".

A casa diz "fica pronto" (dono, 16/11/2026; #2791). O seed já lê o texto novo de
``shopman/shop/notification_copy.py``; esta migração leva o mesmo texto ao banco
que já existe. Atualiza só a linha que ainda tem o texto padrão anterior: texto
personalizado no Admin fica como está.
"""

from django.db import migrations
from django.db.models import F

TEXTS = [
    (
        "waitlist_available",
        "Sua fornada saiu: confirme o pedido {order_ref_short}",
        "Chegou a sua vez: confirme o pedido {order_ref_short}",
        "Oba! 💛✨ Acabou de sair do forno{customer_name_greeting}! Confirme o pedido *{order_ref_short}* para garantir: {tracking_url}",
        "Oi{customer_name_greeting}! A fornada que você esperava ficou pronta. Confirme seu pedido *{order_ref_short}* para garantir a sua vaga: {tracking_url}",
    ),
    (
        "production_ready",
        "{product_name} saiu do forno",
        "Fornada pronta: {product_name}",
        "Olha só o que acabou de sair do forno: *{product_name}*! {availability_note}.\nGaranta já o seu: {action_url}{management_note}",
        "Olha só a fornada que acabou de ficar pronta: *{product_name}*! {availability_note}.\nGaranta já o seu: {action_url}{management_note}",
    ),
]


def _swap(apps, *, forward: bool) -> None:
    template = apps.get_model("shop", "NotificationTemplate")
    for event, old_subject, new_subject, old_body, new_body in TEXTS:
        source = (old_subject, old_body) if forward else (new_subject, new_body)
        target = (new_subject, new_body) if forward else (old_subject, old_body)
        template.objects.filter(event=event, subject=source[0], body=source[1]).update(
            subject=target[0], body=target[1], version=F("version") + 1,
        )


def forwards(apps, schema_editor):
    _swap(apps, forward=True)


def backwards(apps, schema_editor):
    _swap(apps, forward=False)


class Migration(migrations.Migration):
    dependencies = [("shop", "0123_endereco_de_entrega_sem_etiqueta")]
    operations = [migrations.RunPython(forwards, backwards)]
