"""C01/D11: queue and detail use domain guards and explicit actor authority."""
from types import SimpleNamespace

import pytest
from shopman.orderman.models import Order

from shopman.backstage.projections.order_queue import build_operator_order, build_order_card
from shopman.shop.models import Shop
from shopman.shop.services.operator_orders import operational_revision

pytestmark = pytest.mark.django_db


def actor(allowed=True):
    return SimpleNamespace(is_active=True, is_staff=True, has_perm=lambda _: allowed)


@pytest.mark.parametrize("allowed", [True, False])
@pytest.mark.parametrize("approved", [True, False])
def test_confirmation_uses_domain_availability_and_actor_on_both_surfaces(allowed, approved):
    Shop.objects.create(name="Lab")
    order = Order.objects.create(ref="ACTION", status="new", channel_ref="web", data={
        "payment": {"method": "cash"},
        "availability_decision": {"approved": approved, "decisions": []},
    })
    user = actor(allowed)
    card = build_order_card(order, user=user)
    detail = build_operator_order(order, user=user)
    assert card.actions == detail.actions
    confirm, reject = card.actions
    assert confirm.enabled is (allowed and approved)
    assert bool(confirm.reason) is not confirm.enabled
    # Payment/availability blocking acceptance cannot hide the independent refusal.
    assert reject.enabled is allowed


def test_no_actor_never_projects_authorized_mutation():
    order = Order.objects.create(ref="NO-ACTOR", status="accepted")
    assert not any(action.enabled for action in build_order_card(order).actions)


def test_independent_field_revision_and_physical_state_revision():
    order = Order.objects.create(ref="REV", status="accepted", data={"payment": {"method": "cash"}})
    advance = operational_revision(order)
    note = operational_revision(order, field="kitchen_note")
    order.data["assignment"] = {"operator_id": 1}
    assert operational_revision(order) == advance
    assert operational_revision(order, field="kitchen_note") == note
    order.data["payment"]["method"] = "link"
    assert operational_revision(order) != advance
