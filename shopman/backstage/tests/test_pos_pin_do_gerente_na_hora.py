"""O PIN do gerente é conferido no próprio diálogo, não depois do "Recebi o Pix".

Beta test de 05/11/2026 (PDV-05). O diálogo "Quem autoriza?" guardava o PIN e
fechava; o PIN errado só voltava no fechamento, como recusa da venda, depois de
o operador já ter confirmado o Pix com o cliente. A conferência agora é a MESMA
do fechamento (``validate_manager_override``), com a mesma trava do PIN.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from shopman.cashman.models import Shift
from shopman.doorman.models import PinCredential

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/pos/manager-approval/check/"
PIN = "4321"


def _grant(user, codename: str) -> None:
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


@pytest.fixture
def balcao(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    operator = get_user_model().objects.create_user(username="marina", password="x", is_staff=True)
    _grant(operator, "operate_pos")
    manager = get_user_model().objects.create_user(username="joyce", password="x", is_staff=True)
    _grant(manager, "adjust_shift")
    PinCredential.set_for(manager, PIN)
    client.force_login(operator)
    return {"client": client, "manager": manager}


def _check(client, pin: str, username: str = "joyce"):
    return client.post(
        URL, {"manager_approval": {"username": username, "pin": pin}}, content_type="application/json",
    )


def test_pin_certo_responde_quem_assina(balcao):
    response = _check(balcao["client"], PIN)
    assert response.status_code == 200, response.content
    assert response.json() == {"approved_by": "joyce"}


def test_pin_errado_recusa_no_dialogo_e_conta_na_trava(balcao):
    response = _check(balcao["client"], "0000")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "manager_approval_invalid"
    assert body["error"]["field"] == "manager_approval"
    balcao["manager"].pin_credential.refresh_from_db()
    assert balcao["manager"].pin_credential.attempts == 1


def test_sem_pin_pede_a_aprovacao(balcao):
    response = balcao["client"].post(URL, {}, content_type="application/json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "manager_approval_required"


def test_quem_nao_opera_o_pdv_nao_confere_pin(client):
    Shop.objects.create(name="Nelson", brand_name="Nelson")
    stranger = get_user_model().objects.create_user(username="visita", password="x", is_staff=True)
    client.force_login(stranger)
    assert _check(client, PIN).status_code in (401, 403)
