"""Entrega do link de acesso pelo WhatsApp — pela CASA, não pelo ManyChat.

O desenho anterior devolvia o `access_url` no corpo da resposta e confiava no
fluxo do ManyChat para gravá-lo num campo personalizado (Response Mapping) e
montar a mensagem com o botão. Custou caro: em 01 e 02/09, quatro links foram
criados e **nenhum** foi usado (`used_at` nulo nos quatro). O backend cumpria a
parte dele, a mensagem não chegava, e o cliente via "não consegui gerar o link".

O ponto é que a montagem da mensagem morava fora daqui, num lugar sem log, sem
teste e sem quem revisasse. Agora a casa manda a própria mensagem: o fluxo do
ManyChat volta a ser gatilho + External Request, e a copy passa a viver no
`NotificationTemplate` do Admin como todas as outras da loja.

A janela de 24h do WhatsApp está aberta por construção — a pessoa acabou de
mandar mensagem, é isso que dispara o fluxo. Não é envio iniciado pela loja.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

EVENT = "access_link"


def connect() -> None:
    from shopman.doorman.signals import access_link_created

    access_link_created.connect(on_access_link_created, weak=False)


def on_access_link_created(sender, token=None, customer=None, url="", **kwargs) -> None:
    """Manda o link para quem pediu — e nunca derruba a criação do token.

    O login não pode falhar porque o envio falhou: o `access_url` continua na
    resposta, então um fluxo configurado à moda antiga segue funcionando. Mas se
    o envio falhar, isso GRITA: é a diferença entre "o cliente desistiu" e "a
    mensagem nunca saiu", que foi exatamente o que não se conseguiu distinguir.
    """
    metadata = getattr(token, "metadata", None) or {}
    if metadata.get("deliver") != "manychat":
        return

    recipient = getattr(customer, "phone", "") or ""
    if not url or not recipient:
        logger.error(
            "access_link.delivery_no_recipient url=%s tem_telefone=%s — o link foi criado "
            "e não há como entregá-lo",
            bool(url), bool(recipient),
        )
        return

    from shopman.shop.notifications import notify

    context = {
        "access_url": url,
        "customer_name": getattr(customer, "name", "") or "",
        # Sufixo auto-suprimível (padrão da casa): some limpo quando não há sacola.
        "cart_note": (
            "\nSua sacola veio junto." if metadata.get("cart_session_key") else ""
        ),
    }

    try:
        result = notify(event=EVENT, recipient=recipient, context=context, backend="manychat")
    except Exception:
        logger.exception("access_link.delivery_failed recipient=%s", recipient[:6])
        return

    if result.success:
        logger.info("access_link.delivered via manychat")
    else:
        logger.error(
            "access_link.delivery_rejected erro=%s — o cliente NÃO recebeu o link",
            result.error,
        )
