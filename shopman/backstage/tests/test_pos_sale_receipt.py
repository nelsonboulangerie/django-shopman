"""Recibo não fiscal da venda em ESC/POS: o servidor compõe, o balcão relaia.

O recibo é a projeção impressa do que a venda GRAVOU (`Order` + `Order.data`),
para reimprimir igual amanhã. Estes testes ancoram três contratos: o papel
carrega a venda inteira (loja, itens, pagamentos, troco, cliente); a decisão de
"2ª via" é do servidor (`receipt_printed_at`, nunca heurística de tela); e o
endpoint só abre para quem opera o PDV.
"""

from __future__ import annotations

import base64

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.cashman.models import Shift
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop


class POSSaleReceiptTests(TestCase):
    maxDiff = None

    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Padaria Teste", document="02119381000158")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
        self.operator = get_user_model().objects.create_user("op", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(Shift)
        self.operator.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="operate_pos")
        )
        self.client.force_login(self.operator)

    def _order(self, ref: str) -> Order:
        order = Order.objects.create(
            ref=ref,
            channel_ref="pdv",
            session_key=f"s-{ref}",
            status=Order.Status.COMPLETED,
            total_q=1750,
            data={
                "origin_channel": "pos",
                "fulfillment_type": "pickup",
                "tab_display": "1007",
                "customer": {"name": "Dona Cida"},
                "payment": {
                    "method": "cash",
                    "amount_q": 1750,
                    "tenders": [{"method": "cash", "amount_q": 1750, "status": "received"}],
                    "tendered_q": 2000,
                    "change_q": 250,
                },
            },
            snapshot={"items": [{"sku": "PAO", "name": "Pão francês", "qty": 2, "price_q": 875}]},
        )
        order.items.create(sku="PAO", name="Pão francês", qty=2, unit_price_q=875, line_total_q=1750)
        return order

    def _receipt_text(self, ref: str) -> tuple[str, dict]:
        response = self.client.get(f"/api/v1/backstage/pos/orders/{ref}/receipt-escpos/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        return base64.b64decode(body["payload_b64"]).decode("cp860", "replace"), body

    def test_receipt_carries_the_whole_sale(self) -> None:
        self._order("PDV-RC-1")

        text, body = self._receipt_text("PDV-RC-1")

        self.assertEqual(body["title"], "recibo:PDV-RC-1")
        self.assertIn("PADARIA TESTE", text)  # o Shop assina o papel
        self.assertIn("Recibo não fiscal", text)
        self.assertIn("Pedido PDV-RC-1", text)
        self.assertIn("Comanda #1007", text)
        self.assertIn("Cliente: Dona Cida", text)
        self.assertIn("Pão francês", text)
        self.assertIn("2 x R$ 8,75", text)
        self.assertIn("TOTAL R$ 17,50", text)
        self.assertIn("Recebido", text)
        self.assertIn("R$ 20,00", text)
        self.assertIn("Troco", text)
        self.assertIn("R$ 2,50", text)
        self.assertIn("Obrigado pela preferência!", text)

    def test_second_print_is_stamped_by_the_server(self) -> None:
        order = self._order("PDV-RC-2")

        first_text, first = self._receipt_text("PDV-RC-2")
        self.assertFalse(first["reprint"])
        self.assertNotIn("2a VIA", first_text)
        order.refresh_from_db()
        self.assertTrue(order.data.get("receipt_printed_at"))

        second_text, second = self._receipt_text("PDV-RC-2")
        self.assertTrue(second["reprint"])
        self.assertIn("2a VIA", second_text)

    def test_danfe_reprint_is_also_server_decided(self) -> None:
        # A mesma regra vale para a DANFE em bobina: a heurística de tela
        # (venda completa + e-mail enviado) morreu com o carimbo do servidor.
        order = self._order("PDV-RC-3")
        order.data.update(
            nfce_access_key="41260800000000000000650010000001521151375188",
            nfce_status="authorized",
            nfce_number=152,
            nfce_series=1,
            nfce_protocol="123",
            nfce_qrcode_url="http://www.fazenda.pr.gov.br/nfce/qrcode/?p=x",
        )
        order.save(update_fields=["data"])

        first = self.client.get("/api/v1/backstage/pos/orders/PDV-RC-3/danfe-escpos/")
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["reprint"])
        self.assertNotIn(
            "2a VIA", base64.b64decode(first.json()["payload_b64"]).decode("cp860", "replace")
        )
        order.refresh_from_db()
        self.assertTrue(order.data.get("danfe_printed_at"))

        second = self.client.get("/api/v1/backstage/pos/orders/PDV-RC-3/danfe-escpos/")
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["reprint"])
        self.assertIn(
            "2a VIA", base64.b64decode(second.json()["payload_b64"]).decode("cp860", "replace")
        )

    def test_unknown_order_is_404(self) -> None:
        response = self.client.get("/api/v1/backstage/pos/orders/NAO-EXISTE/receipt-escpos/")
        self.assertEqual(response.status_code, 404)

    def test_requires_pos_permission(self) -> None:
        intruder = get_user_model().objects.create_user("intruso", password="x", is_staff=True)
        self.client.force_login(intruder)
        self._order("PDV-RC-4")

        response = self.client.get("/api/v1/backstage/pos/orders/PDV-RC-4/receipt-escpos/")

        self.assertEqual(response.status_code, 403)
        # O 403 não pode carimbar: o pedido segue "nunca impresso".
        self.assertFalse(
            (Order.objects.get(ref="PDV-RC-4").data or {}).get("receipt_printed_at")
        )
