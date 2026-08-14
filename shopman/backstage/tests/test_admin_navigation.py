"""Contrato do menu lateral do Admin (WP-ADM-R0).

O menu é a única navegação do Admin (``show_all_applications: False``), então um
item que não resolve não é um detalhe cosmético: é uma tela que sumiu do alcance
do gestor. Foi exatamente o que aconteceu quando Promotion/Coupon/DeliveryZone
migraram de ``storefront`` para ``shop`` — o menu seguiu apontando para
``admin:storefront_*``, o helper devolvia ``"#"`` em silêncio e cinco telas de
configuração ficaram inalcançáveis sem que nenhum teste reclamasse.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory

from shopman.backstage.admin.navigation import get_sidebar_navigation


def _superuser_request():
    request = RequestFactory().get("/admin/")
    request.user = User(username="nav-admin", is_staff=True, is_superuser=True)
    return request


def _menu_items(request) -> list[dict]:
    return [item for group in get_sidebar_navigation(request) for item in group["items"]]


@pytest.mark.django_db
def test_every_menu_link_resolves():
    """Nenhum item de menu pode apontar para lugar nenhum."""
    broken = [
        item["title"]
        for item in _menu_items(_superuser_request())
        if not item["link"] or item["link"] == "#"
    ]
    assert not broken, f"itens de menu sem destino: {broken}"
