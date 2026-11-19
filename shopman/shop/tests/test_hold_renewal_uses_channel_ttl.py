"""A renovação da reserva da sacola usa o prazo do canal, o mesmo da criação (#2773).

Até 19/11/2026 ``bump_session_hold_expiry`` renovava com 30 minutos fixos, e o
acréscimo pelo seletor de quantidade (``reconcile``) também nascia com 30. O
canal configurado com 15 tinha a reserva esticada para 30 no mesmo gesto que a
criou; o configurado com 60 ficava com itens da mesma sacola em prazos
diferentes. A sacola diz essa hora à cliente ("Guardamos seus itens até 19h18"),
então o prazo tem de ser um só: o do canal.

O que NÃO muda, e estes testes também seguram: a renovação só estende (nunca
encurta), não toca reserva sem prazo e não ressuscita reserva vencida.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import stock as stockman_stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.shop.adapters import stock as stock_adapter
from shopman.shop.models import Channel
from shopman.shop.services import availability

pytestmark = pytest.mark.django_db

SESSION = "SESS-TTL"
#: Folga do relógio do teste: o prazo é comparado com uma janela de um minuto.
SLACK = timedelta(minutes=1)


def _pk(hold_id: str) -> int:
    return int(hold_id.split(":")[1])


def _channel(ref: str, stock: dict | None = None) -> Channel:
    config = {"stock": stock} if stock is not None else {}
    channel, _ = Channel.objects.update_or_create(ref=ref, defaults={"name": ref, "config": config})
    return channel


def _hold(sku: str, *, ttl_minutes: int | None = 5) -> Hold:
    """Uma reserva viva da sessão, com pouco prazo (ou sem prazo, com ``None``)."""
    Product.objects.get_or_create(
        sku=sku, defaults={"name": sku, "base_price_q": 500, "is_published": True, "is_sellable": True},
    )
    position, _ = Position.objects.get_or_create(
        ref="loja", defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stockman_stock.receive(quantity=Decimal("5"), sku=sku, position=position, reason="fornada")
    result = stock_adapter.create_hold(sku=sku, qty=Decimal("1"), reference=SESSION, ttl_minutes=5)
    assert result["success"], result
    hold = Hold.objects.get(pk=_pk(result["hold_id"]))
    if ttl_minutes is None:
        Hold.objects.filter(pk=hold.pk).update(expires_at=None)
    elif ttl_minutes != 5:
        Hold.objects.filter(pk=hold.pk).update(expires_at=timezone.now() + timedelta(minutes=ttl_minutes))
    hold.refresh_from_db()
    return hold


def _minutes_left(hold: Hold) -> timedelta:
    hold.refresh_from_db()
    return hold.expires_at - timezone.now()


def _assert_renewed_to(hold: Hold, minutes: int) -> None:
    left = _minutes_left(hold)
    assert timedelta(minutes=minutes) - SLACK < left <= timedelta(minutes=minutes), (
        f"renovou para {left}, esperado cerca de {minutes} min"
    )


@pytest.mark.parametrize("configured", [30, 45, 10])
def test_renewal_uses_the_ttl_the_channel_configures(configured):
    _channel("web", {"hold_ttl_minutes": configured})
    hold = _hold("TTLCRO", ttl_minutes=2)

    bumped = availability.bump_session_hold_expiry(SESSION, channel_ref="web")

    assert bumped == 1
    _assert_renewed_to(hold, configured)


def test_channel_without_configuration_uses_the_default():
    _channel("web")
    hold = _hold("TTLCRO", ttl_minutes=2)

    assert availability.bump_session_hold_expiry(SESSION, channel_ref="web") == 1

    _assert_renewed_to(hold, 30)


def test_no_channel_uses_the_default():
    hold = _hold("TTLCRO", ttl_minutes=2)

    assert availability.bump_session_hold_expiry(SESSION) == 1

    _assert_renewed_to(hold, 30)


def test_each_channel_renews_with_its_own_ttl():
    """Dois canais, dois prazos: nenhum herda o do outro."""
    _channel("web", {"hold_ttl_minutes": 45})
    _channel("whatsapp", {"hold_ttl_minutes": 10})
    hold = _hold("TTLCRO", ttl_minutes=2)

    availability.bump_session_hold_expiry(SESSION, channel_ref="whatsapp")
    _assert_renewed_to(hold, 10)

    availability.bump_session_hold_expiry(SESSION, channel_ref="web")
    _assert_renewed_to(hold, 45)


def test_explicit_ttl_still_wins():
    _channel("web", {"hold_ttl_minutes": 45})
    hold = _hold("TTLCRO", ttl_minutes=2)

    availability.bump_session_hold_expiry(SESSION, channel_ref="web", ttl_minutes=20)

    _assert_renewed_to(hold, 20)


def test_renewal_never_shortens_a_longer_reservation():
    _channel("web", {"hold_ttl_minutes": 10})
    hold = _hold("TTLCRO", ttl_minutes=40)
    before = hold.expires_at

    assert availability.bump_session_hold_expiry(SESSION, channel_ref="web") == 0

    hold.refresh_from_db()
    assert hold.expires_at == before


def test_renewal_leaves_a_reservation_without_deadline_alone():
    _channel("web", {"hold_ttl_minutes": 45})
    hold = _hold("TTLCRO", ttl_minutes=None)

    assert availability.bump_session_hold_expiry(SESSION, channel_ref="web") == 0

    hold.refresh_from_db()
    assert hold.expires_at is None


def test_renewal_does_not_revive_an_expired_reservation():
    _channel("web", {"hold_ttl_minutes": 45})
    hold = _hold("TTLCRO")
    expired_at = timezone.now() - timedelta(minutes=1)
    Hold.objects.filter(pk=hold.pk).update(expires_at=expired_at)

    assert availability.bump_session_hold_expiry(SESSION, channel_ref="web") == 0

    hold.refresh_from_db()
    assert hold.expires_at == expired_at


@pytest.mark.parametrize("configured", [45, 10])
def test_growing_a_line_creates_the_new_reservation_with_the_channel_ttl(configured):
    """O acréscimo pelo seletor nasce com o prazo do canal, como o primeiro item."""
    _channel("web", {"hold_ttl_minutes": configured})
    first = _hold("TTLCRO", ttl_minutes=2)

    result = availability.reconcile("TTLCRO", Decimal("3"), session_key=SESSION, channel_ref="web")

    assert result["ok"], result
    new = Hold.objects.exclude(pk=first.pk).filter(metadata__reference=SESSION)
    assert new.exists()
    for hold in new:
        _assert_renewed_to(hold, configured)
