"""A configuration change cannot erase an already recorded fiscal obligation."""
from unittest.mock import patch

import pytest
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections import order_queue
from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("worker_state,visible_state", [("failed", "failed"), ("queued", "pending"), ("running", "pending"), ("done", "pending")])
def test_existing_fiscal_attempt_survives_missing_backend(worker_state, visible_state):
    Shop.objects.create(name="Synthetic fiscal evidence lab")
    order = Order.objects.create(ref="LAB-FISCAL-EVIDENCE", status="ready", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status=worker_state, payload={"order_ref": order.ref})
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        state, label, _ = order_queue._fiscal_status(order)
    assert state == visible_state
    assert "não solicitado" not in label


def test_fiscal_evidence_is_batched_for_the_whole_board():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    Shop.objects.create(name="Synthetic fiscal batch lab")
    for index in range(20):
        order = Order.objects.create(ref=f"LAB-FISCAL-{index}", status="ready", total_q=1000,
            data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
        Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None), CaptureQueriesContext(connection) as captured:
        board = order_queue.build_two_zone_queue()
    fiscal_queries = [row["sql"] for row in captured if "fiscal.emit_nfce" in row["sql"]]
    assert len(fiscal_queries) == 1
    assert len(board.expedition_pickup) == 20
    assert all(card.fiscal_status == "failed" for card in board.expedition_pickup)
