"""O link da rota do entregador da casa (DEV-2026-030, frente M2a; plano §4.2 e §4.4)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.shop.models import Courier, CourierLink, DeliveryService
from shopman.shop.services import courier_links as links

pytestmark = pytest.mark.django_db

PHONE_A = "a" * 32
PHONE_B = "b" * 32


@pytest.fixture
def casa():
    return DeliveryService.objects.get(ref="casa")


@pytest.fixture
def diego(casa):
    return Courier.objects.create(service=casa, ref="diego", name="Diego", phone="+5543999990000")


@pytest.fixture
def rui(casa):
    return Courier.objects.create(service=casa, ref="rui", name="Rui", phone="+5543999991234")


def test_issue_creates_an_unguessable_token(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47", "WEB-C03"])
    assert len(link.token) >= 43
    assert link.order_refs == ["WEB-A47", "WEB-C03"]
    other = links.issue(diego, "WEB-B12", ["WEB-B12"])
    assert other.token != link.token


def test_issue_refuses_a_ride_without_orders(diego):
    with pytest.raises(ValueError):
        links.issue(diego, "WEB-A47", [])


def test_opening_does_not_bind_only_confirming_does(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47"])
    # Um operador da casa abre por curiosidade: vê só o pedido de confirmação, nada fica preso.
    assert links.resolve(link.token, PHONE_B).state == links.UNCLAIMED
    link.refresh_from_db()
    assert link.device_hash == "" and link.opened_at is None
    first = links.claim(link.token, PHONE_A)
    assert first.ok
    link.refresh_from_db()
    assert link.opened_at is not None and link.device_hash
    assert PHONE_A not in link.device_hash  # só o hash fica guardado
    assert links.resolve(link.token, PHONE_A).ok


def test_forwarded_link_does_not_open_on_another_phone(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47"])
    links.claim(link.token, PHONE_A)
    assert links.resolve(link.token, PHONE_B).state == links.OTHER_DEVICE
    assert links.claim(link.token, PHONE_B).state == links.OTHER_DEVICE


def test_short_device_key_is_refused_without_binding(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47"])
    assert links.claim(link.token, "curta").state == links.BAD_DEVICE
    link.refresh_from_db()
    assert link.device_hash == ""


def test_unknown_token(diego):
    assert links.resolve("nao-existe", PHONE_A).state == links.UNKNOWN
    assert links.resolve("", PHONE_A).state == links.UNKNOWN


def test_reissuing_to_another_courier_revokes_the_first(diego, rui):
    first = links.issue(diego, "WEB-A47", ["WEB-A47"])
    second = links.issue(rui, "WEB-A47", ["WEB-A47"])
    first.refresh_from_db()
    assert first.revoked_reason == links.REASSIGNED
    assert links.resolve(first.token, PHONE_A).state == links.REVOKED
    assert links.claim(second.token, PHONE_B).ok


def test_reissuing_to_the_same_courier_is_a_resend(diego):
    first = links.issue(diego, "WEB-A47", ["WEB-A47"])
    links.issue(diego, "WEB-A47", ["WEB-A47"])
    first.refresh_from_db()
    assert first.revoked_reason == links.REISSUED


def test_only_one_live_link_per_ride_in_the_database(diego):
    links.issue(diego, "WEB-A47", ["WEB-A47"])
    with pytest.raises(IntegrityError), transaction.atomic():
        CourierLink.objects.create(token="x" * 43, courier=diego, ride_ref="WEB-A47", order_refs=["WEB-A47"])


def test_closed_ride_keeps_the_link_for_two_hours(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47"])
    links.claim(link.token, PHONE_A)
    closed_at = timezone.now()
    links.close("WEB-A47", at=closed_at)
    assert links.resolve(link.token, PHONE_A, now=closed_at + timedelta(minutes=119)).ok
    assert links.resolve(link.token, PHONE_A, now=closed_at + links.LINK_GRACE).state == links.EXPIRED


def test_cancelled_ride_kills_the_link_now(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47"])
    links.revoke("WEB-A47")
    accessed = links.resolve(link.token, PHONE_A)
    assert accessed.state == links.REVOKED
    assert accessed.link.revoked_reason == links.CANCELLED


def test_counter_releases_a_link_stuck_on_the_wrong_phone(diego):
    link = links.issue(diego, "WEB-A47", ["WEB-A47"])
    links.claim(link.token, PHONE_B)
    links.release("WEB-A47")
    assert links.resolve(link.token, PHONE_A).state == links.UNCLAIMED
    assert links.claim(link.token, PHONE_A).ok
    assert links.resolve(link.token, PHONE_B).state == links.OTHER_DEVICE


def test_close_and_revoke_without_a_live_link_do_nothing(diego):
    assert links.close("WEB-ZZZ") is None
    assert links.revoke("WEB-ZZZ") is None
    assert links.release("WEB-ZZZ") is None


def test_shift_is_per_day_and_needs_an_active_courier(diego):
    today = date(2026, 11, 16)
    assert not diego.is_on_shift(today)
    diego.on_shift_on = today
    assert diego.is_on_shift(today)
    assert not diego.is_on_shift(today + timedelta(days=1))
    diego.is_active = False
    assert not diego.is_on_shift(today)
