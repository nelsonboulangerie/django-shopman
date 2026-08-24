"""Integração do counter_handoff: o `close_sale` REAL fecha a venda de balcão.

Os testes unitários provam o predicado e a transição isolados; este prova o
caminho inteiro que o PDV usa em produção: payload → commit → lifecycle →
COMPLETED no mesmo request, linha `sale` no livro do turno, NFC-e enfileirada
com dedupe. O canal aqui carrega o MESMO ``lifecycle.transitions`` que o seed
grava no `pdv` — se o seed e este teste divergirem, um dos dois está mentindo.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from shopman.offerman.models import Product
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.fiscal import fiscal_pool
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service

POS_TRANSITIONS = {
    "new": ["accepted", "cancelled"],
    "accepted": ["preparing", "ready", "completed", "cancelled"],
    "preparing": ["ready", "cancelled"],
    "ready": ["preparing", "dispatched", "completed"],
    "dispatched": ["delivered", "returned"],
    "delivered": ["completed", "returned"],
    "completed": ["returned", "cancelled"],
    "cancelled": [],
    "returned": [],
}


class StubFiscalBackend:
    def emit(self, **kwargs):
        from shopman.fiscalman.contracts import FiscalDocumentResult

        return FiscalDocumentResult(success=True, access_key="stub", status="authorized")

    def query_status(self, *, reference):
        from shopman.fiscalman.contracts import FiscalDocumentResult

        return FiscalDocumentResult(success=False, status="pending")

    def cancel(self, *, reference, reason):
        from shopman.fiscalman.contracts import FiscalCancellationResult

        return FiscalCancellationResult(success=True)


class CounterHandoffIntegrationTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="Balcão",
            is_active=True,
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
                "stock": {"check_on_commit": False, "allow_untracked": False, "sells_nonconforming": True},
                "lifecycle": {"transitions": POS_TRANSITIONS},
            },
        )
        from shopman.cashman import services as cash

        alice = get_user_model().objects.create_user(username="alice", password="x")
        self.shift = cash.open_shift(operator=alice, float_q=0)
        Product.objects.create(
            sku="PAO-FR", name="Pão Francês", base_price_q=100,
            is_published=True, is_sellable=True,
        )
        fiscal_pool.reset()
        self.addCleanup(fiscal_pool.reset)

    def _close(self, *, payment_method="card", request_id="counter-1"):
        # O lifecycle dispara via transaction.on_commit — dentro de TestCase a
        # transação nunca commita, então capturamos e executamos os callbacks,
        # que é exatamente o que produção faz no fim do request.
        with self.captureOnCommitCallbacks(execute=True):
            result = pos_service.close_sale(
                channel_ref="pdv",
                payload={
                    "items": [{"sku": "PAO-FR", "name": "Pão Francês", "qty": 2, "unit_price_q": 100}],
                    "fulfillment_type": "pickup",
                    "payment_method": payment_method,
                    "payment_collection": "terminal",
                    "cash_shift_id": self.shift.pk,
                    "client_request_id": request_id,
                },
                actor="pos:alice",
                operator_username="alice",
            )
        return result

    @override_settings(
        SHOPMAN_FISCAL_ADAPTER="shopman.backstage.tests.test_pos_counter_handoff_integration.StubFiscalBackend",
        SHOPMAN_FISCAL_EMISSION_RESOLVER=(
            "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
            "shopman.shop.fiscal_resolvers.eletronic_payment,"
            "shopman.shop.fiscal_resolvers.deferred_settlement"
        ),
    )
    def test_counter_sale_closes_completed_with_one_fiscal_directive(self) -> None:
        result = self._close(payment_method="card", request_id="counter-fiscal")

        order = Order.objects.get(ref=result.order_ref)
        # O evento já ocorreu: a venda fecha COMPLETED no mesmo request…
        self.assertEqual(order.status, Order.Status.COMPLETED)
        # …e os DOIS gatilhos (on_completed + close_sale) produziram UMA directive.
        self.assertEqual(
            Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref).count(),
            1,
        )
        # A venda continua no livro do turno (linha `sale`).
        from shopman.cashman.models import Entry

        self.assertTrue(Entry.objects.filter(shift=self.shift, order_ref=order.ref).exists())

    def test_counter_sale_creates_no_kds_ticket_for_shelf_bread(self) -> None:
        from shopman.backstage.models import KDSInstance, KDSTicket

        # A catch-all de picking que transformava pão vendido em ticket.
        KDSInstance.objects.create(ref="encomendas", name="Encomendas", type="picking", is_active=True)

        result = self._close(payment_method="cash", request_id="counter-kds")

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertFalse(KDSTicket.objects.filter(session_key=order.session_key).exists())
