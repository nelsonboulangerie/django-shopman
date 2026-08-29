"""Café e Jambon-Beurre não entram em fila de espera — eles são FEITOS NA HORA.

⚠️ Relato de campo que originou este arquivo: a sacola mostrava "Lista de espera"
para um Jambon-Beurre e para cafés, a revisão do pedido dizia "avisamos quando
ficarem prontos", e o acompanhamento abria o painel de fila. Três telas mentindo,
e uma causa só.

A causa era o carimbo do hold. Duas reservas SEM PRAZO existem no sistema:

  • fornada planejada (``quant.target_date``) — o pão ainda não existe. É fila.
  • demanda (``quant is None``, política ``demand_ok``) — montado quando o pedido
    entra. Não há lote a esperar, logo não há fila em que entrar.

As duas ficam sem TTL, e por isso PARECIAM iguais — mas ``metadata.planned``
carimbava as duas, e todo mundo que lia esse carimbo depois herdava a confusão.
O próprio adapter já sabia distinguir (``is_planned`` saía ``False`` para a
demanda) e jogava a distinção fora na linha seguinte.

Agora cada uma tem a sua marca: ``planned`` para a fornada, ``on_demand`` para a
demanda. Estes testes existem para que ninguém volte a fundi-las.
"""
from __future__ import annotations

import json

import pytest
from django.test import RequestFactory
from shopman.offerman.models import AvailabilityPolicy, Product

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import build_cart

pytestmark = pytest.mark.django_db


@pytest.fixture
def cafe(db):
    """Café expresso: `demand_ok`, como no catálogo real da casa."""
    return Product.objects.create(
        sku="CAFE-EXPRESSO",
        name="Café expresso",
        base_price_q=600,
        is_published=True,
        is_sellable=True,
        availability_policy=AvailabilityPolicy.DEMAND_OK,
    )


def _request_wearing(client):
    rf = RequestFactory()
    request = rf.get("/sacola/")
    request.session = client.session  # type: ignore[attr-defined]
    return request


def _add(client, sku: str, qty: int = 1):
    return client.put(
        f"/api/v1/cart/skus/{sku}/",
        data=json.dumps({"qty": qty}),
        content_type="application/json",
    )


class TestTheHoldMarker:
    def test_a_demand_hold_is_not_stamped_as_planned(self, client, channel, cafe):
        """O carimbo é o que três telas leem. Errar aqui erra nas três."""
        from shopman.stockman.models import Hold

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, cafe, price_q=600)
        assert _add(client, cafe.sku).status_code in (200, 201)

        holds = list(Hold.objects.filter(sku=cafe.sku))
        assert holds, "a reserva de demanda deveria existir"
        for hold in holds:
            metadata = hold.metadata or {}
            assert metadata.get("on_demand") is True
            assert "planned" not in metadata, (
                "reserva de demanda carimbada como planejada: é isto que faz um "
                "café aparecer em 'Lista de espera'"
            )

    def test_the_demand_hold_still_has_no_ttl(self, client, channel, cafe):
        """Separar as marcas não pode ligar um relógio que nunca existiu.

        A reserva de demanda é indefinida porque não há materialização a esperar —
        e isso continua valendo.
        """
        from shopman.stockman.models import Hold

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, cafe, price_q=600)
        _add(client, cafe.sku)

        for hold in Hold.objects.filter(sku=cafe.sku):
            assert hold.expires_at is None


class TestTheCartLine:
    def test_the_line_says_made_to_order_and_never_waitlist(self, client, channel, cafe):
        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, cafe, price_q=600)
        _add(client, cafe.sku)

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)
        line = next(item for item in cart.items if item.sku == cafe.sku)

        assert line.is_made_to_order is True
        assert line.made_to_order_label  # o selo tem texto (copy do Admin)
        assert line.is_awaiting_confirmation is False
        assert line.is_ready_for_confirmation is False
        assert line.planned_for_notice is None

    def test_the_cart_does_not_raise_the_waitlist_banner_for_a_coffee(
        self, client, channel, cafe,
    ):
        """O aviso do topo é o mesmo sinal: se ele sobe, a sacola inteira mente."""
        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, cafe, price_q=600)
        _add(client, cafe.sku)

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)

        assert cart.has_awaiting_confirmation_items is False
        assert cart.has_ready_for_confirmation_items is False

    def test_a_legacy_coffee_hold_stamped_planned_does_not_raise_the_badge(
        self, client, channel, cafe,
    ):
        """O banco herdou reservas de café carimbadas ``planned``, e elas não expiram.

        Separar as marcas conserta o café que entra na sacola de hoje. Quem já
        estava lá continuaria lendo "Lista de espera" para sempre — reserva
        indefinida não tem prazo para morrer. Perguntar pelo LOTE (fila espera
        lote, lote tem quant) conserta os dois tempos sem migração de dado.
        """
        from shopman.stockman.models import Hold

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        _ensure_listing_item(channel, cafe, price_q=600)
        _add(client, cafe.sku)

        # Reescreve o carimbo para o de antes de 29/08 — o que está no banco vivo.
        for hold in Hold.objects.filter(sku=cafe.sku):
            hold.metadata = {**(hold.metadata or {}), "planned": True}
            hold.save(update_fields=["metadata"])

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)
        line = next(item for item in cart.items if item.sku == cafe.sku)

        assert line.is_awaiting_confirmation is False
        assert cart.has_awaiting_confirmation_items is False
        assert line.is_made_to_order is True

    def test_a_shelf_item_is_not_labelled_made_to_order(self, client, channel, product):
        """A contraprova: pão de prateleira não ganha o selo de preparado na hora."""
        from shopman.storefront.tests.web.conftest import (
            _ensure_listing_item,
            _seed_stock_for_product_sku,
        )

        _seed_stock_for_product_sku(product.sku)
        _ensure_listing_item(channel, product, price_q=90)
        _add(client, product.sku)

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)
        line = next(item for item in cart.items if item.sku == product.sku)

        assert line.is_made_to_order is False
        assert line.made_to_order_label == ""


class TestTheOrderTracking:
    """A fila do acompanhamento lê o carimbo do hold — e lia o carimbo errado."""

    def _hold(self, order, *, marker: str, sku: str = "CAFE-EXPRESSO", batch: bool | None = None):
        """Reserva viva do pedido, sem prazo, com a marca sob teste.

        Sem prazo é o que as DUAS reservas indefinidas têm em comum; a marca é o
        que as separa. Montar as duas aqui, lado a lado, é o ponto do teste.

        ⚠️ E a reserva de fila nasce ANCORADA no lote que espera: ``next_batch_date``
        só devolve data onde existe quant planejado, e o hold ancora nele. Montar
        uma fila sem quant seria um mundo que a produção não produz — e foi
        exatamente o que deixou passar o café carimbado de "planned": enquanto o
        teste aceita fila sem lote, o carimbo sozinho parece bastar.
        """
        from datetime import date, timedelta
        from decimal import Decimal as D

        from shopman.stockman.models import Hold, HoldStatus, Position, Quant

        # ``batch`` diz se existe LOTE por trás da reserva. Default: a fornada
        # planejada tem, a demanda não — que é o mundo real. Passar explícito
        # monta o caso híbrido (carimbo de fila sem lote) que o banco herdou.
        has_batch = (marker == "planned") if batch is None else batch
        quant = None
        if has_batch:
            position, _ = Position.objects.get_or_create(
                ref="forno", defaults={"name": "Forno"},
            )
            quant = Quant.objects.create(
                sku=sku,
                position=position,
                target_date=date.today() + timedelta(days=1),
                _quantity=D("10"),
            )

        return Hold.objects.create(
            sku=sku,
            quant=quant,
            quantity=D("1"),
            status=HoldStatus.PENDING,
            expires_at=None,
            target_date=date.today(),
            metadata={"reference": f"order:{order.ref}", marker: True},
        )

    def _order(self, channel):
        from shopman.orderman.models import Order

        return Order.objects.create(
            ref="WEB-CAFE-1",
            channel_ref=channel.ref,
            status="new",
            total_q=600,
            handle_type="guest",
            handle_ref="teste",
            data={},
        )

    def test_a_made_to_order_hold_does_not_put_the_order_in_a_queue(self, channel):
        from shopman.shop.services import waitlist

        order = self._order(channel)
        self._hold(order, marker="on_demand")

        assert waitlist._order_holds(order), "a reserva do pedido tem que ser encontrada"
        assert waitlist.state_for(order) == waitlist.NONE

    def test_a_planned_batch_hold_still_does(self, channel):
        """Contraprova: o pão que espera fornada CONTINUA em fila.

        Sem esta metade, apagar a fila inteira passaria no teste acima.
        """
        from shopman.shop.services import waitlist

        order = self._order(channel)
        self._hold(order, marker="planned", sku="PAO-DE-FORNADA")

        assert waitlist.state_for(order) == waitlist.FERMATA

    def test_a_legacy_coffee_stamped_planned_no_longer_reads_as_a_queue(self, channel):
        """Os holds gravados ANTES da separação seguem vivos no banco.

        Reserva indefinida não expira nunca: o café que entrou na sacola de
        alguém em 28/08 continua lá, carimbado ``planned``, dizendo "fila" sobre
        um item que não sai de fornada nenhuma. Separar as marcas conserta quem
        nasce depois; a pergunta pelo LOTE conserta os dois tempos, e sem
        migração de dado — fila espera um lote, e lote tem quant.
        """
        from shopman.shop.services import waitlist

        order = self._order(channel)
        self._hold(order, marker="planned", sku="CAFE-EXPRESSO", batch=False)

        assert waitlist.state_for(order) == waitlist.NONE
