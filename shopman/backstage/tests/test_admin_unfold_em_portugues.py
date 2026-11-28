"""Placeholders do Unfold em português (beta test 05/11/2026, ADM-11).

"Select action", "Return to site", "Search apps and models..." e o seletor
"Light/Dark/System" saíam em inglês: o Unfold não traz catálogo pt-BR para
eles, e o catálogo local (``locale/pt_BR``) é onde a casa os traduz.
"""

from __future__ import annotations

import pytest
from django.utils import translation


@pytest.mark.parametrize(
    ("msgid", "expected"),
    [
        ("Select action", "Escolha uma ação"),
        ("Select value", "Escolha um valor"),
        ("Date", "Data"),
        ("Cancel", "Cancelar"),
        ("Return to site", "Voltar ao site"),
        ("Search apps and models...", "Buscar telas e cadastros..."),
        ("Light", "Claro"),
        ("Dark", "Escuro"),
        ("System", "Do sistema"),
    ],
)
def test_placeholder_do_unfold_sai_em_portugues(msgid, expected):
    with translation.override("pt-br"):
        assert translation.gettext(msgid) == expected


@pytest.mark.django_db
def test_tela_de_acao_em_massa_nao_fala_ingles(admin_client):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    response = admin_client.get("/admin/shop/promotion/")
    body = response.content.decode()
    assert response.status_code == 200
    assert "Select action" not in body
    assert "Search apps and models" not in body
