"""Pix de encomenda do PDV vence no prazo do LINK, não no do Pix de balcão (P2-26).

O Pix do balcão vale o ``payment.timeout_minutes`` do canal (10 min): o cliente
está na frente do caixa, com o celular na mão. A encomenda anotada no PDV não:
o cliente paga depois, de casa, e o pedido pode ser para a semana que vem.
Com o prazo do balcão, o Pix vencia em minutos e o ``payment.timeout``
cancelava a encomenda avisando o cliente.

A encomenda já tinha um prazo decidido para a cobrança remota: o do link de
pagamento, ``min(agora + janela do canal, corte do atendimento)``
(``adapters/_payment_link``, ``services/payment_deadline``). O Pix da mesma
encomenda segue o MESMO relógio; o Pix de balcão continua como estava.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent as PaymanIntent

from shopman.shop.directives import PAYMENT_TIMEOUT
from shopman.shop.models import Channel, Shop
from shopman.shop.services import payment as payment_service
from shopman.shop.services import payment_deadline

pytestmark = pytest.mark.django_db

MOCK_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "link": "shopman.shop.adapters.payment_mock",
    "cash": None,
    "external": None,
}

OPEN_9_TO_18 = {
    day: {"open": "09:00", "close": "18:00"}
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
}


def _setup(*, pix_minutes: int = 10, link_minutes: int = 120) -> None:
    cache.clear()
    Shop.objects.create(
        name="Test Shop", brand_name="Test", timezone="America/Sao_Paulo", opening_hours=OPEN_9_TO_18
    )
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={
            "payment": {
                "method": "cash",
                "timing": "external",
                "timeout_minutes": pix_minutes,
                "link_timeout_minutes": link_minutes,
            }
        },
    )


def _pix_order(ref: str, **data) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=Order.Status.ACCEPTED,
        total_q=900,
        data={
            "origin_channel": "pos",
            "fulfillment_type": "pickup",
            "payment": {"method": "pix", "collection": "terminal"},
            **data,
        },
    )


def _expires_at(order: Order) -> datetime:
    order.refresh_from_db()
    return datetime.fromisoformat(order.data["payment"]["expires_at"])


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS, SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False)
def test_pix_de_encomenda_da_semana_que_vem_vale_a_janela_do_link():
    _setup(pix_minutes=10, link_minutes=120)
    next_week = (timezone.localdate() + timedelta(days=7)).isoformat()
    order = _pix_order("PDV-PIX-SEMANA", delivery_date=next_week)

    payment_service.initiate(order)

    expires_at = _expires_at(order)
    remaining = expires_at - timezone.now()
    assert timedelta(minutes=110) < remaining <= timedelta(minutes=120)
    assert PaymanIntent.objects.get(order_ref=order.ref).expires_at == expires_at
    directive = Directive.objects.get(topic=PAYMENT_TIMEOUT, payload__order_ref=order.ref)
    assert directive.available_at == expires_at


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS, SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False)
def test_pix_de_encomenda_nao_passa_do_corte_do_atendimento():
    """Retirada em 40 min: o Pix não pode valer além dela, como o link."""
    _setup(pix_minutes=10, link_minutes=120)
    order = _pix_order("PDV-PIX-CORTE", pos={"sales_mode": "order"})
    cutoff = (timezone.now() + timedelta(minutes=40)).replace(microsecond=0)

    with patch.object(payment_deadline, "service_cutoff", return_value=cutoff):
        payment_service.initiate(order)

    expires_at = _expires_at(order)
    assert cutoff - timedelta(minutes=1) <= expires_at <= cutoff


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS, SHOPMAN_MOCK_PIX_AUTO_CONFIRM=False)
def test_pix_de_balcao_segue_o_prazo_do_pix_do_canal():
    _setup(pix_minutes=10, link_minutes=120)
    order = _pix_order("PDV-PIX-BALCAO")

    payment_service.initiate(order)

    remaining = _expires_at(order) - timezone.now()
    assert timedelta(minutes=9) < remaining <= timedelta(minutes=10)


def test_pix_de_canal_remoto_nao_muda_por_aqui():
    """Loja online e WhatsApp têm o próprio prazo (pergunta 1 do mapa)."""
    cache.clear()
    Channel.objects.create(
        ref="web",
        name="Loja",
        is_active=True,
        config={"payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10}},
    )
    order = SimpleNamespace(
        ref="WEB-1",
        channel_ref="web",
        data={"origin_channel": "web", "delivery_date": (timezone.localdate() + timedelta(days=7)).isoformat()},
    )

    assert payment_service._adapter_config(order, method="pix")["pix_timeout_minutes"] == 10
