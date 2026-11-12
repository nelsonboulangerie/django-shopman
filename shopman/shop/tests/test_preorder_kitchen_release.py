"""A encomenda chega à Cozinha na hora certa (decisão do dono, 09/11/2026).

Régua: ``hora combinada − tempo de preparo − antecedência``. Ex.: 17h, 30 min de
preparo e 15 min de antecedência → 16h15. O preparo é por SKU
(``Shop.defaults["preorder_kitchen"]["prep_minutes_by_sku"]``) e cai no
``default_prep_minutes`` declarado quando o SKU não tem o dele. Sem hora
combinada, a abertura da loja no dia (sem expediente, 00:05).

E chegar à Cozinha não é "Em preparo": em canal nenhum a ativação leva o pedido
a PREPARING. Quem começa é o "Iniciar" do posto (ou o atalho do Gestor).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.shop import lifecycle
from shopman.shop.directives import PREORDER_ACTIVATE
from shopman.shop.lifecycle import (
    _physical_work_deferred,
    activate_preorder,
    preorder_activation_at,
    release_preorder_now,
)
from shopman.shop.models import Channel, Shop
from shopman.shop.preorder_kitchen_policy import (
    DEFAULT_LEAD_MINUTES,
    DEFAULT_PREP_MINUTES,
    PreorderKitchenPolicy,
)

pytestmark = pytest.mark.django_db


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


@pytest.fixture
def day() -> date:
    return timezone.localdate() + timedelta(days=3)


@pytest.fixture(autouse=True)
def shop(db):
    from django.core.cache import cache

    cache.clear()
    shop = Shop.objects.create(name="Nelson", brand_name="Nelson")
    # Canal com prep_start "auto" (o padrão): mesmo assim a ativação não inicia o preparo.
    Channel.objects.create(ref="balcao", name="Balcão", config={"payment": {"timing": "external", "method": "cash"}})
    yield shop
    cache.clear()


def _set_policy(shop, **block):
    from django.core.cache import cache

    shop.defaults = {**(shop.defaults or {}), "preorder_kitchen": block}
    shop.save()
    cache.clear()


def _order(day: date, *, slot: str = "17:00-17:30", skus=("BAGUETE",), ref="ENC-1", is_preorder=True) -> Order:
    data = {"delivery_date": day.isoformat(), "is_preorder": is_preorder}
    if slot:
        data["delivery_time_slot"] = slot
    order = Order.objects.create(
        ref=ref, channel_ref="balcao", session_key=f"sk-{ref}", status=Order.Status.ACCEPTED,
        total_q=1000, data=data,
    )
    for i, sku in enumerate(skus):
        OrderItem.objects.create(order=order, line_id=f"L{i}", sku=sku, qty=1, unit_price_q=500, line_total_q=500)
    return order


# ── A hora de ativação ────────────────────────────────────────────────────────


def test_with_combined_time_and_no_prep_configured_uses_declared_fallback(day):
    order = _order(day)

    available_at, target = preorder_activation_at(order)

    assert target == day
    assert (DEFAULT_PREP_MINUTES, DEFAULT_LEAD_MINUTES) == (30, 15)
    assert available_at == _at(day, 16, 15), "17h − 30 min de preparo − 15 min de antecedência"


def test_with_combined_time_uses_prep_per_sku_and_configured_lead(shop, day):
    _set_policy(shop, lead_minutes=10, default_prep_minutes=20, prep_minutes_by_sku={"BOLO": 90, "BAGUETE": 30})

    only_bread = _order(day, skus=("BAGUETE",), ref="ENC-PAO")
    cake_and_bread = _order(day, skus=("BAGUETE", "BOLO"), ref="ENC-BOLO")
    unconfigured = _order(day, skus=("CAFE",), ref="ENC-CAFE")

    assert preorder_activation_at(only_bread)[0] == _at(day, 16, 20)
    assert preorder_activation_at(cake_and_bread)[0] == _at(day, 15, 20), "o maior preparo dita a chegada"
    assert preorder_activation_at(unconfigured)[0] == _at(day, 16, 30), "SKU sem tempo próprio usa o padrão"


def test_activation_never_before_the_start_of_the_day(shop, day):
    _set_policy(shop, lead_minutes=60, default_prep_minutes=120)
    order = _order(day, slot="01:00-01:30")

    assert preorder_activation_at(order)[0] == _at(day, 0, 5)


def test_without_combined_time_arrives_at_opening(shop, day):
    from shopman.shop.services.business_calendar import DAY_ORDER

    shop.opening_hours = {DAY_ORDER[day.weekday()]: {"open": "07:00", "close": "19:00"}}
    shop.save()
    order = _order(day, slot="")

    assert preorder_activation_at(order)[0] == _at(day, 7, 0)


def test_without_combined_time_nor_opening_hours_falls_back_to_0005(day):
    order = _order(day, slot="")

    assert preorder_activation_at(order)[0] == _at(day, 0, 5)


def test_policy_ignores_garbage():
    policy = PreorderKitchenPolicy.from_defaults(
        {"preorder_kitchen": {"lead_minutes": "x", "default_prep_minutes": -5, "prep_minutes_by_sku": {"A": "abc", "B": "40"}}}
    )
    assert policy.lead_minutes == DEFAULT_LEAD_MINUTES
    assert policy.default_prep_minutes == DEFAULT_PREP_MINUTES
    assert policy.prep_minutes_by_sku == {"B": 40}
    assert policy.prep_minutes_for([]) == DEFAULT_PREP_MINUTES


# ── A espera no dia ──────────────────────────────────────────────────────────


def test_on_the_day_the_preorder_waits_until_its_time(day):
    order = _order(day)

    with patch("django.utils.timezone.localdate", return_value=day):
        with patch("django.utils.timezone.now", return_value=_at(day, 16, 14)):
            assert _physical_work_deferred(order) is True
        with patch("django.utils.timezone.now", return_value=_at(day, 16, 15)):
            assert _physical_work_deferred(order) is False


def test_same_day_order_without_alarm_goes_to_kitchen_on_accept(day):
    """Pedido feito hoje para hoje não é encomenda: vai à Cozinha no aceite."""
    order = _order(day, is_preorder=False)

    with patch("django.utils.timezone.localdate", return_value=day), patch(
        "django.utils.timezone.now", return_value=_at(day, 9)
    ):
        assert _physical_work_deferred(order) is False


def test_accepting_a_future_preorder_arms_the_alarm_at_kitchen_time(day):
    from shopman.shop.config import ChannelConfig

    order = _order(day)
    with patch.object(lifecycle.notification, "send"):
        lifecycle._on_accepted(order, ChannelConfig.for_channel("balcao"))

    alarm = Directive.objects.get(topic=PREORDER_ACTIVATE, dedupe_key=f"preorder.activate:{order.ref}")
    assert alarm.available_at == _at(day, 16, 15)


# ── Chegar à Cozinha não é "Em preparo" ──────────────────────────────────────


def test_activation_never_marks_preparing_even_with_auto_prep_start(day):
    order = _order(day)

    with (
        patch("django.utils.timezone.localdate", return_value=day),
        patch("django.utils.timezone.now", return_value=_at(day, 16, 15)),
        patch.object(lifecycle, "_dispatch_physical_work", return_value=True) as dispatch,
        patch.object(lifecycle.stock, "fulfill"),
    ):
        activate_preorder(order)

    assert dispatch.called
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED
    assert order.data["kitchen_released_at"]


def test_early_activation_on_the_day_is_a_noop(day):
    order = _order(day)

    with (
        patch("django.utils.timezone.localdate", return_value=day),
        patch("django.utils.timezone.now", return_value=_at(day, 8)),
        patch.object(lifecycle, "_dispatch_physical_work", return_value=True) as dispatch,
    ):
        activate_preorder(order)

    assert not dispatch.called, "a fornada da manhã (holds_materialized) não leva a encomenda das 17h à Cozinha"


# ── Quem age antes da hora antecipa a chegada ────────────────────────────────


def test_release_now_sends_to_kitchen_and_closes_the_alarm(day):
    order = _order(day)
    Directive.objects.create(
        topic=PREORDER_ACTIVATE, dedupe_key=f"preorder.activate:{order.ref}",
        payload={"order_ref": order.ref}, available_at=_at(day, 16, 15),
    )

    with (
        patch("django.utils.timezone.localdate", return_value=day),
        patch("django.utils.timezone.now", return_value=_at(day, 10)),
        patch.object(lifecycle, "_dispatch_physical_work", return_value=True) as dispatch,
        patch.object(lifecycle.stock, "fulfill"),
    ):
        assert release_preorder_now(order) is True

    assert dispatch.called
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED
    assert not Directive.objects.filter(topic=PREORDER_ACTIVATE, status="queued").exists()


def test_release_now_does_not_touch_another_day(day):
    order = _order(day)

    with patch.object(lifecycle, "_dispatch_physical_work", return_value=True) as dispatch:
        assert release_preorder_now(order) is False

    assert not dispatch.called


def test_gestor_start_releases_the_preorder_before_starting(day):
    """O "Iniciar" do Gestor numa encomenda do dia que ainda não chegou à Cozinha."""
    from shopman.shop.services import operator_orders

    order = _order(day)

    with (
        patch("django.utils.timezone.localdate", return_value=day),
        patch("django.utils.timezone.now", return_value=_at(day, 10)),
        patch.object(lifecycle, "release_preorder_now", wraps=lifecycle.release_preorder_now) as release,
        patch.object(lifecycle, "_dispatch_physical_work", return_value=True),
        patch.object(lifecycle.stock, "fulfill"),
        patch.object(lifecycle.notification, "send"),
    ):
        operator_orders.advance_order(order, actor="gerente")

    assert release.called
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    assert order.data["kitchen_released_at"]


# ── Reagendar move o despertador para a hora nova ────────────────────────────


def test_reschedule_to_today_moves_the_alarm_to_kitchen_time(day):
    from shopman.shop.services.reschedule import _move_activation

    order = _order(day)
    alarm = Directive.objects.create(
        topic=PREORDER_ACTIVATE, dedupe_key=f"preorder.activate:{order.ref}",
        payload={"order_ref": order.ref}, available_at=_at(day + timedelta(days=1), 0, 5),
    )

    with (
        patch("django.utils.timezone.localdate", return_value=day),
        patch("django.utils.timezone.now", return_value=_at(day, 9)),
        patch.object(lifecycle, "_dispatch_physical_work", return_value=True) as dispatch,
    ):
        activated = _move_activation(order, day, today=day)

    assert activated is False
    assert not dispatch.called
    alarm.refresh_from_db()
    assert alarm.status == "queued"
    assert alarm.available_at == _at(day, 16, 15)
