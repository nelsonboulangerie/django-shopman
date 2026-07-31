"""RATING-LOOP — the customer rating finally reaches the store.

The customer side has always worked (write to ``Order.data["customer_rating"]``),
but nobody in the store ever read it. These tests lock the read side that closes
the loop:

- the Admin dashboard aggregate (``_customer_ratings``) computes a moving
  average, counts, and the recent comments — reading the very JSON the
  storefront writes;
- a low rating (≤2) raises a registered ``OperatorAlert`` so the manager can act
  while the customer still remembers;
- the ``OrderAdmin`` renders the rating (stars + comment) instead of leaving it
  buried in the JSONField.
"""
from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.dashboard import _customer_ratings, build_dashboard
from shopman.storefront.api.tracking import _alert_low_rating

pytestmark = pytest.mark.django_db


def _rated_order(ref: str, rating: int | None, *, comment: str = "") -> Order:
    data: dict = {}
    if rating is not None:
        data["customer_rating"] = {
            "rating": rating,
            "comment": comment,
            "submitted_at": timezone.now().isoformat(),
            "source": "storefront_nuxt",
        }
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status="completed",
        total_q=2000,
        handle_type="phone",
        handle_ref="+5543999990001",
        data=data,
    )


# ── Aggregate ──────────────────────────────────────────────────────────


def test_customer_ratings_aggregate_average_and_low_count():
    _rated_order("R-5", 5, comment="Maravilhoso")
    _rated_order("R-4", 4)
    _rated_order("R-1", 1, comment="Chegou frio")
    _rated_order("R-NONE", None)  # unrated order is ignored

    average, count, low_count, rows = _customer_ratings()

    assert count == 3
    assert average == "3.3"  # (5 + 4 + 1) / 3
    assert low_count == 1
    refs = {r.order_ref for r in rows}
    assert refs == {"R-5", "R-4", "R-1"}
    low = next(r for r in rows if r.order_ref == "R-1")
    assert low.is_low is True
    assert low.stars == "★☆☆☆☆"
    assert low.comment == "Chegou frio"


def test_customer_ratings_empty_when_no_ratings():
    _rated_order("R-NONE", None)

    average, count, low_count, rows = _customer_ratings()

    assert average == "—"
    assert count == 0
    assert low_count == 0
    assert list(rows) == []


def test_build_dashboard_exposes_rating_fields():
    _rated_order("R-2", 2, comment="Podia melhorar")

    proj = build_dashboard()

    assert proj.rating_count == 1
    assert proj.rating_low_count == 1
    assert proj.recent_ratings[0].order_ref == "R-2"


# ── Low-rating alert ───────────────────────────────────────────────────


def test_low_rating_raises_registered_operator_alert():
    order = _rated_order("R-LOW", 2, comment="Demorou")

    _alert_low_rating(order, 2, "Demorou")

    alert = OperatorAlert.objects.filter(type="low_rating", order_ref=order.ref).first()
    assert alert is not None
    # Registered type → readable label in the operator console, not a raw slug.
    assert alert.get_type_display() != "low_rating"
    assert order.ref in alert.message
    assert "Demorou" in alert.message


def test_low_rating_alert_is_debounced_per_order():
    order = _rated_order("R-DEBOUNCE", 1)

    _alert_low_rating(order, 1, "")
    _alert_low_rating(order, 1, "")

    assert OperatorAlert.objects.filter(type="low_rating", order_ref=order.ref).count() == 1


# ── Admin display ──────────────────────────────────────────────────────


def test_order_admin_renders_rating():
    from django.contrib.admin.sites import AdminSite
    from shopman.orderman.admin import OrderAdmin

    admin = OrderAdmin(Order, AdminSite())
    rated = _rated_order("R-ADMIN", 2, comment="Frio")
    unrated = _rated_order("R-ADMIN-NONE", None)

    assert "★★☆☆☆" in admin.rating_display(rated)
    assert admin.rating_display(unrated) == "-"
    detail = admin.customer_rating_detail(rated)
    assert "★★☆☆☆" in detail
    assert "Frio" in detail
    assert "Sem avaliação" in admin.customer_rating_detail(unrated)
