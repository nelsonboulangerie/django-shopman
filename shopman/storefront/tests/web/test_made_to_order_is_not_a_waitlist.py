"""Café e croque não entram em fila de espera — e o selo deles não é dedução.

⚠️ Relato de campo que originou este arquivo: a sacola mostrava "Lista de espera"
para um Jambon-Beurre e para cafés, a revisão do pedido dizia "avisamos quando
ficarem prontos", e o acompanhamento abria o painel de fila. Três telas mentindo,
e uma causa só — o carimbo do hold.

Duas reservas SEM PRAZO existem no sistema, e elas não são a mesma coisa:

  • fornada planejada (``quant`` datado) — o pão ainda não existe. É fila.
  • demanda (``quant is None``, política ``demand_ok``) — a casa aprova a venda
    sem saldo. Não há lote a esperar, logo não há fila em que entrar.

``metadata.planned`` carimbava as duas, e todo mundo que lia esse carimbo depois
herdava a confusão. Hoje cada uma tem a sua marca, e a pergunta "isto é fila?"
se responde no DADO (``waitlist.WAITLIST_HOLD_FILTER``: carimbo E lote), o que
alcança também os holds indefinidos gravados antes da separação.

⚠️⚠️ **E o selo saiu de cima da política.** "Preparado na hora" era deduzido de
``availability_policy == "demand_ok"`` — que é conferência de ESTOQUE, não uma
afirmação sobre o produto. No cardápio da casa as duas coincidem (café, salgados
de vitrine), mas coincidência não é contrato: um PÃO marcado ``demand_ok`` por
razão de estoque ganhava o selo, e apertar o croque para ``stock_only`` (o
natural quando se passa a controlar o estoque dele) tirava o selo, calado.

Agora são dois eixos com duas fontes, e eles não competem:

  • **o que o item É** → ``Product.metadata["made_to_order"]``, declarado pela casa.
  • **quando ele vem** → o hold desta linha.

Um croque que espera a fornada de amanhã é as duas coisas ao mesmo tempo, e a
sacola diz as duas. Estes testes existem para que ninguém volte a fundi-las.
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
    """Café expresso, como no catálogo real da casa.

    Duas coisas, de propósito, e elas são independentes: ``demand_ok`` é a
    política de CONFERÊNCIA DE ESTOQUE (vende mesmo sem saldo) e
    ``made_to_order`` é a PROMESSA da casa sobre o produto. No café as duas
    coincidem — e é justamente por coincidirem no catálogo que o selo pôde
    viver anos pendurado na política errada.
    """
    return Product.objects.create(
        sku="CAFE-EXPRESSO",
        name="Café expresso",
        base_price_q=600,
        is_published=True,
        is_sellable=True,
        availability_policy=AvailabilityPolicy.DEMAND_OK,
        metadata={"made_to_order": True},
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

    def test_the_badge_and_the_queue_are_independent_axes(self, client, channel):
        """⚠️ Os dois selos NÃO eram exclusivos "por construção" — eu conferi.

        Enquanto o selo saía de ``availability_policy``, um PÃO marcado
        ``demand_ok`` (política de estoque: "vende sem saldo") com fornada
        planejada carregava "Preparado na hora" E "Lista de espera" — a segunda
        certa, a primeira uma promessa que ninguém tinha feito.

        Separados, cada eixo responde à sua pergunta: a casa não declarou este
        pão como preparado na hora, então ele não ganha selo; e o hold ancorou
        no lote planejado, então ele É fila.
        """
        from datetime import date, timedelta
        from decimal import Decimal as D

        from shopman.stockman.models import Position, Quant

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        pao = Product.objects.create(
            sku="PAO-DEMAND-OK",
            name="Pão de forma",
            base_price_q=1200,
            is_published=True,
            is_sellable=True,
            availability_policy=AvailabilityPolicy.DEMAND_OK,
            # A casa NÃO declarou: pão não é preparado na hora.
            metadata={},
        )
        _ensure_listing_item(channel, pao, price_q=1200)

        position, _ = Position.objects.get_or_create(
            ref="producao", defaults={"name": "Produção"},
        )
        Quant.objects.create(
            sku=pao.sku,
            position=position,
            target_date=date.today() + timedelta(days=1),
            _quantity=D("20"),
        )
        channel.config = {
            **(channel.config or {}),
            "waitlist": {"enabled": True, "horizon_days": 2},
        }
        channel.save(update_fields=["config"])

        _add(client, pao.sku)

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)
        line = next(item for item in cart.items if item.sku == pao.sku)

        assert line.is_awaiting_confirmation is True, (
            "pão com fornada planejada e sem estoque hoje É fila — a política de "
            "disponibilidade não muda isso"
        )
        assert line.is_made_to_order is False, (
            "o selo é declarado pela casa, não deduzido da política de estoque"
        )
        assert line.made_to_order_label == ""

    def test_the_showcase_croque_keeps_the_badge(self, client, channel):
        """O caso que o Pablo levantou: lote pré-preparado na vitrine.

        Croque sai de uma fornada realizada (``Quant.target_date=None``, com
        Batch) e ainda assim é gratinado no momento de servir. O selo é sobre o
        ACABAMENTO, e por isso vale mesmo vindo da vitrine. Não é fila: o lote
        já saiu.
        """
        from datetime import date
        from decimal import Decimal as D

        from shopman.stockman.models import Batch, Position, PositionKind, Quant

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        croque = Product.objects.create(
            sku="CMO",
            name="Croque Monsieur",
            base_price_q=2400,
            is_published=True,
            is_sellable=True,
            availability_policy=AvailabilityPolicy.DEMAND_OK,
            metadata={"made_to_order": True},
        )
        _ensure_listing_item(channel, croque, price_q=2400)

        position, _ = Position.objects.get_or_create(
            ref="vitrine",
            defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
        )
        Batch.objects.create(sku="CMO", ref="CMO-20260830", production_date=date.today())
        # Fornada JÁ REALIZADA: realize() credita quant físico (target_date=None).
        Quant.objects.create(
            sku="CMO",
            position=position,
            batch="CMO-20260830",
            target_date=None,
            _quantity=D("10"),
        )

        _add(client, croque.sku)

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)
        line = next(item for item in cart.items if item.sku == croque.sku)

        assert line.is_made_to_order is True
        assert line.is_awaiting_confirmation is False, (
            "lote realizado é estoque físico, não fornada a esperar"
        )

    def test_the_policy_alone_no_longer_grants_the_badge(self, client, channel):
        """A contraprova do desacoplamento, no sentido que quebrava calado.

        Apertar o croque para ``stock_only`` (o natural quando se passa a
        controlar o estoque dele) tirava o selo sem ninguém pedir. Agora a
        política não tem voto: quem declara é a casa.
        """
        from decimal import Decimal as D

        from shopman.stockman.models import Position, PositionKind, Quant

        from shopman.storefront.tests.web.conftest import _ensure_listing_item

        croque = Product.objects.create(
            sku="QQ",
            name="Queijo-Quente",
            base_price_q=2600,
            is_published=True,
            is_sellable=True,
            availability_policy=AvailabilityPolicy.STOCK_ONLY,
            metadata={"made_to_order": True},
        )
        _ensure_listing_item(channel, croque, price_q=2600)
        position, _ = Position.objects.get_or_create(
            ref="vitrine",
            defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
        )
        Quant.objects.create(sku="QQ", position=position, target_date=None, _quantity=D("5"))

        _add(client, croque.sku)

        cart = build_cart(request=_request_wearing(client), channel_ref=STOREFRONT_CHANNEL_REF)
        line = next(item for item in cart.items if item.sku == croque.sku)

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
