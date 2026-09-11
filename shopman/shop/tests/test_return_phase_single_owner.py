"""Return record and lifecycle must not receive the same goods twice."""
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Move

from shopman.shop import lifecycle
from shopman.shop.handlers.returns import ReturnHandler, ReturnService

pytestmark = pytest.mark.django_db


def test_total_return_has_one_stock_receipt_across_phase_and_handler():
    order = Order.objects.create(ref="RETURN-OWNER", status="completed", total_q=1000)
    OrderItem.objects.create(order=order, line_id="RETURN-LINE", sku="LAB-RETURN", name="Lab", qty=Decimal("1"), unit_price_q=1000, line_total_q=1000)
    result = ReturnService.initiate_return(order, [{"line_id": "RETURN-LINE", "qty": "1"}], "Devolução sintética", "lab")
    order.refresh_from_db()
    with patch.object(lifecycle.payment, "refund"), patch.object(lifecycle.fiscal, "cancel"), patch.object(lifecycle.loyalty, "revoke"), patch.object(lifecycle.loyalty, "restore"), patch.object(lifecycle.notification, "send"):
        lifecycle.dispatch(order, "on_returned")
    from shopman.orderman.models import Directive
    ReturnHandler().handle(message=Directive.objects.get(pk=result.directive_id), ctx={})
    moves = Move.objects.filter(quant__sku="LAB-RETURN", kind=Move.Kind.RETURN)
    assert list(moves.values_list("delta", flat=True)) == [Decimal("1")]


def test_refund_failure_keeps_stock_receipt_and_retry_receives_nothing_again():
    from shopman.orderman.exceptions import DirectiveTransientError
    from shopman.orderman.models import Directive

    order = Order.objects.create(ref="RETURN-RETRY", status="completed", total_q=1000)
    OrderItem.objects.create(order=order, line_id="RETRY-LINE", sku="LAB-RETRY", name="Lab", qty=Decimal("1"), unit_price_q=1000, line_total_q=1000)
    result = ReturnService.initiate_return(order, [{"line_id": "RETRY-LINE", "qty": "1"}], "Devolução sintética", "lab")
    task = Directive.objects.get(pk=result.directive_id)
    with patch.object(ReturnService, "process_refund", return_value={"refund": {"success": False}}):
        with pytest.raises(DirectiveTransientError):
            ReturnHandler().handle(message=task, ctx={})
    order.refresh_from_db()
    assert order.data["returns"][0]["stock_processed"] is True
    assert order.data["returns"][0]["refund_processed"] is False
    with patch.object(ReturnService, "process_refund", return_value={"refund": {"success": True}}):
        ReturnHandler().handle(message=task, ctx={})
    assert Move.objects.filter(quant__sku="LAB-RETRY", kind=Move.Kind.RETURN).count() == 1
