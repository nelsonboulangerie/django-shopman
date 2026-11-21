"""A configuration change cannot erase an already recorded fiscal obligation."""
from unittest.mock import patch

import pytest
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections import order_queue
from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


@pytest.mark.parametrize("worker_state,visible_state", [("failed", "failed"), ("queued", "pending"), ("running", "pending"), ("done", "pending")])
def test_existing_fiscal_attempt_survives_missing_backend(worker_state, visible_state):
    Shop.objects.create(name="Synthetic fiscal evidence lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-EVIDENCE", status="ready", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status=worker_state, payload={"order_ref": order.ref})
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        state, label, fiscal_state, _ = order_queue._fiscal_status(order)
    assert state == visible_state
    assert fiscal_state == ("failed" if worker_state == "failed" else "queued")
    assert "não solicitada" not in label


def test_fiscal_evidence_is_batched_for_the_whole_board():
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    Shop.objects.create(name="Synthetic fiscal batch lab")
    for index in range(20):
        order = Order.objects.create(channel_ref="web", ref=f"LAB-FISCAL-{index}", status="ready", total_q=1000,
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


# ── A copy da pill segue o PONTO em que a nota nasce ─────────────────────

ALWAYS = "shopman.shop.fiscal_resolvers.always"


@pytest.fixture
def _backend_present():
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=object()):
        yield


@pytest.mark.parametrize(
    "payment,extra,expected",
    [
        # Pix de balcão sem captura: a nota nasce na CAPTURA, não na conclusão
        # — a pill dizia "Fiscal na conclusão" e mentia.
        ({"method": "pix"}, {"origin_channel": "pos"}, ("awaiting_payment", "NFC-e sai quando o pagamento confirmar", "awaiting_payment")),
        # Encomenda (retirada/entrega pela frente): a nota nasce na SAÍDA da
        # mercadoria (decisão de 26/09/2026), paga ou não.
        ({"method": "pix"}, {}, ("awaiting_pickup", "NFC-e sai na retirada", "awaiting_pickup")),
        ({"method": "cash", "collection": "on_delivery"}, {"fulfillment_type": "delivery"}, ("awaiting_delivery", "NFC-e sai na entrega", "awaiting_delivery")),
        # Venda de balcão em dinheiro: a nota sai no fechamento; até lá, na fila.
        ({"method": "cash"}, {"origin_channel": "pos"}, ("pending", "NFC-e em emissão", "queued")),
        ({"method": "cash"}, {"nfce_access_key": "chave"}, ("authorized", "NFC-e autorizada", "authorized")),
        ({"method": "cash"}, {"nfce_access_key": "chave", "nfce_cancelled": True}, ("cancelled", "NFC-e cancelada", "authorized")),
    ],
)
def test_the_pill_copy_follows_the_fiscal_state(_backend_present, settings, payment, extra, expected):
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal copy lab")
    data = {"payment": payment, "fulfillment_type": "pickup", **extra}
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-COPY", status="accepted", total_q=1000, data=data)

    status, label, state, _ = order_queue._fiscal_status(order)

    assert (status, label, state) == expected
    assert "na conclusão" not in label


def test_a_failed_emission_reads_as_failed_in_both_vocabularies(_backend_present, settings):
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal copy lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-FAIL", status="accepted", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    assert order_queue._fiscal_status(order)[:3] == ("failed", "NFC-e não autorizada", "failed")


@pytest.mark.parametrize(
    "payment,extra,expected_label",
    [
        # O Pix venceu e o worker cancelou: o pagamento nunca vai confirmar (#3127).
        ({"method": "pix"}, {"origin_channel": "pos"}, "Sem NFC-e: o pedido foi cancelado antes do pagamento"),
        # A loja online, retirada: mesmo fato, a mesma frase.
        ({"method": "pix"}, {}, "Sem NFC-e: o pedido foi cancelado antes do pagamento"),
        # Dinheiro na entrega, cancelado antes de sair: a regra caía em ``queued`` e a
        # pill dizia "NFC-e em emissão" sem nota nenhuma a caminho (#3130).
        ({"method": "cash", "collection": "on_delivery"}, {"fulfillment_type": "delivery"},
            "Sem NFC-e: o pedido foi cancelado"),
        # Dinheiro no balcão, cancelado sem tentativa: o mesmo fato.
        ({"method": "cash"}, {"origin_channel": "pos"}, "Sem NFC-e: o pedido foi cancelado"),
    ],
)
def test_cancelled_order_never_promises_a_note(_backend_present, settings, payment, extra, expected_label):
    """O pedido cancelado que ainda esperava o ponto da nota diz o fato, sem prometer."""
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal cancelled lab")
    data = {"payment": payment, "fulfillment_type": "pickup", **extra}
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-CANCELLED", status="cancelled", total_q=1000, data=data)

    status, label, _state, _ = order_queue._fiscal_status(order)

    assert (status, label, _state) == ("not_issued", expected_label, "not_issued")
    assert "sai " not in label
    assert "emissão" not in label


@pytest.mark.parametrize("worker_state", ["queued", "running"])
def test_cancelled_order_with_a_live_emission_still_says_in_emission(_backend_present, settings, worker_state):
    """A Directive viva é emissão de verdade: o cancelamento não a esconde (#3130)."""
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal cancelled lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-CANCELLED-LIVE", status="cancelled", total_q=1000,
        data={"payment": {"method": "cash", "collection": "on_delivery"}, "fulfillment_type": "delivery"})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status=worker_state, payload={"order_ref": order.ref})

    assert order_queue._fiscal_status(order)[:3] == ("pending", "NFC-e em emissão", "queued")


def test_cancelled_order_with_a_failed_emission_still_says_failed(_backend_present, settings):
    """A tentativa que morreu segue com o caminho dela (reprocessar ou cancelar a nota)."""
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal cancelled lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-CANCELLED-FAILED", status="cancelled", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})

    assert order_queue._fiscal_status(order)[:3] == ("failed", "NFC-e não autorizada", "failed")


def test_cancelled_order_without_attempt_is_not_issued_even_without_the_rule(settings):
    """Sem backend ou com a regra dizendo não, o cancelado continua sem nota: o fato vale antes da regra."""
    from shopman.shop.services import fiscal as fiscal_service

    Shop.objects.create(name="Synthetic fiscal cancelled lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-CANCELLED-NORULE", status="cancelled", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        assert fiscal_service.fiscal_state(order) == fiscal_service.FISCAL_STATE_NOT_ISSUED


def test_cancelled_order_with_an_authorized_note_keeps_saying_so(_backend_present, settings):
    """A nota que já saiu continua dizendo o que é: o cancelamento não a apaga."""
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = ALWAYS
    Shop.objects.create(name="Synthetic fiscal cancelled lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-CANCELLED-AUTH", status="cancelled", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup", "nfce_access_key": "chave"})

    assert order_queue._fiscal_status(order)[:2] == ("authorized", "NFC-e autorizada")


def test_not_requested_stays_not_requested(_backend_present, settings):
    settings.SHOPMAN_FISCAL_EMISSION_RESOLVER = "shopman.shop.fiscal_resolvers.on_request_or_tax_id"
    Shop.objects.create(name="Synthetic fiscal copy lab")
    order = Order.objects.create(channel_ref="web", ref="LAB-FISCAL-NOT", status="accepted", total_q=1000,
        data={"payment": {"method": "cash"}, "fulfillment_type": "pickup"})

    assert order_queue._fiscal_status(order)[:3] == ("not_requested", "NFC-e não solicitada", "not_expected")
