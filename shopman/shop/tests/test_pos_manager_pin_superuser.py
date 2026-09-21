"""Superusuário não assina exceção do caixa por PIN nem por crachá.

O PIN é credencial de balcão: curta, digitada à vista da fila e, no elenco de
dev, a mesma para todo mundo. ``has_perm`` de superusuário é sempre True, então
a conta passava no ``cashman.adjust_shift`` e qualquer operador que soubesse o
PIN do ``admin`` se autorizava escolhendo "Admin" em "Quem autoriza?".
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


def test_superusuario_nao_autoriza_por_pin_nem_por_cracha():
    _com_pin_e_cracha(
        get_user_model().objects.create_user("admin", password="x", is_staff=True, is_superuser=True)
    )

    assert _verify_manager_pin("admin", "1234", operator_username="pos:fran") is None
    assert _verify_manager_badge(BADGE, operator_username="pos:fran") is None


def test_gerente_de_verdade_continua_autorizando():
    gerente = get_user_model().objects.create_user("joyce", password="x", is_staff=True)
    gerente.user_permissions.add(
        Permission.objects.get(content_type__app_label="cashman", codename="adjust_shift")
    )
    _com_pin_e_cracha(gerente)

    assert _verify_manager_pin("joyce", "1234", operator_username="pos:fran").username == "joyce"
    assert _verify_manager_badge(BADGE, operator_username="pos:fran").username == "joyce"
