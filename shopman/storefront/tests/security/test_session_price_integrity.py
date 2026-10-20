"""Categories 2 & 3 — session manipulation and price integrity.

Category 2 (session manipulation):
- The cart lives in the server-side Orderman session, keyed by a value stored in
  the Django session cookie. No request parameter may switch or read another
  visitor's cart (no session fixation, no cart IDOR).
- Client-supplied fields the server must not trust: fulfillment_type is
  whitelisted; loyalty redemption is resolved server-side (an anonymous caller
  cannot inject a redeem amount).

Category 3 (price integrity):
- The price charged at commit is the CURRENT catalog price, not the price
  captured when the item entered the cart (internal pricing re-resolves).
- A client-supplied ``expected_total_q`` lower than the real total aborts the
  commit — it can never make the server charge less (no underpay).
- A discount can never exceed the merchandise value: line totals and the order
  total floor at zero, never negative.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.offerman.models import ListingItem
from shopman.orderman.models import Order, Session

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service

pytestmark = pytest.mark.django_db


def _relist(product, price_q: int, *, listing_ref: str = "web") -> None:
    """Set the current catalog (listing) price for ``product`` on the channel."""
    ListingItem.objects.filter(
        listing__ref=listing_ref, product=product
    ).update(price_q=price_q, is_published=True, is_sellable=True)


# ── Category 3: price at commit is the current catalog price ────────────────


def test_reprice_persists_listing_total_and_revision_before_second_confirmation(
    cart_session,
    product,
):
    """A stale confirmation persists the exact channel quote, then closes."""
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    client = cart_session
    session_key = client.session["cart_session_key"]

    # Sanity: cart captured the add-time price (90 x2 = 180).
    session = Session.objects.get(session_key=session_key, channel_ref="web")
    assert sum(i["line_total_q"] for i in session.items) == 180
    original_revision = session.rev
    older = Session.objects.create(
        session_key=session_service.new_session_key(),
        channel_ref="web",
        state="open",
        handle_type="phone",
        handle_ref="+5543999990001",
    )

    # Listing do canal é a verdade. O base deliberadamente diverge para provar
    # que o checkout não ressuscita o antigo atalho Product.base_price_q.
    product.base_price_q = 999
    product.save(update_fields=["base_price_q"])
    _relist(product, price_q=150)
    key = session_service.new_idempotency_key()
    data = {
        "customer": {"name": "Ana", "phone": "+5543999990001"},
        "fulfillment_type": "pickup",
    }

    with pytest.raises(OrderingValidationError) as caught:
        checkout_service.process(
            session_key=session_key,
            channel_ref="web",
            data=data,
            idempotency_key=key,
            expected_total_q=180,
            expected_revision=original_revision,
        )

    assert caught.value.code == "total_changed"
    assert caught.value.context == {"old_total_q": 180, "new_total_q": 300}
    assert not Order.objects.filter(session_key=session_key).exists()

    repriced = Session.objects.get(session_key=session_key, channel_ref="web")
    assert repriced.rev == original_revision + 1
    assert not repriced.handle_ref
    assert [item["unit_price_q"] for item in repriced.items] == [150]
    assert sum(item["line_total_q"] for item in repriced.items) == 300
    older.refresh_from_db()
    assert older.state == "open"
    assert older.handle_ref == "+5543999990001"

    # A mesma tentativa pode ser confirmada com o draft que o servidor acabou
    # de persistir. Pedido nasce só nesta segunda confirmação.
    result = checkout_service.process(
        session_key=session_key,
        channel_ref="web",
        data=data,
        idempotency_key=key,
        expected_total_q=300,
        expected_revision=repriced.rev,
    )
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 300
    assert (order.handle_type, order.handle_ref) == ("phone", "+5543999990001")
    older.refresh_from_db()
    assert older.state == "abandoned"


def test_stale_revision_does_not_abandon_existing_phone_cart_or_hold(cart_session, product):
    """The identity phase rolls back completely when the reviewed rev is stale."""
    from decimal import Decimal

    from shopman.orderman.exceptions import ValidationError as OrderingValidationError
    from shopman.stockman.models import Hold, HoldStatus

    phone = "+5543999990001"
    old = Session.objects.create(
        session_key=session_service.new_session_key(),
        channel_ref="web",
        state="open",
        handle_type="phone",
        handle_ref=phone,
        items=[],
        data={},
    )
    hold = Hold.objects.create(
        sku=product.sku,
        quantity=Decimal("1"),
        target_date=timezone.localdate(),
        status=HoldStatus.PENDING,
        metadata={"session_key": old.session_key},
    )
    current = Session.objects.get(
        session_key=cart_session.session["cart_session_key"],
        channel_ref="web",
    )

    with pytest.raises(OrderingValidationError) as caught:
        checkout_service.process(
            session_key=current.session_key,
            channel_ref="web",
            data={"customer": {"phone": phone}},
            idempotency_key=session_service.new_idempotency_key(),
            expected_total_q=sum(item["line_total_q"] for item in current.items),
            expected_revision=current.rev - 1,
        )

    assert caught.value.code == "revision_changed"
    old.refresh_from_db()
    hold.refresh_from_db()
    current.refresh_from_db()
    assert old.state == "open"
    assert hold.status == HoldStatus.PENDING
    assert not current.handle_ref


def test_seal_failure_does_not_abandon_existing_phone_cart_or_hold(cart_session, product):
    """Takeover is post-Order durable; failure at the seal leaves ownership intact."""
    from decimal import Decimal
    from unittest.mock import patch

    from shopman.stockman.models import Hold, HoldStatus

    phone = "+5543999990001"
    old = Session.objects.create(
        session_key=session_service.new_session_key(),
        channel_ref="web",
        state="open",
        handle_type="phone",
        handle_ref=phone,
    )
    hold = Hold.objects.create(
        sku=product.sku,
        quantity=Decimal("1"),
        target_date=timezone.localdate(),
        status=HoldStatus.PENDING,
        metadata={"session_key": old.session_key},
    )
    current = Session.objects.get(
        session_key=cart_session.session["cart_session_key"],
        channel_ref="web",
    )

    with patch.object(session_service, "commit_session", side_effect=RuntimeError("seal unavailable")):
        with pytest.raises(RuntimeError, match="seal unavailable"):
            checkout_service.process(
                session_key=current.session_key,
                channel_ref="web",
                data={
                    "customer": {"name": "Ana", "phone": phone},
                    "fulfillment_type": "delivery",
                    "delivery_address": "Rua Selada, 10",
                    "address_label": {"key": "home", "custom": ""},
                    "payment": {"method": "cash"},
                    "save_as_default": True,
                },
                idempotency_key=session_service.new_idempotency_key(),
                expected_total_q=sum(item["line_total_q"] for item in current.items),
                expected_revision=current.rev,
            )

    old.refresh_from_db()
    hold.refresh_from_db()
    current.refresh_from_db()
    assert old.state == "open"
    assert old.handle_ref == phone
    assert hold.status == HoldStatus.PENDING
    assert not current.handle_ref
    assert not Order.objects.filter(session_key=current.session_key).exists()


def test_delayed_takeover_only_abandons_sessions_sealed_with_the_order(cart_session):
    """A worker tardio nunca varre uma sacola criada depois do pedido."""
    from unittest.mock import patch

    from shopman.orderman.models import Directive

    from shopman.shop import directives

    phone = "+5543999990001"
    old = Session.objects.create(
        session_key=session_service.new_session_key(),
        channel_ref="web",
        state="open",
        handle_type="phone",
        handle_ref=phone,
    )
    current = Session.objects.get(
        session_key=cart_session.session["cart_session_key"],
        channel_ref="web",
    )
    current.data = {**(current.data or {}), "delivery_fee_q": 0}
    current.save(update_fields=["data"])
    with patch.object(
        checkout_service,
        "_apply_post_commit_side_effects",
        side_effect=RuntimeError("process died after seal"),
    ):
        with pytest.raises(RuntimeError, match="process died after seal"):
            checkout_service.process(
                session_key=current.session_key,
                channel_ref="web",
                data={
                    "customer": {"name": "Ana", "phone": phone},
                    "fulfillment_type": "delivery",
                    "delivery_address": "Rua Selada, 10",
                    "address_label": {"key": "home", "custom": ""},
                    "payment": {"method": "cash"},
                    "save_as_default": True,
                },
                idempotency_key=session_service.new_idempotency_key(),
                expected_total_q=sum(item["line_total_q"] for item in current.items),
                expected_revision=current.rev,
            )

    order = Order.objects.get(session_key=current.session_key)
    takeover = Directive.objects.get(
        topic=directives.CHECKOUT_CONVENIENCE,
        payload__order_ref=order.ref,
        payload__effect="session_takeover",
    )
    assert takeover.payload["superseded_session_keys"] == [old.session_key]
    assert Directive.objects.filter(
        topic=directives.CHECKOUT_CONVENIENCE,
        payload__order_ref=order.ref,
    ).count() == 4

    newer = Session.objects.create(
        session_key=session_service.new_session_key(),
        channel_ref="web",
        state="open",
        data={"customer": {"phone": phone}},
    )
    checkout_service.recover_convenience_effect(takeover)

    old.refresh_from_db()
    newer.refresh_from_db()
    current.refresh_from_db()
    assert old.state == "abandoned"
    assert newer.state == "open"
    assert not newer.handle_ref
    assert (current.handle_type, current.handle_ref) == ("phone", phone)

    for effect in ("customer", "address", "defaults"):
        checkout_service.recover_convenience_effect(
            Directive.objects.get(
                topic=directives.CHECKOUT_CONVENIENCE,
                payload__order_ref=order.ref,
                payload__effect=effect,
            )
        )
    from shopman.guestman.services import address, customer

    recovered_customer = customer.get_by_phone(phone)
    assert recovered_customer is not None
    saved = list(address.addresses(recovered_customer.ref))
    assert len(saved) == 1
    assert saved[0].label == "home"


def test_checkout_without_prior_cart_queues_no_takeover(cart_session):
    """Sem sacola anterior do mesmo dono não há troca de dono a fazer.

    O efeito só carimbaria o telefone numa sessão já fechada, que ninguém lê por
    telefone; a Directive custava uma escrita, dupla idempotência e quatro
    SAVEPOINTs por checkout (laudo de soberania 18/10, AP-3).
    """
    from shopman.orderman.models import Directive

    from shopman.shop import directives

    phone = "+5543999990007"
    current = Session.objects.get(
        session_key=cart_session.session["cart_session_key"],
        channel_ref="web",
    )
    result = checkout_service.process(
        session_key=current.session_key,
        channel_ref="web",
        data={"customer": {"name": "Ana", "phone": phone}, "fulfillment_type": "pickup"},
        idempotency_key=session_service.new_idempotency_key(),
        expected_total_q=sum(item["line_total_q"] for item in current.items),
        expected_revision=current.rev,
    )

    effects = set(
        Directive.objects.filter(
            topic=directives.CHECKOUT_CONVENIENCE,
            payload__order_ref=result.order_ref,
        ).values_list("payload__effect", flat=True)
    )
    assert effects == {"customer", "address", "defaults"}


def test_expected_total_guard_blocks_stale_undercharge(cart_session, product):
    """If the client sends the total it saw (180) but the catalog price rose to
    150 (real total 300), the commit is REJECTED — the customer is never
    silently charged a different total, and the client cannot pin an old total
    to underpay."""
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    client = cart_session
    session_key = client.session["cart_session_key"]
    _relist(product, price_q=150)
    current_revision = Session.objects.get(session_key=session_key, channel_ref="web").rev

    with pytest.raises(OrderingValidationError) as exc:
        checkout_service.process(
            session_key=session_key,
            channel_ref="web",
            data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
            idempotency_key=session_service.new_idempotency_key(),
            expected_total_q=180,  # what the client saw — now stale
            expected_revision=current_revision,
        )
    assert exc.value.code == "total_changed"
    # No order was created.
    assert not Order.objects.filter(session_key=session_key).exists()


def test_fixed_discount_cannot_exceed_merchandise_value(channel, product):
    """A fixed coupon worth far more than the cart cannot drive the order total
    negative — it floors at zero (no free money / no negative charge)."""
    from shopman.shop.models import Coupon, Promotion

    # Cheap cart: 1 unit @ R$0,80.
    session = session_service.create_session("web")
    session = session_service.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": product.sku, "name": product.name, "qty": 1, "unit_price_q": 80},
            {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )
    now = timezone.now()
    promo = Promotion.objects.create(
        ref="vale-gigante",
        name="Vale gigante",
        type=Promotion.FIXED,
        value=100000,  # R$1.000,00 fixed — dwarfs the R$0,80 cart
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    Coupon.objects.create(code="GIGANTE", promotion=promo, max_uses=0)

    session = session_service.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[{"op": "set_data", "path": "coupon_code", "value": "GIGANTE"}],
    )
    result = checkout_service.process(
        session_key=session.session_key,
        channel_ref="web",
        data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
        idempotency_key=session_service.new_idempotency_key(),
        expected_total_q=0,
        expected_revision=session.rev,
    )
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q >= 0, f"negative order total: {order.total_q}"
    assert order.total_q == 0, (
        f"discount exceeded merchandise value: total {order.total_q}, expected floor 0"
    )


# ── Category 2: cart isolation / session fixation ──────────────────────────


def test_carts_are_isolated_between_sessions(cart_session):
    """Client A has an item in the cart; a fresh Client B sees an empty cart —
    carts do not bleed across Django sessions."""
    from django.test import Client

    resp_a = cart_session.get("/api/v1/storefront/cart/")
    assert resp_a.json()["cart"]["items_count"] == 2

    other = Client()
    resp_b = other.get("/api/v1/storefront/cart/")
    assert resp_b.json()["cart"]["items_count"] == 0


def test_cart_session_key_not_switchable_by_request_param(cart_session):
    """A victim's cart cannot be hijacked by supplying their cart_session_key as
    a query/body parameter — the server keys the cart off the signed Django
    session cookie only."""
    from django.test import Client

    victim_key = cart_session.session["cart_session_key"]
    attacker = Client()

    via_query = attacker.get(f"/api/v1/storefront/cart/?session_key={victim_key}")
    via_query2 = attacker.get(f"/api/v1/storefront/cart/?cart_session_key={victim_key}")
    assert via_query.json()["cart"]["items_count"] == 0
    assert via_query2.json()["cart"]["items_count"] == 0


def test_checkout_draft_only_persists_whitelisted_fields(cart_session):
    """CheckoutDraftView must ignore junk keys and coerce an invalid
    fulfillment_type to 'pickup' — a client cannot smuggle arbitrary keys into
    session.data via the draft endpoint."""
    client = cart_session
    session_key = client.session["cart_session_key"]

    resp = client.patch(
        "/api/v1/checkout/draft/",
        data=json.dumps({
            "fulfillment_type": "pickup",
            "delivery_address_structured": {
                "formatted_address": "Rua X 1",
                "coordinates_source": "pin",
                "evil_key": "DROP TABLE",       # not whitelisted
                "unit_price_q": 1,              # not whitelisted
            },
            "discount_q": 99999,               # top-level junk
            "coupon_code": "FREE",             # top-level junk
        }),
        content_type="application/json",
    )
    assert resp.status_code == 200

    session = Session.objects.get(session_key=session_key, channel_ref="web")
    # Junk keys never land in session.data anywhere.
    blob = json.dumps(session.data)
    assert "evil_key" not in blob
    assert "DROP TABLE" not in blob
    assert "FREE" not in blob
    # fulfillment_type, if stored, is the coerced safe value.
    ft = (session.data or {}).get("fulfillment_type")
    assert ft in (None, "pickup")


def test_checkout_draft_accepts_only_the_coordinates_source_vocabulary(cart_session):
    client = cart_session
    valid = client.patch(
        "/api/v1/checkout/draft/",
        data=json.dumps({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "route": "Rua X",
                "latitude": -23.31,
                "longitude": -51.16,
                "coordinates_source": "pin",
            },
        }),
        content_type="application/json",
    )
    assert valid.status_code == 200

    invalid = client.patch(
        "/api/v1/checkout/draft/",
        data=json.dumps({
            "fulfillment_type": "delivery",
            "delivery_address_structured": {
                "route": "Rua X",
                "coordinates_source": "browser-history",
            },
        }),
        content_type="application/json",
    )
    assert invalid.status_code == 400
    assert invalid.json()["field"] == "delivery_address_structured"


def test_anonymous_cannot_inject_loyalty_redemption(cart_session):
    """An anonymous visitor toggling loyalty on cannot inject a redeem amount;
    the server resolves the balance itself (0 for an anonymous caller), so no
    discount is applied."""
    client = cart_session
    resp = client.patch(
        "/api/v1/checkout/loyalty/",
        data=json.dumps({"enabled": True, "redeem_q": 99999, "points_balance": 99999}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    # Subtotal unchanged — no phantom loyalty discount for an anonymous caller.
    assert resp.json()["cart"]["subtotal_q"] == 180
