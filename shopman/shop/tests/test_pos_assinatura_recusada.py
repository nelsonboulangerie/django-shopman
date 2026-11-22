"""A assinatura do gerente que não conferiu diz o fato e o próximo passo (#2667).

"Aprovação gerencial inválida." era jargão sem saída. O Gestor mostra só a frase
da recusa (``detail``), o PDV lê o ``recovery`` antes dela; as duas falam da porta
que o gerente usou, e com o crachá nenhuma manda digitar o PIN de novo (#2691).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from shopman.doorman.models import PinCredential

from shopman.shop.services.pos import (
    MANAGER_BADGE_RECOVERY,
    MANAGER_BADGE_REFUSED,
    MANAGER_PIN_RECOVERY,
    MANAGER_PIN_REFUSED,
    PosIntentError,
    validate_manager_override,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gerente():
    user = get_user_model().objects.create_user("joyce", password="x", is_staff=True, is_superuser=True)
    PinCredential.set_for(user, "1234")
    return user


def _recusa(approval, **kwargs) -> PosIntentError:
    with pytest.raises(PosIntentError) as caught:
        validate_manager_override(approval, operator_username="fran", action="teste", **kwargs)
    return caught.value


def test_pin_errado_diz_o_fato_e_pede_o_pin_de_novo(gerente):
    erro = _recusa({"username": "joyce", "pin": "0000"})

    assert erro.code == "manager_approval_invalid"
    assert erro.message == MANAGER_PIN_REFUSED == "O PIN não confere com o gerente escolhido. Digite de novo."
    assert erro.recovery == MANAGER_PIN_RECOVERY


def test_cracha_que_nao_e_de_gerente_nao_manda_digitar_o_pin_de_novo(gerente):
    erro = _recusa({"badge": "cracha-desconhecido"})

    assert erro.message == MANAGER_BADGE_REFUSED
    assert erro.recovery == MANAGER_BADGE_RECOVERY
    assert "de novo" not in erro.message


def test_quem_chama_ainda_pode_dar_o_proprio_passo_seguinte(gerente):
    erro = _recusa({"username": "joyce", "pin": "0000"}, recovery_invalid="Peça a outro gerente.")

    assert erro.recovery == "Peça a outro gerente."


def test_nenhuma_frase_da_recusa_e_jargao(gerente):
    for approval in ({"username": "joyce", "pin": "0000"}, {"badge": "x"}):
        erro = _recusa(approval)
        assert "inválida" not in erro.message
        assert "gerencial" not in erro.message
