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

A régua: aumentar acontece inteiro ou não acontece; reduzir nunca falha e nunca
solta o que ainda existe. E a sobra devolvida é do tipo do quant em que cai: a
sobra da fila que cai em pão pronto vira reserva comum de sacola (com prazo e
com a margem da vitrine), nunca "fila" presa sem relógio.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind, Quant
from shopman.stockman.services.movements import StockMovements

from shopman.shop.adapters.stock import is_cart_hold
from shopman.shop.services.waitlist import is_waitlist_hold
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


def _receive_ready(product, qty: str):
    """Pão pronto como a produção grava: quant físico, sem data."""
    stock.receive(
        quantity=Decimal(qty), sku=product.sku, position=_position(),
        target_date=None, reason="pronta-entrega (teste de ajuste)",
    )


def _set_margin(channel, margin: int):
    """A margem da vitrine do canal (``stock.safety_margin``; o alpha usa 2)."""
    cfg = dict(channel.config or {})
    cfg["stock"] = {**(cfg.get("stock") or {}), "safety_margin": margin}
    channel.config = cfg
    channel.save(update_fields=["config"])


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

    def test_queue_remainder_landing_on_ready_bread_is_a_regular_cart_hold(
        self, client, channel, product,
    ):
        """Sobra da fila que cai no pão pronto que chegou: reserva comum, nunca 'fila'.

        O Stockman escolhe o quant por validade, não pela origem da reserva; o
        pão pronto (quant sem data, como a produção grava) vence a fornada.
        Herdar ``planned`` e o "sem prazo" da fila prenderia pão pronto sem
        relógio, fora do alcance do balcão e da materialização da fornada.
        """
        _ensure_listing_item(channel, product, price_q=90)
        _enable_waitlist(channel)
        # O quant de pronta-entrega já existiu e foi vendido: nasce antes da fornada.
        _receive_ready(product, "2")
        StockMovements.issue(
            Decimal("2"), Quant.objects.get(sku=product.sku, target_date__isnull=True), reason="vendido",
        )
        _plan_tomorrow(product, "4")
        assert _set_qty(client, product.sku, 3).status_code == 200
        assert {h.target_date for h in _active_holds(product.sku)} == {TOMORROW}

        _receive_ready(product, "5")  # chega a pronta-entrega
        assert _set_qty(client, product.sku, 2).status_code == 200

        assert _reserved(product.sku) == Decimal("2")
        assert any(
            h.quant is not None and h.quant.target_date is None for h in _active_holds(product.sku)
        ), "o cenário exige que a sobra caia no pão pronto"
        for hold in _active_holds(product.sku):
            on_ready_bread = hold.quant is not None and hold.quant.target_date is None
            if on_ready_bread:
                assert not hold.metadata.get("planned"), "pão pronto não é fila"
                assert hold.expires_at is not None, "reserva de pão pronto corre relógio"
                assert is_cart_hold(hold), "o balcão alcança a reserva de sacola"
                assert not is_waitlist_hold(hold)
            else:
                assert is_waitlist_hold(hold) and hold.expires_at is None


class TestShrinkNeverFails:
    def test_shrink_after_the_quant_shrank_keeps_what_exists(self, client, channel, product):
        """Sacola com 3 prontos; uma perda deixa o quant em 1; o cliente pede 2.

        Reduzir não pode ser recusado (antes: 409 "INSUFFICIENT_AVAILABLE" com
        "Usar 3.000 unidades"). A linha fica com o que o cliente pediu; a
        reserva, com o que existe.
        """
        _ensure_listing_item(channel, product, price_q=90)
        _receive_today(product, "3")
        assert _set_qty(client, product.sku, 3).status_code == 200
        StockMovements.adjust(
            Quant.objects.get(sku=product.sku, target_date=date.today()), Decimal("1"), reason="perda",
        )

        resp = _set_qty(client, product.sku, 2)

        assert resp.status_code == 200, resp.content[:400]
        assert _line_qty(client, product.sku) == 2
        assert _reserved(product.sku) == Decimal("1"), "a reserva fica com o que existe"


    @pytest.mark.parametrize("margin", [0, 2])
    def test_shrink_after_a_loss_keeps_the_unit_the_cart_held_whatever_the_margin(
        self, client, channel, product, margin,
    ):
        """5 prontos, sacola com 3, a perda deixa o quant com 1, o cliente pede 2.

        O pão que sobrou é da sacola: ela o segurava antes da perda. Com a
        margem 2 (a do alpha) a devolução reaplicava a margem e, com o livre do
        quant (1) abaixo dela, a sacola ficava com ZERO reservado, embora o pão
        existisse. A margem protege a vitrine do estoque que ninguém segura,
        não o que a própria sacola já tinha.
        """
        _ensure_listing_item(channel, product, price_q=90)
        _set_margin(channel, margin)
        _receive_ready(product, "5")
        assert _set_qty(client, product.sku, 3).status_code == 200
        quant = Quant.objects.get(sku=product.sku, target_date__isnull=True)
        StockMovements.adjust(quant, Decimal("1"), reason="perda")

        resp = _set_qty(client, product.sku, 2)

        assert resp.status_code == 200, resp.content[:400]
        assert _line_qty(client, product.sku) == 2
        holds = _active_holds(product.sku)
        assert sum(h.quantity for h in holds) == Decimal("1"), "a reserva fica com o pão que existe"
        assert {h.quant_id for h in holds} == {quant.pk}
        assert all(is_cart_hold(h) and h.expires_at is not None for h in holds)
        quant.refresh_from_db()
        assert quant.available == Decimal("0"), "nunca reserva além do que existe"

    @pytest.mark.parametrize(("margin", "reserved"), [(2, "1"), (1, "2"), (0, "2")])
    def test_the_margin_still_guards_stock_the_cart_never_held(
        self, client, channel, product, margin, reserved,
    ):
        """A sobra só dispensa a margem no quant que já era da sacola.

        5 prontos (quant A), sacola com 3; depois chegam 2 do dia (quant B),
        que a sacola nunca segurou. A perda deixa A com 1 e o cliente pede 2.
        Com margem 2 só o 1 de A volta (sem margem, era da sacola) e B fica
        inteiro na vitrine; com margem menor, a sobra inteira cabe com a margem
        valendo. Em todos, o livre que sobra nunca fica abaixo da margem.
        """
        _ensure_listing_item(channel, product, price_q=90)
        _set_margin(channel, margin)
        _receive_ready(product, "5")
        assert _set_qty(client, product.sku, 3).status_code == 200
        own = Quant.objects.get(sku=product.sku, target_date__isnull=True)
        _receive_today(product, "2")
        other = Quant.objects.get(sku=product.sku, target_date=date.today())
        StockMovements.adjust(own, Decimal("1"), reason="perda")

        resp = _set_qty(client, product.sku, 2)

        assert resp.status_code == 200, resp.content[:400]
        assert _line_qty(client, product.sku) == 2
        assert _reserved(product.sku) == Decimal(reserved)
        own.refresh_from_db()
        other.refresh_from_db()
        assert own.available >= 0 and other.available >= 0, "nunca reserva além do que existe"
        assert own.available + other.available >= Decimal(margin), "a margem vale no estoque alheio"
        if margin == 2:
            assert own.available == Decimal("0") and other.available == Decimal("2")


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
