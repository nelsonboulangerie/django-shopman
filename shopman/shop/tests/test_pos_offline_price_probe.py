"""Venda "sem conexão" que chega cobrada abaixo do preço do catálogo (auditoria 03/11/2026).

A regra D (dono, 10/10/2026) diz que na venda feita sem conexão vale o preço que foi
cobrado. O servidor não tem como provar que o dispositivo estava mesmo sem conexão: o
`offline_captured_at` vem do corpo. Um dispositivo com conexão que se declare "sem
conexão" sela o pedido no preço que escolher, e só sobra o aviso ao gerente depois.

O teste fica `xfail` até o dono decidir o que o servidor faz (PR draft desta prova).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.services.pos_intent import PosIntentError
from shopman.shop.tests.test_pos_cash_ledger import _Counter

pytestmark = pytest.mark.django_db


@pytest.fixture
def counter():
    return _Counter()


@pytest.mark.xfail(strict=True, reason="decisão do dono pendente: venda sem conexão abaixo do catálogo")
def test_offline_flag_cannot_seal_any_price(counter):
    captured = (timezone.now() - timedelta(minutes=1)).isoformat()
    try:
        result = counter.close(
            client_request_id="audit-offline-forged",
            items=[{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1}],
            offline_captured_at=captured,
            expected_total_q=1,
        )
    except PosIntentError:
        return
    order = Order.objects.get(ref=result.order_ref)
    assert order.total_q == 1200, f"pedido selado em {order.total_q} centavos (catálogo: 1200)"


def test_online_sale_forged_unit_price_is_refused(counter):
    """Controle: sem a marca de "sem conexão", o preço do navegador não vale."""
    with pytest.raises(PosIntentError):
        counter.close(
            client_request_id="audit-direct-forged",
            items=[{"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1}],
            expected_total_q=1,
        )
