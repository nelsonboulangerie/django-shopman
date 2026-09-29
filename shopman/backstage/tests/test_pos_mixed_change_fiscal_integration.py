"""Venda MISTA com troco no PDV: a NFC-e declara o que a venda cobrou.

Venda de 13,00 paga com crédito 10,00 + dinheiro 5,00 — o troco de 2,00 sai da
nota em dinheiro. A NFC-e tem que somar 13,00 nas formas de pagamento: com
15,00 contra 13,00 de produtos (e sem ``valor_troco``), a SEFAZ recusa a nota.

``TransactionTestCase`` de propósito, pelo mesmo motivo do
``test_pos_link_sale_expiry_integration``: em produção os ``on_commit`` do
commit rodam ao sair da transação do ``close_sale`` — o lifecycle leva a venda
de balcão a COMPLETED e o ``on_completed`` pede a nota ANTES de o ``settle``
acertar o troco. Dentro de um ``TestCase`` os callbacks rodam só depois do
acerto, e o defeito some do teste.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
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


@override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.backstage.tests.test_pos_mixed_change_fiscal_integration.StubFiscalBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.eletronic_payment",
)
class MixedSaleWithChangeFiscalTests(TransactionTestCase):
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
            sku="BOLO", name="Bolo", base_price_q=1300, is_published=True, is_sellable=True,
        )
        fiscal_pool.reset()
        self.addCleanup(fiscal_pool.reset)

    def test_nfce_payment_is_the_settled_one_not_the_cash_handed_over(self) -> None:
        result = pos_service.close_sale(
            channel_ref="pdv",
            payload={
                "items": [{"sku": "BOLO", "name": "Bolo", "qty": 1, "unit_price_q": 1300}],
                "fulfillment_type": "pickup",
                "payment_method": "mixed",
                "payment_collection": "terminal",
                "payment_tenders": [
                    {"method": "card", "amount_q": 1000, "collection": "terminal"},
                    {"method": "cash", "amount_q": 500, "collection": "terminal"},
                ],
                "cash_shift_id": self.shift.pk,
                "client_request_id": "mixed-change-fiscal",
            },
            actor="pos:alice",
            operator_username="alice",
        )

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.total_q, 1300)
        # O pedido guarda o acerto: dinheiro líquido 3,00, troco 2,00.
        self.assertEqual(order.data["payment"]["change_q"], 200)

        directives = Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order.ref)
        self.assertEqual(directives.count(), 1)
        payment = directives.get().payload["payment"]
        tenders = {t["method"]: t["amount_q"] for t in payment["tenders"]}
        self.assertEqual(tenders, {"card": 1000, "cash": 300}, payment)
        self.assertEqual(payment["amount_q"], 1300)


def test_change_only_comes_out_of_cash_and_settled_payment_is_untouched():
    from shopman.shop.services.fiscal import _payment_net_of_change

    settled = {"amount_q": 1300, "tenders": [{"method": "card", "amount_q": 1000}, {"method": "cash", "amount_q": 300}]}
    assert _payment_net_of_change(settled, 1300) is settled

    # Troco maior que uma linha de dinheiro: sai da última para a primeira.
    raw = {"amount_q": 1300, "tenders": [
        {"method": "cash", "amount_q": 200}, {"method": "card", "amount_q": 1000}, {"method": "cash", "amount_q": 500},
    ]}
    net = _payment_net_of_change(raw, 1000)
    assert [t["amount_q"] for t in net["tenders"]] == [0, 1000, 0]
    assert net["amount_q"] == 1000
    assert [t["amount_q"] for t in raw["tenders"]] == [200, 1000, 500]  # o pedido não é mutado

    # Excedente que o dinheiro não cobre não é troco: fica, e a SEFAZ recusa alto.
    overcharged = {"amount_q": 1500, "tenders": [{"method": "card", "amount_q": 1500}]}
    assert _payment_net_of_change(overcharged, 1300) is overcharged
