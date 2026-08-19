"""Builder do payload fiscal: catálogo ilegível ≠ produto sem NCM.

Regressão do audit do Fiscalman (F2): ``_products_by_sku`` capturava
``except Exception`` e devolvia ``{}``. Um soluço de banco fazia todos os itens
perderem o metadado fiscal, o adapter recusava por "produto sem NCM" e o handler
classificava a recusa como TERMINAL — nota morta na fila, sem retry, com um
diagnóstico que mentia sobre a causa.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db.utils import OperationalError
from django.test import override_settings
from shopman.fiscalman.contracts import FiscalDocumentResult
from shopman.offerman.models import Product
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.fiscal import NFCeEmitHandler
from shopman.shop.models import Channel
from shopman.shop.services import fiscal as fiscal_service

pytestmark = pytest.mark.django_db

EMIT_ALWAYS = override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.tests.test_fiscal_items_builder.StubFiscalBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.always",
)


class StubFiscalBackend:
    """Backend fiscal só para o pool não estar vazio (``fiscal.emit`` é no-op sem backend)."""

    def emit(self, **kwargs):
        return FiscalDocumentResult(success=True, access_key="x", status="authorized")

    def query_status(self, *, reference):
        return FiscalDocumentResult(success=False)

    def cancel(self, *, reference, reason):
        raise NotImplementedError


@pytest.fixture
def order_with_item(db):
    from shopman.shop.fiscal import fiscal_pool

    fiscal_pool.reset()
    Channel.objects.create(ref="pdv", name="PDV")
    Product.objects.create(
        sku="PAO-1",
        name="Pão",
        metadata={"fiscal": {"profile": "own_production", "ncm": "19059010"}},
    )
    order = Order.objects.create(
        ref="ORD-FISCAL-BUILD-1", channel_ref="pdv", status=Order.Status.COMPLETED, total_q=1000
    )
    order.items.create(sku="PAO-1", name="Pão", qty=1, unit_price_q=1000, line_total_q=1000)
    yield order
    fiscal_pool.reset()


@EMIT_ALWAYS
def test_unreadable_catalog_raises_instead_of_queueing_a_note_without_ncm(order_with_item):
    with patch.object(
        Product.objects.__class__, "filter", side_effect=OperationalError("conexão caiu")
    ):
        with pytest.raises(OperationalError):
            fiscal_service.emit(order_with_item)

    # E, principalmente: nenhuma directive nasceu com um retrato falso do catálogo.
    assert not Directive.objects.filter(topic="fiscal.emit_nfce").exists()


@EMIT_ALWAYS
def test_readable_catalog_queues_items_with_their_fiscal_codes(order_with_item):
    fiscal_service.emit(order_with_item)

    directive = Directive.objects.get(topic="fiscal.emit_nfce")
    item = directive.payload["items"][0]
    assert item["fiscal"]["ncm"] == "19059010"
    assert item["fiscal"]["cfop"] == "5102"


@EMIT_ALWAYS
def test_product_without_ncm_is_terminal_in_the_handler_and_that_is_the_truth(order_with_item):
    Product.objects.filter(sku="PAO-1").update(metadata={})
    fiscal_service.emit(order_with_item)
    directive = Directive.objects.get(topic="fiscal.emit_nfce")

    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    backend = FocusNFeBackend()
    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=directive, ctx={})
