"""
Email notification adapter — sends via Django email backend.

Tries Django template at notifications/email/{template}.html,
falls back to inline text templates.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SUBJECT_TEMPLATES: dict[str, str] = {
    "order_received": "Recebemos seu pedido {order_ref}",
    "order_accepted": "Pedido {order_ref} confirmado",
    "order_preparing": "Pedido {order_ref} em preparo",
    "order_ready_pickup": "Pedido {order_ref} pronto para retirada",
    "order_ready_delivery": "Pedido {order_ref} pronto para envio",
    "order_dispatched": "Pedido {order_ref} saiu para entrega",
    "order_delivered": "Pedido {order_ref} entregue",
    "order_cancelled": "Pedido {order_ref} cancelado",
    "order_rejected": "Pedido {order_ref} não confirmado",
    "payment_confirmed": "Pagamento do pedido {order_ref} confirmado",
    "payment_requested": "Pedido {order_ref}: pagamento liberado",
    "payment_link_sent": "Pedido {order_ref}: link de pagamento",
    "payment_expired": "Pedido {order_ref}: reserva liberada",
    "payment_failed": "Falha ao preparar pagamento do pedido {order_ref}",
    "preorder_reminder": "Lembrete: pedido {order_ref} agendado para amanhã",
    "stock_alert": "Alerta de estoque: {sku}",
    "stock_arrived": "Boa notícia: {product_name} chegou",
    "production_ready": "Saiu do forno agora: {product_name}",
    "announcement_published": "Novidade na padaria",
    "purchase_request": "Pedido de compra {purchase_ref} — {shop_name}",
    "purchase_receipt_rejected": "Devolução de recebimento {receipt_ref} — {shop_name}",
}

BODY_TEMPLATES: dict[str, str] = {
    "order_received": (
        "Olá{customer_name_greeting}!\n\n"
        "Recebemos seu pedido {order_ref}.\n\n"
        "O estabelecimento vai conferir a disponibilidade e avisaremos a próxima etapa.\n"
    ),
    "order_accepted": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi confirmado.\n\n"
        "Total: {total}\n\nObrigado pela preferência!\n"
    ),
    "order_preparing": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} está em preparo.\n\n"
        "Avisaremos quando estiver pronto!\n"
    ),
    "order_ready_pickup": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} está pronto para retirada.\n\n"
        "Venha buscar. Obrigado!\n"
    ),
    "order_ready_delivery": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} está pronto e será enviado em breve.\n\n"
        "Obrigado!\n"
    ),
    "order_dispatched": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} saiu para entrega."
        "{courier_tracking_suffix}\n\n"
        "Quando receber, é só confirmar por aqui: {tracking_url}\n"
    ),
    "order_delivered": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi entregue.\n\nObrigado pela preferência!\n"
    ),
    "order_cancelled": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi cancelado.{reason_note}\n\n"
        "Veja os detalhes do pedido por aqui: {tracking_url}\n"
    ),
    "order_rejected": (
        "Olá{customer_name_greeting}!\n\n"
        "O estabelecimento não conseguiu confirmar o pedido {order_ref}.{reason_note}\n\n"
        "Veja os detalhes do pedido por aqui: {tracking_url}\n"
    ),
    "payment_confirmed": (
        "Olá{customer_name_greeting}!\n\n"
        "O pagamento do pedido {order_ref} foi confirmado.\n\n"
        "Avisamos a cada passo. Acompanhe por aqui: {tracking_url}\n\n"
        "Obrigado!\n"
    ),
    "payment_requested": (
        "Olá{customer_name_greeting}!\n\n"
        "Conferimos a disponibilidade do pedido {order_ref}.\n\n"
        "Agora falta o pagamento. Acesse: {payment_url}\n\n"
        "{pix_suffix}\n"
    ),
    "payment_link_sent": (
        "Olá{customer_name_greeting}!\n\n"
        "Anotamos seu pedido {order_ref}. Total: {total}.\n\n"
        "Para confirmar, conclua o pagamento por aqui:\n"
        "{checkout_url}{payment_deadline_note}\n\n"
        "Qualquer dúvida, é só responder este e-mail.\n"
    ),
    "payment_expired": (
        "Olá{customer_name_greeting}!\n\n"
        "Não recebemos o pagamento do pedido {order_ref} dentro do prazo, "
        "então liberamos a reserva.\n\n"
        "Se ainda quiser, é só falar com a gente que refazemos o pedido.\n"
    ),
    "payment_failed": (
        "Olá{customer_name_greeting}!\n\n"
        "Não conseguimos preparar o pagamento do pedido {order_ref}.\n\n"
        "Acesse {payment_url} para tentar novamente.\n"
    ),
    "stock_alert": (
        "Alerta de estoque\n\n"
        "Produto: {sku}\nQuantidade atual: {available}\n"
        "Mínimo configurado: {min_quantity}\n\nProvidencie reposição.\n"
    ),
    "preorder_reminder": (
        "Lembrete: seu pedido {order_ref} está agendado para amanhã.\n"
        "Já estamos preparando tudo!"
    ),
    "stock_arrived": (
        "Boa notícia!\n\n"
        "{product_name} chegou.{reserve_note}{deadline_note}\n\n"
        "{cta} {action_url}\n"
    ),
    "production_ready": (
        "Saiu do forno agora!\n\n"
        "{product_name} acabou de ficar pronto.\n\n"
        "{cta} {action_url}\n"
    ),
    "announcement_published": "{body}\n\n{cta} {action_url}\n",
    "purchase_request": (
        "Olá, {supplier_greeting}!\n\n"
        "Aqui é da {shop_name}. Precisamos repor um item e gostaríamos de "
        "fechar com vocês:\n\n"
        "{lines_text}\n\n"
        "Pelo nosso cadastro isso fica em torno de {estimated_total} — o valor "
        "que vale é o de vocês.\n"
        "Entrega desejada: {requested_delivery_label}\n"
        "{operator_note}\n"
        "Pode confirmar disponibilidade, prazo e valor final?\n\n"
        "Obrigado!\n"
        "{shop_name} — pedido {purchase_ref}\n"
    ),
    "purchase_receipt_rejected": (
        "Recebimento recusado/devolvido.\n\n"
        "Fornecedor: {supplier_name}\n"
        "Documento: {document_ref}\n"
        "Motivo: {reason}\n\n"
        "{lines_text}"
        "{supplier_contact_note}\n"
    ),
}


def _render_html(template: str, context: dict[str, Any]) -> str | None:
    """Try to render a Django HTML template for this event."""
    from shopman.shop.adapters._notification_templates import derive_context

    template_name = f"notifications/email/{template}.html"
    try:
        return render_to_string(template_name, derive_context(context))
    except TemplateDoesNotExist:
        return None


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send an email notification.

    Args:
        recipient: Email address.
        template: Event template name (e.g. "order_accepted").
        context: Template variables.

    Returns:
        True if sent successfully, False otherwise.
    """
    from shopman.shop.adapters._notification_templates import (
        db_template,
        derive_context,
        render_message,
        render_template,
    )

    # As chaves auxiliares (`customer_name_greeting`, `total`, sufixos) vêm do ponto
    # único compartilhado com SMS e WhatsApp — o assunto precisa delas explicitamente
    # porque `render_template` é primitiva crua; o corpo já deriva dentro de
    # `render_message`.
    ctx = derive_context(context)

    # Assunto e corpo editados no Admin (NotificationTemplate) valem para
    # e-mail também; os dicts hardcoded são o fallback. render_template protege
    # contra chave malformada no template do Admin (não suprime o e-mail).
    db_subject, _ = db_template(template)
    subject_tpl = db_subject or SUBJECT_TEMPLATES.get(template, f"Notificacao: {template}")
    subject = render_template(subject_tpl, ctx)

    subject_prefix = config.get("subject_prefix", "")
    if subject_prefix:
        subject = f"{subject_prefix} {subject}"

    body = render_message(template, ctx, BODY_TEMPLATES)

    try:
        html_body = _render_html(template, context or {})
    except Exception:
        logger.debug("email: HTML render failed for template=%s, sending plain text", template, exc_info=True)
        html_body = None

    from_email = config.get("from_email") or getattr(
        settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info("Email sent: %s -> %s", template, recipient)
        return True
    except Exception:
        logger.exception("Email error sending to %s", recipient)
        return False


#: Backends que NÃO entregam a ninguém. O de console imprime em stdout, o
#: locmem guarda numa lista, o dummy descarta — todos "com sucesso".
_BACKENDS_INERTES = ("console", "locmem", "dummy")

#: Domínios de remetente que NÃO existem no DNS público. `.local` é TLD
#: reservado para mDNS (RFC 6762) e `example.*` é reservado para documentação
#: (RFC 2606) — nenhum dos dois tem SPF, DKIM ou DMARC possível, então o
#: receptor rejeita ou joga em spam.
_DOMINIOS_DE_REMETENTE_INERTES = (".local", "example.com", "example.org", "example.net")


def _remetente_entrega(from_email: str) -> bool:
    """O endereço de remetente é capaz de sair da casa?

    Um backend SMTP vivo com remetente `noreply@shopman.local` é o mesmo
    fail-open do backend de console, por outra porta: o relay ACEITA a mensagem,
    `send_mail` não levanta, `send()` devolve ``True`` — e esse ``True``
    interrompe a cadeia de fallback antes do SMS e do WhatsApp. O cliente não
    recebe o link de pagamento, e o log diz "Email sent".
    """
    dominio = from_email.rpartition("@")[2].strip().lower().rstrip(">")
    if not dominio:
        return False
    return not any(
        dominio == mau or dominio.endswith(mau)
        for mau in _DOMINIOS_DE_REMETENTE_INERTES
    )


def is_available(recipient: str | None = None, **config) -> bool:
    """Este canal ENTREGA de verdade?

    ⚠️ Isto já foi ``bool(EMAIL_HOST or EMAIL_BACKEND)``, e era um fail-open
    caro: ``EMAIL_BACKEND`` tem string por default (o de console), então a
    expressão era **incondicionalmente True**. O backend de console imprime em
    stdout e não levanta, ``send()`` devolvia ``True``, e esse ``True``
    **curto-circuitava a cadeia inteira de fallback** em
    ``services/notification.py``: SMS e WhatsApp nunca eram tentados.

    O resultado é o pior possível para quem espera: o cliente NÃO recebe o link
    de pagamento, o fornecedor NÃO recebe o pedido de compra, e o log diz
    "Email sent". Um canal inerte tem que devolver ``False`` para a cadeia
    seguir — é o que ``notification_sms.is_available`` já faz certo.
    """
    backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    if any(inerte in backend for inerte in _BACKENDS_INERTES):
        return False
    # Um backend SMTP sem host não fala com ninguém — falha na primeira conexão.
    if "smtp" in backend and not str(getattr(settings, "EMAIL_HOST", "") or "").strip():
        return False
    # Remetente que não existe no DNS = canal inerte, mesmo com SMTP de pé.
    remetente = str(
        config.get("from_email") or getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    ).strip()
    if not _remetente_entrega(remetente):
        logger.warning(
            "E-mail indisponível: remetente %r não é entregável (domínio reservado ou ausente). "
            "Defina DEFAULT_FROM_EMAIL com um domínio real; a cadeia segue para SMS/WhatsApp.",
            remetente,
        )
        return False
    return bool(backend)
