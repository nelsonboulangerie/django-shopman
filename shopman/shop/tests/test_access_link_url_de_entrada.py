"""A URL de entrada é a da LOJA, e tem um construtor só.

02/09: o link que chegou no WhatsApp foi

    https://menu.nelsonboulangerie.com.br/auth/access/?t=mMYQ2fJgo...

Host certo, caminho errado — `/auth/access/` é rota do Django, e a loja Nuxt
serve `/a`. Deu 404 na cara de quem clicou.

A causa foram DOIS construtores para a mesma URL: a view montava `{loja}/a?t=`
para a resposta, e o serviço montava `{domínio}{reverse(...)}?t=` para tudo o
mais — mensagem do WhatsApp, magic link por e-mail e `send_access_link`.
"""

from __future__ import annotations

import pytest
from shopman.doorman.services.access_link import AccessLinkService

LOJA = "https://menu.nelsonboulangerie.com.br"


@pytest.fixture
def com_loja(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_ENTRY_URL"] = LOJA
    settings.DOORMAN = base


def test_a_url_aponta_para_a_entrada_da_loja(com_loja):
    url = AccessLinkService._build_url("abc123")
    assert url == f"{LOJA}/a?t=abc123"


def test_nunca_a_rota_do_django(com_loja):
    url = AccessLinkService._build_url("abc123")
    assert "/auth/access/" not in url, (
        "é a rota do Django; a loja Nuxt não a serve e o cliente toma 404"
    )


def test_a_barra_sobrando_na_config_nao_dobra(settings):
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_ENTRY_URL"] = LOJA + "/"
    settings.DOORMAN = base
    assert AccessLinkService._build_url("x") == f"{LOJA}/a?t=x"


def test_o_token_e_escapado(com_loja):
    assert AccessLinkService._build_url("a+b/c=d") == f"{LOJA}/a?t=a%2Bb%2Fc%3Dd"


def test_sem_loja_configurada_sobra_a_rota_do_django(settings):
    """Instalação sem storefront Nuxt: o próprio Django ainda responde."""
    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_ENTRY_URL"] = ""
    settings.DOORMAN = base
    assert "/auth/access/" in AccessLinkService._build_url("x")


@pytest.mark.django_db
def test_a_resposta_do_endpoint_e_a_mensagem_dizem_a_MESMA_url(com_loja, settings):
    """O defeito era exatamente as duas discordarem."""
    import json
    from unittest.mock import patch

    from django.test import Client

    base = dict(getattr(settings, "DOORMAN", {}) or {})
    base["ACCESS_LINK_API_KEY"] = "k"
    base["ACCESS_LINK_ENTRY_URL"] = LOJA
    settings.DOORMAN = base

    enviado = {}

    def _captura(sender, url="", **kw):
        enviado["url"] = url

    from shopman.doorman.signals import access_link_created

    access_link_created.connect(_captura, weak=False)
    try:
        with patch("shopman.shop.notifications.notify"):
            r = Client().post(
                "/api/auth/access/create/",
                data=json.dumps({"subscriber": {"id": "1", "whatsapp_id": "5543999990001"}}),
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer k",
            )
    finally:
        access_link_created.disconnect(_captura)

    assert r.status_code == 200, r.content
    assert r.json()["access_url"] == enviado["url"]
    assert enviado["url"].startswith(f"{LOJA}/a?t=")
