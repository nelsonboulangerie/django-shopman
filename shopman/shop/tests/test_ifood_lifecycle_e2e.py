"""Hermetic FOOD rehearsal: real domain services, local fiscal, no external I/O."""

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.fiscalman.contracts import FiscalDocumentResult
from shopman.offerman.models import Product
from shopman.orderman import registry
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive, Fulfillment, Order
from shopman.orderman.signals import order_changed
from shopman.stockman.adapters.sku_validation import reset_sku_validator
from shopman.stockman.models import Hold, Position, PositionKind, Quant
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.handlers.fiscal import NFCeEmitHandler
from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler, on_order_status_changed
from shopman.shop.handlers.lifecycle_phase import LifecyclePhaseHandler
from shopman.shop.models import Channel, Shop
from shopman.shop.services import cancellation, ifood_auth, ifood_cancellation, ifood_events, kds, operator_orders

pytestmark = pytest.mark.django_db


class LocalFiscalBackend:
    """Only fiscal provider boundary is substituted; the fiscal handler is real."""

    def __init__(self):
        self.emissions = []

    def emit(self, **payload):
        self.emissions.append(payload)
        return FiscalDocumentResult(success=True, status="authorized", access_key="local-rehearsal-key")


@pytest.fixture
def rehearsal(settings, django_capture_on_commit_callbacks, request):
    settings.SHOPMAN_IFOOD = {"merchant_id": "local-merchant", "api_base": "https://ifood.invalid"}
    settings.SHOPMAN_FISCAL_ADAPTER = f"{__name__}.LocalFiscalBackend"
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.always"
    settings.STOCKMAN = {**settings.STOCKMAN, "SKU_VALIDATOR": "shopman.stockman.adapters.noop.NoopSkuValidator"}
    reset_sku_validator()
    fiscal_pool.reset()
    request.addfinalizer(reset_sku_validator)
    request.addfinalizer(fiscal_pool.reset)
    Shop.objects.create(name="Local iFood rehearsal")
    Channel.objects.create(ref="ifood", name="iFood", config={
        "confirmation": {"mode": "manual"}, "payment": {"method": "external", "timing": "external"},
        "fulfillment": {"prep_start": "operator", "courier": "none"},
        "stock": {"check_on_commit": False, "allow_untracked": False},
        "notification": {"backend": "console"},
    })
    KDSInstance.objects.create(ref="local-picking", name="Separação local", type="picking", is_active=True)
    raw = json.loads((Path(__file__).parent / "fixtures" / "ifood_order_real.json").read_text())
    # Preserve the captured FOOD items/prices/options. Only merchant isolation
    # and the logistics variant differ from the original MERCHANT fixture.
    raw["merchant"]["id"] = "local-merchant"
    raw["delivery"]["deliveredBy"] = "IFOOD"
    position = Position.objects.create(ref="local-stock", name="Stock", kind=PositionKind.PHYSICAL, is_saleable=True)
    for item in raw["items"]:
        sku = item.get("externalCode") or item["id"]
        Product.objects.create(sku=sku, name=item["name"], unit="un", is_sellable=True, base_price_q=500)
        StockMovements.receive(quantity=Decimal("10"), sku=sku, position=position)

    calls = []
    def transport(_session, method, url, **kwargs):
        calls.append((method.upper(), url, deepcopy(kwargs.get("json"))))
        if method.upper() == "GET" and url == f"https://ifood.invalid/order/v1.0/orders/{raw['id']}":
            return SimpleNamespace(status_code=200, json=lambda: deepcopy(raw), text="")
        if method.upper() == "POST" and url.startswith("https://ifood.invalid/order/v1.0/"):
            action = url.rsplit("/", 1)[-1]
            if action in {"acknowledgment", "confirm", "readyToPickup", "dispatch", "requestCancellation"}:
                return SimpleNamespace(status_code=202, json=lambda: {}, text="")
        raise AssertionError(f"Unexpected HTTP blocked in local rehearsal: {method} {url}")

    backend = fiscal_pool.get_backend()
    handlers = [LifecyclePhaseHandler(), IFoodStatusCallbackHandler(), NFCeEmitHandler(backend)]
    handler_map = {handler.topic: handler for handler in handlers}

    def settle():
        # Drain only locally configured handlers; notifications remain durable
        # queued records and never reach email, messaging or another provider.
        for _ in range(20):
            pending = list(Directive.objects.filter(topic__in=handler_map, status="queued", available_at__lte=timezone.now()))
            if not pending:
                break
            with django_capture_on_commit_callbacks(execute=True):
                for directive in pending:
                    _process_directive(directive)
        assert not Directive.objects.filter(topic__in=handler_map, status__in=["queued", "running", "failed"]).exists()

    def act(action):
        with django_capture_on_commit_callbacks(execute=True):
            result = action()
        settle()
        return result

    def event(code, event_id=None):
        return act(lambda: ifood_events.process_events([{
            "id": event_id or f"local-{code}", "code": code, "orderId": raw["id"], "merchantId": "local-merchant",
        }]))

    with (
        patch.dict(registry._registry._directive_handlers, handler_map, clear=True),
        patch.object(ifood_auth, "get_access_token", return_value="local-test-token"),
        patch("requests.sessions.Session.request", new=transport),
    ):
        # Test settings intentionally omit OAuth, so app startup omits this
        # receiver. Connect the real production receiver for this local run.
        order_changed.connect(on_order_status_changed, dispatch_uid="local_ifood_rehearsal", weak=False)
        try:
            yield SimpleNamespace(raw=raw, event=event, act=act, calls=calls, fiscal=backend)
        finally:
            order_changed.disconnect(dispatch_uid="local_ifood_rehearsal")


def _quantities():
    return {quant.sku: quant.quantity for quant in Quant.objects.all()}


def _ingest_and_prepare(rehearsal):
    assert rehearsal.event("PLC")["ingested"] == 1
    order = Order.objects.get(external_ref=rehearsal.raw["id"])
    assert order.status == "new"
    assert order.session_key
    assert Hold.objects.count() == len(rehearsal.raw["items"])
    assert set(Hold.objects.values_list("status", flat=True)) == {HoldStatus.PENDING}
    assert not KDSTicket.objects.exists()
    assert rehearsal.event("CFM")["ingested"] == 1
    order.refresh_from_db()
    assert order.status == "accepted"
    assert set(Hold.objects.values_list("status", flat=True)) == {HoldStatus.FULFILLED}
    expected = {(item.get("externalCode") or item["id"]): Decimal("10") - Decimal(str(item["quantity"]))
                for item in rehearsal.raw["items"]}
    assert _quantities() == expected
    assert not KDSTicket.objects.exists()
    rehearsal.act(lambda: operator_orders.advance_order(order, actor="local-operator"))
    order.refresh_from_db()
    assert order.status == "preparing"
    assert KDSTicket.objects.filter(session_key=order.session_key).exists()
    assert sum(len(ticket.items) for ticket in KDSTicket.objects.all()) == len(rehearsal.raw["items"])
    return order, expected


def test_food_fixture_full_lifecycle_keeps_stock_kds_and_fiscal_exactly_once(rehearsal):
    order, expected = _ingest_and_prepare(rehearsal)
    for ticket in KDSTicket.objects.filter(session_key=order.session_key):
        assert rehearsal.act(lambda ticket=ticket: kds.complete_ticket(ticket, actor="local-operator"))
    order.refresh_from_db()
    assert order.status == "ready"
    assert rehearsal.event("DSP")["ingested"] == 1
    assert rehearsal.event("CON")["ingested"] == 1
    order.refresh_from_db()
    assert order.status == "completed"
    assert order.fulfillments.get().status == Fulfillment.Status.DELIVERED
    assert order.data["nfce_access_key"] == "local-rehearsal-key"
    assert len(rehearsal.fiscal.emissions) == 1
    assert len(rehearsal.fiscal.emissions[0]["items"]) == len(rehearsal.raw["items"])
    assert _quantities() == expected
    ticket_count, event_count = KDSTicket.objects.count(), order.events.count()
    for code in ("PLC", "CFM", "DSP", "CON"):
        assert rehearsal.event(code)["deduped"] == 1
    assert KDSTicket.objects.count() == ticket_count
    assert order.events.count() == event_count
    assert len(rehearsal.fiscal.emissions) == 1
    assert _quantities() == expected
    actions = [url.rsplit("/", 1)[-1] for method, url, _ in rehearsal.calls if method == "POST"]
    assert "confirm" not in actions and "dispatch" not in actions
    assert actions.count("readyToPickup") == 1


def test_food_cancellation_waits_for_can_then_restores_stock_and_cancels_kds(rehearsal):
    order, expected = _ingest_and_prepare(rehearsal)
    rehearsal.act(lambda: cancellation.cancel(
        order, reason="Sem condições de atender", actor="local-operator", extra_data={"ifood_cancellation_code": "501"},
    ))
    order.refresh_from_db()
    assert order.status == "preparing"
    assert order.data[ifood_cancellation.KEY]["state"] == "sent"
    assert _quantities() == expected
    assert set(KDSTicket.objects.values_list("status", flat=True)) == {"pending"}
    assert rehearsal.event("CAN")["ingested"] == 1
    order.refresh_from_db()
    assert order.status == "cancelled"
    assert order.data[ifood_cancellation.KEY]["state"] == "confirmed"
    assert set(KDSTicket.objects.values_list("status", flat=True)) == {"cancelled"}
    assert all(qty == Decimal("10") for qty in _quantities().values())
    assert not rehearsal.fiscal.emissions
    assert rehearsal.event("CAN")["deduped"] == 1
    assert all(qty == Decimal("10") for qty in _quantities().values())
    actions = [url.rsplit("/", 1)[-1] for method, url, _ in rehearsal.calls if method == "POST"]
    assert actions.count("requestCancellation") == 1
