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

    assert resolve("/gestor/events/me/").url_name == "user_events"


@override_settings(SHOPMAN_ADMIN_HOST=ADMIN_HOST, ALLOWED_HOSTS=["*"])
def test_o_admin_em_si_segue_respondendo_nos_dois_hosts(client):
    """⚠️ Fechar `/admin/` na API derruba o login de PDV, KDS e Gestor: o BFF
    inicializa o CSRF batendo em `/admin/login/` lá."""
    for host in (ADMIN_HOST, "api.boulangerie.com.br"):
        response = client.get("/admin/login/", HTTP_HOST=host)
        assert response.status_code == 200, host
