"""O elenco de dev/staging existe, e existe LIGADO A GRUPOS.

O `seed` antigo dava `user_permissions` direto: `marina` recebia sete
permissões copiadas à mão que imitavam o grupo "Gerente" sem serem ele. Duas
listas para a mesma pergunta saem de sincronia no primeiro dia — mudar o grupo
não alcançava ninguém, e a tela de Grupos do Admin mostrava gente sem grupo
nenhum operando o sistema inteiro.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from shopman.shop.management.commands import setup_operators

pytestmark = pytest.mark.django_db


@pytest.fixture
def elenco():
    call_command("setup_operators", "--yes", verbosity=0)
    return {u.username: u for u in get_user_model().objects.all()}


def test_sem_yes_o_comando_recusa():
    """PIN 1234 e senha 'admin' não podem sair de um job automático.

    O `--yes` é uma frase que alguém digita de propósito. Sem ele, um release
    distraído poderia plantar contas de dev em produção.
    """
    with pytest.raises(CommandError, match="produção"):
        call_command("setup_operators", verbosity=0)

    assert not get_user_model().objects.filter(username="marina").exists()


def test_o_elenco_cobre_os_quatro_papeis(elenco):
    assert set(elenco) >= {"admin", "marina", "ana", "joao"}


@pytest.mark.parametrize(
    ("username", "grupo"),
    [("admin", "Dono"), ("marina", "Gerente"), ("ana", "Caixa"), ("joao", "Cozinha")],
)
def test_cada_um_no_seu_grupo(elenco, username, grupo):
    assert [g.name for g in elenco[username].groups.all()] == [grupo]


def test_ninguem_tem_permissao_avulsa(elenco):
    """O grupo é a ÚNICA resposta para "por que essa pessoa consegue isso?".

    Permissão direta no usuário não aparece na tela de Grupos e sobrevive a
    qualquer mudança em `setup_groups` — é acesso que ninguém explica.
    """
    for user in elenco.values():
        assert user.user_permissions.count() == 0, f"{user.username} tem permissão avulsa"


def test_o_dono_audita_e_o_gerente_nao(elenco):
    """O coração da política, agora exercitado por gente de verdade."""
    from shopman.backstage.permissions import can_audit_cash, can_operate_pos

    marina = get_user_model().objects.get(pk=elenco["marina"].pk)
    assert can_operate_pos(marina)
    assert not can_audit_cash(marina)

    # `admin` é superusuário: audita por isso. O grupo importa mesmo assim —
    # sem ele o "Dono" nasceria vazio, e a apuração ficaria invisível para
    # qualquer não-superusuário que devesse vê-la.
    assert "Dono" in [g.name for g in elenco["admin"].groups.all()]


def test_todos_tem_pin_para_destravar_a_superficie(elenco):
    from shopman.doorman.models import PinCredential

    for user in elenco.values():
        cred = PinCredential.objects.get(user=user)
        assert cred.verify(setup_operators.DEV_PIN)


def test_admin_entra_com_senha_e_os_outros_so_com_pin(elenco):
    """Confiança do dispositivo entra pelo `admin`; quem opera se identifica pelo PIN."""
    assert elenco["admin"].check_password(setup_operators.ADMIN_PASSWORD)
    assert elenco["admin"].is_superuser

    for username in ("marina", "ana", "joao"):
        assert not elenco[username].has_usable_password()
        assert not elenco[username].is_superuser
        assert elenco[username].is_staff


def test_rodar_duas_vezes_nao_duplica_nem_acumula(elenco):
    """Idempotente de verdade: é assim que se conserta acesso no staging."""
    call_command("setup_operators", "--yes", verbosity=0)

    marina = get_user_model().objects.get(username="marina")
    assert get_user_model().objects.filter(username="marina").count() == 1
    assert [g.name for g in marina.groups.all()] == ["Gerente"]
    assert marina.user_permissions.count() == 0


def test_permissao_avulsa_antiga_e_LIMPA(elenco):
    """Rodar de novo tira o que alguém deu à mão — inclusive o seed velho.

    Sem isto, um banco que já passou pelo seed antigo ficaria para sempre com as
    sete permissões da `marina` por cima do grupo, e o grupo mentiria.
    """
    from django.contrib.auth.models import Permission

    marina = get_user_model().objects.get(username="marina")
    marina.user_permissions.add(Permission.objects.get(codename="audit_shift"))
    assert marina.user_permissions.count() == 1

    call_command("setup_operators", "--yes", verbosity=0)

    assert get_user_model().objects.get(username="marina").user_permissions.count() == 0
