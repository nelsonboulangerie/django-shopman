"""O exemplo fiscal do seed não fabrica consulta de uma nota na SEFAZ."""
from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from config.management.commands.seed import Command
from shopman.backstage.projections.order_queue import _fiscal_status


@pytest.mark.django_db
def test_illustrative_fiscal_example_does_not_offer_a_fabricated_sefaz_qr():
    order = Order.objects.create(ref="FISCAL-EXAMPLE", status="completed", channel_ref="web", total_q=800)
    OrderItem.objects.create(
        order=order, line_id="1", sku="ESP", name="Espresso", qty=1,
        unit_price_q=800, line_total_q=800,
    )
    Command()._seed_fiscal_example()
    order.refresh_from_db()
    assert not order.data.get("nfce_qrcode_url")
    assert order.data["nfce_danfe_url"].startswith("https://homologacao.focusnfe.com.br/")
    _status, _label, _state, links = _fiscal_status(order)
    assert [link["label"] for link in links] == ["DANFE"]
