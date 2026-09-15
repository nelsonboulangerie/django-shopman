from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.offerman.models import ListingItem
from shopman.orderman.models import Order, Session

from shopman.shop.models import Coupon, DeliveryZone, Promotion, Shop
from shopman.shop.services import checkout as checkout_service

pytestmark = pytest.mark.django_db

EFI_SANDBOX = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
        "cash": None,
    },
    SHOPMAN_EFI={
        "sandbox": True,
        "client_id": "",
        "client_secret": "",
        "certificate_path": "",
        "pix_key": "",
    },
)


@EFI_SANDBOX
def test_direct_checkout_bypass_is_blocked_before_order_and_retry_can_change_method(
    cart_session,
    product,
):
    session_key = cart_session.session["cart_session_key"]
    ListingItem.objects.filter(listing__ref="web", product=product).update(price_q=1001)
    cart = Session.objects.get(session_key=session_key, channel_ref="web")
    authoritative_total_q = sum(int(item["qty"]) * 1001 for item in cart.items)
    key = "pix-sandbox-blocked-then-cash"
    common = {
        "customer": {"name": "Ana", "phone": "+5543999990001"},
        "fulfillment_type": "pickup",
    }

    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    with pytest.raises(OrderingValidationError) as caught:
        checkout_service.process(
            session_key=session_key,
            channel_ref="web",
            data={**common, "payment": {"method": "pix"}},
            idempotency_key=key,
            expected_total_q=authoritative_total_q,
        )

    assert caught.value.code == "pix_test_amount_limit"
    assert caught.value.context["current_amount_q"] == authoritative_total_q
    assert not Order.objects.filter(session_key=session_key).exists()
    cart = Session.objects.get(session_key=session_key, channel_ref="web")
    assert cart.state == "open"

    # A recusa aconteceu antes do claim/commit: a mesma tentativa pode ser
    # corrigida sem criar pedido duplicado nem ficar presa em replay de erro.
    result = checkout_service.process(
        session_key=session_key,
        channel_ref="web",
        data={**common, "payment": {"method": "cash"}},
        idempotency_key=key,
        expected_total_q=authoritative_total_q,
    )
    assert result.total_q == authoritative_total_q
    assert Order.objects.filter(session_key=session_key).count() == 1


@EFI_SANDBOX
def test_checkout_error_mapping_keeps_structured_limit_context():
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    exc = OrderingValidationError(
        code="pix_test_amount_limit",
        message="limite",
        context={"current_amount_q": 1001, "max_amount_q": 1000},
    )
    assert checkout_service.map_checkout_error(exc) is None
    mapped = checkout_service.map_order_error(exc)
    assert mapped is not None
    assert mapped.http_status == 422
    assert mapped.error_code == "pix_test_amount_limit"
    assert mapped.context["max_amount_q"] == 1000


@EFI_SANDBOX
@pytest.mark.parametrize(
    ("delivery_fee_q", "effective_total_q", "blocked"),
    [(99, 999, False), (100, 1000, False), (101, 1001, True)],
)
def test_checkout_boundary_uses_composed_discounted_total_plus_delivery(
    cart_session,
    product,
    delivery_fee_q,
    effective_total_q,
    blocked,
):
    """The gate sees 1200 merchandise - 300 coupon + delivery, to the cent."""
    from shopman.shop.projections.cart import build_cart
    from shopman.shop.services import sessions

    session_key = cart_session.session["cart_session_key"]
    ListingItem.objects.filter(listing__ref="web", product=product).update(price_q=600)
    now = timezone.now()
    promotion = Promotion.objects.create(
        ref=f"pix-composed-{effective_total_q}",
        name="Desconto composto Pix",
        type=Promotion.FIXED,
        value=300,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    Coupon.objects.create(code=f"PIX{effective_total_q}", promotion=promotion)
    shop = Shop.objects.get()
    DeliveryZone.objects.create(
        shop=shop,
        name=f"Zona {effective_total_q}",
        zone_type=DeliveryZone.ZONE_TYPE_NEIGHBORHOOD,
        match_value="Centro",
        mode=DeliveryZone.MODE_OVERRIDE,
        fee_q=delivery_fee_q,
        is_active=True,
    )
    address = {
        "formatted_address": "Rua Teste, 1 - Centro",
        "neighborhood": "Centro",
        "postal_code": "86000-000",
    }
    sessions.modify_session(
        session_key=session_key,
        channel_ref="web",
        ops=[
            {"op": "set_data", "path": "coupon_code", "value": f"PIX{effective_total_q}"},
            {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
            {"op": "set_data", "path": "delivery_address_structured", "value": address},
            {"op": "set_data", "path": "payment.method", "value": "pix"},
        ],
    )
    assert build_cart(session_key, "web").grand_total_q == effective_total_q

    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    if blocked:
        with pytest.raises(OrderingValidationError) as caught:
            checkout_service.process_ops(
                session_key=session_key,
                channel_ref="web",
                ops=[],
                idempotency_key=f"pix-composed-{effective_total_q}",
            )
        assert caught.value.code == "pix_test_amount_limit"
        assert caught.value.context["current_amount_q"] == effective_total_q
        assert not Order.objects.filter(session_key=session_key).exists()
    else:
        result = checkout_service.process_ops(
            session_key=session_key,
            channel_ref="web",
            ops=[],
            idempotency_key=f"pix-composed-{effective_total_q}",
        )
        assert result.total_q == effective_total_q
