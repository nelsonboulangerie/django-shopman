"""A reserva que vence avisa a vitrine no próprio prazo (#2785).

O Stockman já tira a reserva vencida da conta no ``expires_at`` (``Hold.objects.active()``),
sem escrita nenhuma. Quem dá o prazo é o shop (a renovação da sacola e o ``extend_hold``
do adapter), e é ele que agenda, para esse instante, a releitura dos SKUs
(``stock.shelf_recheck``). Na hora, o aviso só sai para o SKU cuja reserva de fato venceu:
a renovação seguinte move o prazo e não acorda tela nenhuma.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive
from shopman.stockman.models import Hold

from shopman.shop.directives import STOCK_SHELF_RECHECK
from shopman.shop.handlers.shelf_recheck import ShelfRecheckHandler
from shopman.shop.services import shelf_recheck
from shopman.shop.services.availability import bump_session_hold_expiry

pytestmark = pytest.mark.django_db


def _hold(sku="BAGUETE", *, expires_at, status="pending", reference="sess-1"):
    return Hold.objects.create(
        sku=sku,
        quantity=Decimal("1"),
        status=status,
        target_date=timezone.localdate(),
        expires_at=expires_at,
        metadata={"reference": reference, "source_sku": sku},
    )


def _rechecks():
    return Directive.objects.filter(topic=STOCK_SHELF_RECHECK).order_by("available_at", "pk")


def _bag(reference="sess-1", skus=("BAGUETE",), *, minutes_left=2):
    """Uma sacola com uma reserva por SKU, perto do prazo, que a cliente acabou de mexer."""
    for sku in skus:
        _hold(sku, expires_at=timezone.now() + timedelta(minutes=minutes_left), reference=reference)
    bump_session_hold_expiry(reference, ttl_minutes=30)
    return Hold.objects.filter(metadata__reference=reference).first().expires_at


def _run(directive, *, now):
    with patch("shopman.shop.handlers.shelf_recheck.timezone.now", return_value=now), patch(
        "shopman.shop.handlers._sse_emitters._emit_for_sku"
    ) as emit:
        ShelfRecheckHandler().handle(message=directive, ctx={})
    return emit


# ── a janela ────────────────────────────────────────────────────────────


def test_the_deadline_falls_at_the_end_of_its_window():
    at = datetime(2026, 11, 20, 18, 30, 7, tzinfo=UTC)
    assert shelf_recheck.bucket_end(at) == datetime(2026, 11, 20, 18, 30, 15, tzinfo=UTC)
    on_edge = datetime(2026, 11, 20, 18, 30, 15, tzinfo=UTC)
    assert shelf_recheck.bucket_end(on_edge) == on_edge


# ── quem dá o prazo agenda a releitura ─────────────────────────────────


def test_the_bag_renewal_schedules_one_recheck_with_every_sku_at_the_deadline():
    deadline = _bag(skus=("BAGUETE", "CROISSANT"))

    [directive] = _rechecks()
    assert directive.available_at == shelf_recheck.bucket_end(deadline)
    assert directive.payload == {"skus": ["BAGUETE", "CROISSANT"], "at": shelf_recheck.bucket_end(deadline).isoformat()}


def test_gestures_of_the_same_bag_in_the_same_window_share_one_recheck():
    _bag()
    bump_session_hold_expiry("sess-1", ttl_minutes=30)

    assert _rechecks().count() == 1


def test_saving_a_reservation_schedules_nothing_by_itself():
    # A criação é coberta pela renovação que a sacola faz logo depois; o post_save só
    # publica o aviso de sempre, sem custo extra por reserva.
    _hold(expires_at=timezone.now() + timedelta(minutes=30))

    assert not _rechecks().exists()


def test_the_adapter_extension_schedules_the_new_deadline():
    from shopman.shop.adapters.stock import extend_hold

    hold = _hold(expires_at=timezone.now() + timedelta(minutes=2))
    later = timezone.now() + timedelta(hours=2)

    assert extend_hold(f"hold:{hold.pk}", expires_at=later) is True

    [directive] = _rechecks()
    assert directive.available_at == shelf_recheck.bucket_end(later)
    assert directive.payload["skus"] == ["BAGUETE"]


# ── na hora: só avisa o vencimento de verdade ──────────────────────────


def test_a_lapsed_reservation_tells_the_shelf():
    _bag()
    [directive] = _rechecks()

    emit = _run(directive, now=directive.available_at + timedelta(seconds=1))

    emit.assert_called_once_with("BAGUETE", event_type="stock-update")


def test_a_renewed_reservation_wakes_nobody():
    _bag()
    [old] = _rechecks()
    # Dois minutos depois a cliente mexe de novo: o prazo vai para frente.
    later = timezone.now() + timedelta(minutes=2)
    with patch("django.utils.timezone.now", return_value=later):
        bump_session_hold_expiry("sess-1", ttl_minutes=30)

    emit = _run(old, now=old.available_at + timedelta(seconds=1))

    emit.assert_not_called()


def test_a_reservation_taken_out_of_the_bag_before_the_deadline_wakes_nobody():
    _bag()
    [directive] = _rechecks()
    Hold.objects.update(status="released", resolved_at=timezone.now())

    emit = _run(directive, now=directive.available_at + timedelta(seconds=1))

    emit.assert_not_called()


def test_a_reservation_the_sweep_already_released_still_tells_the_shelf():
    deadline = _bag()
    [directive] = _rechecks()
    Hold.objects.update(status="released", resolved_at=deadline + timedelta(seconds=3))

    emit = _run(directive, now=directive.available_at + timedelta(seconds=5))

    emit.assert_called_once_with("BAGUETE", event_type="stock-update")


def test_only_the_sku_that_lapsed_is_announced():
    deadline = _bag(skus=("BAGUETE", "CROISSANT"))
    [directive] = _rechecks()
    Hold.objects.filter(sku="CROISSANT").update(status="released", resolved_at=deadline - timedelta(minutes=1))

    emit = _run(directive, now=directive.available_at + timedelta(seconds=1))

    emit.assert_called_once_with("BAGUETE", event_type="stock-update")


def test_too_early_goes_back_to_the_queue_at_the_right_time():
    _bag()
    [directive] = _rechecks()

    emit = _run(directive, now=directive.available_at - timedelta(seconds=20))

    emit.assert_not_called()
    directive.refresh_from_db()
    assert directive.status == "queued"
