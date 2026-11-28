from __future__ import annotations

from django.test import TestCase
from shopman.guestman.adapters.orderman import OrdermanOrderHistoryBackend
from shopman.guestman.models import Customer, PriceTier
from shopman.orderman.models import Order


class GuestmanOrderHistoryTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        tier = PriceTier.objects.create(ref="regular", name="Regular", is_default=True, priority=0)
        self.customer = Customer.objects.create(
            ref="CUST-HIST-001",
            first_name="Ana",
            last_name="Silva",
            phone="+5543999990001",
            price_tiers=tier,
        )
        self.backend = OrdermanOrderHistoryBackend()

    def test_reads_orders_via_customer_ref_in_order_data(self) -> None:
        Order.objects.create(
            ref="ORD-HIST-001",
            channel_ref="web",
            session_key="sess-hist-1",
            status=Order.Status.COMPLETED,
            snapshot={"pricing": {"total_q": 2500}, "items": [{"sku": "SKU-1"}]},
            data={"customer_ref": self.customer.ref},
            total_q=2500,
        )
        Order.objects.create(
            ref="ORD-HIST-002",
            channel_ref="web",
            session_key="sess-hist-2",
            status=Order.Status.CANCELLED,
            snapshot={"pricing": {"total_q": 900}, "items": [{"sku": "SKU-2"}]},
            data={"customer_ref": "OTHER-CUST"},
            total_q=900,
        )

        orders = self.backend.get_customer_orders(self.customer.ref)
        stats = self.backend.get_order_stats(self.customer.ref)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_ref, "ORD-HIST-001")
        self.assertEqual(stats.total_orders, 1)
        self.assertEqual(stats.total_spent_q, 2500)

    def test_cancelled_and_returned_orders_are_not_purchases(self) -> None:
        """Beta 06/11, PIXEXP-07: quatro Pix vencidos faziam "Cliente fiel · 5
        pedidos", com ticket médio e favorito tirados de pedido que não existiu."""
        for ref, status, total_q, sku in (
            ("ORD-PAID", Order.Status.COMPLETED, 1530, "PAID-SKU"),
            ("ORD-PIX-EXPIRED", Order.Status.CANCELLED, 510, "TRABB"),
            ("ORD-RETURNED", Order.Status.RETURNED, 2200, "KUP"),
        ):
            Order.objects.create(
                ref=ref,
                channel_ref="web",
                session_key=f"sess-{ref}",
                status=status,
                snapshot={"items": [{"sku": sku, "qty": 1}]},
                data={"customer_ref": self.customer.ref},
                total_q=total_q,
            )

        stats = self.backend.get_order_stats(self.customer.ref)
        orders = self.backend.get_customer_orders(self.customer.ref)

        self.assertEqual(stats.total_orders, 1)
        self.assertEqual(stats.total_spent_q, 1530)
        self.assertEqual(stats.average_order_q, 1530)
        self.assertEqual([o.order_ref for o in orders], ["ORD-PAID"])

    def test_customer_detail_still_lists_the_cancelled_order_with_its_status(self) -> None:
        from shopman.orderman.services import CustomerOrderHistoryService

        Order.objects.create(
            ref="ORD-PIX-EXPIRED",
            channel_ref="web",
            session_key="sess-expired",
            status=Order.Status.CANCELLED,
            data={"customer_ref": self.customer.ref},
            total_q=510,
        )

        listed = CustomerOrderHistoryService.list_customer_orders(self.customer.ref, include_not_purchases=True)

        self.assertEqual([(o.order_ref, o.status) for o in listed], [("ORD-PIX-EXPIRED", "cancelled")])

    def test_cancelling_an_order_takes_it_out_of_the_customer_insight(self) -> None:
        from shopman.guestman.contrib.insights import InsightService

        from shopman.shop.models import Channel

        Channel.objects.update_or_create(ref="web", defaults={"name": "Loja online", "is_active": True})
        order = Order.objects.create(
            ref="ORD-PIX-WAITING",
            channel_ref="web",
            session_key="sess-waiting",
            status=Order.Status.NEW,
            snapshot={"items": [{"sku": "TRABB", "name": "Pão de Hambúrguer", "qty": 1}]},
            data={"customer_ref": self.customer.ref},
            total_q=510,
        )
        InsightService.recalculate(self.customer.ref)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.insight.total_orders, 1)

        with self.captureOnCommitCallbacks(execute=True):
            order.transition_status(Order.Status.CANCELLED, actor="payment.timeout")

        insight = type(self.customer.insight).objects.get(customer=self.customer)
        self.assertEqual(insight.total_orders, 0)
        self.assertEqual(insight.average_ticket_q, 0)
        self.assertEqual(insight.favorite_products, [])
