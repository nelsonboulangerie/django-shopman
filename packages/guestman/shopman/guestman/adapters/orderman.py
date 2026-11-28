"""Pontes do Guestman para o Orderman: histórico de pedidos e cerca do titular."""

from shopman.guestman.protocols.orders import OrderStats, OrderSummary


class OrdermanOrderHistoryBackend:
    """
    Adapter that implements OrderHistoryBackend by querying Orderman.

    Configuration in settings.py:
        GUESTMAN = {
            "ORDER_HISTORY_BACKEND": "shopman.guestman.adapters.orderman.OrdermanOrderHistoryBackend",
        }
    """

    def get_customer_orders(
        self,
        customer_ref: str,
        limit: int = 10,
    ) -> list[OrderSummary]:
        """Return last orders for customer from Orderman's public history contract."""
        from shopman.orderman.services import CustomerOrderHistoryService

        orders = CustomerOrderHistoryService.list_customer_orders(
            customer_ref,
            limit=limit,
        )

        return [
            OrderSummary(
                order_ref=o.order_ref,
                channel_ref=o.channel_ref,
                ordered_at=o.ordered_at,
                total_q=o.total_q,
                items_count=o.items_count,
                status=o.status,
                items=list(o.items),
            )
            for o in orders
        ]

    def get_order_stats(self, customer_ref: str) -> OrderStats:
        """Return aggregated order statistics from Orderman's public history contract."""
        from shopman.orderman.services import CustomerOrderHistoryService

        stats = CustomerOrderHistoryService.get_customer_stats(customer_ref)

        return OrderStats(
            total_orders=stats.total_orders,
            total_spent_q=stats.total_spent_q,
            first_order_at=stats.first_order_at,
            last_order_at=stats.last_order_at,
            average_order_q=stats.average_order_q,
        )

class GuestmanCustomerFence:
    """A cerca do titular canônico do Orderman, implementada pelo cadastro do Guestman.

    Configuração em settings.py:
        ORDERMAN = {
            "CUSTOMER_FENCE": "shopman.guestman.adapters.orderman.GuestmanCustomerFence",
        }

    Trava a linha do ``Customer`` (``select_for_update``) antes da sessão: a
    ordem global de locks é Customer → Session, e é ela que impede uma exclusão
    de conta de correr por baixo de um commit ou de uma associação de titular.
    """

    def lock_by_identity(self, *, customer_ref: str, phone: str):
        from django.db.models import Q
        from shopman.guestman.models import Customer
        from shopman.orderman.protocols import CustomerIdentityConflict

        phone_query = Q(phone=phone) | Q(
            contact_points__value_normalized=phone,
            contact_points__type__in=("phone", "whatsapp"),
        )
        if customer_ref and phone:
            query = Q(ref=customer_ref) & phone_query
        elif customer_ref:
            query = Q(ref=customer_ref)
        else:
            query = phone_query
        matches = list(Customer.objects.filter(query).values_list("pk", flat=True).distinct()[:2])
        if len(matches) > 1:
            raise CustomerIdentityConflict("customer_identity_ambiguous")
        if not matches:
            if customer_ref and phone and Customer.objects.filter(Q(ref=customer_ref) | phone_query).exists():
                raise CustomerIdentityConflict("customer_identity_mismatch")
            # Integrações podem selar um ref externo sem Customer local.
            return None
        return self._fenced(Customer.objects.select_for_update().get(pk=matches[0]))

    def lock_by_ref(self, customer_ref: str):
        from shopman.guestman.models import Customer

        customer = Customer.objects.select_for_update().filter(ref=customer_ref).first()
        return self._fenced(customer) if customer is not None else None

    def owns_phone(self, customer, phone: str) -> bool:
        from shopman.guestman.models import ContactPoint

        return ContactPoint.objects.filter(
            customer_id=customer.pk,
            value_normalized=phone,
            type__in=("phone", "whatsapp"),
        ).exists()

    def is_active_owner(self, customer, customer_ref: str) -> bool:
        from shopman.guestman.models import Customer

        return Customer.objects.filter(pk=customer.pk, ref=customer_ref, is_active=True).exists()

    @staticmethod
    def _fenced(customer):
        from shopman.orderman.protocols import FencedCustomer
        from shopman.utils.phone import normalize_phone

        return FencedCustomer(
            pk=customer.pk,
            ref=customer.ref,
            phone=normalize_phone(customer.phone) or customer.phone,
            is_active=customer.is_active,
        )
