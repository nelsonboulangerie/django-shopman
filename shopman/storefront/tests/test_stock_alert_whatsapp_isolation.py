"""O "Me avise" por WhatsApp sob a isolação por construção dos flows do ManyChat.

Duas garantias do lado do aviso, gêmeas das da campanha:

- **contato ocupado volta depois da janela** — o ManyChat recusou antes de escrever
  qualquer campo porque a pessoa ainda tem outra mensagem com flow assentando. Isso não
  é "tentar novamente" nem resultado incerto: a entrega volta à fila e a directive é
  reagendada para depois da janela, sem gastar tentativa;
- **no ensaio, só a lista recebe** — quem está fora (inclusive a assinatura anônima)
  é suprimido no claim com motivo explícito, antes de virar tentativa.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.protocols import NotificationResult
from shopman.shop.services import manychat_marketing_safety
from shopman.storefront.models import StockAlertDelivery
from shopman.storefront.services import stock_alerts
from shopman.storefront.stock_alert_delivery import StockAlertDeliveryHandler

pytestmark = pytest.mark.django_db

PHONE = "+5543999990077"


@pytest.fixture(autouse=True)
def configured_channel():
    from shopman.shop.models import Channel

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})


@pytest.fixture
def canary(settings, monkeypatch):
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "canary"
    settings.SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS = ("CLI-CANARIO",)
    monkeypatch.setattr(manychat_marketing_safety, "serialization_available", lambda: True)


def _available():
    return MagicMock(can_add_to_cart=True, available_qty=3)


def _message(delivery, *, attempts=1):
    return MagicMock(payload={"delivery_id": delivery.pk}, attempts=attempts, status="running")


def _customer(ref: str, phone: str) -> Customer:
    return Customer.objects.create(ref=ref, first_name="Ana", phone=phone)


def test_busy_subscriber_requeues_the_delivery_and_defers_the_directive_past_the_window():
    sub = stock_alerts.subscribe("SKU-BUSY", phone=PHONE, adult_declared=True)
    busy = NotificationResult(success=False, error="subscriber_busy", retry_after_seconds=120)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch("shopman.shop.notifications.notify", return_value=busy) as notify,
    ):
        assert stock_alerts.notify_back_in_stock(sub.sku) == 1
        delivery = StockAlertDelivery.objects.get()
        message = _message(delivery, attempts=1)
        before = timezone.now()
        # Não levanta DirectiveTransientError: o backoff de 2 s cairia dentro da janela.
        StockAlertDeliveryHandler().handle(message=message, ctx={})

    notify.assert_called_once()
    delivery.refresh_from_db()
    assert delivery.status == StockAlertDelivery.Status.QUEUED
    assert delivery.last_error_code == "subscriber_busy"
    assert delivery.claimed_at is None
    assert message.status == "queued"
    assert message.attempts == 0, "ocupado não gasta tentativa"
    assert message.available_at >= before + timedelta(seconds=120)
    message.save.assert_called_once_with(update_fields=["status", "attempts", "available_at", "updated_at"])
    sub.refresh_from_db()
    assert sub.notified_at is None


def test_after_the_window_the_same_delivery_is_claimed_and_accepted():
    sub = stock_alerts.subscribe("SKU-BUSY-THEN-FREE", phone=PHONE, adult_declared=True)
    results = iter((
        NotificationResult(success=False, error="subscriber_busy", retry_after_seconds=120),
        NotificationResult(success=True),
    ))

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch("shopman.shop.notifications.notify", side_effect=lambda **kw: next(results)),
    ):
        stock_alerts.notify_back_in_stock(sub.sku)
        delivery = StockAlertDelivery.objects.get()
        StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})
        StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})

    delivery.refresh_from_db()
    assert delivery.status == StockAlertDelivery.Status.ACCEPTED


def test_canary_suppresses_a_contact_outside_the_list_before_any_provider_call(canary):
    outsider = _customer("CLI-FORA", PHONE)
    sub = stock_alerts.subscribe("SKU-CANARY-OUT", customer=outsider, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch("shopman.shop.notifications.notify") as notify,
    ):
        stock_alerts.notify_back_in_stock(sub.sku)
        delivery = StockAlertDelivery.objects.get()
        StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})

    notify.assert_not_called()
    delivery.refresh_from_db()
    assert delivery.status == StockAlertDelivery.Status.SUPPRESSED
    assert delivery.last_error_code == "whatsapp_canary_recipient_excluded"


def test_canary_suppresses_the_anonymous_subscription(canary):
    sub = stock_alerts.subscribe("SKU-CANARY-ANON", phone=PHONE, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch("shopman.shop.notifications.notify") as notify,
    ):
        stock_alerts.notify_back_in_stock(sub.sku)
        delivery = StockAlertDelivery.objects.get()
        StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})

    notify.assert_not_called()
    delivery.refresh_from_db()
    assert delivery.last_error_code == "whatsapp_canary_recipient_excluded"


def test_canary_lets_the_listed_contact_through_with_its_ref_for_the_last_door(canary):
    listed = _customer("CLI-CANARIO", "+5543999990078")
    sub = stock_alerts.subscribe("SKU-CANARY-IN", customer=listed, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=True),
        ) as notify,
    ):
        stock_alerts.notify_back_in_stock(sub.sku)
        delivery = StockAlertDelivery.objects.get()
        StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})

    notify.assert_called_once()
    context = notify.call_args.kwargs["context"]
    assert context["customer_ref"] == "CLI-CANARIO"
    delivery.refresh_from_db()
    assert delivery.status == StockAlertDelivery.Status.ACCEPTED


def test_canary_does_not_touch_an_alert_that_leaves_by_another_backend(canary, monkeypatch):
    """O ensaio é do ManyChat: aviso configurado para outro transporte segue o fluxo dele."""
    outsider = _customer("CLI-EMAIL", PHONE)
    sub = stock_alerts.subscribe("SKU-CANARY-EMAIL", customer=outsider, adult_declared=True)
    monkeypatch.setattr(stock_alerts, "delivery_backend", lambda _sub: "email")

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=True),
        ) as notify,
    ):
        stock_alerts.notify_back_in_stock(sub.sku)
        delivery = StockAlertDelivery.objects.get()
        StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})

    notify.assert_called_once()
    assert notify.call_args.kwargs["backend"] == "email"


def test_blocked_mode_keeps_todays_behaviour_the_adapter_refuses(settings):
    """`blocked` é exatamente o comportamento de antes: nada suprimido no claim."""
    settings.SHOPMAN_MARKETING_WHATSAPP_MODE = "blocked"
    outsider = _customer("CLI-BLOCKED", PHONE)
    sub = stock_alerts.subscribe("SKU-BLOCKED", customer=outsider, adult_declared=True)

    with (
        patch("shopman.storefront.services.sku_state.resolve", return_value=_available()),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=False, error="Adapter manychat returned False"),
        ) as notify,
    ):
        stock_alerts.notify_back_in_stock(sub.sku)
        delivery = StockAlertDelivery.objects.get()
        with pytest.raises(Exception, match="provider rejected"):
            StockAlertDeliveryHandler().handle(message=_message(delivery), ctx={})

    notify.assert_called_once()
    delivery.refresh_from_db()
    assert delivery.status == StockAlertDelivery.Status.RETRYABLE
