"""Alertas do Admin seguem o público de quem lê (beta test 05/11/2026, ADM-05).

O Dashboard e a trilha de alertas mostravam à Gerente "o caixa fechou fora da
tolerância: falta de R$ 3,00". A diferença do caixa é do dono (público
``finance``): quem sabe o esperado não conta às cegas (dono, 08/10/2026). A régua
é a mesma do sino do Gestor, ``visible_alert_audiences``.
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.dashboard import build_dashboard

pytestmark = pytest.mark.django_db


@pytest.fixture
def gerente():
    user = User.objects.create_user("gerente-alertas", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="shop", codename="manage_orders"),
        Permission.objects.get(content_type__app_label="backstage", codename="view_operatoralert"),
    )
    return User.objects.get(pk=user.pk)


@pytest.fixture
def alertas():
    caixa = OperatorAlert.objects.create(
        type="cash_out_of_tolerance",
        severity="warning",
        message="O caixa fechou fora da tolerância: falta de R$ 3,00",
        audience="finance",
    )
    pedido = OperatorAlert.objects.create(
        type="stale_new_order",
        severity="warning",
        message="Pedido novo parado",
        audience="orders",
    )
    return caixa, pedido


def test_dashboard_da_gerente_nao_mostra_a_diferenca_do_caixa(gerente, alertas):
    caixa, pedido = alertas
    pks = {a.pk for a in build_dashboard(gerente).operator_alerts}
    assert pedido.pk in pks
    assert caixa.pk not in pks


def test_dashboard_do_dono_mostra_tudo(alertas):
    dono = User.objects.create_superuser("dono-alertas", password="pw")
    pks = {a.pk for a in build_dashboard(dono).operator_alerts}
    assert pks == {a.pk for a in alertas}


def test_trilha_de_alertas_do_admin_tem_o_mesmo_recorte(gerente, alertas):
    caixa, pedido = alertas
    request = RequestFactory().get("/admin/backstage/operatoralert/")
    request.user = gerente
    queryset = site._registry[OperatorAlert].get_queryset(request)
    assert pedido in queryset
    assert caixa not in queryset
