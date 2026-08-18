"""Em qualquer tela, o menu acende UM item — o da tela (WP-ADM-R8).

Menu que acende três itens não diz onde você está: diz onde você poderia estar.
E acontecia em quase todo lugar. Duas causas somadas:

1. **Aba e menu apontando para a mesma tela.** O Unfold marca como ativo todo
   item do menu que participe do grupo de abas da página atual
   (`_get_is_tab_active`). Com Produtos, Coleções e Vitrines no menu E na mesma
   aba, os três acendiam juntos. A regra que ficou: aba serve para a vizinhança
   que o menu NÃO mostra.
2. **Comparação por substring.** O `_get_is_active` do Unfold usa
   `link_path in request.path`, então itens que compartilham caminho acendem
   juntos. Onde isso importa, o item declara `active` explícito.

E havia o oposto, igualmente ruim: nas telas de configuração o menu não acendia
NADA, porque elas são alcançadas pela Configuração e não têm item próprio. Agora
o escopo delas fica destacado.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

# (caminho visitado, título que deve acender)
_EXPECTED = [
    ("/admin/offerman/product/", "Produtos"),
    ("/admin/offerman/collection/", "Coleções"),
    ("/admin/offerman/listing/", "Vitrines"),
    ("/admin/orderman/order/", "Histórico de pedidos"),
    ("/admin/orderman/session/", "Sessões de venda"),
    ("/admin/payman/paymentintent/", "Cobranças"),
    ("/admin/stockman/quant/", "Saldos"),
    ("/admin/guestman/customer/", "Clientes"),
    ("/admin/craftsman/recipe/", "Fichas técnicas"),
    # Telas de configuração: acendem o ESCOPO, que é o caminho por onde se chega.
    ("/admin/shop/shop/", "A loja"),
    ("/admin/shop/shopappearance/", "A loja"),
    ("/admin/shop/promotion/", "Como vendemos"),
    ("/admin/shop/deliveryzone/", "Como entregamos"),
    ("/admin/shop/notificationtemplate/", "O que dizemos"),
    ("/admin/shop/qualitydefect/", "Produção e estoque"),
    ("/admin/cashman/terminal/", "Equipamentos"),
    ("/admin/cashman/shift/", "Turnos de caixa"),
    ("/admin/auth/user/", "Quem entra"),
]


def _active_titles(path: str) -> list[str]:
    request = RequestFactory().get(path)
    request.user = User(username="nav", is_staff=True, is_superuser=True)
    return [
        item["title"]
        for group in admin.site.get_sidebar_list(request)
        for item in group["items"]
        if item.get("active")
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(("path", "expected"), _EXPECTED, ids=[p for p, _ in _EXPECTED])
def test_exactly_one_menu_item_is_active(path, expected):
    active = _active_titles(path)

    assert active == [expected], (
        f"em {path} o menu deveria acender só '{expected}', acendeu {active}"
    )


@pytest.mark.django_db
def test_each_configuration_scope_is_its_own_screen():
    """Subitem de Configuração abre uma TELA, não uma âncora.

    A primeira versão apontava para `#ancora` na página inteira: os oito subitens
    compartilhavam caminho, o Unfold acendia todos, e clicar num deles não parecia
    navegar. Cada escopo agora tem URL própria, como qualquer outro item do menu.
    """
    request = RequestFactory().get("/admin/")
    request.user = User(username="nav", is_staff=True, is_superuser=True)

    config = next(
        group
        for group in admin.site.get_sidebar_list(request)
        if group["title"] == "Configuração"
    )
    links = [item["link"] for item in config["items"]]

    assert links[0] == reverse("admin_console_settings_hub")
    for link in links[1:]:
        assert "#" not in link, f"{link} ainda é âncora"
        assert link != links[0], "escopo caindo na mesma tela do hub"
    assert len(set(links)) == len(links), "dois escopos apontando para a mesma tela"
