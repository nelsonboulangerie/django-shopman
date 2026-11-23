"""O cookie de CSRF do Admin tem nome próprio (#3372).

Medido no Chrome do dono em 23/11/2026: no host do Admin chegavam DOIS
``csrftoken``, o host-only e um velho com ``Domain=.boulangerie.com.br`` (sobra de
quando o Admin herdava o domínio-pai, antes de 17/09). O Django lia um só, e todo
POST do Admin, a inscrição do 2FA inclusive, caía em "Verificação CSRF falhou".
"""

from __future__ import annotations

import pytest
from django.test import Client, override_settings

from shopman.shop.middleware import ADMIN_CSRF_COOKIE_NAME

pytestmark = pytest.mark.django_db

ADMIN_HOST = "admin.boulangerie.com.br"
API_HOST = "api.boulangerie.com.br"
OPERATOR_COOKIE_DOMAIN = ".boulangerie.com.br"
STALE_PARENT_DOMAIN = "a" * 32
STALE_HOST_ONLY = "b" * 32
PASSWORD = "S3nha-forte-123"

ADMIN_SETTINGS = {
    "SHOPMAN_ADMIN_HOST": ADMIN_HOST,
    "ALLOWED_HOSTS": ["*"],
    "SHOPMAN_OPERATOR_COOKIE_DOMAIN": OPERATOR_COOKIE_DOMAIN,
    "SHOPMAN_OPERATOR_API_HOST": API_HOST,
}


@pytest.fixture
def superuser(django_user_model):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja", brand_name="Loja")
    return django_user_model.objects.create_superuser("root", "r@x.com", PASSWORD)


def _admin_csrf_secret() -> str:
    response = Client(enforce_csrf_checks=True).get("/admin/login/", HTTP_HOST=ADMIN_HOST)
    assert response.status_code == 200
    assert "csrftoken" not in response.cookies
    return response.cookies[ADMIN_CSRF_COOKIE_NAME].value


def _post_login(cookie_header: str, form_token: str):
    return Client(enforce_csrf_checks=True).post(
        "/admin/login/",
        {"username": "root", "password": PASSWORD, "next": "/admin/", "csrfmiddlewaretoken": form_token},
        HTTP_HOST=ADMIN_HOST,
        HTTP_COOKIE=cookie_header,
    )


@override_settings(**ADMIN_SETTINGS)
def test_no_host_do_admin_o_cookie_de_csrf_sai_com_nome_proprio_e_host_only(client):
    response = client.get("/admin/login/", HTTP_HOST=ADMIN_HOST)

    assert response.status_code == 200
    assert "csrftoken" not in response.cookies
    cookie = response.cookies[ADMIN_CSRF_COOKIE_NAME]
    assert cookie.value
    assert cookie["domain"] == ""
    assert cookie["path"] == "/"
    assert cookie["samesite"] == "Lax"
    assert cookie["max-age"]


@override_settings(**ADMIN_SETTINGS)
def test_o_post_do_admin_passa_com_os_dois_csrftoken_velhos_no_navegador(superuser):
    """O caso medido: dois ``csrftoken`` no request, e o Admin segue gravando."""
    secret = _admin_csrf_secret()
    cookies = f"csrftoken={STALE_PARENT_DOMAIN}; csrftoken={STALE_HOST_ONLY}; {ADMIN_CSRF_COOKIE_NAME}={secret}"

    response = _post_login(cookies, secret)

    assert response.status_code == 302, response.content[:300]
    assert response["Location"] == "/admin/"


@override_settings(**ADMIN_SETTINGS)
def test_no_host_do_admin_o_csrftoken_nao_vale_mais(superuser):
    """O nome velho é ignorado: mesmo com o segredo certo, só ele não passa."""
    secret = _admin_csrf_secret()

    response = _post_login(f"csrftoken={secret}", secret)

    assert response.status_code == 403


@override_settings(**ADMIN_SETTINGS)
def test_o_token_do_formulario_ainda_tem_de_bater_com_o_cookie_proprio(superuser):
    secret = _admin_csrf_secret()

    response = _post_login(f"{ADMIN_CSRF_COOKIE_NAME}={secret}", STALE_HOST_ONLY)

    assert response.status_code == 403


@override_settings(**ADMIN_SETTINGS)
def test_fora_do_host_do_admin_o_cookie_segue_csrftoken_no_dominio_do_operador(client):
    """O BFF dos apps de operador inicializa o CSRF por `GET /admin/login/` na API e
    traduz `csrftoken`: ali o nome do Django não muda."""
    response = client.get("/admin/login/", HTTP_HOST=API_HOST)

    assert ADMIN_CSRF_COOKIE_NAME not in response.cookies
    assert response.cookies["csrftoken"]["domain"] == OPERATOR_COOKIE_DOMAIN


@override_settings(SHOPMAN_ADMIN_HOST="", ALLOWED_HOSTS=["*"])
def test_sem_host_do_admin_configurado_o_nome_e_o_do_django(client):
    """Dev local e deployment sem a variável seguem como antes."""
    response = client.get("/admin/login/", HTTP_HOST=ADMIN_HOST)

    assert ADMIN_CSRF_COOKIE_NAME not in response.cookies
    assert response.cookies["csrftoken"].value
