"""D42: o PDV fecha a venda com o total que a tela mostrou.

A tela manda ``expected_total_q`` (o total da revisão que o operador conferiu com
o cliente). O servidor recalcula pela conta de sempre e, se o dele for outro,
para cima ou para baixo, recusa a venda sem fechar nada. A retentativa da MESMA
venda (mesmo ``client_request_id``) devolve a venda feita, nunca uma recusa.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.cashman import services as cash
from shopman.cashman.models import Shift, Terminal
from shopman.offerman.models import Listing, ListingItem, Product
from shopman.orderman.models import IdempotencyKey, Order

from shopman.backstage.models import POSTab
from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

REVIEW_URL = "/api/v1/backstage/pos/sale/review/"
CLOSE_URL = "/api/v1/backstage/pos/sale/close/"


class POSExpectedTotalTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={
                "payment": {"method": "cash", "timing": "external"},
                "surface_policy": {"fulfillment_types": ["pickup", "delivery"]},
            },
        )
        POSTab.objects.create(ref="00001042", label="1042")
        product = Product.objects.create(
            sku="POS-D42-ITEM", name="Pão D42", base_price_q=1200, is_published=True, is_sellable=True,
        )
        listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
        self.listing_item = ListingItem.objects.create(
            listing=listing, product=product, price_q=1300, is_published=True, is_sellable=True,
        )
        operator = get_user_model().objects.create_user(username="pos-d42", password="x", is_staff=True)
        operator.user_permissions.add(
            Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
        )
        self.client.force_login(operator)
        terminal = Terminal.default()
        bind_station(self.client, terminal.ref)
        self.shift = cash.open_shift(operator=operator, terminal=terminal, float_q=0)

    def _intent(self, **overrides) -> dict:
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "POS-D42-ITEM", "name": "Pão D42", "qty": 2, "unit_price_q": 1300}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "client_request_id": "pos-d42-001",
        }
        payload.update(overrides)
        return payload

    def _post(self, url: str, payload: dict):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def _assert_nothing_closed(self) -> None:
        self.assertFalse(Order.objects.exists())
        # A trava de idempotência também volta: a mesma chave fica livre para o
        # reenvio depois que o operador conferir o total novo.
        self.assertFalse(IdempotencyKey.objects.filter(key="pos-d42-001").exists())

    def test_the_total_the_screen_showed_closes_the_sale(self) -> None:
        review = self._post(REVIEW_URL, self._intent())
        self.assertEqual(review.status_code, 200, review.content)
        shown_q = review.json()["review"]["total_q"]
        self.assertEqual(shown_q, 2600)

        closed = self._post(CLOSE_URL, self._intent(expected_total_q=shown_q))

        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(Order.objects.get(ref=closed.json()["order_ref"]).total_q, 2600)

    def test_a_server_total_below_the_screen_refuses_with_both_values(self) -> None:
        closed = self._post(CLOSE_URL, self._intent(expected_total_q=3000))

        self.assertEqual(closed.status_code, 422, closed.content)
        body = closed.json()
        message = "O total mudou de R$ 30,00 para R$ 26,00. Confira com o cliente antes de cobrar."
        self.assertEqual(body["detail"], message)
        self.assertEqual(body["field"], "expected_total_q")
        self.assertEqual(body["errors"], {"expected_total_q": [message]})
        self.assertEqual(body["error"]["code"], "total_changed")
        self.assertEqual(body["error"]["context"], {"old_total_q": 3000, "new_total_q": 2600})
        self._assert_nothing_closed()

    def test_a_server_total_above_the_screen_refuses_too(self) -> None:
        """O preço subiu entre a revisão e o Finalizar: a tela mostrou R$ 26,00."""
        self.listing_item.price_q = 1500
        self.listing_item.save(update_fields=["price_q"])

        closed = self._post(CLOSE_URL, self._intent(
            items=[{"sku": "POS-D42-ITEM", "name": "Pão D42", "qty": 2, "unit_price_q": 1500}],
            expected_total_q=2600,
        ))

        self.assertEqual(closed.status_code, 422, closed.content)
        body = closed.json()
        self.assertEqual(body["error"]["code"], "total_changed")
        self.assertEqual(
            body["detail"], "O total mudou de R$ 26,00 para R$ 30,00. Confira com o cliente antes de cobrar.",
        )
        self._assert_nothing_closed()

    def test_without_the_screen_total_the_sale_does_not_close(self) -> None:
        closed = self._post(CLOSE_URL, self._intent())

        self.assertEqual(closed.status_code, 422, closed.content)
        body = closed.json()
        self.assertEqual(body["error"]["code"], "expected_total_required")
        self.assertEqual(body["field"], "expected_total_q")
        self._assert_nothing_closed()

    def test_the_retry_of_the_same_sale_returns_the_sale_not_a_refusal(self) -> None:
        """Retentativa (fila offline, resposta perdida) com o mesmo total: a mesma venda.

        Nem um preço mudado DEPOIS do fechamento transforma o replay em recusa:
        a venda existe, e é ela que responde.
        """
        first = self._post(CLOSE_URL, self._intent(expected_total_q=2600))
        self.assertEqual(first.status_code, 200, first.content)

        again = self._post(CLOSE_URL, self._intent(expected_total_q=2600))
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["order_ref"], first.json()["order_ref"])

        self.listing_item.price_q = 1500
        self.listing_item.save(update_fields=["price_q"])
        late = self._post(CLOSE_URL, self._intent(
            items=[{"sku": "POS-D42-ITEM", "name": "Pão D42", "qty": 2, "unit_price_q": 1500}],
            expected_total_q=2600,
        ))
        self.assertEqual(late.status_code, 200, late.content)
        self.assertEqual(late.json()["order_ref"], first.json()["order_ref"])
        self.assertEqual(Order.objects.count(), 1)

    def test_the_discount_is_part_of_the_total_the_screen_showed(self) -> None:
        """Desconto de linha: o total esperado é o JÁ descontado, o da revisão."""
        items = [{
            "sku": "POS-D42-ITEM", "name": "Pão D42", "qty": 2, "unit_price_q": 1300,
            "discount": {"type": "fixed", "value": 1, "reason": "Cortesia"},
        }]
        review = self._post(REVIEW_URL, self._intent(items=items))
        self.assertEqual(review.status_code, 200, review.content)
        shown_q = review.json()["review"]["total_q"]
        self.assertLess(shown_q, 2600)

        stale = self._post(CLOSE_URL, self._intent(items=items, expected_total_q=2600))
        self.assertEqual(stale.status_code, 422, stale.content)
        self.assertEqual(stale.json()["error"]["code"], "total_changed")

        closed = self._post(CLOSE_URL, self._intent(items=items, expected_total_q=shown_q))
        self.assertEqual(closed.status_code, 200, closed.content)
        self.assertEqual(Order.objects.get(ref=closed.json()["order_ref"]).total_q, shown_q)
