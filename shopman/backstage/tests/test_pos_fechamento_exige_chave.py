"""O fechamento da venda exige a chave da tentativa (EXCELENCIA-PDV F8, #2565).

A chave (``client_request_id``) é o que faz a retentativa de uma venda devolver a
MESMA venda: a resposta perdida, a fila sem conexão, o toque duplo. Sem ela, o
reenvio fechava uma segunda venda, e a gaveta contava o dinheiro duas vezes. As
rotas de caixa já recusavam sem chave (422 ``client_request_id_required``); o
``sale/close`` aceitava. O PDV sempre manda a chave (``cart.clientRequestId``):
quem chega sem ela é cliente fora do contrato, e a recusa diz o que falta no
dialeto canônico ``{detail, field, errors}``.
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
from shopman.orderman.models import Order

from shopman.backstage.tests.pos_test_runtime import bind_station
from shopman.shop.models import Channel, Shop
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION

CLOSE_URL = "/api/v1/backstage/pos/sale/close/"
MESSAGE = "Identifique a tentativa antes de registrar."


class POSCloseRequiresAttemptKeyTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="pdv",
            name="PDV",
            is_active=True,
            config={"payment": {"method": "cash", "timing": "external"}},
        )
        product = Product.objects.create(
            sku="POS-F8-ITEM", name="Pão F8", base_price_q=1200, is_published=True, is_sellable=True,
        )
        listing = Listing.objects.create(ref="pdv", name="PDV", is_active=True)
        ListingItem.objects.create(listing=listing, product=product, price_q=1200, is_published=True, is_sellable=True)
        operator = get_user_model().objects.create_user(username="pos-f8", password="x", is_staff=True)
        operator.user_permissions.add(
            Permission.objects.get(content_type=ContentType.objects.get_for_model(Shift), codename="operate_pos"),
        )
        self.client.force_login(operator)
        terminal = Terminal.default()
        bind_station(self.client, terminal.ref)
        cash.open_shift(operator=operator, terminal=terminal, float_q=0)

    def _close(self, **overrides):
        payload = {
            "intent_version": POS_SALE_INTENT_VERSION,
            "items": [{"sku": "POS-F8-ITEM", "name": "Pão F8", "qty": 1, "unit_price_q": 1200}],
            "fulfillment_type": "pickup",
            "payment_method": "cash",
            "payment_collection": "terminal",
            "expected_total_q": 1200,
            "client_request_id": "pos-f8-001",
        }
        payload.update(overrides)
        payload = {key: value for key, value in payload.items() if value is not None}
        return self.client.post(CLOSE_URL, data=json.dumps(payload), content_type="application/json")

    def test_sem_a_chave_a_venda_nao_fecha_e_a_recusa_diz_o_que_falta(self) -> None:
        for missing in (None, "", "   "):
            with self.subTest(client_request_id=missing):
                response = self._close(client_request_id=missing)

                self.assertEqual(response.status_code, 422, response.content)
                body = response.json()
                self.assertEqual(body["detail"], MESSAGE)
                self.assertEqual(body["field"], "client_request_id")
                self.assertEqual(body["errors"], {"client_request_id": [MESSAGE]})
                self.assertEqual(body["error"]["code"], "client_request_id_required")
                self.assertFalse(Order.objects.exists())

    def test_com_a_chave_a_venda_fecha_e_o_reenvio_devolve_a_mesma(self) -> None:
        first = self._close()
        self.assertEqual(first.status_code, 200, first.content)

        retry = self._close()

        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(retry.json()["order_ref"], first.json()["order_ref"])
        self.assertEqual(Order.objects.count(), 1)
