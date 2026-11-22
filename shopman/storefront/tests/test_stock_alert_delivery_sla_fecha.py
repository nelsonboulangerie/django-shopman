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


def _indeterminate_delivery(sku: str):
    from unittest.mock import MagicMock, patch

    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import stock_alerts

    sub = stock_alerts.subscribe(sku, phone="+5543999990001", adult_declared=True)
    with patch(
        "shopman.storefront.services.sku_state.resolve",
        return_value=MagicMock(can_add_to_cart=True, available_qty=None),
    ):
        stock_alerts.notify_back_in_stock(sub.sku, source_ref=f"move-{sku}")
    delivery = StockAlertDelivery.objects.get(subscription=sub)
    delivery.status = StockAlertDelivery.Status.INDETERMINATE
    delivery.save(update_fields=["status", "updated_at"])
    create_operator_alert(
        type="stock_alert_dispatch_unknown", severity="critical",
        message=f"Aviso ao cliente com resultado incerto no ManyChat. delivery_ref={delivery.ref}",
        dedupe_key=f"stock-alert-critical:{delivery.ref}",
    )
    return delivery, OperatorAlert.objects.get(type="stock_alert_dispatch_unknown", message__contains=str(delivery.ref))


def test_uncertain_dispatch_alert_closes_once_the_delivery_has_an_outcome():
    """#3094: a conciliação definiu o resultado, o aviso de envio incerto fecha."""
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.stock_alert_delivery import resolve_settled_dispatch_alerts

    settled, settled_alert = _indeterminate_delivery("SKU-INCERTO-A")
    pending, pending_alert = _indeterminate_delivery("SKU-INCERTO-B")
    settled.status = StockAlertDelivery.Status.ACCEPTED
    settled.save(update_fields=["status", "updated_at"])

    assert resolve_settled_dispatch_alerts() == 1
    settled_alert.refresh_from_db()
    pending_alert.refresh_from_db()
    assert settled_alert.resolved_by == "sistema: entrega do aviso já tem resultado"
    assert pending_alert.resolved_at is None


def test_uncertain_dispatch_alert_closes_when_the_delivery_is_gone():
    from shopman.storefront.stock_alert_delivery import resolve_settled_dispatch_alerts

    delivery, alert = _indeterminate_delivery("SKU-INCERTO-C")
    delivery.delete()
    assert resolve_settled_dispatch_alerts() == 1
    alert.refresh_from_db()
    assert alert.resolved_by == "sistema: entrega do aviso não existe mais"
