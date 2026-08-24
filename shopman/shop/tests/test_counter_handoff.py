"""Venda de balcão presencial: um evento já ocorrido, não uma esteira.

O pão sai pela porta antes do commit. Três consequências, cada uma ancorada
aqui:

1. o pedido FECHA no próprio fechamento da venda (ACCEPTED→COMPLETED via
   ``system:counter_handoff``) — mas só se o CANAL declarou a transição no seu
   ``lifecycle.transitions`` (config-driven, assada no snapshot);
2. item de prateleira NÃO vira ticket de picking nem alerta de item sem
   estação (``prep_only``) — a estação "Encomendas" é para pedido que alguém
   precisa separar, não para a sacola que o cliente já segura;
3. a NFC-e é enfileirada UMA vez, com dedupe no banco, mesmo com dois
   gatilhos (fechamento da venda + ``on_completed``).
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive, Order

from shopman.shop import lifecycle
from shopman.shop.config import ChannelConfig
from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.models import Channel, Shop
from shopman.shop.services import fiscal as fiscal_service

pytestmark = pytest.mark.django_db

# O mapa default + a permissão do balcão (o que o seed grava no canal pdv).
POS_TRANSITIONS = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "completed", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["preparing", "dispatched", "completed"],
    "dispatched": ["delivered", "returned"],
    "delivered": ["completed", "returned"],
    "completed": ["returned", "cancelled"],
    "cancelled": [],
    "returned": [],
}


class StubFiscalBackend:
    def emit(self, **kwargs):
        from shopman.fiscalman.contracts import FiscalDocumentResult

        return FiscalDocumentResult(success=True, access_key="stub", status="authorized")

    def query_status(self, *, reference):
        from shopman.fiscalman.contracts import FiscalDocumentResult

        return FiscalDocumentResult(success=False, status="pending")

    def cancel(self, *, reference, reason):
        from shopman.fiscalman.contracts import FiscalCancellationResult

        return FiscalCancellationResult(success=True)


@pytest.fixture(autouse=True)
def _shop_and_channel():
    Shop.objects.create(name="Test Shop", brand_name="Test")
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False, "allow_untracked": True},
            "lifecycle": {"transitions": POS_TRANSITIONS},
        },
    )
    fiscal_pool.reset()
    yield
    fiscal_pool.reset()


def _counter_order(ref="PDV-TEST-1", *, transitions=POS_TRANSITIONS, data_extra=None, status=Order.Status.ACCEPTED):
    data = {
        "origin_channel": "pos",
        "fulfillment_type": "pickup",
        "payment": {"method": "cash", "collection": "terminal", "amount_q": 1000,
                    "tenders": [{"method": "cash", "amount_q": 1000, "status": "received"}]},
    }
    if data_extra:
        data.update(data_extra)
    snapshot = {"items": [{"sku": "PAO", "name": "Pão", "qty": 1, "price_q": 1000}]}
    if transitions is not None:
        snapshot["lifecycle"] = {"transitions": transitions}
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        session_key=f"sess-{ref}",
        status=status,
        total_q=1000,
        data=data,
        snapshot=snapshot,
    )


def test_counter_sale_completes_at_accept():
    """Sem trabalho de cozinha, o balcão fecha na hora — via a transição do canal."""
    order = _counter_order()
    config = ChannelConfig.for_channel("pdv")

    lifecycle._on_accepted(order, config)

    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_channel_without_the_transition_keeps_the_esteira():
    """Config-driven de verdade: sem a permissão no snapshot, nada muda."""
    order = _counter_order(ref="PDV-TEST-2", transitions=None)  # DEFAULT_TRANSITIONS
    config = ChannelConfig.for_channel("pdv")

    lifecycle._on_accepted(order, config)

    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED


def test_delivery_sale_keeps_the_esteira():
    """Entrega tem trajeto pela frente; a esteira existe para ela."""
    order = _counter_order(ref="PDV-TEST-3", data_extra={"fulfillment_type": "delivery"})
    config = ChannelConfig.for_channel("pdv")

    lifecycle._on_accepted(order, config)

    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED


@override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.tests.test_counter_handoff.StubFiscalBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.always",
)
def test_fiscal_emission_is_deduped_across_both_triggers():
    """Dois gatilhos (fechamento + on_completed), UMA directive viva."""
    order = _counter_order(ref="PDV-TEST-4")

    fiscal_service.emit(order)
    fiscal_service.emit(order)  # segundo gatilho: dedupe-hit, não segunda nota

    directives = Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)
    assert directives.count() == 1


def test_completed_counter_sale_can_still_be_undone_in_the_window():
    """O desfazer não morre no commit: completed cancela DENTRO da janela,
    porque o canal do balcão declarou completed→cancelled."""
    from shopman.shop.services import pos as pos_service

    order = _counter_order(
        ref="PDV-TEST-8",
        status=Order.Status.COMPLETED,
        data_extra={"payment": {"method": "card", "collection": "terminal", "amount_q": 1000,
                                "tenders": [{"method": "card", "amount_q": 1000, "status": "received"}]}},
    )

    pos_service.cancel_recent_order(order_ref=order.ref, actor="op", max_age_minutes=10)

    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED


def test_completed_sale_without_the_transition_still_refuses_cancel():
    """Canal sem completed→cancelled continua protegido: o guard segue a máquina."""
    from shopman.shop.services import pos as pos_service

    order = _counter_order(ref="PDV-TEST-9", transitions=None, status=Order.Status.COMPLETED)

    with pytest.raises(ValueError):
        pos_service.cancel_recent_order(order_ref=order.ref, actor="op", max_age_minutes=10)


def test_customer_holds_the_goods_predicate():
    from shopman.shop.services.kds import _customer_holds_the_goods

    counter = _counter_order(ref="PDV-TEST-5")
    assert _customer_holds_the_goods(counter) is True

    delivery = _counter_order(ref="PDV-TEST-6", data_extra={"fulfillment_type": "delivery"})
    assert _customer_holds_the_goods(delivery) is False

    web = _counter_order(ref="WEB-TEST-7", data_extra={"origin_channel": "web"})
    assert _customer_holds_the_goods(web) is False
