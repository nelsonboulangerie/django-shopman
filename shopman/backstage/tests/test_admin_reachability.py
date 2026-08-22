"""Link oferecido no Admin é porta que abre — no menu e nos cards.

A sidebar e os cards do dashboard existem para levar alguém a uma tela. Enquanto
eles respondiam a pergunta por conta própria (``is_staff``, na maioria) e a tela
respondia outra (``view_<model>``), o resultado media assim, com os grupos do
``setup_groups``: a Fran (Caixa) via 26 itens de menu e 10 cards, e **os 36
respondiam 403**. Placa de aberto em porta trancada é pior que porta que falta —
manda a pessoa pedir suporte para um acesso que ela nem deveria ter.

O contrato aqui não enumera permissão (isso tem dono: ``admin.gates`` pergunta ao
``ModelAdmin`` e ao ``permission_required`` da view). Ele PEDE cada link
oferecido e exige 200. Com o contrapeso do superusuário, que continua vendo tudo
— senão um filtro fechado demais passaria verde escondendo tudo de todo mundo.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory

from shopman.backstage.admin.dashboard import dashboard_callback
from shopman.backstage.admin.navigation import get_sidebar_navigation

pytestmark = pytest.mark.django_db

#: Toda etiqueta que o dashboard sabe desenhar. O superusuário vê esta lista
#: inteira; qualquer persona vê um subconjunto dela.
TODOS_OS_CARDS = [
    "Loja e contato",
    "Produtos",
    "Regras de preço",
    "Promoções",
    "Textos da interface",
    "Canais",
    "Histórico de pedidos",
    "Cobranças",
    "Turnos de caixa",
    "Fechamentos do dia",
]


@pytest.fixture
def grupos():
    from django.core.management import call_command

    call_command("setup_groups", verbosity=0)
    return {g.name: g for g in Group.objects.all()}


@pytest.fixture
def _loja():
    """Sem Shop o OnboardingMiddleware desvia todo /admin/ para o cadastro da loja."""
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


def _com_grupo(nome: str, grupos) -> object:
    user = get_user_model().objects.create_user(username=f"u-{nome}", password="x", is_staff=True)
    user.groups.add(grupos[nome])
    return get_user_model().objects.get(pk=user.pk)  # recarrega: cache de permissão


def _cards(user) -> list[dict]:
    request = RequestFactory().get("/admin/")
    request.user = user
    context = dashboard_callback(request, {})
    return context["config_links"] + context["audit_links"]


def _etiquetas(user) -> list[str]:
    return [card["label"] for card in _cards(user)]


def test_o_superusuario_ve_a_lista_inteira():
    """Controle positivo: sem ele, um filtro que esconde tudo também passa verde."""
    root = get_user_model().objects.create_superuser(username="root", password="x")

    assert _etiquetas(root) == TODOS_OS_CARDS


def test_o_dashboard_nao_oferece_turnos_de_caixa_a_quem_opera(grupos):
    """O mesmo que ``test_o_menu_nao_oferece_turnos_de_caixa_a_quem_opera`` cobre
    na sidebar. A apuração é do Dono; o balcão e o gerente contam às cegas."""
    assert "Turnos de caixa" in _etiquetas(_com_grupo("Dono", grupos))
    assert "Turnos de caixa" not in _etiquetas(_com_grupo("Caixa", grupos))
    assert "Turnos de caixa" not in _etiquetas(_com_grupo("Gerente", grupos))


def test_o_gerente_continua_vendo_o_que_e_dele(grupos):
    """Contrapeso: o fechamento do dia é dele, e some se o filtro exagerar."""
    assert "Fechamentos do dia" in _etiquetas(_com_grupo("Gerente", grupos))
    assert "Fechamentos do dia" not in _etiquetas(_com_grupo("Caixa", grupos))


@pytest.mark.parametrize("persona", ["Caixa", "Gerente", "Dono"])
def test_todo_card_oferecido_abre(client, _loja, grupos, persona):
    """O coração: card oferecido é porta que abre. Nada de placa mentindo."""
    user = _com_grupo(persona, grupos)
    client.force_login(user)

    oferecidos = _cards(user)

    for card in oferecidos:
        resposta = client.get(card["url"])
        assert resposta.status_code == 200, f"{persona} clicou em {card['label']} e levou {resposta.status_code}"


def test_todo_card_oferecido_abre_para_o_superusuario(client, _loja):
    """O mesmo contrato do lado de cima: o dono do sistema vê tudo e tudo abre."""
    root = get_user_model().objects.create_superuser(username="root-cards", password="x")
    client.force_login(root)

    for card in _cards(root):
        assert client.get(card["url"]).status_code == 200, card["label"]


# ── A sidebar ────────────────────────────────────────────────────────────────


def _itens_de_menu(user) -> list[tuple[str, str]]:
    """Os itens do menu que este usuário enxerga e que apontam para o Admin.

    Os links para os apps Nuxt (PDV, KDS, Pedidos, Produção) ficam de fora: a
    porta deles é o gate da API do outro lado, não uma tela daqui.
    """
    request = RequestFactory().get("/admin/")
    request.user = user
    return [
        (item["title"], item["link"])
        for group in get_sidebar_navigation(request)
        for item in group["items"]
        if item["link"].startswith("/") and item["permission"](request)
    ]


@pytest.mark.parametrize("persona", ["Caixa", "Cozinha", "Gerente", "Dono"])
def test_todo_item_do_menu_abre(client, _loja, grupos, persona):
    user = _com_grupo(persona, grupos)
    client.force_login(user)

    for titulo, link in _itens_de_menu(user):
        # ``follow``: a lista de ordens de produção redireciona para o dia de
        # hoje por desenho — 302 aqui é auto-escopo, não porta fechada.
        resposta = client.get(link, follow=True)
        assert resposta.status_code == 200, f"{persona} clicou em {titulo} e levou {resposta.status_code}"


def test_o_menu_do_superusuario_abre_inteiro(client, _loja):
    """Controle positivo: um filtro que esconde tudo passaria verde sem isto."""
    root = get_user_model().objects.create_superuser(username="root-menu", password="x")
    client.force_login(root)

    itens = _itens_de_menu(root)

    assert len(itens) >= 40, "o menu do dono do sistema encolheu — o filtro está fechado demais"
    for titulo, link in itens:
        assert client.get(link, follow=True).status_code == 200, titulo
