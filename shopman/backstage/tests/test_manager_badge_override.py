"""O gerente autoriza com o CRACHÁ, não só com o PIN.

Sangria e pedido de troco são a hora em que o gerente mais aparece no balcão, e
era justamente onde o crachá não valia: o desafio só aceitava username + PIN,
então quem tinha o crachá no pescoço digitava mesmo assim.

⚠️ Crachá e PIN são o mesmo nível de prova aqui, e é decisão: identificam a
MESMA pessoa contra a mesma credencial, exigem a mesma permissão
(``cashman.adjust_shift``), e produzem a mesma assinatura em ``Entry.approved_by``.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman.models import Shift
from shopman.doorman.models import PinCredential

from shopman.shop.services.pos import validate_manager_override
from shopman.shop.services.pos_intent import PosIntentError

pytestmark = pytest.mark.django_db


def _com_permissao(username: str, *codenames: str):
    user = get_user_model().objects.create_user(username=username, password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def gerente():
    user = _com_permissao("joyce", "adjust_shift", "operate_pos")
    PinCredential.set_for(user, "1234")
    return user


def test_o_cracha_do_gerente_autoriza(gerente):
    token = PinCredential.issue_badge(gerente)

    aprovador = validate_manager_override(
        {"badge": token}, operator_username="fran", action="cash_sangria"
    )

    assert aprovador == gerente


def test_o_pin_continua_valendo(gerente):
    aprovador = validate_manager_override(
        {"username": "joyce", "pin": "1234"}, operator_username="fran", action="cash_sangria"
    )

    assert aprovador == gerente


def test_cracha_de_quem_nao_autoriza_e_recusado():
    """O balconista tem crachá e opera o PDV, e não assina exceção.

    É a mesma permissão que o PIN exige. Aceitar o crachá de qualquer operador
    transformaria "chamar o gerente" em "encostar o próprio crachá".
    """
    balconista = _com_permissao("fran", "operate_pos")
    PinCredential.set_for(balconista, "1111")
    token = PinCredential.issue_badge(balconista)

    with pytest.raises(PosIntentError) as exc:
        validate_manager_override({"badge": token}, operator_username="fran", action="cash_sangria")

    assert exc.value.code == "manager_approval_invalid"


def test_cracha_inexistente_e_recusado(gerente):
    with pytest.raises(PosIntentError) as exc:
        validate_manager_override(
            {"badge": "ffffffffffff"}, operator_username="fran", action="cash_sangria"
        )

    assert exc.value.code == "manager_approval_invalid"


def test_sem_cracha_e_sem_pin_pede_autorizacao(gerente):
    with pytest.raises(PosIntentError) as exc:
        validate_manager_override({}, operator_username="fran", action="cash_sangria")

    assert exc.value.code == "manager_approval_required"
    # A frase precisa citar as DUAS portas: quem tem crachá não pode ler
    # "aprove com o PIN" e concluir que o crachá não serve aqui.
    assert "crachá" in exc.value.recovery


def test_cracha_revogado_para_de_autorizar(gerente):
    token = PinCredential.issue_badge(gerente)
    PinCredential.objects.get(user=gerente).clear_badge()

    with pytest.raises(PosIntentError):
        validate_manager_override({"badge": token}, operator_username="fran", action="cash_sangria")
