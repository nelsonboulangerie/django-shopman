"""Fiscal outages have a bounded recovery window and a per-order terminal alert."""
from unittest.mock import Mock

import pytest
from django.utils import timezone
from shopman.fiscalman.contracts import FiscalDocumentResult
from shopman.orderman import dispatch, registry
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.handlers.fiscal import NFCeEmitHandler

pytestmark = pytest.mark.django_db


def test_fiscal_retry_window_queries_before_retry_and_alerts_on_exhaustion(monkeypatch):
    monkeypatch.setattr(dispatch, "_on_commit_callback", lambda *args: None)
    Order.objects.create(ref="FISCAL-RETRY", data={}, total_q=1000)
    backend = Mock()
    backend.emit.return_value = FiscalDocumentResult(success=False, error_code="focus_nfe_http_503", error_message="unavailable")
    backend.query_status.return_value = FiscalDocumentResult(success=False, error_code="not_found")
    handler = NFCeEmitHandler(backend)
    monkeypatch.setattr(registry, "get_directive_handler", lambda topic: handler)
    directive = Directive.objects.create(topic=handler.topic, payload={"order_ref": "FISCAL-RETRY", "items": [], "payment": {}})
    for attempt, delay in enumerate(handler.retry_delays_seconds, start=1):
        before = timezone.now()
        dispatch._process_directive(directive)
        directive.refresh_from_db()
        assert directive.status == "queued"
        assert directive.attempts == attempt
        assert delay - 1 <= (directive.available_at - before).total_seconds() <= delay + 1
        assert not OperatorAlert.objects.filter(type="fiscal_emit_failed").exists()
    dispatch._process_directive(directive)
    directive.refresh_from_db()
    assert directive.status == "failed"
    assert backend.emit.call_count == 8
    assert backend.query_status.call_count == 7
    assert OperatorAlert.objects.filter(type="fiscal_emit_failed", order_ref="FISCAL-RETRY").count() == 1
    dispatch._process_directive(directive)
    assert backend.emit.call_count == 8


def test_permanent_fiscal_refusal_alerts_on_first_attempt(monkeypatch):
    monkeypatch.setattr(dispatch, "_on_commit_callback", lambda *args: None)
    Order.objects.create(ref="FISCAL-REJECTED", data={}, total_q=1000)
    backend = Mock()
    backend.emit.return_value = FiscalDocumentResult(success=False, error_code="focus_nfe_http_400", error_message="rejected")
    handler = NFCeEmitHandler(backend)
    monkeypatch.setattr(registry, "get_directive_handler", lambda topic: handler)
    directive = Directive.objects.create(topic=handler.topic, payload={"order_ref": "FISCAL-REJECTED", "items": [], "payment": {}})
    dispatch._process_directive(directive)
    directive.refresh_from_db()
    assert directive.status == "failed"
    assert directive.attempts == 1
    assert OperatorAlert.objects.filter(type="fiscal_emit_failed", order_ref="FISCAL-REJECTED").exists()


def test_manual_retry_reopens_the_whole_window_after_exhaustion(monkeypatch):
    """"Tentar novamente" depois de esgotar: a janela volta inteira, e com consulta.

    Antes, o reprocesso reenfileirava com ``attempts`` no teto: o primeiro
    transiente (Focus ainda instável) matava a directive de novo, sem espera.
    """
    from shopman.backstage.services.orders import requeue_fiscal_emission

    monkeypatch.setattr(dispatch, "_on_commit_callback", lambda *args: None)
    order = Order.objects.create(
        ref="FISCAL-REQUEUE", status="completed", total_q=1000,
        data={"fiscal": {"issue_document": True}, "payment": {"method": "cash", "amount_q": 1000}},
    )
    backend = Mock()
    backend.emit.return_value = FiscalDocumentResult(success=False, error_code="focus_nfe_http_503", error_message="unavailable")
    backend.query_status.return_value = FiscalDocumentResult(success=False, error_code="not_found")
    handler = NFCeEmitHandler(backend)
    monkeypatch.setattr(registry, "get_directive_handler", lambda topic: handler)
    directive = Directive.objects.create(
        topic=handler.topic, status="failed", attempts=len(handler.retry_delays_seconds) + 1,
        last_error="unavailable", payload={"order_ref": order.ref, "items": [], "payment": {}},
    )

    requeue_fiscal_emission(order, actor="manager")
    directive.refresh_from_db()
    assert directive.status == "queued"
    assert directive.attempts == 1

    before = timezone.now()
    dispatch._process_directive(directive)
    directive.refresh_from_db()
    # O Focus segue fora: a directive espera o primeiro degrau da janela, não morre.
    assert directive.status == "queued"
    assert directive.attempts == 2
    delay = handler.retry_delays_seconds[1]
    assert delay - 1 <= (directive.available_at - before).total_seconds() <= delay + 1
    # A tentativa que falhou antes pode ter autorizado a nota: consulta antes do POST.
    backend.query_status.assert_called_once_with(reference=order.ref)
    assert backend.emit.call_count == 1
