"""Quem vê a apuração do caixa — e quem não vê, por desenho.

A regra do dono: **o gerente opera, o dono audita.** O gerente abre e fecha
turno, autoriza sangria, resolve exceção — e conta às cegas, como todo mundo.
Quem sabe o esperado não conta às cegas: confere um gabarito, e o fechamento
cego perde a única coisa que existe para pegar.

Este arquivo testa a POLÍTICA (quem tem o quê, via ``setup_groups``), não a
mecânica de uma tela. Uma política que só vive no comentário de um card volta a
ser afrouxada na primeira refatoração — e volta calada.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from shopman.backstage.permissions import can_audit_cash, can_operate_pos

pytestmark = pytest.mark.django_db

AUDITA = "cashman.audit_shift"
OPERA = "cashman.operate_pos"


@pytest.fixture
def grupos():
    from django.core.management import call_command

    call_command("setup_groups", verbosity=0)
    return {g.name: g for g in Group.objects.all()}


def _com_grupo(nome: str, grupos):
    user = get_user_model().objects.create_user(username=f"u-{nome}", password="x", is_staff=True)
    user.groups.add(grupos[nome])
    return get_user_model().objects.get(pk=user.pk)  # recarrega: cache de permissão


def test_o_gerente_opera(grupos):
    assert can_operate_pos(_com_grupo("Gerente", grupos))


def test_o_gerente_NAO_ve_a_apuracao(grupos):
    """O coração da regra. Se este teste cair, alguém afrouxou a política."""
    gerente = _com_grupo("Gerente", grupos)

    assert not gerente.has_perm(AUDITA)
    assert not can_audit_cash(gerente)


def test_o_balcao_tambem_nao(grupos):
    caixa = _com_grupo("Caixa", grupos)

    assert can_operate_pos(caixa)
    assert not can_audit_cash(caixa)


def test_o_dono_ve(grupos):
    assert can_audit_cash(_com_grupo("Dono", grupos))


def test_o_dono_e_so_o_financeiro(grupos):
    """O grupo é um portão, não uma persona: auditar não dá direito a operar.

    Quem faz as duas coisas entra nos dois grupos — permissões somam. Assim a
    pergunta "quem vê dinheiro?" tem uma resposta só, legível no Admin.
    """
    dono = _com_grupo("Dono", grupos)

    assert can_audit_cash(dono)
    assert not can_operate_pos(dono)


def test_existe_UM_lugar_para_conceder(grupos):
    """A permissão precisa morar num grupo, senão ninguém a administra.

    Antes ela existia e nenhum grupo a concedia: só chegava a um superusuário ou
    a quem alguém lembrasse de marcar na mão. Permissão sem lugar onde conceder
    some do Admin e reaparece como "por que não consigo ver isso?" meses depois.
    """
    concedem = [g.name for g in grupos.values() if g.permissions.filter(codename="audit_shift").exists()]

    assert concedem == ["Dono"]


def test_o_superusuario_ve_sem_grupo_nenhum():
    """O dono de verdade não pode ficar de fora do próprio caixa por um grupo."""
    root = get_user_model().objects.create_superuser(username="root", password="x")

    assert can_audit_cash(root)


# ── A tela, não só a política ────────────────────────────────────────────────
#
# Os testes acima provam quem TEM a permissão. Não provavam quem ALCANÇA a
# apuração, e por isso a suíte passou verde enquanto o ``ShiftAdmin`` abria
# `/admin/cashman/shift/` para qualquer um com ``operate_pos`` — a permissão do
# caixa. O balcão lia "Esperado R$ 286,00" na aba ao lado e digitava R$ 286,00.
# Daqui para baixo o alvo é a TELA, com controle positivo: o auditor vê o
# número, e é o mesmo número que o livro prova.


@pytest.fixture
def _loja():
    """Sem Shop o OnboardingMiddleware desvia todo /admin/ para o cadastro da loja."""
    from shopman.shop.models import Shop

    return Shop.objects.create(name="Nelson")


def _turno_com_venda():
    """Um turno com R$ 100 de fundo e R$ 186 de venda: esperado R$ 286,00."""
    from shopman.cashman import services as cash
    from shopman.cashman.models import Entry, Terminal

    terminal = Terminal.objects.create(ref="balcao-apuracao", label="Balcão")
    caixa = get_user_model().objects.create_user("joyce-caixa", password="x", is_staff=True)
    shift = cash.open_shift(operator=caixa, terminal=terminal, float_q=10_000)
    cash.record(Entry.Kind.SALE, shift=shift, operator=caixa, amount_q=18_600, order_ref="A11")
    return shift


def _usuario(nome: str, *codenames: str):
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from shopman.cashman.models import Shift

    user = get_user_model().objects.create_user(nome, password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)  # recarrega: cache de permissão


def test_a_lista_de_turnos_mostra_a_apuracao_para_quem_audita(client, _loja):
    """Controle positivo: sem ele, "não contém Esperado" também passa num 404."""
    _turno_com_venda()
    client.force_login(_usuario("dono-apuracao", "audit_shift"))

    resposta = client.get("/admin/cashman/shift/")

    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "Esperado" in corpo
    assert "R$ 286,00" in corpo


def test_quem_opera_o_caixa_NAO_alcanca_a_apuracao(client, _loja):
    """O P0: ``operate_pos`` abria esta tela, e com ela o gabarito da contagem."""
    _turno_com_venda()
    client.force_login(_usuario("caixa-apuracao", "operate_pos"))

    resposta = client.get("/admin/cashman/shift/")

    assert resposta.status_code == 403
    assert "R$ 286,00" not in resposta.content.decode()


def test_o_gerente_tambem_nao(client, _loja, grupos):
    """Ele opera e autoriza exceção. Contar às cegas vale para ele igual."""
    _turno_com_venda()
    client.force_login(_com_grupo("Gerente", grupos))

    assert client.get("/admin/cashman/shift/").status_code == 403


def test_o_menu_nao_oferece_turnos_de_caixa_a_quem_opera(rf, grupos):
    """Link que responde 403 é porta trancada com placa de aberto."""
    from shopman.backstage.admin.navigation import get_sidebar_navigation

    def _oferece(user) -> bool:
        request = rf.get("/admin/")
        request.user = user
        for group in get_sidebar_navigation(request):
            for item in group["items"]:
                if item["title"] == "Turnos de caixa":
                    return bool(item["permission"](request))
        raise AssertionError("o item 'Turnos de caixa' sumiu do menu")

    assert _oferece(_com_grupo("Dono", grupos))
    assert not _oferece(_com_grupo("Caixa", grupos))
    assert not _oferece(_com_grupo("Gerente", grupos))


def test_a_apuracao_nao_vaza_para_quem_esta_no_balcao(client, _loja):
    """O buraco original, pelo caminho por onde ele se abria: a aba ao lado.

    O cookie de sessão vale em ``.boulangerie.com.br``, então a sessão do balcão
    abre o Admin em ``admin.boulangerie.com.br``. Enquanto o balcão ficava
    logado como ``admin`` superusuário, ``is_superuser`` curto-circuitava
    ``has_perm`` e a apuração — o gabarito que o fechamento cego existe para
    esconder — aparecia inteira para quem estivesse ali.

    Com uma identidade, quem está no balcão É a Joyce, e a Joyce não audita.
    Não há mais um segundo sujeito a consultar: o Admin pergunta a
    ``request.user``, e é a pessoa certa por construção.

    O contrapeso — que a tela CONTINUA aparecendo para quem audita — está em
    ``test_a_lista_de_turnos_mostra_a_apuracao_para_quem_audita``; sem ele, um
    gate fechado para todo mundo passaria por aqui.
    """
    _turno_com_venda()
    caixa = _usuario("joyce-identificada", "operate_pos")
    client.force_login(caixa)

    resposta = client.get("/admin/cashman/shift/")

    assert resposta.status_code == 403
    assert "R$ 286,00" not in resposta.content.decode()

