"""A raiz do host do Admin.

`admin.boulangerie.com.br/admin` é redundante: o host já diz o que é. Estes
testes travam que o atalho existe SÓ onde deve — inventar redirect na raiz da
API seria comportamento que ninguém pediu.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db

ADMIN_HOST = "admin.boulangerie.com.br"


@override_settings(SHOPMAN_ADMIN_HOST=ADMIN_HOST, ALLOWED_HOSTS=["*"])
def test_a_raiz_do_host_do_admin_cai_no_admin(client):
    response = client.get("/", HTTP_HOST=ADMIN_HOST)

    assert response.status_code == 302
    assert response["Location"] == "/admin/"


@override_settings(SHOPMAN_ADMIN_HOST=ADMIN_HOST, ALLOWED_HOSTS=["*"])
def test_a_raiz_dos_outros_hosts_nao_muda(client):
    """Na API, `/` não é porta de Admin — transformar em redirect era invenção."""
    response = client.get("/", HTTP_HOST="api.boulangerie.com.br")

    assert response.status_code == 404


@override_settings(SHOPMAN_ADMIN_HOST="", ALLOWED_HOSTS=["*"])
def test_sem_host_canonico_configurado_nada_muda(client):
    """Deployment que não declarou host de Admin segue como antes."""
    response = client.get("/", HTTP_HOST=ADMIN_HOST)

    assert response.status_code == 404


@override_settings(SHOPMAN_ADMIN_HOST=ADMIN_HOST, ALLOWED_HOSTS=["*"])
def test_o_atalho_NAO_sombreia_as_rotas_do_backstage(client):
    """`path("")` casa só a raiz exata; SSE e companhia seguem resolvendo.

    Se sombreasse, o Gestor perderia o stream de eventos e ninguém ligaria o
    defeito a um atalho de conveniência no Admin.
    """
    from django.urls import resolve

    assert resolve("/events/me/").url_name == "user_events"


API_HOST = "api.boulangerie.com.br"


@override_settings(SHOPMAN_ADMIN_HOST=ADMIN_HOST, ALLOWED_HOSTS=["*"])
def test_o_login_do_admin_so_abre_no_host_do_admin(client):
    response = client.get("/admin/login/", HTTP_HOST=ADMIN_HOST)
    assert response.status_code == 200


@override_settings(
    SHOPMAN_ADMIN_HOST=ADMIN_HOST,
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=".boulangerie.com.br",
    SHOPMAN_OPERATOR_API_HOST=API_HOST,
)
def test_fora_do_host_do_admin_o_login_so_entrega_o_cookie_de_csrf(client):
    """⚠️ O BFF dos apps de operador inicializa o CSRF com `GET /admin/login/` na
    API. Fechar a rota inteira derrubaria o login de PDV, KDS e Gestor; abrir o
    formulário deixava logar no Admin pela API (laudo S4). Fica só o cookie."""
    response = client.get("/admin/login/", HTTP_HOST=API_HOST)
    assert response.status_code == 204
    assert response.content == b""
    assert response.cookies["csrftoken"].value
    assert response.cookies["csrftoken"]["domain"] == ".boulangerie.com.br"


@override_settings(
    SHOPMAN_ADMIN_HOST=ADMIN_HOST,
    ALLOWED_HOSTS=["*"],
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=".boulangerie.com.br",
    SHOPMAN_OPERATOR_API_HOST=API_HOST,
)
def test_fora_do_host_do_admin_nao_ha_login_nem_tela_de_admin(client, django_user_model):
    """Era o caminho do laudo S4: logar em `api.` dava sessão de superusuário com
    `Domain=.boulangerie.com.br`, enviada aos nove subdomínios de operador."""
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja", brand_name="Loja")
    django_user_model.objects.create_superuser("root", "r@x.com", "S3nha-forte-123")
    admin_client = client.__class__(enforce_csrf_checks=False)
    response = admin_client.post(
        "/admin/login/",
        {"username": "root", "password": "S3nha-forte-123", "next": "/admin/"},
        HTTP_HOST=API_HOST,
    )
    assert response.status_code == 404
    assert "sessionid" not in response.cookies

    admin_client.force_login(django_user_model.objects.get(username="root"))
    for path in ("/admin/", "/admin/settings/", "/admin/auth/user/", "/admin/2fa/verify/", "/admin/logout/"):
        assert admin_client.get(path, HTTP_HOST=API_HOST).status_code == 404, path
        assert admin_client.get(path, HTTP_HOST=ADMIN_HOST).status_code != 404, path


@override_settings(SHOPMAN_ADMIN_HOST="", ALLOWED_HOSTS=["*"])
def test_sem_host_do_admin_configurado_o_admin_responde_em_qualquer_host(client):
    """Dev local e deployment sem a variável seguem como antes."""
    for host in (ADMIN_HOST, API_HOST, "localhost"):
        assert client.get("/admin/login/", HTTP_HOST=host).status_code == 200, host
