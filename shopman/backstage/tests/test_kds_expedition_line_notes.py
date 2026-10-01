"""A Saída mostra a observação da linha ("sem cebola").

O card da Saída lia ``item.notes``, atributo que nem ``OrderItem`` nem
``EffectiveItem`` (pedido + ajustes) têm: a observação vinha sempre vazia. Ela
mora em ``meta["notes"]``, a mesma chave que o PDV e a loja escrevem.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.kds import _build_expedition_card

pytestmark = pytest.mark.django_db


def _order() -> Order:
    return Order.objects.create(
        ref="WEB-SAIDA-NOTA",
        channel_ref="web",
        status=Order.Status.READY,
        total_q=3000,
        data={"origin_channel": "web", "customer": {"name": "Ana"}},
    )


def test_expedition_card_shows_the_line_note():
    order = _order()
    OrderItem.objects.create(
        order=order, line_id="1", sku="CROQUE", name="Croque", qty=1,
        unit_price_q=1500, line_total_q=1500, meta={"notes": "sem cebola"},
    )
    OrderItem.objects.create(
        order=order, line_id="2", sku="PAO", name="Pão", qty=1,
        unit_price_q=1500, line_total_q=1500,
    )

    items = {item.sku: item.notes for item in _build_expedition_card(order).items}

    assert items == {"CROQUE": "sem cebola", "PAO": ""}


def test_expedition_card_reads_the_note_from_the_adjusted_order():
    """Pedido ajustado (iFood ``ORDER_PATCHED``): a nota vem do ajuste."""
    order = _order()
    OrderItem.objects.create(
        order=order, line_id="1", sku="CROQUE", name="Croque", qty=1,
        unit_price_q=1500, line_total_q=1500,
    )
    order.data["adjustment"] = {
        "items": [
            {"line_id": "1", "sku": "CROQUE", "name": "Croque", "qty": 2,
             "unit_price_q": 1500, "line_total_q": 3000, "meta": {"notes": "bem quente"}},
        ],
        "total_q": 3000,
    }
    Order.objects.filter(pk=order.pk).update(data=order.data)
    order.refresh_from_db()

    (item,) = _build_expedition_card(order).items

    assert item.notes == "bem quente"
