"""Loja online desligada no Gestor: a home avisa antes de o cliente montar a sacola.

O commit recusa de qualquer jeito (``channel_switch.ensure_accepting_orders``); o
aviso existe para que o "não" não chegue só no último botão do checkout.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import Channel, Shop
from shopman.shop.services import channel_switch
from shopman.storefront.presentation.home import build_home

pytestmark = pytest.mark.django_db


@pytest.fixture
def web():
    Shop.objects.create(name="Nelson", phone="554333231997")
    return Channel.objects.create(ref="web", name="Loja online")


def _notice(home, ref):
    return next((notice for notice in home.notices if notice.ref == ref), None)


def test_home_avisa_que_a_loja_online_nao_recebe_pedidos(rf, web):
    assert _notice(build_home(rf.get("/")), "ordering_off") is None

    channel_switch.request_switch("web", False, period="open", reason="Loja cheia", actor=None)

    notice = _notice(build_home(rf.get("/")), "ordering_off")
    assert notice is not None
    assert notice.title == "A loja online não está recebendo pedidos agora"
    assert notice.message == "O cardápio continua aqui para você consultar."
    assert notice.priority == "contextual"  # a home do app mostra os contextuais
