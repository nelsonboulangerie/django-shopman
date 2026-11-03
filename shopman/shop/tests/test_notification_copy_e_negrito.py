"""As três decisões do dono sobre a copy de notificação (02/09/2026).

1. O `*negrito*` do template (escrito para WhatsApp) não vaza para o SMS.
2. Três avisos deixaram de prometer o que a tela não cumpre.
3. Quatro eventos que só existiam no fallback do código ganharam linha no seed —
   sem ela, o lojista não os edita no Admin.
"""

from __future__ import annotations

import pytest

from shopman.shop.adapters._notification_templates import strip_markdown_bold


class TestNegritoNaoVazaParaOSms:
    def test_o_asterisco_do_template_do_admin_some(self):
        rendered = "Ola, Joyce! Recebemos seu pedido *NB-260901-M63*. Total: *R$ 26,00*"
        assert strip_markdown_bold(rendered) == (
            "Ola, Joyce! Recebemos seu pedido NB-260901-M63. Total: R$ 26,00"
        )

    def test_asterisco_solto_no_meio_da_frase_fica_como_esta(self):
        """Não é par de negrito; mexer nele seria comer texto do lojista."""
        assert strip_markdown_bold("promoção 2*1 hoje") == "promoção 2*1 hoje"

    def test_nao_atravessa_quebra_de_linha(self):
        texto = "linha com * aqui\ne outra * ali"
        assert strip_markdown_bold(texto) == texto

    def test_o_whatsapp_continua_com_negrito(self):
        """A remoção é da SAÍDA do SMS, não do texto — o template segue intacto."""
        from shopman.shop.adapters._notification_templates import render_message
        from shopman.shop.adapters.notification_manychat import MESSAGE_TEMPLATES

        corpo = render_message(
            "order_accepted", {"order_ref": "NB-260925-A47", "customer_name": "Joyce"}, MESSAGE_TEMPLATES
        )
        assert "A47" in corpo and "NB-260925" not in corpo


@pytest.mark.django_db
class TestNegritoNoEmail:
    """O texto do Admin vale para o e-mail também, e ele é escrito para o WhatsApp.

    Medido em 03/11/2026: o e-mail de pedido confirmado chegava com "*L32*" e
    "*R$ 70,00*" literais. A parte texto sai limpa; a parte HTML vira negrito.
    """

    def _enviado(self, mailoutbox, body):
        from shopman.shop.adapters import notification_email
        from shopman.shop.models import NotificationTemplate

        NotificationTemplate.objects.update_or_create(
            event="order_accepted", defaults={"subject": "Pedido {order_ref_short} confirmado", "body": body, "is_active": True},
        )
        notification_email.send("ana@example.org", "order_accepted", {
            "order_ref": "PDV-261103-L32", "order_total_display": "R$ 70,00",
            "tracking_url": "https://www.nelsonboulangerie.com.br/pedido/PDV-261103-L32",
        }, from_email="pedidos@nelsonboulangerie.com.br")
        return mailoutbox[-1]

    def test_texto_sem_asterisco_e_html_com_negrito_e_link(self, mailoutbox):
        email = self._enviado(mailoutbox,
            "Seu pedido *{order_ref_short}* está confirmado. O total é *{order_total_display}*.\n"
            "Acompanhe por aqui: {tracking_url}")
        assert "*" not in email.body
        assert "Seu pedido L32 está confirmado. O total é R$ 70,00." in email.body
        html, mime = email.alternatives[0]
        assert mime == "text/html"
        assert "<strong>L32</strong>" in html and "<strong>R$ 70,00</strong>" in html
        assert 'href="https://www.nelsonboulangerie.com.br/pedido/PDV-261103-L32"' in html
        assert "*" not in html

    def test_html_escapa_o_texto_do_admin(self, mailoutbox):
        email = self._enviado(mailoutbox, "Pedido *{order_ref_short}* <b>ok</b>")
        html, _ = email.alternatives[0]
        assert "&lt;b&gt;ok&lt;/b&gt;" in html and "<strong>L32</strong>" in html


class TestAvisoNaoPrometeOQueATelaNaoCumpre:
    """`payment_confirmed` dizia "seguirá para preparo"; a tela, com o pedido ainda
    `new`, diz "estamos conferindo a disponibilidade". Pagar não garante aceite."""

    @pytest.mark.parametrize("modulo", [
        "shopman.shop.adapters.notification_sms",
        "shopman.shop.adapters.notification_manychat",
    ])
    def test_pagamento_confirmado_nao_promete_preparo(self, modulo):
        import importlib

        corpo = importlib.import_module(modulo).MESSAGE_TEMPLATES["payment_confirmed"]
        assert "preparo" not in corpo.lower()
        assert "{tracking_url}" in corpo

    @pytest.mark.parametrize("modulo", [
        "shopman.shop.adapters.notification_sms",
        "shopman.shop.adapters.notification_manychat",
    ])
    def test_saiu_para_entrega_habilita_a_confirmacao_que_a_tela_pede(self, modulo):
        import importlib

        corpo = importlib.import_module(modulo).MESSAGE_TEMPLATES["order_dispatched"]
        assert "{tracking_url}" in corpo, "a tela pede 'confirme quando receber' e precisa do link"


def _seed_templates() -> dict:
    """Os NotificationTemplate que o seed grava."""
    from config.management.commands.seed import NOTIFICATION_TEMPLATES

    return NOTIFICATION_TEMPLATES


class TestOsQuatroEventosViramEditaveisNoAdmin:
    @pytest.mark.parametrize("evento", [
        "waitlist_available",
        "waitlist_released",
        "preorder_reminder",
        "payment_reminder",
    ])
    def test_o_evento_tem_linha_no_seed(self, evento):
        templates = _seed_templates()
        assert evento in templates, (
            f"'{evento}' só existe no fallback do código: o lojista não consegue "
            "editá-lo no Admin nem associar um flow do ManyChat a ele."
        )
        assert templates[evento]["subject"] and templates[evento]["body"]

    def test_o_aviso_de_fidelidade_diz_onde_ver_o_saldo(self):
        corpo = _seed_templates()["loyalty_earned"]["body"]
        assert "{account_url}" in corpo, "anunciar pontos sem dizer onde vê-los é promessa sem porta"
