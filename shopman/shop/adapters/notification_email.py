"""
Email notification adapter — sends via Django email backend.

Tries Django template at notifications/email/{template}.html,
falls back to inline text templates.
"""

from __future__ import annotations

import logging
import smtplib
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

from shopman.shop import notification_copy
from shopman.shop.mailers import default_mailer

logger = logging.getLogger(__name__)

SUBJECT_TEMPLATES: dict[str, str] = {
    "operator_critical": "Alerta crítico operacional — {alert_type}",
    "stock_alert": "Alerta de estoque: {product_label}",
    "announcement_published": "Novidade na padaria",
    "purchase_request": "Pedido de compra {purchase_ref} — {shop_name}",
    "purchase_receipt_rejected": "Devolução de recebimento {receipt_ref} — {shop_name}",
    # Avisos ao cliente: fonte única em `shopman/shop/notification_copy.py`.
    **notification_copy.subjects(),
}

BODY_TEMPLATES: dict[str, str] = {
    "operator_critical": "O alerta {alert_type} exige atenção no Gestor. Referência: {order_ref}. Confira os alertas operacionais antes de repetir a operação.",
    "stock_alert": (
        "Alerta de estoque\n\n"
        "Produto: {product_label}\nQuantidade atual: {available}\n"
        "Mínimo configurado: {min_quantity}\n\nProvidencie reposição.\n"
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
    # Avisos ao cliente: fonte única em `shopman/shop/notification_copy.py`.
    **notification_copy.plain_bodies(),
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
        count = send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info("Email result: template=%s accepted=%s", template, count == 1)
        return count == 1
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused,
            smtplib.SMTPDataError, smtplib.SMTPAuthenticationError,
            smtplib.SMTPConnectError, smtplib.SMTPHeloError) as exc:
        # These exceptions report refusal before SMTP accepted the message.
        # A disconnect/timeout can occur after DATA acceptance and stays unknown.
        logger.warning("Email rejected: template=%s error=%s", template, type(exc).__name__)
        return False
    except Exception as exc:
        raise RuntimeError("acceptance_unconfirmed") from exc


#: Backends que NÃO entregam a ninguém. O de console imprime em stdout, o
#: locmem guarda numa lista, o dummy descarta — todos "com sucesso".
_BACKENDS_INERTES = ("console", "locmem", "dummy")

#: Domínios de remetente que NÃO existem no DNS público. `.local` é TLD
#: reservado para mDNS (RFC 6762) e `example.*` é reservado para documentação
#: (RFC 2606) — nenhum dos dois tem SPF, DKIM ou DMARC possível, então o
#: receptor rejeita ou joga em spam.
_DOMINIOS_DE_REMETENTE_INERTES = (".local", "example.com", "example.org", "example.net")


def remetente_entrega(from_email: str) -> bool:
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
    mailer = default_mailer()
    backend = mailer.backend.lower()
    if any(inerte in backend for inerte in _BACKENDS_INERTES):
        return False
    # Um backend SMTP sem host não fala com ninguém — falha na primeira conexão.
    if "smtp" in backend and not mailer.host.strip():
        return False
    # Remetente que não existe no DNS = canal inerte, mesmo com SMTP de pé.
    remetente = str(
        config.get("from_email") or getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    ).strip()
    if not remetente_entrega(remetente):
        logger.warning(
            "E-mail indisponível: remetente %r não é entregável (domínio reservado ou ausente). "
            "Defina DEFAULT_FROM_EMAIL com um domínio real; a cadeia segue para SMS/WhatsApp.",
            remetente,
        )
        return False
    return bool(backend)
