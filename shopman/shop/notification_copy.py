"""O texto dos avisos ao cliente — fonte única.

Revisão do dono, 25/09/2026 (doc "Revisão das frases das notificações"). O seed
grava estes textos no Admin (``NotificationTemplate``), e os fallbacks de cada canal
(ManyChat, e-mail, SMS) saem daqui também: antes eram quatro cópias à mão, e cada
revisão de voz esquecia uma delas.

Regras da voz, para quem for mexer:

- Voz da concierge, no FEMININO ("Obrigada").
- Abre com ``Oi{customer_name_greeting}!`` ("Oi, Ana!" / "Oi!"); notícia ruim com
  ponto ("Oi, Ana."). Nunca começar com o nome solto: sem nome, a frase quebra.
- O pedido é chamado pelo final do ref (``{order_ref_short}``); o link leva o ref.
- Emoji só os da casa: 💛✨, e 😌 / 😊 de vez em quando.
- ``{status_note}`` é a informação do pedido que muda (hora prevista, motivo) e
  NUNCA fica vazia: sem o dado, entra uma frase-padrão
  (``services/notification._status_note``). É assim que ela cabe no template do
  WhatsApp, que não aceita variável vazia.

O WhatsApp fora da janela de 24h fala pelo template aprovado na Meta, que é outro
texto (sem as linhas de link, que lá viram botão):
``docs/reference/whatsapp-templates-meta.md``.
"""

from __future__ import annotations

import unicodedata

CUSTOMER_COPY: dict[str, dict[str, str]] = {
    # ── Ciclo do pedido ──────────────────────────────────────────────────
    "order_received": {
        "subject": "Pedido {order_ref_short} recebido",
        "body": (
            "Oi{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}*.\n"
            "Estamos conferindo a disponibilidade e avisamos em seguida.\n"
            "Acompanhe por aqui: {tracking_url}"
        ),
    },
    "order_received_outside_hours": {
        "subject": "Pedido {order_ref_short} recebido",
        "body": (
            "Oi{customer_name_greeting}! Recebemos seu pedido *{order_ref_short}* fora do nosso horário. "
            "Vamos conferir assim que abrirmos e avisamos por aqui.\n"
            "{tracking_url}"
        ),
    },
    # Só sai quando não falta nada (quem ainda paga recebe o payment_requested).
    "order_accepted": {
        "subject": "Pedido {order_ref_short} confirmado",
        "body": (
            "Seu pedido *{order_ref_short}* está confirmado. O total é *{order_total_display}*. "
            "Vamos preparar com todo carinho. ✨\n"
            "Acompanhe por aqui: {tracking_url}"
        ),
    },
    # {status_note} vem SEM ponto final: o ponto é do texto, porque o template da Meta
    # não pode terminar em variável.
    "order_preparing": {
        "subject": "Pedido {order_ref_short} em preparo",
        "body": (
            "Estamos preparando seu pedido *{order_ref_short}*. {status_note}.\nAcompanhe por aqui: {tracking_url}"
        ),
    },
    "order_ready_pickup": {
        "subject": "Pedido {order_ref_short} pronto para retirada",
        "body": (
            "Seu pedido *{order_ref_short}* está pronto e esperando por você no balcão. ✨\n"
            "Endereço e detalhes: {tracking_url}"
        ),
    },
    "order_ready_delivery": {
        "subject": "Pedido {order_ref_short} pronto, aguardando o entregador",
        "body": (
            "Seu pedido *{order_ref_short}* está pronto e aguardando o entregador. Avisamos assim que sair.\n"
            "Acompanhe por aqui: {tracking_url}"
        ),
    },
    "order_dispatched": {
        "subject": "Pedido {order_ref_short} saiu para entrega",
        "body": (
            "Seu pedido *{order_ref_short}* saiu para entrega.{courier_tracking_suffix}\n"
            "Quando receber, é só confirmar por aqui: {tracking_url}"
        ),
    },
    "order_delivered": {
        "subject": "Pedido {order_ref_short} entregue",
        "body": (
            "Seu pedido *{order_ref_short}* foi entregue.\n"
            "Esperamos que tenha gostado{customer_name_greeting}! Obrigada por nos prestigiar! 💛✨"
        ),
    },
    "order_cancelled": {
        "subject": "Pedido {order_ref_short} cancelado",
        "body": (
            "Oi{customer_name_greeting}. Seu pedido *{order_ref_short}* foi cancelado. {status_note} "
            "Qualquer dúvida, estamos à disposição. 😌\n"
            "Veja os detalhes: {tracking_url}"
        ),
    },
    # "Se houve cobrança": quem pagou no checkout e teve o pedido recusado foi
    # cobrado e recebe estorno; quem ia pagar depois, não. A frase serve aos dois.
    "order_rejected": {
        "subject": "Pedido {order_ref_short} não confirmado",
        "body": (
            "Oi{customer_name_greeting}. Não conseguimos confirmar seu pedido *{order_ref_short}* desta vez. "
            "{status_note} Se houve cobrança, devolvemos o valor. "
            "Qualquer dúvida, estamos à disposição. 😌\n"
            "Veja os detalhes: {tracking_url}"
        ),
    },
    "preorder_reminder": {
        "subject": "Lembrete: pedido {order_ref_short} agendado para amanhã",
        "body": (
            "Oi{customer_name_greeting}! Lembrando que seu pedido *{order_ref_short}* está agendado para amanhã. "
            "Vamos preparar com todo carinho. ✨\n"
            "Acompanhe por aqui: {tracking_url}"
        ),
    },
    "fiscal_note_ready": {
        "subject": "Nota fiscal do pedido {order_ref_short}",
        "body": "A nota fiscal do pedido *{order_ref_short}* está disponível: {danfe_url}{fiscal_test_note}",
    },
    # ── Pagamento ────────────────────────────────────────────────────────
    # Sai no lugar do order_accepted quando a loja confere antes de o cliente pagar.
    "payment_requested": {
        "subject": "Pedido {order_ref_short}: falta só o pagamento",
        "body": (
            "Oi{customer_name_greeting}! Seu pedido *{order_ref_short}* está reservado. "
            "Falta só o pagamento: {payment_url}{pix_suffix}"
        ),
    },
    # Pedido remoto anotado no PDV: a venda fechou e o cliente paga pelo link.
    "payment_link_sent": {
        "subject": "Pedido {order_ref_short}: link de pagamento",
        "body": (
            "Oi{customer_name_greeting}! Anotamos seu pedido *{order_ref_short}* no valor de *{order_total_display}*. "
            "Pague por aqui para garantir: {checkout_url}{payment_deadline_note}"
        ),
    },
    "payment_confirmed": {
        "subject": "Pagamento do pedido {order_ref_short} recebido",
        "body": (
            "Obrigada{customer_name_greeting}! Recebemos o pagamento do seu pedido *{order_ref_short}*. "
            "Vamos atualizando você por aqui: {tracking_url}"
        ),
    },
    "payment_reminder": {
        "subject": "Pedido {order_ref_short} aguarda pagamento",
        "body": (
            "Oi{customer_name_greeting}! Seu pedido *{order_ref_short}* ainda aguarda o pagamento via Pix.\n"
            "Pague por aqui: {payment_url}{pix_suffix}"
        ),
    },
    # "Nada foi cobrado" é sempre verdade aqui: o prazo venceu sem pagamento.
    "payment_expired": {
        "subject": "Pedido {order_ref_short}: reserva liberada",
        "body": (
            "Oi{customer_name_greeting}. O prazo para pagar o pedido *{order_ref_short}* acabou "
            "e liberamos a reserva. Nada foi cobrado.\n"
            "Para pedir de novo: {reorder_url}"
        ),
    },
    "payment_failed": {
        "subject": "Pedido {order_ref_short}: não conseguimos gerar o pagamento",
        "body": (
            "Oi{customer_name_greeting}. Não conseguimos gerar o pagamento do seu pedido *{order_ref_short}*.\n"
            "Tente de novo por aqui: {payment_url}"
        ),
    },
    "payment_refunded": {
        "subject": "Reembolso do pedido {order_ref_short} processado",
        "body": (
            "Oi{customer_name_greeting}! O reembolso do pedido *{order_ref_short}*, no valor de *{order_total_display}*, "
            "foi processado. Qualquer dúvida, estamos à disposição."
        ),
    },
    # ── Fila de espera, fidelidade, acesso e produto ─────────────────────
    "waitlist_available": {
        "subject": "Sua fornada saiu: confirme o pedido {order_ref_short}",
        "body": (
            "Oba! 💛✨ Acabou de sair do forno{customer_name_greeting}! "
            "Confirme o pedido *{order_ref_short}* para garantir: {tracking_url}"
        ),
    },
    "waitlist_released": {
        "subject": "Pedido {order_ref_short}: reserva liberada",
        "body": (
            "Oi{customer_name_greeting}. O prazo para confirmar o pedido *{order_ref_short}* acabou "
            "e liberamos a reserva. Nada foi cobrado.\n"
            "Para pedir de novo: {tracking_url}"
        ),
    },
    "loyalty_earned": {
        "subject": "Você ganhou pontos de fidelidade!",
        "body": (
            "Parabéns{customer_name_greeting}! 💛✨ Você ganhou pontos de fidelidade "
            "com o pedido *{order_ref_short}*.\n"
            "Veja seu saldo: {account_url}"
        ),
    },
    # Sempre resposta a uma mensagem que a pessoa acabou de mandar: dentro da janela
    # de 24h, sem template da Meta. `{cart_note}` termina em espaço (divide a linha).
    "access_link": {
        "subject": "Seu acesso à loja",
        "body": "Oi{customer_name_greeting}! Use o link para entrar na loja: {access_url}\n{cart_note}Válido por 5 min.",
    },
    # Login que começou no SITE: a mensagem da pessoa já fez a aba de lá entrar. O link
    # é reserva (se ela não achar o caminho de volta), e o "Não foi você?" é a defesa
    # contra quem pede a alguém que envie a mensagem com o código dele.
    "access_link_site": {
        "subject": "Você entrou na loja",
        "body": (
            "Pronto{customer_name_greeting}! Pode voltar ao site: você já entrou{origin_note}. 💛\n"
            "Se o site não abrir sozinho, toque aqui: {access_url}\n"
            "Não foi você? Encerre este acesso: {revoke_url}"
        ),
    },
    # Dois usos: o "Me avise" (sem reserva, CTA "Garanta o seu:") e a reserva que a
    # loja separou (`handlers/_stock_receivers`: "Sua reserva está garantida.", prazo
    # para confirmar, CTA "Finalize seu pedido:"). As notas começam com espaço e
    # somem vazias no primeiro caso.
    "stock_arrived": {
        "subject": "{product_name} disponível",
        "body": (
            "Oi{customer_name_greeting}! Você pediu pra avisar quando *{product_name}* estivesse disponível "
            "e agora está! 💛✨{reserve_note}{deadline_note}\n"
            "{cta} {action_url}{management_note}"
        ),
    },
    # `{availability_note}` nunca vem vazia e vem SEM ponto final (o ponto é daqui:
    # o template da Meta não termina em variável). services/availability_copy.py.
    "production_ready": {
        "subject": "{product_name} saiu do forno",
        "body": (
            "Olha só o que acabou de sair do forno: *{product_name}*! {availability_note}.\n"
            "Garanta já o seu: {action_url}{management_note}"
        ),
    },
}


def plain_bodies() -> dict[str, str]:
    """Os corpos sem o `*negrito*` do WhatsApp — para o e-mail."""
    return {event: copy["body"].replace("*", "") for event, copy in CUSTOMER_COPY.items()}


def subjects() -> dict[str, str]:
    return {event: copy["subject"] for event, copy in CUSTOMER_COPY.items()}


def sms_bodies() -> dict[str, str]:
    """Os corpos em ASCII: acento fora do GSM-7 força UCS-2 e dobra o custo do SMS.

    Só o fallback. O texto do Admin, que vale quando existe, segue acentuado.
    """
    return {event: _gsm_ascii(copy["body"].replace("*", "")) for event, copy in CUSTOMER_COPY.items()}


def _gsm_ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(ch for ch in decomposed if ord(ch) < 128)
    # Emoji some por inteiro; o espaço que o antecedia não fica pendurado.
    return "\n".join(" ".join(line.split()) for line in ascii_only.split("\n"))
