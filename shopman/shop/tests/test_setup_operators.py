"""O elenco de dev/staging existe, e existe LIGADO A GRUPOS.

O `seed` antigo dava `user_permissions` direto: `joyce` recebia sete
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

    assert not get_user_model().objects.filter(username="joyce").exists()


def test_o_elenco_cobre_os_quatro_papeis(elenco):
    assert set(elenco) >= {"admin", "joyce", "fran", "diofer"}


@pytest.mark.parametrize(
    ("username", "grupo"),
    [("admin", "Dono"), ("joyce", "Gerente"), ("fran", "Caixa"), ("diofer", "Cozinha")],
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

    joyce = get_user_model().objects.get(pk=elenco["joyce"].pk)
    assert can_operate_pos(joyce)
    assert not can_audit_cash(joyce)

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

    for username in ("joyce", "fran", "diofer"):
        assert not elenco[username].has_usable_password()
        assert not elenco[username].is_superuser
        assert elenco[username].is_staff


def test_rodar_duas_vezes_nao_duplica_nem_acumula(elenco):
    """Idempotente de verdade: é assim que se conserta acesso no staging."""
    call_command("setup_operators", "--yes", verbosity=0)

    joyce = get_user_model().objects.get(username="joyce")
    assert get_user_model().objects.filter(username="joyce").count() == 1
    assert [g.name for g in joyce.groups.all()] == ["Gerente"]
    assert joyce.user_permissions.count() == 0


def test_permissao_avulsa_antiga_e_LIMPA(elenco):
    """Rodar de novo tira o que alguém deu à mão — inclusive o seed velho.

    Sem isto, um banco que já passou pelo seed antigo ficaria para sempre com as
    sete permissões da `joyce` por cima do grupo, e o grupo mentiria.
    """
    from django.contrib.auth.models import Permission

    joyce = get_user_model().objects.get(username="joyce")
    joyce.user_permissions.add(Permission.objects.get(codename="audit_shift"))
    assert joyce.user_permissions.count() == 1

    call_command("setup_operators", "--yes", verbosity=0)

    assert get_user_model().objects.get(username="joyce").user_permissions.count() == 0


# ── Crachá ────────────────────────────────────────────────────────────────


def test_todos_saem_com_cracha_emitido(elenco):
    """A máquina de ler crachá estava pronta; faltava CRACHÁ.

    Sem token emitido, passar o leitor não acha ninguém — e a tela parece
    quebrada quando o que falta é o cadastro.
    """
    from shopman.doorman.models import PinCredential

    for username, user in elenco.items():
        cred = PinCredential.objects.get(user=user)
        assert cred.badge_hash, f"{username} sem crachá"


def test_o_cracha_de_dev_tem_o_FORMATO_QUE_A_TELA_ACEITA(elenco):
    """Hexadecimais, no comprimento que o doorman sorteia.

    A primeira versão era `CRACHA-<USUARIO>`, escolhida para ser digitável. O
    servidor resolvia, e ficou provado que resolvia; a TELA descartava calada,
    porque `isLikelyBadge` exige hexadecimais e "CRACHA-FRAN" tem hífen. O token
    nunca virava requisição.

    Este teste é o par do que vive em `operator-kit/tests/components/
    OperatorLock.test.ts`: lá se prova que a tela descarta o formato errado;
    aqui, que o que emitimos tem o formato certo. Um sem o outro deixa o buraco
    exatamente onde ele estava.
    """
    import re

    from shopman.doorman.models import PinCredential

    # O comprimento sai do doorman, não de um número copiado: é o mesmo orçamento
    # que decide a largura da barra no papel (ver `barcode.DEFAULT_MODULE_MM`).
    n = PinCredential.BADGE_BYTES * 2
    for username, *_ in setup_operators.CAST:
        token = setup_operators.dev_badge(username)
        assert re.fullmatch(rf"[0-9a-f]{{{n}}}", token), f"{username}: {token!r} não passa na tela"


def test_o_cracha_e_estavel_entre_execucoes(elenco):
    """O crachá impresso ontem continua valendo depois de rodar de novo."""
    antes = setup_operators.dev_badge("fran")
    call_command("setup_operators", "--yes", verbosity=0)
    assert setup_operators.dev_badge("fran") == antes


def test_cada_pessoa_tem_um_cracha_diferente(elenco):
    tokens = {setup_operators.dev_badge(u) for u, *_ in setup_operators.CAST}
    assert len(tokens) == len(setup_operators.CAST)


def test_o_cracha_resolve_para_a_pessoa_certa(elenco):
    from shopman.backstage.services.operator import resolve_operator_by_badge

    achado = resolve_operator_by_badge(
        setup_operators.dev_badge("fran"), required_perm="cashman.operate_pos"
    )
    assert achado is not None
    assert achado.username == "fran"


def test_cracha_de_outra_pessoa_nao_resolve_para_mim(elenco):
    from shopman.backstage.services.operator import resolve_operator_by_badge

    achado = resolve_operator_by_badge(
        setup_operators.dev_badge("diofer"), required_perm="cashman.operate_pos"
    )
    # diofer é da Cozinha: o crachá dele existe, mas não abre o PDV.
    assert achado is None


# ── Absorver a identidade antiga ──────────────────────────────────────────


@pytest.mark.django_db
def test_a_gerente_nova_herda_o_historico_da_antiga():
    """Apagar direto jogaria fora o passado; reatribuir preserva a trilha.

    Turnos, linhas do livro, movimentos de estoque e fechamentos apontam para
    quem fez. Quem era a gerente continua sendo a gerente.
    """
    from shopman.cashman.models import Shift, Terminal

    antiga = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    terminal = Terminal.default()
    turno = Shift.objects.create(terminal=terminal, operator=antiga)

    call_command("setup_operators", "--yes", verbosity=0)

    turno.refresh_from_db()
    assert turno.operator.username == "joyce"
    assert not get_user_model().objects.filter(username="marina").exists()


@pytest.mark.django_db
def test_absorver_e_idempotente():
    """Rodar de novo não acha ninguém para absorver, e não explode."""
    antiga = get_user_model().objects.create_user(username="ana", password="x", is_staff=True)
    assert antiga.pk

    call_command("setup_operators", "--yes", verbosity=0)
    call_command("setup_operators", "--yes", verbosity=0)

    assert not get_user_model().objects.filter(username="ana").exists()
    assert get_user_model().objects.filter(username="fran").count() == 1


@pytest.mark.django_db
def test_sem_conta_antiga_nada_acontece():
    """Banco novo: não há passado para herdar, e o comando roda igual."""
    call_command("setup_operators", "--yes", verbosity=0)

    assert get_user_model().objects.filter(username="joyce").exists()
    assert not get_user_model().objects.filter(username="marina").exists()


# ── O log não pode mentir ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_nao_anuncia_travessia_de_livro_imutavel_que_nao_houve(capsys):
    """Herdar NADA não pode logar "livro imutável reatribuído".

    O `update()` do livro imutável levanta sem olhar se há linha, então
    tentar-e-avisar anunciava travessia que nunca houve. Numa auditoria isso é
    pior que não avisar: quem lê acredita que a trilha do caixa foi reescrita.
    """
    get_user_model().objects.create_user(username="marina", password="x", is_staff=True)

    call_command("setup_operators", "--yes")

    assert "livro imutável" not in capsys.readouterr().out


@pytest.mark.django_db
def test_anuncia_a_travessia_quando_ela_ACONTECE(capsys):
    """E quando há linha de verdade, diz quantas — o número é a prova."""
    from shopman.cashman.models import Entry, Shift, Terminal

    antiga = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    turno = Shift.objects.create(terminal=Terminal.default(), operator=antiga)
    Entry.objects.create(shift=turno, operator=antiga, kind=Entry.Kind.DRAWER_OPEN, amount_q=0)

    call_command("setup_operators", "--yes")
    saida = capsys.readouterr().out

    assert "1 linha de livro imutável reatribuída" in saida
    assert "cashman.Entry.operator" in saida


@pytest.mark.django_db
def test_o_aviso_sai_DEPOIS_da_pessoa_a_quem_pertence(capsys):
    """Antes ele saía acima, e o leitor atribuía a travessia à pessoa anterior."""
    from shopman.cashman.models import Entry, Shift, Terminal

    antiga = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    turno = Shift.objects.create(terminal=Terminal.default(), operator=antiga)
    Entry.objects.create(shift=turno, operator=antiga, kind=Entry.Kind.DRAWER_OPEN, amount_q=0)

    call_command("setup_operators", "--yes")
    linhas = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]

    idx_joyce = next(i for i, ln in enumerate(linhas) if ln.strip().startswith("joyce:"))
    idx_aviso = next(i for i, ln in enumerate(linhas) if "livro imutável" in ln)
    assert idx_aviso > idx_joyce
