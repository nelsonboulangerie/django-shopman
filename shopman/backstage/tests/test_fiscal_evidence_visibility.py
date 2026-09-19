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
        state, label, fiscal_state, _ = order_queue._fiscal_status(order)
    assert state == visible_state
    assert fiscal_state == ("failed" if worker_state == "failed" else "queued")
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
    # O alerta de emissão morta também entra em LOTE: uma query para o quadro.
    alert_queries = [row["sql"] for row in captured if "fiscal_emit_failed" in row["sql"]]
    assert len(alert_queries) == 1
    assert len(board.expedition_pickup) == 20
    assert all(card.fiscal_status == "failed" for card in board.expedition_pickup)
    assert all(card.fiscal_state == "failed" for card in board.expedition_pickup)


# ── A copy da pill segue o PONTO em que a nota nasce ─────────────────────

ALWAYS = "shopman.shop.fiscal_resolvers.always"


@pytest.fixture
def _backend_present():
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=object()):
        yield


@pytest.mark.parametrize(
    "payment,extra,expected",
    [
        # Pix sem captura: a nota nasce na CAPTURA, não na conclusão — a pill
        # dizia "Fiscal na conclusão" e mentia.
        ({"method": "pix"}, {}, ("awaiting_payment", "NFC-e sai quando o pagamento confirmar", "awaiting_payment")),
        # COD aceito: a nota sai na conclusão; até lá está na fila.
        ({"method": "cash", "collection": "on_delivery"}, {"fulfillment_type": "delivery"}, ("pending", "NFC-e na fila", "queued")),
        ({"method": "cash"}, {"nfce_access_key": "chave"}, ("authorized", "NFC-e autorizada", "authorized")),
        ({"method": "cash"}, {"nfce_access_key": "chave", "nfce_cancelled": True}, ("cancelled", "NFC-e cancelada", "authorized")),
    ],
)
def test_the_pill_copy_follows_the_fiscal_state(_backend_present, settings, payment, extra, expected):
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal copy lab")
    data = {"payment": payment, "fulfillment_type": "pickup", **extra}
    order = Order.objects.create(ref="LAB-FISCAL-COPY", status="accepted", total_q=1000, data=data)

    status, label, state, _ = order_queue._fiscal_status(order)

    assert (status, label, state) == expected
    assert "na conclusão" not in label


def test_a_failed_emission_reads_as_failed_in_both_vocabularies(_backend_present, settings):
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal copy lab")
    order = Order.objects.create(ref="LAB-FISCAL-FAIL", status="accepted", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    assert order_queue._fiscal_status(order)[:3] == ("failed", "NFC-e falhou", "failed")


def test_not_requested_stays_not_requested(_backend_present, settings):
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    Shop.objects.create(name="Synthetic fiscal copy lab")
    order = Order.objects.create(ref="LAB-FISCAL-NOT", status="accepted", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})

    assert order_queue._fiscal_status(order)[:3] == ("not_requested", "Fiscal não solicitado", "not_expected")
