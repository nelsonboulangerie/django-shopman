"""Beta 05/11 (LOJA-02): o celular era tratado como computador no login pelo WhatsApp.

O BFF da loja não repassava o user-agent, e o Django lia o UA do Node. A trava
do lado do BFF mora em `surfaces/storefront-nuxt/tests/djangoProxyBehavior.test.ts`;
esta confere que, com o UA do navegador chegando, a escada decide certo, e que
o UA do Node (o que chegava antes) não passa por celular.
"""

from django.test import RequestFactory
from shopman.shop.services.access import site_origin_is_phone

ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _request(user_agent: str):
    return RequestFactory().post("/api/v1/auth/access-link/", HTTP_USER_AGENT=user_agent)


def test_celular_repassado_pelo_bff_conta_como_celular():
    assert site_origin_is_phone(_request(ANDROID)) is True
    assert site_origin_is_phone(_request(IPHONE)) is True


def test_computador_conta_como_computador():
    assert site_origin_is_phone(_request(MAC)) is False


def test_ua_do_node_nao_e_o_do_cliente():
    """O que o Django via antes do conserto: decide 'computador' para todo mundo."""
    assert site_origin_is_phone(_request("node")) is False
