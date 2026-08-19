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
