"""O "avançar" do operador lê o próximo passo do ciclo do Orderman (Constituição C6).

O orquestrador não guarda tabela de transição própria: o próximo passo vem de
``Order.next_status``, que segue as transições do canal gravadas no snapshot do
pedido. O orquestrador só informa o fato que é dele, se o pedido sai por entrega.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db

S = Order.Status


def _order(status: str, *, fulfillment: str = "pickup", transitions: dict | None = None) -> Order:
    snapshot = {"lifecycle": {"transitions": transitions}} if transitions else {}
    return Order.objects.create(
        ref=f"NX-{status}-{fulfillment}",
        channel_ref="web",
        session_key=f"sk-{status}-{fulfillment}",
        status=status,
        total_q=1000,
        snapshot=snapshot,
        data={"fulfillment_type": fulfillment},
    )


# A sequência que o botão "avançar" sempre seguiu no ciclo padrão.
@pytest.mark.parametrize(
    ("status", "fulfillment", "expected"),
    [
        (S.NEW, "pickup", ""),
        (S.NEW, "delivery", ""),
        (S.ACCEPTED, "pickup", S.PREPARING),
        (S.ACCEPTED, "delivery", S.PREPARING),
        (S.PREPARING, "pickup", S.READY),
        (S.PREPARING, "delivery", S.READY),
        (S.READY, "pickup", S.COMPLETED),
        (S.READY, "delivery", S.DISPATCHED),
        (S.DISPATCHED, "delivery", S.DELIVERED),
        (S.DELIVERED, "delivery", S.COMPLETED),
        (S.COMPLETED, "pickup", ""),
        (S.CANCELLED, "pickup", ""),
        (S.RETURNED, "delivery", ""),
    ],
)
def test_ciclo_padrao_mantem_a_sequencia_do_avancar(status, fulfillment, expected):
    assert operator_orders.next_status_for(_order(status, fulfillment=fulfillment)) == expected


def test_canal_sem_preparo_avanca_direto_para_pronto():
    """O ciclo é do canal: sem a etapa de preparo, aceitar leva direto a pronto."""
    transitions = {
        S.NEW: [S.ACCEPTED, S.CANCELLED],
        S.ACCEPTED: [S.READY, S.CANCELLED],
        S.READY: [S.COMPLETED],
        S.COMPLETED: [],
        S.CANCELLED: [],
    }
    order = _order(S.ACCEPTED, transitions=transitions)
    assert operator_orders.next_status_for(order) == S.READY


def test_entrega_em_canal_sem_despacho_conclui_no_pronto():
    """Pedido de entrega num canal cujo ciclo não tem despacho não inventa o passo."""
    transitions = {
        S.READY: [S.COMPLETED],
        S.COMPLETED: [],
    }
    order = _order(S.READY, fulfillment="delivery", transitions=transitions)
    assert operator_orders.next_status_for(order) == S.COMPLETED
