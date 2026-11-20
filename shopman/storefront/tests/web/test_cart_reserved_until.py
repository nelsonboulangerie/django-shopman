"""A sacola diz até quando guarda os itens (WP-L11, decisão do dono 4 de 16/11/2026).

O prazo é do servidor: o menor ``expires_at`` das reservas vivas da sessão. A
tela só o repete ("Guardamos seus itens até 19h18"), e conta o tempo pelo relógio
que veio na mesma resposta. Estes testes fecham o que a hora não pode fazer:
prometer sem reserva, prometer por uma reserva que não tem prazo (fornada futura)
e continuar prometendo depois de vencida.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind
from shopman.utils.formatting import format_clock, format_local

from shopman.shop.projections import cart as cart_data
from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _receive_ready(product, qty: str):
    """Pão pronto como a produção grava: quant físico, sem data."""
    stock.receive(
        quantity=Decimal(qty), sku=product.sku, position=_position(),
        target_date=None, reason="pronta-entrega (teste do prazo da reserva)",
    )


def _plan_tomorrow(product, qty: str):
    stock.plan(
        quantity=Decimal(qty), product=product,
        target_date=timezone.localdate() + timedelta(days=1),
        position=_position(), reason="fornada de amanhã (teste do prazo da reserva)",
    )


def _set_qty(client, sku, qty):
    return client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


def _cart(client) -> dict:
    return client.get("/api/v1/storefront/cart/").json()["cart"]


def _session_key(client) -> str:
    return client.session["cart_session_key"]


def _timed_holds(client):
    return Hold.objects.filter(
        metadata__reference=_session_key(client), expires_at__isnull=False,
    ).order_by("pk")


@pytest.fixture
def ready(channel, product):
    """Um produto com pão pronto na prateleira."""
    _ensure_listing_item(channel, product, price_q=90)
    _receive_ready(product, "20")
    return product


@pytest.fixture
def batch_tomorrow(channel, croissant):
    """Outro produto, sem nada pronto: só a fornada de amanhã, com a fila ligada."""
    _ensure_listing_item(channel, croissant, price_q=120)
    channel.config = {**(channel.config or {}), "waitlist": {"enabled": True, "horizon_days": 2}}
    channel.save(update_fields=["config"])
    _plan_tomorrow(croissant, "6")
    return croissant


class TestCartSaysUntilWhenItHoldsTheItems:
    def test_empty_cart_promises_no_time(self, client):
        cart = _cart(client)

        assert cart["is_empty"] is True
        assert cart["reserved_until_iso"] is None
        assert cart["reserved_until_display"] is None

    def test_ready_item_shows_the_hour_the_reservation_lasts_until(self, client, ready):
        assert _set_qty(client, ready.sku, 2).status_code == 200

        cart = _cart(client)
        hold = _timed_holds(client).get()

        assert datetime.fromisoformat(cart["reserved_until_iso"]) == hold.expires_at
        # A hora sai no formato da casa ("19h18", "9h05", "9h"): nunca "19:18".
        local = timezone.localtime(hold.expires_at)
        expected = f"{local.hour}h{local.minute:02d}" if local.minute else f"{local.hour}h"
        assert cart["reserved_until_display"] == expected
        assert ":" not in cart["reserved_until_display"]

    def test_the_mutation_answer_already_carries_the_hour(self, client, ready):
        response = _set_qty(client, ready.sku, 1)

        assert response.status_code == 200
        cart = response.json()["cart"]
        assert cart["reserved_until_iso"] is not None
        assert cart["reserved_until_display"]

    def test_server_clock_comes_with_the_cart_read(self, client, ready):
        _set_qty(client, ready.sku, 1)
        before = timezone.now()

        body = client.get("/api/v1/storefront/cart/").json()

        server_now = datetime.fromisoformat(body["server_now_iso"])
        assert before <= server_now <= timezone.now()
        # O prazo está no futuro PELO relógio do servidor: a tela não depende do aparelho.
        assert datetime.fromisoformat(body["cart"]["reserved_until_iso"]) > server_now

    def test_the_cart_itself_carries_no_clock(self, client, ready):
        """A projeção é o estado: duas leituras do mesmo estado saem iguais.

        Um relógio dentro dela quebraria quem compara ou guarda a sacola (o replay
        de uma oferta, o gêmeo público da home). O relógio mora no envelope.
        """
        _set_qty(client, ready.sku, 1)

        first = client.get("/api/v1/storefront/cart/").json()
        second = client.get("/api/v1/storefront/cart/").json()

        assert first["cart"] == second["cart"]
        assert "server_now_iso" not in first["cart"]

    def test_every_gesture_renews_the_hour(self, client, ready):
        _set_qty(client, ready.sku, 1)
        hold = _timed_holds(client).get()
        # A reserva já gastou parte do prazo: sobram 10 minutos.
        short = timezone.now() + timedelta(minutes=10)
        Hold.objects.filter(pk=hold.pk).update(expires_at=short)
        assert datetime.fromisoformat(_cart(client)["reserved_until_iso"]) == short

        renewed = _set_qty(client, ready.sku, 2).json()["cart"]

        assert datetime.fromisoformat(renewed["reserved_until_iso"]) > short + timedelta(minutes=5)

    def test_the_earliest_deadline_is_the_one_shown(self, client, ready, channel, croissant):
        _ensure_listing_item(channel, croissant, price_q=120)
        _receive_ready(croissant, "20")
        _set_qty(client, ready.sku, 1)
        _set_qty(client, croissant.sku, 1)
        first, second = list(_timed_holds(client))
        sooner = timezone.now() + timedelta(minutes=7)
        later = timezone.now() + timedelta(minutes=25)
        Hold.objects.filter(pk=first.pk).update(expires_at=later)
        Hold.objects.filter(pk=second.pk).update(expires_at=sooner)

        cart = _cart(client)

        assert datetime.fromisoformat(cart["reserved_until_iso"]) == sooner

    def test_only_a_future_batch_reservation_promises_no_time(self, client, batch_tomorrow):
        assert _set_qty(client, batch_tomorrow.sku, 2).status_code == 200

        cart = _cart(client)

        assert cart["is_empty"] is False
        # A vaga na fornada não tem relógio: prometer hora aqui seria inventar.
        assert not _timed_holds(client).exists()
        assert cart["reserved_until_iso"] is None
        assert cart["reserved_until_display"] is None

    def test_future_batch_does_not_change_the_hour_of_the_ready_item(self, client, ready, batch_tomorrow):
        _set_qty(client, ready.sku, 1)
        _set_qty(client, batch_tomorrow.sku, 1)

        cart = _cart(client)

        timed = _timed_holds(client).get()
        assert timed.sku == ready.sku
        assert datetime.fromisoformat(cart["reserved_until_iso"]) == timed.expires_at

    def test_expired_reservation_stops_promising(self, client, ready):
        _set_qty(client, ready.sku, 2)
        _timed_holds(client).update(expires_at=timezone.now() - timedelta(seconds=1))

        cart = _cart(client)

        # A sacola continua com a linha; o que não existe mais é a reserva.
        assert [item["sku"] for item in cart["items"]] == [ready.sku]
        assert cart["reserved_until_iso"] is None
        assert cart["reserved_until_display"] is None

    def test_another_session_reservation_is_not_mine(self, client, ready):
        from django.test import Client

        other = Client()
        assert _set_qty(other, ready.sku, 1).status_code == 200
        _set_qty(client, ready.sku, 1)
        mine = _timed_holds(client).get()
        Hold.objects.filter(metadata__reference=_session_key(other)).update(
            expires_at=timezone.now() + timedelta(minutes=2),
        )

        assert datetime.fromisoformat(_cart(client)["reserved_until_iso"]) == mine.expires_at


class TestCartSaysTheReservationLapsed:
    """Quem abre a sacola depois do prazo lê que a reserva venceu (#2767).

    Até o #2767 a frase só existia para quem estava com a sacola aberta na hora em
    que o prazo passou: a tela guardava a hora que viu vencer. Quem voltava depois
    via as linhas normais e nenhuma palavra sobre a reserva.
    """

    def _lapse(self, client, *, ago=timedelta(minutes=5)):
        expired_at = timezone.now() - ago
        _timed_holds(client).update(expires_at=expired_at)
        return expired_at

    def test_live_reservation_says_nothing_about_lapsing(self, client, ready):
        _set_qty(client, ready.sku, 1)

        assert _cart(client)["reservation_lapsed_display"] is None

    def test_reservation_past_its_deadline_says_until_when_it_held(self, client, ready):
        _set_qty(client, ready.sku, 2)
        expired_at = self._lapse(client)

        cart = _cart(client)

        assert cart["reserved_until_iso"] is None
        assert cart["reservation_lapsed_display"] == format_clock(expired_at)

    def test_reservation_released_by_the_sweep_still_says_it_lapsed(self, client, ready):
        from shopman.stockman.services.holds import StockHolds

        _set_qty(client, ready.sku, 2)
        expired_at = self._lapse(client)
        assert StockHolds.release_expired() >= 1

        cart = _cart(client)

        assert [item["sku"] for item in cart["items"]] == [ready.sku]
        assert cart["reservation_lapsed_display"] == format_clock(expired_at)

    def test_reservation_from_another_day_carries_the_date(self, client, ready):
        _set_qty(client, ready.sku, 1)
        expired_at = self._lapse(client, ago=timedelta(days=1))

        display = _cart(client)["reservation_lapsed_display"]

        assert display == format_local(expired_at, "%d/%m às {clock}")
        assert " às " in display

    def test_a_gesture_reserves_again_and_the_lapsed_hour_goes_away(self, client, ready):
        _set_qty(client, ready.sku, 1)
        self._lapse(client)
        assert _cart(client)["reservation_lapsed_display"]

        renewed = _set_qty(client, ready.sku, 2).json()["cart"]

        assert renewed["reserved_until_iso"] is not None
        assert renewed["reservation_lapsed_display"] is None

    def test_reservation_released_before_its_deadline_is_not_a_lapse(self, client, ready):
        _set_qty(client, ready.sku, 1)
        # Solta antes do prazo (não foi o relógio): a sacola não diz que venceu.
        _timed_holds(client).update(status="released", resolved_at=timezone.now())

        assert _cart(client)["reservation_lapsed_display"] is None

    def test_only_items_still_in_the_bag_count(self, client, ready, channel, croissant):
        _ensure_listing_item(channel, croissant, price_q=120)
        _receive_ready(croissant, "20")
        _set_qty(client, ready.sku, 1)
        _set_qty(client, croissant.sku, 1)
        session_key = _session_key(client)
        # A do pão venceu pelo relógio; a do croissant foi solta antes do prazo.
        _timed_holds(client).filter(sku=ready.sku).update(expires_at=timezone.now() - timedelta(minutes=5))
        _timed_holds(client).filter(sku=croissant.sku).update(status="released", resolved_at=timezone.now())

        assert cart_data.reservation_lapsed_at(session_key, [croissant.sku]) is None
        assert cart_data.reservation_lapsed_at(session_key, [ready.sku]) is not None

        # Tirado da sacola o último item, a sacola vazia não fala de reserva.
        _set_qty(client, ready.sku, 0)
        _set_qty(client, croissant.sku, 0)
        cart = _cart(client)
        assert cart["is_empty"] is True
        assert cart["reservation_lapsed_display"] is None

    def test_future_batch_reservation_never_lapses(self, client, batch_tomorrow):
        _set_qty(client, batch_tomorrow.sku, 1)

        assert _cart(client)["reservation_lapsed_display"] is None


class TestReservedUntilFacade:
    def test_no_session_no_deadline(self):
        assert cart_data.reserved_until(None) is None
        assert cart_data.reserved_until("") is None
        assert cart_data.reserved_until("sessao-que-nao-existe") is None

    def test_lapsed_needs_a_session_and_an_item(self):
        assert cart_data.reservation_lapsed_at(None, ["PAO"]) is None
        assert cart_data.reservation_lapsed_at("sessao", []) is None
        assert cart_data.reservation_lapsed_at("sessao-que-nao-existe", ["PAO"]) is None

    def test_released_reservation_does_not_count(self, client, ready):
        _set_qty(client, ready.sku, 1)
        assert cart_data.reserved_until(_session_key(client)) is not None

        # Tirar o item da sacola solta a reserva.
        assert _set_qty(client, ready.sku, 0).status_code == 200

        assert cart_data.reserved_until(_session_key(client)) is None


def _set_hold_ttl(channel, minutes: int | None):
    """O prazo da reserva do canal (``stock.hold_ttl_minutes``); ``None`` tira a configuração."""
    cfg = dict(channel.config or {})
    stock_cfg = {k: v for k, v in (cfg.get("stock") or {}).items() if k != "hold_ttl_minutes"}
    if minutes is not None:
        stock_cfg["hold_ttl_minutes"] = minutes
    cfg["stock"] = stock_cfg
    channel.config = cfg
    channel.save(update_fields=["config"])


class TestTheHourFollowsTheChannelTtl:
    """A hora que a sacola diz é o prazo do canal, na criação e em cada gesto (#2773)."""

    @pytest.mark.parametrize("configured", [30, 45, 10, None])
    def test_first_item_and_every_gesture_use_the_channel_ttl(self, client, ready, channel, configured):
        _set_hold_ttl(channel, configured)
        expected = timedelta(minutes=configured or 30)
        slack = timedelta(minutes=1)

        first = _set_qty(client, ready.sku, 1).json()["cart"]
        left = datetime.fromisoformat(first["reserved_until_iso"]) - timezone.now()
        assert expected - slack < left <= expected

        # A reserva gastou quase todo o prazo; um gesto a renova para o prazo do canal.
        _timed_holds(client).update(expires_at=timezone.now() + timedelta(minutes=2))
        renewed = _set_qty(client, ready.sku, 2).json()["cart"]

        left = datetime.fromisoformat(renewed["reserved_until_iso"]) - timezone.now()
        assert expected - slack < left <= expected
        # Todas as reservas da sacola ficam com o mesmo prazo: nenhuma com 30 por fora.
        for hold in _timed_holds(client):
            hold_left = hold.expires_at - timezone.now()
            assert expected - slack < hold_left <= expected, (hold.sku, hold_left)

