"""O "Não retirado" ligado no web e no WhatsApp do banco vivo (#2694, migração 0137).

Palavra do dono, 22/11/2026: "Ligar o Não retirado para web e WhatsApp no ar: Sim
(mas VOCÊ aplica, não eu)". A migração leva ao banco a transição ``ready →
cancelled`` que o descritor já declara, e o banco tem de sair IGUAL ao descritor:
senão o próximo ``instance_descriptor diff`` acusaria drift.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps

from config.instance_descriptors import declared_channel, load_descriptor
from shopman.shop.models import Channel, Shop

pytestmark = pytest.mark.django_db


def _forwards():
    importlib.import_module("shopman.shop.migrations.0137_nao_retirado_no_web_e_whatsapp").forwards(apps, None)


def _declared_transitions(ref: str) -> dict:
    from config.management.commands.seed import NELSON_INSTANCE_DESCRIPTOR

    channel = declared_channel(load_descriptor(NELSON_INSTANCE_DESCRIPTOR), ref)
    return channel["config"]["overrides"]["lifecycle"]["transitions"]


@pytest.fixture
def shop():
    return Shop.objects.create(name="Test Shop")


@pytest.mark.parametrize("ref", ["web", "whatsapp"])
def test_canal_sem_o_mapa_fica_igual_ao_descritor(shop, ref):
    channel = Channel.objects.create(ref=ref, name=ref, config={"short_name": "Site"})

    _forwards()

    channel.refresh_from_db()
    assert channel.config["short_name"] == "Site"
    assert channel.config["lifecycle"]["transitions"] == _declared_transitions(ref)
    assert "cancelled" in channel.config["lifecycle"]["transitions"]["ready"]


def test_canal_com_o_mapa_ganha_so_a_transicao_que_faltava(shop):
    transitions = {
        "new": ["accepted", "cancelled"],
        "ready": ["preparing", "dispatched", "completed"],
        "completed": ["returned"],
    }
    whatsapp = Channel.objects.create(
        ref="whatsapp", name="WhatsApp", config={"lifecycle": {"transitions": transitions}},
    )

    _forwards()

    whatsapp.refresh_from_db()
    assert whatsapp.config["lifecycle"]["transitions"] == {
        **transitions,
        "ready": ["preparing", "dispatched", "completed", "cancelled"],
    }


def test_canal_que_ja_tem_a_transicao_nao_muda_e_a_migracao_e_idempotente(shop):
    already = {"ready": ["cancelled", "completed"], "new": ["accepted"]}
    web = Channel.objects.create(ref="web", name="Loja", config={"lifecycle": {"transitions": already}})
    whatsapp = Channel.objects.create(ref="whatsapp", name="WhatsApp", config={})

    _forwards()
    whatsapp.refresh_from_db()
    first = whatsapp.config
    _forwards()

    web.refresh_from_db()
    whatsapp.refresh_from_db()
    assert web.config == {"lifecycle": {"transitions": already}}
    assert whatsapp.config == first


def test_outros_canais_e_banco_sem_os_canais_nao_mudam_nem_falham(shop):
    _forwards()  # banco de teste sem web nem whatsapp

    pdv = Channel.objects.create(ref="pdv", name="PDV", config={})
    ifood = Channel.objects.create(ref="ifood", name="iFood", config={"fulfillment": {"courier_ticket": "anonymous"}})
    _forwards()

    pdv.refresh_from_db()
    ifood.refresh_from_db()
    assert pdv.config == {}
    assert ifood.config == {"fulfillment": {"courier_ticket": "anonymous"}}


def test_depois_da_migracao_o_canal_deixa_o_pronto_ir_a_cancelado(shop):
    from django.core.cache import cache

    from shopman.shop.config import ChannelConfig

    Channel.objects.create(ref="web", name="Loja", config={})
    _forwards()
    cache.clear()

    config = ChannelConfig.for_channel("web")
    assert "cancelled" in config.lifecycle["transitions"]["ready"]
