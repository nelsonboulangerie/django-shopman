"""Voz dos avisos do ciclo do pedido (decisão do dono, 24/09/2026).

Leva ao banco já semeado — o alpha, que não se ressemeia sem a palavra dele — os
textos novos do ``seed``: primeira pessoa, presente, nome só na abertura, link
com rótulo em toda mensagem e agradecimento uma vez só, no fim.

Só troca o campo que ainda está **exatamente** como o seed antigo o gravou.
Texto que o lojista reescreveu no Admin é dele, e fica. Banco sem a linha (ou
teste) passa direto: quem cria a linha é o ``seed``, não esta migração.
"""

from django.db import migrations

# (evento, assunto antigo, assunto novo, corpo antigo, corpo novo)
TEXTS = [
    (
        "order_received",
        "Pedido {order_ref} recebido",
        "Pedido {order_ref} recebido",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}*. O estabelecimento vai conferir a disponibilidade. Acompanhe por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}*.\nEstamos conferindo a disponibilidade e avisamos em seguida.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_accepted",
        "Pedido {order_ref} confirmado",
        "Pedido {order_ref} confirmado",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* foi confirmado. Total: *{total}*.\n\nObrigado pela preferência!",
        "Seu pedido *{order_ref}* está confirmado. Total: *{total}*.\nJá vamos preparar.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_preparing",
        "Pedido {order_ref} em preparo",
        "Pedido {order_ref} em preparo",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está sendo preparado.\n\nAvisaremos quando estiver pronto!",
        "Estamos preparando seu pedido *{order_ref}*.{eta_note}\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_ready_pickup",
        "Pedido {order_ref} pronto para retirada",
        "Pedido {order_ref} pronto para retirada",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está pronto para retirada! 🎉\n\nVenha buscar. Obrigado!",
        "Seu pedido *{order_ref}* está pronto e esperando por você no balcão. 🥐\nEndereço e detalhes: {tracking_url}",
    ),
    (
        "order_ready_delivery",
        "Pedido {order_ref} pronto para entrega",
        "Pedido {order_ref} pronto — aguardando entregador",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está pronto e aguardando entregador. Assim que sair para entrega avisamos. 📦",
        "Seu pedido *{order_ref}* está pronto e aguardando o entregador.\nAvisamos assim que sair. 📦\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_rejected",
        "Pedido {order_ref} não confirmado",
        "Pedido {order_ref} não confirmado",
        "Olá{customer_name_greeting}! O estabelecimento não conseguiu confirmar o pedido *{order_ref}*.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! Não conseguimos confirmar o pedido *{order_ref}*.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
    ),
    (
        "payment_confirmed",
        "Pagamento do pedido {order_ref} confirmado",
        "Pagamento do pedido {order_ref} recebido",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref}* foi recebido.\n\nValor: *{total}*\n\nAvisamos a cada passo. Acompanhe por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref}* foi recebido.\n\nValor: *{total}*\n\nAvisamos a cada passo. Acompanhe por aqui: {tracking_url}",
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
    dependencies = [("shop", "0074_perfil_fiscal_so_diz_se_tem_st")]

    operations = [migrations.RunPython(forwards, backwards)]
