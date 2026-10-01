"""Ajustar a quantidade na sacola nunca custa a reserva que ela já tinha.

O defeito que estes testes fecham (medido em 01/10/2026 no ``main``): com a
fila de espera ligada, a primeira unidade de uma fornada de amanhã entrava na
sacola ancorada no dia da FORNADA (``reserve`` resolve a data pela fila), mas
todo ajuste posterior passava por ``reconcile``, que criava o hold sem data —
isto é, para HOJE, onde não há nada. Daí:

- aumentar de 2 para 4 numa fornada de 4 dava 409 com "disponível 0";
- diminuir de 2 para 1 soltava o hold de 2 e tentava re-reservar 1 para hoje;
  a compensação falhava, o log dizia ``session now under-reserved`` e a linha
  ficava com 1 na tela e ZERO reservado — o cliente perdia a vaga na fila.

A régua: ou o ajuste acontece inteiro, ou nada muda.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind

from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db

TOMORROW = date.today() + timedelta(days=1)


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _enable_waitlist(channel):
    channel.config = {**(channel.config or {}), "waitlist": {"enabled": True, "horizon_days": 2}}
    channel.save(update_fields=["config"])


def _plan_tomorrow(product, qty: str):
    stock.plan(
        quantity=Decimal(qty), product=product, target_date=TOMORROW,
        position=_position(), reason="fornada de amanhã (teste de ajuste)",
    )


def _receive_today(product, qty: str):
    stock.receive(
        quantity=Decimal(qty), sku=product.sku, position=_position(),
        target_date=date.today(), reason="pronta-entrega (teste de ajuste)",
    )


def _set_qty(client, sku, qty):
    return client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


def _active_holds(sku):
    return list(Hold.objects.filter(sku=sku).active().order_by("pk"))


def _reserved(sku) -> Decimal:
    return sum((h.quantity for h in _active_holds(sku)), Decimal("0"))


def _line_qty(client, sku) -> int:
    cart = client.get("/api/v1/storefront/cart/").json()["cart"]
    line = next((item for item in cart["items"] if item["sku"] == sku), None)
    return int(line["qty"]) if line else 0


@pytest.fixture
def queue(channel, product):
    """Fila ligada, nada pronto hoje, fornada de 4 amanhã."""
    _ensure_listing_item(channel, product, price_q=90)
    _enable_waitlist(channel)
    _plan_tomorrow(product, "4")
    return product


class TestQueueReservationAdjustments:
    def test_growing_inside_the_batch_is_admitted_on_the_batch_day(self, client, queue):
        assert _set_qty(client, queue.sku, 2).status_code == 200

        resp = _set_qty(client, queue.sku, 4)

        assert resp.status_code == 200, resp.content[:400]
        assert _reserved(queue.sku) == Decimal("4")
        assert {h.target_date for h in _active_holds(queue.sku)} == {TOMORROW}, (
            "o acréscimo entra na mesma fornada, não em HOJE"
        )
        assert all(h.metadata.get("planned") for h in _active_holds(queue.sku))
        assert _line_qty(client, queue.sku) == 4

    def test_refusal_above_the_batch_keeps_the_reservation(self, client, queue):
        assert _set_qty(client, queue.sku, 2).status_code == 200

        refused = _set_qty(client, queue.sku, 6)

        assert refused.status_code == 409
        assert refused.json()["is_planned"] is True, (
            "recusa de fila é 'próximo lote', não 'acabou'"
        )
        assert _reserved(queue.sku) == Decimal("2"), "o 409 não toca na reserva que existia"
        assert _line_qty(client, queue.sku) == 2

        # E o que cabe continua cabendo: o cliente compra o que existe.
        assert _set_qty(client, queue.sku, 4).status_code == 200
        assert _reserved(queue.sku) == Decimal("4")

    def test_shrinking_keeps_the_rest_of_the_queue_reservation(self, client, queue, caplog):
        assert _set_qty(client, queue.sku, 3).status_code == 200

        with caplog.at_level(logging.WARNING, logger="shopman.shop.services.availability"):
            # Duas reduções seguidas: a segunda solta o troco da primeira.
            assert _set_qty(client, queue.sku, 2).status_code == 200
            assert _reserved(queue.sku) == Decimal("2")
            resp = _set_qty(client, queue.sku, 1)

        assert resp.status_code == 200, resp.content[:400]
        assert "under-reserved" not in caplog.text
        assert "remainder hold failed" not in caplog.text
        holds = _active_holds(queue.sku)
        assert sum(h.quantity for h in holds) == Decimal("1"), "a linha diz 1 e a reserva também"
        assert {h.target_date for h in holds} == {TOMORROW}
        assert all(h.metadata.get("planned") for h in holds)
        assert all(h.expires_at is None for h in holds), "vaga na fila continua sem relógio"
        assert _line_qty(client, queue.sku) == 1

    def test_shrink_whose_compensation_fails_changes_nothing(self, client, queue):
        """Se a sobra não puder voltar para a sacola, o ajuste não acontece."""
        assert _set_qty(client, queue.sku, 2).status_code == 200
        before = [h.pk for h in _active_holds(queue.sku)]

        failure = {"success": False, "hold_id": None, "error_code": "INSUFFICIENT_AVAILABLE"}
        with patch("shopman.shop.adapters.stock.create_hold", return_value=failure):
            resp = _set_qty(client, queue.sku, 1)

        assert resp.status_code == 409
        assert [h.pk for h in _active_holds(queue.sku)] == before, "nada foi solto"
        assert _reserved(queue.sku) == Decimal("2")
        assert _line_qty(client, queue.sku) == 2


class TestTodayStockAdjustments:
    @pytest.mark.parametrize("waitlist_on", [False, True])
    def test_refusal_keeps_reservation_and_next_fitting_request_passes(
        self, client, channel, product, waitlist_on,
    ):
        _ensure_listing_item(channel, product, price_q=90)
        if waitlist_on:
            _enable_waitlist(channel)
        _receive_today(product, "3")

        assert _set_qty(client, product.sku, 2).status_code == 200
        assert _set_qty(client, product.sku, 5).status_code == 409
        assert _reserved(product.sku) == Decimal("2")
        assert _line_qty(client, product.sku) == 2

        assert _set_qty(client, product.sku, 3).status_code == 200
        assert _reserved(product.sku) == Decimal("3")

        assert _set_qty(client, product.sku, 1).status_code == 200
        holds = _active_holds(product.sku)
        assert sum(h.quantity for h in holds) == Decimal("1")
        assert {h.target_date for h in holds} == {date.today()}
        assert _line_qty(client, product.sku) == 1


class TestOneLineOneDate:
    def test_growing_a_ready_line_never_splits_it_across_days(self, client, channel, product):
        """Linha de pronta-entrega cresce dentro de HOJE; a fornada não entra pela porta dos fundos.

        O número que cabe (e se a linha deveria poder virar "parte hoje, parte
        amanhã") é decisão de produto; o invariante aqui é que a linha promete
        um dia só e que a reserva bate com a linha, seja qual for a resposta.
        """
        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        _receive_today(product, "2")
        _plan_tomorrow(product, "4")

        assert _set_qty(client, product.sku, 2).status_code == 200
        _set_qty(client, product.sku, 4)

        holds = _active_holds(product.sku)
        assert {h.target_date for h in holds} == {date.today()}
        assert sum(h.quantity for h in holds) == Decimal(_line_qty(client, product.sku))
