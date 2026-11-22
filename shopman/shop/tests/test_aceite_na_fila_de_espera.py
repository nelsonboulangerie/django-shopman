"""O aceite desligado de um pedido na fila de espera não fala em pagamento (#3177).

Na fila nada se cobra de propósito até o cliente confirmar a vaga
(``charge_at="confirmation"``). "Aceite quando o dinheiro entrar" ali faz alguém
ligar para cobrar quem não tem o que pagar.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders, waitlist

pytestmark = pytest.mark.django_db

PAGAMENTO = "Pagamento ainda não confirmado. Aceite o pedido quando o dinheiro entrar."


@pytest.fixture(autouse=True)
def canal():
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja online", config={"payment": {"timing": "at_commit"}})


def _pedido(ref: str, data_extra: dict | None = None) -> Order:
    data = {"payment": {"method": "pix"}, "availability_decision": {"approved": True, "decisions": []}}
    data.update(data_extra or {})
    return Order.objects.create(ref=ref, channel_ref="web", status=Order.Status.NEW, total_q=1500, data=data)


def test_fora_da_fila_o_aceite_segue_esperando_o_pagamento():
    assert operator_orders.confirmation_block_reason(_pedido("FILA-NADA")) == PAGAMENTO


def test_esperando_o_lote_o_aceite_diz_o_que_espera_e_que_nada_foi_cobrado():
    reason = operator_orders.confirmation_block_reason(_pedido("FILA-LOTE"), waitlist_state=waitlist.FERMATA)
    assert reason == "Na fila de espera: o pedido espera o lote ficar pronto. Nada foi cobrado do cliente."
    assert "dinheiro" not in reason


def test_com_o_lote_pronto_o_aceite_diz_que_a_vez_e_do_cliente_e_ate_quando():
    prazo = datetime(2026, 11, 21, 12, 15, tzinfo=ZoneInfo("America/Sao_Paulo"))
    pedido = _pedido("FILA-VEZ", {"waitlist": {"state": "confirming", "deadline": prazo.isoformat()}})
    reason = operator_orders.confirmation_block_reason(pedido)
    assert reason == (
        "O lote ficou pronto e a vez é do cliente: ele tem até 12h15 para confirmar a vaga. Nada foi cobrado ainda."
    )


def test_depois_de_confirmar_a_vaga_a_frase_de_pagamento_volta_a_valer():
    pedido = _pedido("FILA-PAGA", {"waitlist": {"state": "confirmed"}})
    assert operator_orders.confirmation_block_reason(pedido) == PAGAMENTO


def test_o_botao_aceitar_do_cartao_le_a_mesma_frase():
    from django.contrib.auth.models import Permission, User

    pedido = _pedido("FILA-BOTAO")
    gerente = User.objects.create_user("gerente-fila", is_staff=True)
    gerente.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    gerente = User.objects.get(pk=gerente.pk)
    acoes = operator_orders.operational_actions(pedido, user=gerente, waitlist_state=waitlist.FERMATA)
    aceitar = next(a for a in acoes if a.ref == "confirm")
    assert not aceitar.enabled
    assert aceitar.reason.startswith("Na fila de espera")
