"""Canal remoto só fica "Em preparo" quando a Cozinha começa (#3165).

Decisão da coordenação em 22/11/2026, reversível: "um campo = um significado;
derive de onde a operação já decide". Quem decide que o preparo começou é o posto da
Cozinha ("Iniciar preparo", ou o atalho do Gestor, que é o mesmo ato). Antes, só o
``web`` esperava o posto; no WhatsApp e no iFood o aceite já escrevia "Em preparo"
com o ticket pendente, e o Gestor e o cliente liam que a Cozinha tinha começado.

O PDV fica de fora de propósito: é o balcão, com o cliente na frente, e não um canal
remoto.
"""

from __future__ import annotations

import importlib
from io import StringIO

import pytest
from django.apps import apps
from django.core.cache import cache
from shopman.orderman.models import Order, OrderItem

from shopman.shop.config import ChannelConfig
from shopman.shop.lifecycle import dispatch
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db

REMOTE_CHANNELS = ("web", "whatsapp", "ifood")


@pytest.fixture
def instance_channels():
    from config.management.commands.seed import NELSON_INSTANCE_DESCRIPTOR, Command

    command = Command()
    command.stdout = StringIO()
    command._materialize_instance(NELSON_INSTANCE_DESCRIPTOR)
    cache.clear()
    yield command._instance_channels()
    cache.clear()


@pytest.fixture
def estacao():
    from shopman.backstage.models import KDSInstance

    return KDSInstance.objects.create(ref="picking", name="Separação", type="picking")


def _accepted_paid_order(channel_ref: str) -> Order:
    from shopman.payman import PaymentService

    ref = f"REMOTO-{channel_ref.upper()}"
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"SESS-{ref}",
        status=Order.Status.ACCEPTED,
        total_q=2000,
        data={"payment": {"method": "pix"}},
    )
    for line_id, sku in (("1", "PAO"), ("2", "BOLO")):
        OrderItem.objects.create(
            order=order, line_id=line_id, sku=sku, name=sku,
            qty="1", unit_price_q=1000, line_total_q=1000,
        )
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="pix")
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data"])
    PaymentService.authorize(intent.ref, gateway_id=f"gw-{ref}")
    PaymentService.capture(intent.ref)
    return order


def _tickets(order):
    from shopman.backstage.models import KDSTicket

    return list(KDSTicket.objects.filter(session_key=order.session_key).order_by("pk"))


@pytest.mark.parametrize("channel_ref", REMOTE_CHANNELS)
def test_o_canal_remoto_declara_que_o_preparo_comeca_na_cozinha(instance_channels, channel_ref):
    config = ChannelConfig.for_channel(instance_channels[channel_ref])
    assert config.fulfillment.prep_start == "operator"


def test_o_balcao_segue_comecando_sozinho(instance_channels):
    assert ChannelConfig.for_channel(instance_channels["pdv"]).fulfillment.prep_start == "auto"


@pytest.mark.parametrize("channel_ref", REMOTE_CHANNELS)
def test_aceito_fica_aceito_ate_a_cozinha_comecar(instance_channels, estacao, channel_ref):
    from shopman.shop.services import kds

    order = _accepted_paid_order(channel_ref)

    dispatch(order, "on_accepted")
    order.refresh_from_db()

    # O ticket já está na Cozinha, esperando o posto; o pedido não diz que começou.
    (ticket,) = _tickets(order)
    assert ticket.status == "pending"
    assert order.status == Order.Status.ACCEPTED

    # O posto começa: aí, e só aí, o pedido fica "Em preparo".
    assert kds.start_ticket(ticket, actor="cozinheira") is True
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING


# ── O banco vivo (migração 0138) ─────────────────────────────────────────────


def _migration():
    return importlib.import_module("shopman.shop.migrations.0138_canais_remotos_esperam_a_cozinha")


def test_migracao_poe_whatsapp_e_ifood_para_esperar_a_cozinha():
    Shop.objects.create(name="Test Shop")
    ifood = Channel.objects.create(
        ref="ifood", name="iFood", config={"fulfillment": {"courier_ticket": "anonymous"}},
    )
    whatsapp = Channel.objects.create(ref="whatsapp", name="WhatsApp", config={"pricing": {"listing_from": "web"}})
    pdv = Channel.objects.create(ref="pdv", name="PDV", config={})

    _migration().forwards(apps, None)
    _migration().forwards(apps, None)  # idempotente

    for channel in (ifood, whatsapp, pdv):
        channel.refresh_from_db()
    assert ifood.config == {"fulfillment": {"courier_ticket": "anonymous", "prep_start": "operator"}}
    assert whatsapp.config == {"pricing": {"listing_from": "web"}, "fulfillment": {"prep_start": "operator"}}
    assert pdv.config == {}


def test_migracao_nao_esmaga_a_escolha_feita_a_mao():
    Shop.objects.create(name="Test Shop")
    whatsapp = Channel.objects.create(ref="whatsapp", name="WhatsApp", config={"fulfillment": {"prep_start": "auto"}})

    _migration().forwards(apps, None)

    whatsapp.refresh_from_db()
    assert whatsapp.config == {"fulfillment": {"prep_start": "auto"}}
