"""As frases revisadas das notificações ao cliente (revisão do dono, 25/09/2026).

Voz da concierge no feminino, "Oi, Ana!" para abrir, emoji só os da casa, e a
informação que muda de pedido para pedido (hora prevista, motivo) em
``{status_note}``, que nunca fica vazia. O texto vive em
``shopman/shop/notification_copy.py``; esta migração o leva ao banco já semeado.

Mesmo padrão da ``0075``: só troca o campo que ainda está **exatamente** como o
seed gravou; texto reescrito no Admin fica como está.
"""

from django.db import migrations

# (evento, assunto antigo, assunto novo, corpo antigo, corpo novo)
TEXTS = [
    (
        "order_received",
        "Pedido {order_ref_short} recebido",
        "Pedido {order_ref_short} recebido",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}*.\nEstamos conferindo a disponibilidade e avisamos em seguida.\nAcompanhe por aqui: {tracking_url}",
        "Oi{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}*.\nEstamos conferindo a disponibilidade e avisamos em seguida.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_received_outside_hours",
        "Pedido {order_ref_short} recebido",
        "Pedido {order_ref_short} recebido",
        "Olá{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}* fora do nosso horário de atendimento. Vamos processar assim que abrirmos. Total: *{total}*.",
        "Oi{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}* fora do nosso horário. Vamos conferir assim que abrirmos e avisamos por aqui.\n{tracking_url}",
    ),
    (
        "order_accepted",
        "Pedido {order_ref_short} confirmado",
        "Pedido {order_ref_short} confirmado",
        "Seu pedido *{order_ref_short}* está confirmado. Total: *{total}*.\nJá vamos preparar.\nAcompanhe por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* está confirmado. O total é *{total}*. Já vamos preparar.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_preparing",
        "Pedido {order_ref_short} em preparo",
        "Pedido {order_ref_short} em preparo",
        "Estamos preparando seu pedido *{order_ref_short}*.{eta_note}\nAcompanhe por aqui: {tracking_url}",
        "Estamos preparando seu pedido *{order_ref_short}*. {status_note}.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_ready_pickup",
        "Pedido {order_ref_short} pronto para retirada",
        "Pedido {order_ref_short} pronto para retirada",
        "Seu pedido *{order_ref_short}* está pronto e esperando por você no balcão. 🥐\nEndereço e detalhes: {tracking_url}",
        "Seu pedido *{order_ref_short}* está pronto e esperando por você no balcão. ✨\nEndereço e detalhes: {tracking_url}",
    ),
    (
        "order_ready_delivery",
        "Pedido {order_ref_short} pronto — aguardando entregador",
        "Pedido {order_ref_short} pronto, aguardando o entregador",
        "Seu pedido *{order_ref_short}* está pronto e aguardando o entregador.\nAvisamos assim que sair. 📦\nAcompanhe por aqui: {tracking_url}",
        "Seu pedido *{order_ref_short}* está pronto e aguardando o entregador. Avisamos assim que sair.\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "order_delivered",
        "Pedido {order_ref_short} entregue",
        "Pedido {order_ref_short} entregue",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* foi entregue.\n\nEsperamos que tenha gostado! Obrigado pela preferência.",
        "Seu pedido *{order_ref_short}* foi entregue.\nEsperamos que tenha gostado{customer_name_greeting}! Obrigada por nos prestigiar! 💛✨",
    ),
    (
        "order_cancelled",
        "Pedido {order_ref_short} cancelado",
        "Pedido {order_ref_short} cancelado",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* foi cancelado.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
        "Oi{customer_name_greeting}. Seu pedido *{order_ref_short}* foi cancelado. {status_note} Qualquer dúvida, estamos à disposição. 😌\nVeja os detalhes: {tracking_url}",
    ),
    (
        "order_rejected",
        "Pedido {order_ref_short} não confirmado",
        "Pedido {order_ref_short} não confirmado",
        "Olá{customer_name_greeting}! Não conseguimos confirmar o pedido *{order_ref_short}*.{reason_note}\n\nVeja os detalhes do pedido por aqui: {tracking_url}",
        "Oi{customer_name_greeting}. Não conseguimos confirmar seu pedido *{order_ref_short}* desta vez. {status_note} Se houve cobrança, devolvemos o valor. Qualquer dúvida, estamos à disposição. 😌\nVeja os detalhes: {tracking_url}",
    ),
    (
        "preorder_reminder",
        "Lembrete: pedido {order_ref_short} agendado para amanhã",
        "Lembrete: pedido {order_ref_short} agendado para amanhã",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* está agendado para amanhã. Já estamos preparando tudo!\n\nAcompanhe por aqui: {tracking_url}",
        "Oi{customer_name_greeting}! Lembrando que seu pedido *{order_ref_short}* está agendado para amanhã. Vamos preparar tudo com muito carinho. ✨\nAcompanhe por aqui: {tracking_url}",
    ),
    (
        "payment_requested",
        "Pedido {order_ref_short}: pagamento disponível",
        "Pedido {order_ref_short}: falta só o pagamento",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref_short}* está disponível.\n\nPara continuar, pague dentro do prazo: {payment_url}{pix_suffix}",
        "Oi{customer_name_greeting}! Seu pedido *{order_ref_short}* está reservado. Falta só o pagamento: {payment_url}{pix_suffix}",
    ),
    (
        "payment_link_sent",
        "Pedido {order_ref_short}: link de pagamento",
        "Pedido {order_ref_short}: link de pagamento",
        "Olá{customer_name_greeting}! Anotamos seu pedido *{order_ref_short}* — total *{total}*.\n\nPara confirmar, é só pagar por aqui: {checkout_url}{payment_deadline_note}\n\nQualquer coisa, é só responder esta mensagem. 🥖",
        "Oi{customer_name_greeting}! Anotamos seu pedido *{order_ref_short}* ({total}). Pague por aqui para garantir: {checkout_url}{payment_deadline_note}",
    ),
    (
        "payment_confirmed",
        "Pagamento do pedido {order_ref_short} recebido",
        "Pagamento do pedido {order_ref_short} recebido",
        "Olá{customer_name_greeting}! O pagamento do pedido *{order_ref_short}* foi recebido.\n\nValor: *{total}*\n\nAvisamos a cada passo. Acompanhe por aqui: {tracking_url}",
        "Obrigada{customer_name_greeting}! Recebemos o pagamento do seu pedido *{order_ref_short}*. Vamos atualizando você por aqui: {tracking_url}",
    ),
    (
        "payment_reminder",
        "Pedido {order_ref_short} aguarda pagamento",
        "Pedido {order_ref_short} aguarda pagamento",
        "Olá{customer_name_greeting}! Seu pedido *{order_ref_short}* aguarda o pagamento.\n\nConclua por aqui: {payment_url}{pix_suffix}",
        "Oi{customer_name_greeting}! Seu pedido *{order_ref_short}* ainda aguarda o pagamento via Pix.\nPague por aqui: {payment_url}{pix_suffix}",
    ),
    (
        "payment_expired",
        "Pedido {order_ref_short}: reserva liberada",
        "Pedido {order_ref_short}: reserva liberada",
        "Olá{customer_name_greeting}! Não recebemos o pagamento do pedido *{order_ref_short}* dentro do prazo, então liberamos a reserva. Se ainda quiser, é só falar com a gente que refazemos o pedido. 🥖",
        "Oi{customer_name_greeting}. O prazo para pagar o pedido *{order_ref_short}* acabou e liberamos a reserva. Nada foi cobrado.\nPara pedir de novo: {reorder_url}",
    ),
    (
        "payment_failed",
        "Falha ao preparar pagamento do pedido {order_ref_short}",
        "Pedido {order_ref_short}: não conseguimos gerar o pagamento",
        "Olá{customer_name_greeting}! Não conseguimos preparar o pagamento do pedido *{order_ref_short}*.\n\nAcesse {payment_url} para tentar novamente.",
        "Oi{customer_name_greeting}. Não conseguimos gerar o pagamento do seu pedido *{order_ref_short}*.\nTente de novo por aqui: {payment_url}",
    ),
    (
        "payment_refunded",
        "Reembolso do pedido {order_ref_short} processado",
        "Reembolso do pedido {order_ref_short} processado",
        "Olá{customer_name_greeting}! O reembolso do pedido *{order_ref_short}* foi processado.\n\nValor: *{total}*",
        "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de *{total}*, foi processado. Qualquer dúvida, estamos à disposição.",
    ),
    (
        "waitlist_available",
        "Sua fornada saiu — confirme o pedido {order_ref_short}",
        "Sua fornada saiu: confirme o pedido {order_ref_short}",
        "Olá{customer_name_greeting}! Sua fornada saiu 🥐\n\nConfirme o pedido *{order_ref_short}* para garantir o seu: {tracking_url}",
        "Oba! 💛✨ Acabou de sair do forno{customer_name_greeting}! Confirme o pedido *{order_ref_short}* para garantir: {tracking_url}",
    ),
    (
        "waitlist_released",
        "Pedido {order_ref_short}: a vaga passou a vez",
        "Pedido {order_ref_short}: reserva liberada",
        "Olá{customer_name_greeting}! O prazo de confirmação do pedido *{order_ref_short}* passou e liberamos a sua vaga.\n\nNada foi cobrado, e é só entrar na fila da próxima fornada: {tracking_url}",
        "Oi{customer_name_greeting}. O prazo para confirmar o pedido *{order_ref_short}* acabou e liberamos a reserva. Nada foi cobrado.\nPara pedir de novo: {tracking_url}",
    ),
    (
        "loyalty_earned",
        "Você ganhou pontos de fidelidade!",
        "Você ganhou pontos de fidelidade!",
        "Olá{customer_name_greeting}! Você ganhou pontos de fidelidade com o pedido *{order_ref_short}*.\n\nSeu saldo fica aqui: {account_url}",
        "Parabéns{customer_name_greeting}! 💛✨ Você ganhou pontos de fidelidade com o pedido *{order_ref_short}*.\nVeja seu saldo: {account_url}",
    ),
    (
        "access_link",
        "Seu acesso à loja",
        "Seu acesso à loja",
        "Olá{customer_name_greeting}! Aqui está seu acesso à loja:\n{access_url}{cart_note}\n\nO link é só seu e vale por poucos minutos.",
        "Oi{customer_name_greeting}! Use o link para entrar na loja: {access_url}\n{cart_note}Válido por 5 min.",
    ),
    (
        "stock_arrived",
        "{product_name} disponível",
        "{product_name} disponível",
        "Olá{customer_name_greeting}! O {product_name} que você pediu para acompanhar está disponível: {action_url}{management_note}",
        "Oi{customer_name_greeting}! Você pediu pra avisar quando *{product_name}* estivesse disponível e agora está! 💛✨{reserve_note}{deadline_note}\n{cta} {action_url}{management_note}",
    ),
    (
        "production_ready",
        "{product_name} saiu do forno",
        "{product_name} saiu do forno",
        "Olá{customer_name_greeting}! O {product_name} acabou de sair do forno: {action_url}{management_note}",
        "Olha só o que acabou de sair do forno: *{product_name}*! {availability_note}.\nGaranta o seu: {action_url}{management_note}",
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
    dependencies = [("shop", "0077_mensagem_chama_pedido_pelo_final")]

    operations = [migrations.RunPython(forwards, backwards)]
