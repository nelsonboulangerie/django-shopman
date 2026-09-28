"""Avisos de Encomendas na voz aprovada pelo dono (28/09/2026).

Revisão contra os templates já aprovados na Meta: abre com "Oi, Ana!", chama
"seu pedido", a frase que muda vem inteira na variável (com o próprio ponto, como
o "Motivo: …." do cancelado) e fecha com "Qualquer dúvida, estamos à
disposição." — sem 💛, que é emoji de festa e faz a Meta reclassificar aviso de
serviço como Marketing. Ajustes do dono: "foi reagendado para", "conforme
combinado", "O novo total é …".

Mesmo padrão da ``0079``: só troca o corpo que ainda está EXATAMENTE como o seed
gravou; texto reescrito no Admin fica como está.
"""

from django.db import migrations

TEXTS = [
    ("order_rescheduled", 'Oi{customer_name_greeting}! Tudo certo: seu pedido *{order_ref_short}* agora está marcado para {status_note}. Qualquer dúvida, estamos à disposição. 💛\nAcompanhe por aqui: {tracking_url}', 'Oi{customer_name_greeting}! Seu pedido *{order_ref_short}* foi reagendado para {status_note}. Qualquer dúvida, estamos à disposição.\nAcompanhe por aqui: {tracking_url}'),
    ("order_updated", 'Oi{customer_name_greeting}! Tudo certo: atualizamos seu pedido *{order_ref_short}*. {status_note}. Qualquer dúvida, estamos à disposição. 💛\nAcompanhe por aqui: {tracking_url}', 'Oi{customer_name_greeting}! Atualizamos seu pedido *{order_ref_short}* conforme combinado. {status_note} Qualquer dúvida, estamos à disposição.\nAcompanhe por aqui: {tracking_url}'),
]


def _swap(apps, *, forward):
    NotificationTemplate = apps.get_model("shop", "NotificationTemplate")
    for event, old_body, new_body in TEXTS:
        if not forward:
            old_body, new_body = new_body, old_body
        NotificationTemplate.objects.filter(event=event, body=old_body).update(body=new_body)


def forwards(apps, schema_editor):
    _swap(apps, forward=True)


def backwards(apps, schema_editor):
    _swap(apps, forward=False)


class Migration(migrations.Migration):
    dependencies = [("shop", "0081_order_updated_notification_template")]

    operations = [migrations.RunPython(forwards, backwards)]
