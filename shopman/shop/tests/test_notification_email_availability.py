"""Um canal que não entrega tem que dizer que não entrega.

Item 4 do inventário de fallbacks perigosos, e o menos visível dos quatro de
Tier 1. `is_available()` era `bool(EMAIL_HOST or EMAIL_BACKEND)` — e
`EMAIL_BACKEND` tem string por default (o de console), então a expressão era
**incondicionalmente True**.

O estrago não está no e-mail que não chega: está no que ele IMPEDE. Em
`services/notification.py` o primeiro backend que devolve sucesso encerra a
cadeia. O backend de console imprime em stdout e não levanta, `send()` devolve
`True`, e **SMS e WhatsApp nunca são tentados**. O cliente não recebe o link de
pagamento, o fornecedor não recebe o pedido de compra, e o log diz "Email sent".
"""

from __future__ import annotations

import pytest

from shopman.shop.adapters import notification_email

pytestmark = pytest.mark.django_db


class TestCanalInerteDizQueEstaInerte:
    def test_console_nao_esta_disponivel(self, settings):
        """O default do Django, e o que o alpha roda hoje."""
        settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
        settings.EMAIL_HOST = ""

        assert notification_email.is_available() is False

    def test_locmem_nao_esta_disponivel(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

        assert notification_email.is_available() is False

    def test_dummy_nao_esta_disponivel(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"

        assert notification_email.is_available() is False

    def test_smtp_SEM_host_nao_esta_disponivel(self, settings):
        """Backend real sem host não fala com ninguém — falha na conexão."""
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = ""

        assert notification_email.is_available() is False

    def test_smtp_COM_host_esta_disponivel(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = "smtp.sendgrid.net"

        assert notification_email.is_available() is True


def test_o_console_deixa_de_curto_circuitar_a_cadeia(settings):
    """O eixo que importa: com o e-mail inerte, a cadeia SEGUE.

    Este é o comportamento que estava quebrado — e ele não aparecia em lugar
    nenhum, porque o log dizia sucesso.
    """
    from shopman.shop.notifications import get_backend

    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    settings.EMAIL_HOST = ""

    backend = get_backend("email")
    assert backend is not None
    # `services/notification.py` faz exatamente isto antes de tentar entregar:
    # `if not backend_module.is_available(): continue`.
    assert backend.is_available() is False, (
        "com o e-mail se dizendo disponível, SMS e WhatsApp nunca são tentados"
    )
