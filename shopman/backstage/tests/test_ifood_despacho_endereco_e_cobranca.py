"""O que o iFood manda e o despacho precisa: o complemento e o dinheiro da porta.

Esta suíte anda o caminho inteiro — pedido cru do iFood → ``map_order`` →
``ingest`` → as DUAS superfícies que despacham (o card do Gestor e a comanda
ESC/POS) — porque a perda era exatamente no meio: o mapper já trazia
``complement``, ``reference``, ``postal_code`` e a parcela em dinheiro, e o
ingest gravava só o endereço formatado e ``{method, gateway, status}``. Cada
lado, medido sozinho, parecia certo; o entregador é que saía sem saber em que
andar tocar e sem quanto cobrar.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.orderman.models import Order

from shopman.backstage.projections import order_queue
from shopman.backstage.services.receipt_escpos import ENCODING, order_ticket
from shopman.shop.services import ifood_ingest, ifood_orders

pytestmark = pytest.mark.django_db


# ── Cenário ───────────────────────────────────────────────────────────────


@pytest.fixture
def canal_ifood(db):
    from shopman.shop.models import Channel, Shop

    Shop.objects.get_or_create(name="Nelson Boulangerie")
    Channel.objects.get_or_create(ref="ifood", defaults={
        "name": "iFood", "config": {"payment": {"method": "external", "timing": "external"}},
    })


def _pedido_cru(*, order_id: str, delivery: dict, payments: dict | None = None, order_type: str = "DELIVERY") -> dict:
    """Um pedido do jeito que o Order Module v1.0 entrega."""
    return {
        "id": order_id,
        "orderType": order_type,
        "total": {"orderAmount": 45},
        "payments": payments or {},
        "delivery": delivery,
        "items": [{"id": "item-1", "externalCode": "PAO-001", "name": "Pão francês",
                   "quantity": 1, "unitPrice": 45, "totalPrice": 45}],
    }


def _ingerir(cru: dict) -> Order:
    # O lifecycle tem suíte própria; aqui se mede o que o ingest ESCREVE.
    with patch.object(ifood_ingest.order_changed, "send"):
        return ifood_ingest.ingest(ifood_orders.map_order(cru))


def _papel(order: Order) -> str:
    return order_ticket(order).decode(ENCODING, "replace")


_ENDERECO_COMPLETO = {
    "deliveredBy": "MERCHANT",
    "deliveryAddress": {
        "formattedAddress": "Rua das Flores, 123",
        "complement": "Apto 42, bloco B",
        "reference": "portão azul ao lado da farmácia",
        "postalCode": "86020-000",
    },
}

_DINHEIRO_COM_TROCO = {
    "pending": 45, "prepaid": 0,
    "methods": [{"method": "CASH", "type": "OFFLINE", "prepaid": False, "value": 45,
                 "cash": {"changeFor": 50}}],
}


# ── 1. O complemento, a referência e o CEP chegam inteiros ────────────────


def test_o_complemento_e_a_referencia_do_cliente_chegam_as_duas_superficies(canal_ifood):
    """⚠️ Era isto que sumia: o mapper trazia, o ingest jogava fora.

    O ``formattedAddress`` do iFood é rua e número. Quem faz achar a porta —
    apartamento, bloco, ponto de referência — vem em campo separado, e as duas
    telas de despacho leem esses campos de ``delivery_address_structured``.
    """
    order = _ingerir(_pedido_cru(order_id="IFOOD-ENDERECO", delivery=_ENDERECO_COMPLETO))

    estruturado = order.data["delivery_address_structured"]
    assert estruturado == {
        "complement": "Apto 42, bloco B",
        "delivery_instructions": "portão azul ao lado da farmácia",
        "postal_code": "86020-000",
    }

    card = order_queue.build_order_card(order)
    assert card.delivery_address == "Rua das Flores, 123 - Apto 42, bloco B"
    assert card.delivery_instructions == "portão azul ao lado da farmácia"

    papel = _papel(order)
    assert "Rua das Flores, 123 - Apto 42, bloco B" in papel
    assert "Referência: portão azul ao lado da farmácia" in papel


def test_endereco_sem_complemento_nao_inventa_bloco_estruturado(canal_ifood):
    order = _ingerir(_pedido_cru(order_id="IFOOD-SIMPLES", delivery={
        "deliveredBy": "MERCHANT", "deliveryAddress": {"formattedAddress": "Rua das Flores, 123"},
    }))

    assert "delivery_address_structured" not in order.data
    assert order_queue.build_order_card(order).delivery_address == "Rua das Flores, 123"


def test_o_endereco_formatado_tem_um_dono_so(canal_ifood):
    """Dois donos do mesmo texto é divergência esperando acontecer.

    ``delivery_address`` continua sendo o endereço formatado; o bloco
    estruturado guarda só o que ele NÃO carrega.
    """
    order = _ingerir(_pedido_cru(order_id="IFOOD-UM-DONO", delivery=_ENDERECO_COMPLETO))

    assert order.data["delivery_address"] == "Rua das Flores, 123"
    assert "formatted_address" not in order.data["delivery_address_structured"]


# ── 2. A comanda diz quanto cobrar e quanto de troco levar ────────────────


def test_entrega_em_dinheiro_manda_cobrar_na_porta_e_levar_o_troco(canal_ifood):
    """⚠️ Antes saía só "PAGAMENTO PENDENTE": sem valor e sem troco.

    O ingest distinguia o pendente, mas não dizia ONDE o dinheiro entra. Sem a
    marca ``collection`` a comanda não tinha o que imprimir, e o entregador
    saía sem saber quanto cobrar nem quanto de troco levar da gaveta.
    """
    order = _ingerir(_pedido_cru(
        order_id="IFOOD-DINHEIRO", delivery=_ENDERECO_COMPLETO, payments=_DINHEIRO_COM_TROCO,
    ))

    pagamento = order.data["payment"]
    assert pagamento["collection"] == "on_delivery"
    assert pagamento["tenders"] == [
        {"method": "cash", "amount_q": 4500, "collection": "on_delivery", "status": "pending"},
    ]
    assert pagamento["change_for_q"] == 5000
    # O método do topo NÃO muda: é ele que o lifecycle lê para baixar estoque
    # sem fingir captura (`_stock_fulfill_allowed`).
    assert (pagamento["method"], pagamento["gateway"], pagamento["status"]) == ("external", "ifood", "pending")

    papel = _papel(order)
    assert "COBRAR NA ENTREGA" in papel
    assert "Dinheiro" in papel and "R$ 45,00" in papel
    assert "Troco para" in papel and "R$ 50,00" in papel
    assert "Levar de troco" in papel and "R$ 5,00" in papel


def test_o_card_do_gestor_mostra_com_quanto_o_cliente_paga(canal_ifood):
    order = _ingerir(_pedido_cru(
        order_id="IFOOD-CARD-TROCO", delivery=_ENDERECO_COMPLETO, payments=_DINHEIRO_COM_TROCO,
    ))

    card = order_queue.build_order_card(order)
    assert card.change_for_q == 5000
    assert card.change_out_suggested_q == 500
    assert "R$ 50,00" in card.change_label and "R$ 5,00" in card.change_label


def test_cartao_na_porta_manda_cobrar_sem_prometer_troco(canal_ifood):
    order = _ingerir(_pedido_cru(order_id="IFOOD-CARTAO", delivery=_ENDERECO_COMPLETO, payments={
        "pending": 45, "prepaid": 0,
        "methods": [{"method": "CREDIT", "type": "OFFLINE", "prepaid": False, "value": 45,
                     "card": {"brand": "VISA"}}],
    }))

    papel = _papel(order)
    assert "COBRAR NA ENTREGA" in papel
    assert "Crédito" in papel
    assert "Troco" not in papel


def test_pedido_pago_online_nao_manda_cobrar_de_novo(canal_ifood):
    order = _ingerir(_pedido_cru(order_id="IFOOD-PAGO", delivery=_ENDERECO_COMPLETO, payments={
        "prepaid": 45, "pending": 0,
        "methods": [{"method": "CREDIT", "type": "ONLINE", "prepaid": True, "value": 45}],
    }))

    assert "collection" not in order.data["payment"]
    assert "COBRAR NA ENTREGA" not in _papel(order)


# ── 3. As três portas que fecham por falta de prova ───────────────────────


def test_entregador_do_ifood_nao_manda_a_casa_cobrar(canal_ifood):
    """⚠️ Quem recebe é o iFood; o repasse vem no acerto deles.

    Carimbar ``on_delivery`` aqui mandaria a casa cobrar um dinheiro que ela
    não recebe.
    """
    order = _ingerir(_pedido_cru(order_id="IFOOD-ENTREGA-DELES", payments=_DINHEIRO_COM_TROCO, delivery={
        "deliveredBy": "IFOOD", "deliveryAddress": {"formattedAddress": "Rua das Flores, 123"},
    }))

    assert "collection" not in order.data["payment"]
    assert "COBRAR NA ENTREGA" not in _papel(order)


def test_responsavel_pela_entrega_nao_informado_nao_autoriza_cobranca(canal_ifood):
    order = _ingerir(_pedido_cru(order_id="IFOOD-SEM-RESPONSAVEL", payments=_DINHEIRO_COM_TROCO, delivery={
        "deliveryAddress": {"formattedAddress": "Rua das Flores, 123"},
    }))

    assert "collection" not in order.data["payment"]


def test_retirada_nao_recebe_marca_de_cobranca_na_porta(canal_ifood):
    order = _ingerir(_pedido_cru(
        order_id="IFOOD-RETIRADA", order_type="TAKEOUT", payments=_DINHEIRO_COM_TROCO,
        delivery={"deliveredBy": "MERCHANT", "pickupCode": "1234"},
    ))

    assert order.data["fulfillment_type"] == "pickup"
    assert "collection" not in order.data["payment"]


def test_forma_que_a_casa_nao_sabe_nomear_nao_vira_linha_de_cobranca(canal_ifood):
    """⚠️ A comanda é papel de balcão: nada de vocabulário cru do marketplace.

    Sem ref da casa para a forma de pagamento, a linha sairia como
    ``meal_voucher``. O pendente continua dito — e o Gestor já detalha o caso
    em ``ifood.payment_summary``.
    """
    order = _ingerir(_pedido_cru(order_id="IFOOD-VALE", delivery=_ENDERECO_COMPLETO, payments={
        "pending": 45, "prepaid": 0,
        "methods": [{"method": "MEAL_VOUCHER", "type": "OFFLINE", "prepaid": False, "value": 45}],
    }))

    assert "collection" not in order.data["payment"]
    papel = _papel(order)
    assert "meal_voucher" not in papel.lower()
    assert "PAGAMENTO PENDENTE" in papel
