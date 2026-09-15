"""
Senders for delivering verification codes.

Protocol-based for extensibility.
"""

import logging
from typing import Protocol

logger = logging.getLogger("shopman.doorman.senders")


class MessageSenderProtocol(Protocol):
    """Protocol that senders must implement."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        """
        Send verification code.

        Args:
            target: Phone number (E.164) or email
            code: 6-digit code
            method: Delivery method (whatsapp, sms, email)

        Returns:
            True if sent successfully
        """
        ...


class ConsoleSender:
    """Ack local sem expor segredo; requer uma superfície de debug protegida."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        # O código de desenvolvimento é recuperado apenas pela interface de
        # debug autenticada. stdout costuma ser coletado e retido externamente.
        print(f"Código de teste gerado pelo Doorman ({method}); consulte a interface de debug.")
        logger.info("Código de teste gerado", extra={"method": method})
        return True


class LogSender:
    """Ack de teste sem entrega; não deve ser usado por endpoint interativo genérico."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        logger.info("Código de teste aceito", extra={"method": method})
        return True


class WhatsAppCloudAPISender:
    """Sender via WhatsApp Cloud API."""

    def __init__(self):
        from .conf import doorman_settings

        self.access_token = doorman_settings.WHATSAPP_ACCESS_TOKEN
        self.phone_id = doorman_settings.WHATSAPP_PHONE_ID
        self.template_name = doorman_settings.WHATSAPP_CODE_TEMPLATE

    def send_code(self, target: str, code: str, method: str) -> bool:
        if not all([self.access_token, self.phone_id, self.template_name]):
            logger.error("WhatsApp not configured")
            return False

        try:
            import httpx
        except ImportError:
            logger.error("httpx not installed - required for WhatsApp sender")
            return False

        # Remove + and spaces from phone
        phone = target.replace("+", "").replace(" ", "")

        try:
            response = httpx.post(
                f"https://graph.facebook.com/v18.0/{self.phone_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": phone,
                    "type": "template",
                    "template": {
                        "name": self.template_name,
                        "language": {"code": "pt_BR"},
                        "components": [
                            {
                                "type": "body",
                                "parameters": [{"type": "text", "text": code}],
                            },
                        ],
                    },
                },
                timeout=10,
            )
            response.raise_for_status()
            logger.info("WhatsApp code sent", extra={"phone": phone})
            return True
        except Exception:
            logger.exception("WhatsApp send failed", extra={"phone": phone})
            return False


class SMSSender:
    """
    SMS sender stub.

    Implement with your SMS provider (Twilio, AWS SNS, etc.)
    """

    def send_code(self, target: str, code: str, method: str) -> bool:
        logger.warning("SMS sender not implemented — configure a real sender for %s", method)
        return False


class EmailSender:
    """
    Email sender using Django's email backend.

    Uses Django templates for email body (D1) and gettext for subject.
    Uses Django's DEFAULT_FROM_EMAIL setting for the sender address.
    """

    def send_code(self, target: str, code: str, method: str) -> bool:
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.translation import gettext as _

        from .conf import doorman_settings

        ttl = doorman_settings.ACCESS_CODE_TTL_MINUTES
        context = {"code": code, "ttl_minutes": ttl}

        try:
            subject = _("Your verification code")
            text_body = render_to_string("auth/email_code.txt", context)
            html_body = render_to_string("auth/email_code.html", context)

            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=None,  # Uses DEFAULT_FROM_EMAIL
                to=[target],
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)

            logger.info("Email code sent", extra={"target": target})
            return True
        except Exception:
            logger.exception("Email send failed", extra={"target": target})
            return False
