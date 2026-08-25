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
    "payment_expired": "Pagamento do pedido {order_ref} expirado",
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
        "Acompanhe pelo link de rastreamento.\n"
    ),
    "order_delivered": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi entregue.\n\nObrigado pela preferência!\n"
    ),
    "order_cancelled": (
        "Olá{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi cancelado.{reason_note}\n\n"
        "Em caso de dúvidas, entre em contato.\n"
    ),
    "order_rejected": (
        "Olá{customer_name_greeting}!\n\n"
        "O estabelecimento não conseguiu confirmar o pedido {order_ref}.\n\n"
        "Motivo: {reason}\n\n"
        "Em caso de dúvidas, entre em contato.\n"
    ),
    "payment_confirmed": (
        "Olá{customer_name_greeting}!\n\n"
        "O pagamento do pedido {order_ref} foi confirmado.\n\n"
        "Seu pedido seguirá para preparo.\n\n"
        "Obrigado!\n"
    ),
    "payment_requested": (
        "Olá{customer_name_greeting}!\n\n"
        "Conferimos a disponibilidade do pedido {order_ref}.\n\n"
        "Agora falta o pagamento. Acesse: {payment_url}\n\n"
        "{pix_suffix}\n"
    ),
    "payment_expired": (
        "Olá{customer_name_greeting}!\n\n"
        "O prazo de pagamento do pedido {order_ref} expirou.\n\n"
        "Caso ainda deseje comprar, faça um novo pedido.\n"
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
        "Olá, {supplier_name}.\n\n"
        "Segue pedido de compra da {shop_name}.\n\n"
        "{lines_text}\n\n"
        "Total estimado: {estimated_total}\n"
        "Entrega desejada: {requested_delivery_label}\n"
        "{operator_note}"
        "Por favor confirme disponibilidade, prazo e valor final.\n"
    ),
    "purchase_receipt_rejected": (
        "Recebimento recusado/devolvido.\n\n"
        "Fornecedor: {supplier_name}\n"
        "Documento: {document_ref}\n"
        "Motivo: {reason}\n\n"
        "{lines_text}\n"
    ),
}


def _enrich_context(context: dict[str, Any]) -> dict[str, Any]:
    """Add computed fields to template context."""
    ctx = dict(context)

    if ctx.get("customer_name"):
        ctx["customer_name_greeting"] = f", {ctx['customer_name']}"
    else:
        ctx["customer_name_greeting"] = ""

    total_q = ctx.get("total_q")
    if total_q and not ctx.get("total"):
        ctx["total"] = f"R$ {total_q / 100:,.2f}"

    # Definido por notification._build_context; default vazio p/ chamadas diretas.
    ctx.setdefault("courier_tracking_suffix", "")

    return ctx


def _render_html(template: str, context: dict[str, Any]) -> str | None:
    """Try to render a Django HTML template for this event."""
    template_name = f"notifications/email/{template}.html"
    try:
        return render_to_string(template_name, _enrich_context(context))
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
        render_message,
        render_template,
    )

    ctx = _enrich_context(context or {})

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


def is_available(recipient: str | None = None, **config) -> bool:
    """Email is available if Django email backend is configured."""
    return bool(getattr(settings, "EMAIL_HOST", None) or getattr(settings, "EMAIL_BACKEND", None))
