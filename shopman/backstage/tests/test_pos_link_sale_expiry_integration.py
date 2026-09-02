"""Venda de LINK no PDV, ponta a ponta: o pedido remoto tem trajeto — e prazo.

Irmão de ``test_pos_counter_handoff_integration``: lá a venda de balcão fecha
COMPLETED no próprio request, porque o pão já saiu pela porta. Aqui é o
contrário, e pelo MESMO ``close_sale`` de produção: a venda em link é o pedido
remoto anotado no balcão — o cliente não está na loja, paga depois pelo celular
e vem buscar. Então:

1. a venda NÃO fecha: fica ACCEPTED aguardando o ``on_paid``, com o estoque
   reservado (não baixado) e sem ticket de cozinha;
2. o prazo do link chega ao pedido (``payment.expires_at``), à tela do PDV e à
   Directive ``payment.timeout`` — armada exatamente para o vencimento;
3. vencido o prazo, o handler pergunta ao gateway e, com "não pago", cancela o
   pedido, avisa o cliente (``payment_expired``) e devolve o estoque.

Antes disto, a venda de link para hoje fechava COMPLETED sem um centavo
capturado, e o vencimento não a alcançava mais (o handler só age em NEW/ACCEPTED).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent
from shopman.stockman import HoldStatus, PositionKind
from shopman.stockman.models import Hold, Position, Quant
from shopman.stockman.services import StockQueries

from shopman.shop.directives import PAYMENT_TIMEOUT
from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler
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

MOCK_LINK_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "link": "shopman.shop.adapters.payment_mock",
    "cash": None,
    "external": None,
}

SKU = "PAO-FR"
STOCK_QTY = 10
SOLD_QTY = 2


def _hold_rows(order: Order) -> list[Hold]:
    ids = [int(entry["hold_id"].split(":")[1]) for entry in order.data.get("hold_ids") or [] if entry.get("hold_id")]
    return list(Hold.objects.filter(pk__in=ids))


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_LINK_ADAPTERS, SHOPMAN_PAYMENT_LINK_TTL_HOURS=24)
class LinkSaleExpiryIntegrationTests(TransactionTestCase):
    """``TransactionTestCase`` de propósito: o lifecycle dispara via
    ``transaction.on_commit`` ao sair da transação do commit — ANTES de o
    ``close_sale`` chamar o ``initiate`` do gateway, como em produção. Dentro
    de um ``TestCase`` os callbacks só rodam ao fim do teste, e o lifecycle
    então salvaria uma instância velha do pedido por cima do ``payment`` que o
    ``initiate`` acabou de gravar — um defeito do harness, não do código."""

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
        Product.objects.create(sku=SKU, name="Pão Francês", base_price_q=100, is_published=True, is_sellable=True)
        position = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
        Quant.objects.create(sku=SKU, position=position, _quantity=Decimal(STOCK_QTY))

    def _close_with_link(self, request_id: str = "link-1") -> tuple[Order, dict]:
        result = pos_service.close_sale(
            channel_ref="pdv",
            payload={
                "items": [{"sku": SKU, "name": "Pão Francês", "qty": SOLD_QTY, "unit_price_q": 100}],
                "fulfillment_type": "pickup",
                "customer_name": "Maria",
                # O contato é obrigatório no link: a URL existe para ser enviada.
                "customer_phone": "43999990000",
                "payment_tenders": [{"method": "link", "amount_q": 100 * SOLD_QTY, "collection": "terminal"}],
                "cash_shift_id": self.shift.pk,
                "client_request_id": request_id,
            },
            actor="pos:alice",
            operator_username="alice",
        )
        return Order.objects.get(ref=result.order_ref), dict(result.payment or {})

    def _timeout_directive(self, order: Order) -> Directive:
        return Directive.objects.get(topic=PAYMENT_TIMEOUT, payload__order_ref=order.ref)

    def _run_timeout(self, directive: Directive, *, at: datetime) -> None:
        with patch("django.utils.timezone.now", return_value=at):
            PaymentTimeoutHandler().handle(message=directive, ctx={})

    def test_link_sale_for_today_stays_open_with_the_deadline_armed(self) -> None:
        order, screen = self._close_with_link()

        # 1. Não é entrega de balcão: fica aguardando o cliente pagar.
        self.assertEqual(order.status, Order.Status.ACCEPTED)

        # 2. O prazo é UM, e chega a todo mundo: pedido, Payman, tela, Directive.
        payment = order.data["payment"]
        self.assertEqual(payment["method"], "link")
        self.assertTrue(payment["checkout_url"].startswith("http"))
        expires_at = datetime.fromisoformat(payment["expires_at"])
        self.assertTrue(timezone.is_aware(expires_at))
        self.assertLess(timedelta(hours=23, minutes=50), expires_at - timezone.now())
        self.assertLessEqual(expires_at - timezone.now(), timedelta(hours=24))

        intent = PaymentIntent.objects.get(order_ref=order.ref)
        self.assertEqual(intent.status, PaymentIntent.Status.PENDING)
        self.assertEqual(intent.expires_at, expires_at)

        self.assertEqual(screen["expires_at"], payment["expires_at"])
        self.assertEqual(screen["checkout_url"], payment["checkout_url"])

        directive = self._timeout_directive(order)
        self.assertEqual(directive.status, Directive.Status.QUEUED)
        self.assertEqual(directive.available_at, expires_at)
        self.assertEqual(directive.payload["intent_ref"], intent.ref)

        # 3. Estoque RESERVADO, não baixado: o dinheiro ainda não entrou.
        holds = _hold_rows(order)
        self.assertTrue(holds, "a venda do PDV reserva o que vendeu")
        self.assertTrue(all(hold.status != HoldStatus.FULFILLED for hold in holds))
        self.assertEqual(StockQueries.available(SKU), Decimal(STOCK_QTY - SOLD_QTY))

        # 4. E o aviso da loja online ("conferimos a disponibilidade…") não sai
        #    daqui — o do balcão nasce junto com a URL.
        self.assertFalse(
            Directive.objects.filter(
                topic="notification.send", payload__order_ref=order.ref, payload__template="payment_requested"
            ).exists()
        )

    def test_expired_link_cancels_the_order_warns_the_customer_and_frees_the_stock(self) -> None:
        order, _screen = self._close_with_link("link-2")
        directive = self._timeout_directive(order)
        expires_at = datetime.fromisoformat(order.data["payment"]["expires_at"])

        # O gateway simulado responde "pending" para um link que ninguém pagou —
        # a resposta definitiva de "não pago" que autoriza o cancelamento.
        self._run_timeout(directive, at=expires_at + timedelta(minutes=1))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.data.get("cancellation_reason"), "payment_timeout")
        self.assertEqual(PaymentIntent.objects.get(order_ref=order.ref).status, PaymentIntent.Status.CANCELLED)
        self.assertTrue(
            Directive.objects.filter(
                topic="notification.send", payload__order_ref=order.ref, payload__template="payment_expired"
            ).exists()
        )
        # O estoque volta: reserva liberada, nada a devolver ao ledger.
        self.assertTrue(all(hold.status == HoldStatus.RELEASED for hold in _hold_rows(order)))
        self.assertEqual(StockQueries.available(SKU), Decimal(STOCK_QTY))

    def test_timeout_before_the_deadline_waits_instead_of_cancelling(self) -> None:
        """Chamado cedo (worker adiantado, re-arme da reconciliação), o handler
        re-agenda para o vencimento — nunca cancela um link que ainda vale."""
        order, _screen = self._close_with_link("link-3")
        directive = self._timeout_directive(order)
        expires_at = datetime.fromisoformat(order.data["payment"]["expires_at"])

        self._run_timeout(directive, at=expires_at - timedelta(hours=1))

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ACCEPTED)
        directive.refresh_from_db()
        self.assertEqual(directive.status, Directive.Status.QUEUED)
        self.assertEqual(directive.available_at, expires_at)

    def test_paid_link_is_not_cancelled_at_the_deadline(self) -> None:
        """Webhook perdido ≠ não pago: o handler pergunta ao gateway antes."""
        from shopman.payman import PaymentService

        order, _screen = self._close_with_link("link-4")
        directive = self._timeout_directive(order)
        intent = PaymentIntent.objects.get(order_ref=order.ref)
        PaymentService.authorize(intent.ref, gateway_id="mock-paid")
        PaymentService.capture(intent.ref)
        expires_at = datetime.fromisoformat(order.data["payment"]["expires_at"])

        self._run_timeout(directive, at=expires_at + timedelta(minutes=1))

        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.Status.CANCELLED)
        self.assertFalse(
            Directive.objects.filter(
                topic="notification.send", payload__order_ref=order.ref, payload__template="payment_expired"
            ).exists()
        )
