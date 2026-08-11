"""
Integration test: Ordering <-> Customers.

Tests the flow: customer -> session -> order.
"""


from django.test import TestCase


class TestOrderingCustomersIntegration(TestCase):
    """Integration between Ordering (orders) and Customers."""

    def setUp(self):
        from shopman.guestman.models import Customer, PriceTier

        from shopman.shop.models import Channel

        # Create customer tier
        self.tier = PriceTier.objects.create(
            ref="regular",
            name="Regular",
            is_default=True,
        )

        # Create customer
        self.customer = Customer.objects.create(
            ref="INT-CUST-001",
            first_name="Integration",
            last_name="Test",
            price_tier=self.tier,
        )

        # Create channel
        self.channel = Channel.objects.create(
            ref="loja-test",
            name="Loja Test",
        )

    def test_session_with_customer_data(self):
        """Session can store customer reference."""
        from shopman.orderman.models import Session

        session = Session.objects.create(
            session_key="INT-SESSION-001",
            channel_ref=self.channel.ref,
            state="open",
            items=[],
            data={"customer_ref": self.customer.ref},
        )

        assert session.data["customer_ref"] == "INT-CUST-001"

    def test_the_price_tier_provides_the_listing_ref(self):
        """Customer tier can provide listing_ref for pricing."""
        self.tier.listing_ref = "atacado"
        self.tier.save()

        assert self.customer.price_tier.listing_ref == "atacado"

    def test_customer_lookup_by_ref(self):
        """Customer can be retrieved by ref for session association."""
        from shopman.guestman.models import Customer

        found = Customer.objects.filter(ref="INT-CUST-001").first()
        assert found is not None
        assert found.first_name == "Integration"
