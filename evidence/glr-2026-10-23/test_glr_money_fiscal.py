# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
import pytest
from shopman.fiscalman.contracts import FiscalDocumentResult
from shopman.orderman.exceptions import DirectiveTerminalError

from shopman.shop.handlers.fiscal import NFCeEmitHandler
from shopman.shop.tests.test_fiscal_handlers import (  # noqa
    FakeBackend,
    _emit_directive,
    _error,
    fiscal_backend_configured,
    order,
)

pytestmark = pytest.mark.django_db

def test_live_order_retry_while_processing_reposts_and_goes_terminal(order, fiscal_backend_configured):
    processing = FiscalDocumentResult(success=False, status="processing", error_code="focus_nfe_processing")
    backend = FakeBackend(query_result=processing, emit_result=_error("focus_nfe_http_422", "ja processada"))
    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=_emit_directive(order, attempts=2), ctx={})
    assert backend.emit_calls == 1
    assert backend.query_calls == 2


def test_cancel_handler_overwrites_concurrent_order_data(order, fiscal_backend_configured):
    from shopman.fiscalman.contracts import FiscalCancellationResult
    from shopman.orderman.models import Directive, Order

    from shopman.shop.handlers.fiscal import NFCeCancelHandler
    from shopman.shop.services import fiscal as fiscal_service

    data = dict(order.data); data["nfce_access_key"] = "4125" + "0" * 40
    Order.objects.filter(pk=order.pk).update(data=data, status=Order.Status.CANCELLED)

    class Concurrent(FakeBackend):
        def cancel(self, *, reference, reason):
            o = Order.objects.get(pk=order.pk)
            d = dict(o.data); d["payment"] = {"refund_status": "written_by_other_worker"}
            Order.objects.filter(pk=order.pk).update(data=d)
            return FiscalCancellationResult(success=True, protocol_number="P1")

    import unittest.mock as m
    with m.patch.object(fiscal_service, "cancellation_path", return_value={"path": "cancel"}):
        d = Directive.objects.create(topic="fiscal.cancel_nfce", payload={"order_ref": order.ref, "reason": "cancelado pelo operador x"})
        NFCeCancelHandler(Concurrent()).handle(message=d, ctx={})
    o = Order.objects.get(pk=order.pk)
    assert o.data.get("nfce_cancelled") is True
    assert "payment" not in o.data  # escrita concorrente perdida
