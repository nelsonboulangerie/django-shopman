"""Os cards do dashboard do Admin não podem oferecer porta trancada.

A sidebar já filtra por permissão (``test_cash_audit_policy`` prova para os
turnos de caixa). Os cards do dashboard não filtravam nada: as três personas
viam a mesma lista, e para a Fran (Caixa) e a Joyce (Gerente) quase todo card
respondia 403. Placa de aberto em porta trancada é pior que porta que falta —
manda a pessoa procurar suporte para um acesso que ela não deveria ter.

O teste central aqui é o de baixo, ``test_todo_card_oferecido_abre``: ele não
enumera permissões (isso já tem dono), ele PEDE cada card oferecido e exige 200.
Com o contrapeso do superusuário, que continua vendo a lista inteira — senão um
filtro fechado demais passaria verde escondendo tudo de todo mundo.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory

from shopman.backstage.admin.dashboard import dashboard_callback

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


def test_o_operador_identificado_decide_e_nao_a_conta_do_aparelho(_loja):
    """A estação fica logada como a conta do APARELHO — no staging, um
    superusuário. Quando alguém se identifica por PIN, quem responde pela tela é
    o operador (``ShiftAdmin._viewer``), e o card tem de acompanhar: perguntar à
    porta é o que faz isso sair de graça."""
    from shopman.backstage.services.operator import ACTIVE_OPERATOR_SESSION_KEY

    aparelho = get_user_model().objects.create_superuser(username="admin-terminal", password="x")
    caixa = get_user_model().objects.create_user(username="joyce-identificada", password="x", is_staff=True)

    request = RequestFactory().get("/admin/")
    request.user = aparelho
    request.session = {}
    sem_operador = [card["label"] for card in dashboard_callback(request, {})["audit_links"]]

    request.session = {ACTIVE_OPERATOR_SESSION_KEY: {"id": caixa.pk, "username": caixa.username, "name": caixa.username}}
    com_operador = [card["label"] for card in dashboard_callback(request, {})["audit_links"]]

    assert "Turnos de caixa" in sem_operador
    assert "Turnos de caixa" not in com_operador
