"""Sem mediana, a promessa não encolhe sem decisão (#3178).

"Fica pronto às" é uma estimativa só (#3168): a mediana dos preparos de agora para
todos. Sem mediana, a meta da estação que a loja CONFIGUROU (no canal ou na loja);
sem ela, os 30 minutos que a loja já prometia ao cliente, nunca o padrão de 15 do
código, que é meta do cartão do Gestor.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop
from shopman.shop.services import kitchen_eta

pytestmark = pytest.mark.django_db

SEM_MEDIANA = kitchen_eta.PrepExpectation(minutes=None, samples=0)


def _station(minutes: int) -> dict:
    return {"fulfillment": {"stage_goal_minutes": {"station": minutes}}}


@pytest.fixture
def shop():
    shop = Shop.load() or Shop.objects.create(name="Loja")
    shop.defaults = {}
    shop.save()
    return shop


@pytest.fixture
def channel(shop):
    channel, _ = Channel.objects.update_or_create(
        ref="eta-web", defaults={"name": "Loja online", "commerce_policy": Channel.CommercePolicy.ORDER, "config": {}},
    )
    return channel


def _preparing(ref: str, started, channel_ref: str = "eta-web"):
    order = Order.objects.create(ref=ref, channel_ref=channel_ref, status=Order.Status.PREPARING, total_q=1000, data={})
    Order.objects.filter(pk=order.pk).update(preparing_at=started)
    order.refresh_from_db()
    return order


def test_sem_mediana_e_sem_meta_configurada_vale_a_promessa_de_30_minutos(channel):
    assert kitchen_eta.prep_goal_minutes("eta-web") == 30
    assert kitchen_eta.prep_goal_minutes(None) == 30


def test_sem_mediana_vale_a_meta_configurada_na_loja_e_o_canal_vence(shop, channel):
    shop.defaults = _station(20)
    shop.save()
    assert kitchen_eta.prep_goal_minutes("eta-web") == 20

    channel.config = _station(25)
    channel.save()
    assert kitchen_eta.prep_goal_minutes("eta-web") == 25


def test_o_pronto_previsto_usa_o_fallback_e_com_mediana_usa_a_mediana(channel):
    now = timezone.now()
    started = now - timedelta(minutes=5)
    order = _preparing("ETA-FALLBACK", started)

    assert kitchen_eta.ready_eta(order, SEM_MEDIANA, now=now) == started + timedelta(minutes=30)

    com_mediana = kitchen_eta.PrepExpectation(minutes=12, samples=5)
    assert kitchen_eta.ready_eta(order, com_mediana, now=now) == started + timedelta(minutes=12)
