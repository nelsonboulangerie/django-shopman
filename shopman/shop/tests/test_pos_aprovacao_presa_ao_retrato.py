"""A aprovação do gerente vale para o retrato que ele viu (EXCELENCIA-PDV F1, #2558).

Venda PDV-261116-U44: a Joyce aprovou desconto de R$ 6,00, a Fran voltou da
maquininha, trocou para R$ 30,00, e o livro saiu "approved_by=joyce" com R$ 30.
O PIN ficava no carrinho e o servidor conferia só a credencial. Agora o diálogo
devolve um carimbo assinado, preso a operador, comanda e valores, e o fechamento
o gasta uma vez.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from shopman.cashman.models import Shift

from shopman.shop.services.pos import (
    SaleApprovalScope,
    _redeem_sale_approval,
    issue_sale_approval,
)
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_limpo():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def joyce():
    user = get_user_model().objects.create_user(username="joyce", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="adjust_shift"))
    return user


def _carimbo(joyce, *, discount_q=600, tab_ref="M1", operador="pos:fran"):
    return issue_sale_approval(
        joyce, operator_username=operador, scope=SaleApprovalScope(tab_ref=tab_ref, discount_q=discount_q),
    )


def _resgatar(token, *, discount_q=600, tab_ref="M1", operador="pos:fran", pedido="req-1"):
    return _redeem_sale_approval(
        token,
        operator_username=operador,
        snapshot=SaleApprovalScope(tab_ref=tab_ref, discount_q=discount_q),
        client_request_id=pedido,
    )


def test_o_valor_assinado_libera_e_assina_com_o_gerente(joyce):
    assert _resgatar(_carimbo(joyce)).get_username() == "joyce"


def test_valor_diferente_do_assinado_e_recusado(joyce):
    """O roteiro da U44: assinou R$ 6,00, a venda chegou com R$ 30,00."""
    with pytest.raises(PosIntentError) as exc:
        _resgatar(_carimbo(joyce, discount_q=600), discount_q=3000)
    assert exc.value.code == "manager_approval_invalid"
    assert "R$ 6,00" in exc.value.recovery and "R$ 30,00" in exc.value.recovery


def test_outra_comanda_e_recusada(joyce):
    with pytest.raises(PosIntentError):
        _resgatar(_carimbo(joyce, tab_ref="M1"), tab_ref="M2")


def test_outro_operador_e_recusado(joyce):
    with pytest.raises(PosIntentError):
        _resgatar(_carimbo(joyce, operador="pos:fran"), operador="pos:marina")


def test_uso_unico_venda_nova_pede_o_gerente_de_novo(joyce):
    token = _carimbo(joyce)
    _resgatar(token, pedido="req-1")
    with pytest.raises(PosIntentError) as exc:
        _resgatar(token, pedido="req-2")
    assert "já foi usada" in exc.value.recovery


def test_a_mesma_venda_pode_reapresentar_o_carimbo(joyce):
    """A fila sem conexão e a recusa da maquininha reenviam o MESMO fechamento."""
    token = _carimbo(joyce)
    _resgatar(token, pedido="req-1")
    assert _resgatar(token, pedido="req-1").get_username() == "joyce"


def test_sem_chave_da_venda_o_carimbo_nao_volta(joyce):
    token = _carimbo(joyce)
    _resgatar(token, pedido="")
    with pytest.raises(PosIntentError):
        _resgatar(token, pedido="")


def test_carimbo_adulterado_e_recusado(joyce):
    token = _carimbo(joyce)
    with pytest.raises(PosIntentError):
        _resgatar(token[:-2] + ("aa" if not token.endswith("aa") else "bb"))


def test_gerente_que_perdeu_a_permissao_nao_assina_mais(joyce):
    token = _carimbo(joyce)
    joyce.user_permissions.clear()
    joyce = get_user_model().objects.get(pk=joyce.pk)
    with pytest.raises(PosIntentError):
        _resgatar(token)
