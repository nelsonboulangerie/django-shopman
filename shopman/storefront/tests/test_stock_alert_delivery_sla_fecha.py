"""O aviso de entrega atrasada do "voltou ao estoque" fecha quando nada mais está atrasado (#3108)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from shopman.backstage.models import OperatorAlert
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db


def test_sla_alert_closes_when_no_delivery_is_late():
    create_operator_alert(
        type="stock_alert_delivery_stuck", severity="warning",
        message="2 aviso(s) excederam 10 min", dedupe_key="stock-alert-delivery-sla",
    )
    alert = OperatorAlert.objects.get(type="stock_alert_delivery_stuck")
    call_command("check_stock_alert_delivery_sla", stdout=StringIO())
    alert.refresh_from_db()
    assert alert.resolved_by == "sistema: nenhuma entrega de aviso de estoque atrasada"
