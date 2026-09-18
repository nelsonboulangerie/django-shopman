"""As duas portas por onde a mercadoria sai gritam quando a NFC-e não está autorizada.

Nenhum portão de expedição conferia ``nfce_access_key``: um pedido podia ser
despachado pelo Gestor ou concluído pela expedição do KDS com a nota na fila
(ou morta) e ninguém ficava sabendo. O aviso é alerta por pedido, sem barrar —
barrar é decisão do dono, porque a nota do COD só nasce na conclusão por
desenho.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import kds, operator_orders

pytestmark = pytest.mark.django_db

ALWAYS = "shopman.shop.fiscal_resolvers.always"


@pytest.fixture(autouse=True)
def _canal_e_backend():
    from shopman.shop.models import Channel

    Channel.objects.create(
        ref="gate-pdv",
        name="Balcão (gate)",
        config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": ["cash", "pix", "link"], "timing": "external"},
        },
    )
    cache.clear()
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=object()):
        yield
    cache.clear()


def _cod(ref: str, *, fulfillment_type: str = "delivery") -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="gate-pdv",
        session_key=f"SESS-{ref}",
        status=Order.Status.READY,
        total_q=3200,
        data={"fulfillment_type": fulfillment_type, "payment": {"method": "cash", "collection": "on_delivery"}},
    )


def _alertas(ref: str):
    return OperatorAlert.objects.filter(type="fiscal_handoff_without_nfce", order_ref=ref)


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_o_gestor_despacha_e_o_alerta_nasce_sem_barrar():
    order = _cod("HANDOFF-GESTOR")

    assert operator_orders.advance_order(order, actor="operator:test") == Order.Status.DISPATCHED

    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert _alertas(order.ref).count() == 1
    assert "saiu sem NFC-e autorizada" in _alertas(order.ref).get().message


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_a_expedicao_do_kds_conclui_e_o_alerta_nasce_sem_barrar():
    order = _cod("HANDOFF-KDS", fulfillment_type="pickup")
    order.data["payment"]["cod_settled_at"] = "2026-09-16T10:00:00Z"
    order.save(update_fields=["data"])

    assert kds.expedition_action(order, action="complete", actor="operator:test") == Order.Status.COMPLETED

    assert _alertas(order.ref).count() == 1


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_pedido_com_a_nota_autorizada_sai_em_silencio():
    order = _cod("HANDOFF-OK")
    order.data["nfce_access_key"] = "chave"
    order.save(update_fields=["data"])

    operator_orders.advance_order(order, actor="operator:test")

    assert not _alertas(order.ref).exists()


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=ALWAYS)
def test_a_transicao_recusada_nao_deixa_alerta_para_tras():
    """O aviso mora na transação da transição: sem transição, sem aviso."""
    order = _cod("HANDOFF-ROLLBACK")

    with patch.object(Order, "transition_status", side_effect=RuntimeError("boom")), pytest.raises(RuntimeError):
        operator_orders.advance_order(order, actor="operator:test")

    assert not _alertas(order.ref).exists()
