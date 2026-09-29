"""Nas mensagens ao cliente, o pedido é chamado pelo final do ref (decisão do dono, 25/09/2026).

"Seu pedido A47", não "Seu pedido NB-260925-A47": o final é o que o balcão fala e o
que o card mostra em destaque, e é único no dia entre todos os canais
(``orderman.ids.generate_order_ref``). O link continua com o ref completo.

Mesmo padrão da ``0075``: só troca o campo que ainda está **exatamente** como o seed
gravou; texto reescrito no Admin fica como está.
"""

from django.db import migrations

# (evento, assunto antigo, assunto novo, corpo antigo, corpo novo)
TEXTS = [
    (
        "order_received",
        "Pedido {order_ref} recebido",
        "Pedido {order_ref_short} recebido",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}*.\nEstamos conferindo a disponibilidade e avisamos em seguida.\nAcompanhe por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}*.\nEstamos conferindo a disponibilidade e avisamos em seguida.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_received_outside_hours",
        "Pedido {order_ref} recebido",
        "Pedido {order_ref_short} recebido",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref}* fora do nosso horário de atendimento. Vamos processar assim que abrirmos. Total: *{total}*.",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}* fora do nosso horário de atendimento. Vamos processar assim que abrirmos. Total: *{total}*.",
    ),
    (
        "order_accepted",
        "Pedido {order_ref} confirmado",
        "Pedido {order_ref_short} confirmado",
        "Seu pedido *{order_ref}* está confirmado. Total: *{total}*.\nJá vamos preparar.\nAcompanhe por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* está confirmado. Total: *{total}*.\nJá vamos preparar.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_preparing",
        "Pedido {order_ref} em preparo",
        "Pedido {order_ref_short} em preparo",
        "Estamos preparando seu pedido *{order_ref}*.{eta_note}\nAcompanhe por aqui: {tracking_url}",
        "Estamos preparando seu pedido *{order_ref_short}*.{eta_note}\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_ready_pickup",
        "Pedido {order_ref} pronto para retirada",
        "Pedido {order_ref_short} pronto para retirada",
        "Seu pedido *{order_ref}* está pronto e esperando por você no balcão. 🥐\nEndereço e detalhes: {tracking_url}",
        "Seu pedido *{order_ref_short}* está pronto e esperando por você no balcão. 🥐\nEndereço e detalhes: {tracking_url}",
    ),
    (
        "order_ready_delivery",
        "Pedido {order_ref} pronto — aguardando entregador",
        "Pedido {order_ref_short} pronto — aguardando entregador",
        "Seu pedido *{order_ref}* está pronto e aguardando o entregador.\nAvisamos assim que sair. 📦\nAcompanhe por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* está pronto e aguardando o entregador.\nAvisamos assim que sair. 📦\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_dispatched",
        "Pedido {order_ref} saiu para entrega",
        "Pedido {order_ref_short} saiu para entrega",
        "Seu pedido *{order_ref}* saiu para entrega.{courier_tracking_suffix}\nQuando receber, é só confirmar por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* saiu para entrega.{courier_tracking_suffix}\nQuando receber, é só confirmar por aqui: {tracking_url}",
    ),
    (
        "order_delivered",
        "Pedido {order_ref} entregue",
        "Pedido {order_ref_short} entregue",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* foi entregue.\n\nEsperamos que tenha gostado! Obrigado pela preferência.",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* foi entregue.\n\nEsperamos que tenha gostado! Obrigado pela preferência.",
    ),
    (
        "order_cancelled",
        "Pedido {order_ref} cancelado",
        "Pedido {order_ref_short} cancelado",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* foi cancelado.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* foi cancelado.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
    ),
    (
        "order_rejected",
        "Pedido {order_ref} não confirmado",
        "Pedido {order_ref_short} não confirmado",
        "Olá{customer_name_greeting}! Não conseguimos confirmar o pedido *{order_ref}*.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! Não conseguimos confirmar o pedido *{order_ref_short}*.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
    ),
    (
        "payment_requested",
        "Pedido {order_ref}: pagamento disponível",
        "Pedido {order_ref_short}: pagamento disponível",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref}* está disponível.\n\nPara continuar, pague dentro do prazo: {payment_url}{pix_suffix}",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref_short}* está disponível.\n\nPara continuar, pague dentro do prazo: {payment_url}{pix_suffix}",
    ),
    (
        "payment_confirmed",
        "Pagamento do pedido {order_ref} recebido",
        "Pagamento do pedido {order_ref_short} recebido",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref}* foi recebido.\n\nValor: *{total}*\n\nAvisamos a cada passo. Acompanhe por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref_short}* foi recebido.\n\nValor: *{total}*\n\nAvisamos a cada passo. Acompanhe por aqui: {tracking_url}",
    ),
    (
        "payment_link_sent",
        "Pedido {order_ref}: link de pagamento",
        "Pedido {order_ref_short}: link de pagamento",
        "Olá{customer_name_greeting}! Anotamos seu pedido *{order_ref}* — total *{total}*.\n\nPara confirmar, é só pagar por aqui: {checkout_url}{payment_deadline_note}\n\nQualquer coisa, é só responder esta mensagem. 🥖",
        "Olá{customer_name_greeting}! Anotamos seu pedido *{order_ref_short}* — total *{total}*.\n\nPara confirmar, é só pagar por aqui: {checkout_url}{payment_deadline_note}\n\nQualquer coisa, é só responder esta mensagem. 🥖",
    ),
    (
        "payment_expired",
        "Pedido {order_ref}: reserva liberada",
        "Pedido {order_ref_short}: reserva liberada",
        "Olá{customer_name_greeting}! Não recebemos o pagamento do pedido *{order_ref}* dentro do prazo, então liberamos a reserva. Se ainda quiser, é só falar com a gente que refazemos o pedido. 🥖",
        "Olá{customer_name_greeting}! Não recebemos o pagamento do pedido *{order_ref_short}* dentro do prazo, então liberamos a reserva. Se ainda quiser, é só falar com a gente que refazemos o pedido. 🥖",
    ),
    (
        "payment_failed",
        "Falha ao preparar pagamento do pedido {order_ref}",
        "Falha ao preparar pagamento do pedido {order_ref_short}",
        "Olá{customer_name_greeting}! Não conseguimos preparar o pagamento do pedido *{order_ref}*.\n\nAcesse {payment_url} para tentar novamente.",
        "Olá{customer_name_greeting}! Não conseguimos preparar o pagamento do pedido *{order_ref_short}*.\n\nAcesse {payment_url} para tentar novamente.",
    ),
    (
        "payment_refunded",
        "Reembolso do pedido {order_ref} processado",
        "Reembolso do pedido {order_ref_short} processado",
        "Olá{customer_name_greeting}! O reembolso do pedido *{order_ref}* foi processado.\n\nValor: *{total}*",
        "Olá{customer_name_greeting}! O reembolso do pedido *{order_ref_short}* foi processado.\n\nValor: *{total}*",
    ),
    (
        "loyalty_earned",
        "Você ganhou pontos de fidelidade!",
        "Você ganhou pontos de fidelidade!",
        "Olá{customer_name_greeting}! Você ganhou pontos de fidelidade com o pedido *{order_ref}*.\n\nSeu saldo fica aqui: {account_url}",
        "Olá{customer_name_greeting}! Você ganhou pontos de fidelidade com o pedido *{order_ref_short}*.\n\nSeu saldo fica aqui: {account_url}",
    ),
    (
        "waitlist_available",
        "Sua fornada saiu — confirme o pedido {order_ref}",
        "Sua fornada saiu — confirme o pedido {order_ref_short}",
        "Olá{customer_name_greeting}! Sua fornada saiu 🥐\n\nConfirme o pedido *{order_ref}* para garantir o seu: {tracking_url}",
        "Olá{customer_name_greeting}! Sua fornada saiu 🥐\n\nConfirme o pedido *{order_ref_short}* para garantir o seu: {tracking_url}",
    ),
    (
        "waitlist_released",
        "Pedido {order_ref}: a vaga passou a vez",
        "Pedido {order_ref_short}: a vaga passou a vez",
        "Olá{customer_name_greeting}! O prazo de confirmação do pedido *{order_ref}* passou e liberamos a sua vaga.\n\nNada foi cobrado, e é só entrar na fila da próxima fornada: {tracking_url}",
        "Olá{customer_name_greeting}! O prazo de confirmação do pedido *{order_ref_short}* passou e liberamos a sua vaga.\n\nNada foi cobrado, e é só entrar na fila da próxima fornada: {tracking_url}",
    ),
    (
        "preorder_reminder",
        "Lembrete: pedido {order_ref} agendado para amanhã",
        "Lembrete: pedido {order_ref_short} agendado para amanhã",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* está agendado para amanhã. Já estamos preparando tudo!\n\nAcompanhe por aqui: {tracking_url}",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* está agendado para amanhã. Já estamos preparando tudo!\n\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "payment_reminder",
        "Pedido {order_ref} aguarda pagamento",
        "Pedido {order_ref_short} aguarda pagamento",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref}* aguarda o pagamento.\n\nConclua por aqui: {payment_url}{pix_suffix}",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* aguarda o pagamento.\n\nConclua por aqui: {payment_url}{pix_suffix}",
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
    dependencies = [("shop", "0076_saiu_para_entrega_sem_cumprimento")]

    operations = [migrations.RunPython(forwards, backwards)]
