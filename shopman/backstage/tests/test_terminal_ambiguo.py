"""Com duas gavetas ativas, a mutação de dinheiro RECUSA em vez de escolher.

⚠️ A Onda 2A acabou com a paralisação (dois resolvers discordantes travavam o PDV
inteiro), mas deixou o caso silencioso de pé: com 2+ gavetas ativas e nenhuma estação
vinculada, um resolver concordante escolhe a errada COM CONVICÇÃO. Os dois lados
apontam para `balcao-2` consistentemente, e o operador do balcão 1 lança sangria na
gaveta do balcão 2 sem erro nenhum. Em dinheiro, falha silenciosa é pior que falha
ruidosa — a régua da casa manda recusar aí.

Fechar isso exigia o `terminal_ref` atravessar as onze funções de caixa e suas views.
Feito isso, a recusa é 409: o operador não errou nada, falta a loja dizer qual é o
balcão dele.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from shopman.cashman.models import Terminal

from shopman.backstage.services import pos as pos_service
from shopman.backstage.services.exceptions import POSTerminalAmbiguous

pytestmark = pytest.mark.django_db


@pytest.fixture
def operador(db):
    user = User.objects.create_user("op-ambiguo", password="pw", is_staff=True)
    for codename in ("operate_pos", "adjust_shift"):
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return User.objects.get(pk=user.pk)


@pytest.fixture
def duas_gavetas(db):
    Terminal.objects.all().update(is_active=False)
    return (
        Terminal.objects.create(ref="balcao-1", label="Balcão 1", is_active=True),
        Terminal.objects.create(ref="balcao-2", label="Balcão 2", is_active=True),
    )


def test_com_duas_gavetas_a_mutacao_sem_ref_recusa(operador, duas_gavetas):
    """O caso que era silencioso: sangria caindo na gaveta do colega."""
    with pytest.raises(POSTerminalAmbiguous):
        pos_service.register_cash_movement(
            operator=operador, movement_type="sangria", amount_raw="200,00", reason="cofre"
        )


def test_dizer_qual_gaveta_resolve(operador, duas_gavetas):
    """Assert-positivo: a recusa é por AMBIGUIDADE, não por haver duas gavetas.

    Com o ref, o caminho volta a andar — e é justamente isso que a canalização do
    `terminal_ref` pelas onze funções comprou.
    """
    terminal = pos_service.resolve_terminal("balcao-1")
    assert terminal.ref == "balcao-1"


def test_a_leitura_nao_derruba_o_quadro(duas_gavetas):
    """⚠️ Só a ESCRITA recusa.

    Derrubar o quadro inteiro do PDV por ambiguidade trocaria um problema por outro
    maior — foi exatamente o modo de falha que a Onda 2A tinha acabado de consertar.
    A leitura escolhe; quem anda com dinheiro é que precisa saber onde está.
    """
    assert pos_service.resolve_terminal(strict=False) is not None
    assert pos_service.current_shift() is None  # nenhuma aberta, mas não levantou


def test_uma_gaveta_so_nao_muda_nada(operador, db):
    """O caso de hoje na padaria: uma gaveta, nada muda."""
    Terminal.objects.all().update(is_active=False)
    Terminal.objects.create(ref="pdv-main", label="Balcão", is_active=True)

    assert pos_service.resolve_terminal().ref == "pdv-main"


def test_a_ambiguidade_vira_409_e_nomeia_o_campo(client, operador, duas_gavetas):
    """400 diria "seu pedido está errado", e o pedido está certo.

    O que falta é a loja dizer qual é o balcão — por isso 409, com `terminal_ref`
    nomeado para a tela saber o que perguntar.
    """
    client.force_login(operador)

    resposta = client.post(
        "/api/v1/backstage/pos/cash/movement/",
        {"kind": "sangria", "amount": "200,00", "reason": "cofre"},
        content_type="application/json",
    )

    assert resposta.status_code == 409, resposta.content
    assert resposta.json()["field"] == "terminal_ref"


def test_o_corpo_manda_mais_que_o_cookie(operador, duas_gavetas):
    """O ref do corpo é AFIRMAÇÃO de quem chama; o cookie é contexto ambiente."""
    from shopman.backstage.api.operations import _terminal_do_pedido

    class _Req:
        data = {"terminal_ref": "balcao-2"}
        COOKIES: dict = {}

    assert _terminal_do_pedido(_Req()) == "balcao-2"
