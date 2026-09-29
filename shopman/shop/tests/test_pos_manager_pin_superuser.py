"""Superusuário assina exceção do caixa ("Quem autoriza?") por PIN e por crachá.

O PIN é individual, em HMAC, com limite de tentativas e bloqueio: o dono que
cadastrou o dele assina como qualquer gerente. O risco concreto era o PIN
compartilhado do seed, e esse continua fechado no ``setup_operators``. Quem opera
não se autoriza, superusuário ou não.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from shopman.doorman.models import PinCredential

from shopman.shop.services.pos import _verify_manager_badge, _verify_manager_pin

pytestmark = pytest.mark.django_db

BADGE = "abcdef012345"


def _com_pin_e_cracha(user):
    PinCredential.set_for(user, "1234")
    cred = PinCredential.objects.get(user=user)
    cred.set_badge(BADGE)
    cred.save(update_fields=["badge_hash"])
    return user


def _dono():
    return _com_pin_e_cracha(
        get_user_model().objects.create_user("admin", password="x", is_staff=True, is_superuser=True)
    )


def test_superusuario_autoriza_por_pin_e_por_cracha():
    _dono()

    assert _verify_manager_pin("admin", "1234", operator_username="pos:fran").username == "admin"
    assert _verify_manager_badge(BADGE, operator_username="pos:fran").username == "admin"


def test_superusuario_com_pin_errado_nao_autoriza():
    _dono()

    assert _verify_manager_pin("admin", "0000", operator_username="pos:fran") is None


def test_superusuario_nao_autoriza_a_propria_operacao():
    _dono()

    assert _verify_manager_pin("admin", "1234", operator_username="pos:admin") is None
    assert _verify_manager_badge(BADGE, operator_username="pos:admin") is None


def test_quem_autoriza_lista_o_superusuario_menos_quando_ele_opera():
    from shopman.backstage.projections.pos import _manager_cards

    dono = _dono()
    fran = get_user_model().objects.create_user("fran", password="x", is_staff=True)

    assert [c["username"] for c in _manager_cards(fran)] == ["admin"]
    assert _manager_cards(dono) == ()


def test_gerente_de_verdade_continua_autorizando():
    gerente = get_user_model().objects.create_user("joyce", password="x", is_staff=True)
    gerente.user_permissions.add(
        Permission.objects.get(content_type__app_label="cashman", codename="adjust_shift")
    )
    _com_pin_e_cracha(gerente)

    assert _verify_manager_pin("joyce", "1234", operator_username="pos:fran").username == "joyce"
    assert _verify_manager_badge(BADGE, operator_username="pos:fran").username == "joyce"
