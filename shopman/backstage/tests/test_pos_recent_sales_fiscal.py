"""Últimas vendas do PDV: o estado fiscal mora numa lista, não na tela da venda.

A emissão é assíncrona e a confirmação da venda some quando a próxima começa.
Estes testes ancoram o contrato da lista e das três ações — imprimir DANFE,
reenviar e-mail, reprocessar falha — todas seguindo o FATO (a nota), nunca o
toggle do operador.
"""

from __future__ import annotations

import base64
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.cashman.models import Shift
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop


class StubFiscalBackend:
    # ⚠️ Registro em atributo de CLASSE não funciona aqui: o runner importa o
    # módulo como ``backstage.tests...`` e o dotted path do settings importa
    # como ``shopman.backstage.tests...`` — duas cópias do módulo, duas
    # classes. O registro de chamadas dos testes de reenvio usa mock.patch.

    def emit(self, **kwargs):
        from shopman.fiscalman.contracts import FiscalDocumentResult

        return FiscalDocumentResult(success=True, access_key="stub", status="authorized")

    def query_status(self, *, reference):
        from shopman.fiscalman.contracts import FiscalDocumentResult

        return FiscalDocumentResult(success=False, status="pending")

    def cancel(self, *, reference, reason):
        from shopman.fiscalman.contracts import FiscalCancellationResult

        return FiscalCancellationResult(success=True)

    def send_email(self, *, reference, emails):
        return True, "Os e-mails serão enviados em breve."


class POSRecentSalesFiscalTests(TestCase):
    maxDiff = None

    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test", document="02119381000158")
        Channel.objects.create(ref="pdv", name="PDV", is_active=True, config={})
        user = get_user_model().objects.create_user("op", password="x", is_staff=True)
        ct = ContentType.objects.get_for_model(Shift)
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename="operate_pos"))
        self.client.force_login(user)

    def _order(self, ref: str, *, nfce: bool, failed: bool = False) -> Order:
        data = {
            "origin_channel": "pos",
            "fulfillment_type": "pickup",
            "customer": {"name": "Cliente", "email": "cliente@example.org"},
            "payment": {"method": "card", "amount_q": 1500,
                        "tenders": [{"method": "card", "amount_q": 1500, "status": "received"}]},
            "receipt": {"mode": "email", "email": "cliente@example.org"},
        }
        if nfce:
            data.update(
                nfce_access_key="41260800000000000000650010000001521151375188",
                nfce_status="authorized",
                nfce_number=152, nfce_series=1, nfce_protocol="123",
                nfce_qrcode_url="http://www.fazenda.pr.gov.br/nfce/qrcode/?p=x",
                nfce_danfe_url="https://homologacao.focusnfe.com.br/x.html",
            )
        order = Order.objects.create(
            ref=ref, channel_ref="pdv", session_key=f"s-{ref}",
            status=Order.Status.COMPLETED, total_q=1500, data=data,
            snapshot={"items": [{"sku": "PAO", "name": "Pão", "qty": 1, "price_q": 1500}]},
        )
        order.items.create(sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500)
        if failed:
            from shopman.orderman.models import Directive

            Directive.objects.create(
                topic="fiscal.emit_nfce", status="failed",
                payload={"order_ref": ref}, last_error="boom",
            )
        return order

    def test_recent_sales_lists_fiscal_state_and_actions(self) -> None:
        self._order("PDV-RS-1", nfce=True)
        self._order("PDV-RS-2", nfce=False, failed=True)

        from shopman.shop.fiscal import fiscal_pool

        fiscal_pool.reset()
        self.addCleanup(fiscal_pool.reset)
        with self.settings(
            SHOPMAN_FISCAL_ADAPTER="shopman.backstage.tests.test_pos_recent_sales_fiscal.StubFiscalBackend",
            SHOPMAN_FISCAL_EMISSION_RESOLVER=(
                "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
                "shopman.shop.fiscal_resolvers.eletronic_payment,"
                "shopman.shop.fiscal_resolvers.deferred_settlement"
            ),
        ):
            response = self.client.get("/api/v1/backstage/pos/recent-sales/")

        self.assertEqual(response.status_code, 200)
        sales = {s["order_ref"]: s for s in response.json()["sales"]}
        authorized = sales["PDV-RS-1"]
        self.assertEqual(authorized["fiscal_status"], "authorized")
        self.assertTrue(authorized["can_print_danfe"])
        self.assertTrue(authorized["can_resend_email"])
        self.assertFalse(authorized["can_requeue_fiscal"])
        failed = sales["PDV-RS-2"]
        self.assertEqual(failed["fiscal_status"], "failed")
        self.assertFalse(failed["can_print_danfe"])
        self.assertTrue(failed["can_requeue_fiscal"])

    def test_danfe_escpos_returns_printable_bytes(self) -> None:
        self._order("PDV-RS-3", nfce=True)

        response = self.client.get("/api/v1/backstage/pos/orders/PDV-RS-3/danfe-escpos/")

        self.assertEqual(response.status_code, 200)
        payload = base64.b64decode(response.json()["payload_b64"])
        text = payload.decode("cp860", "replace")
        self.assertIn("DANFE NFC-e", text)
        self.assertIn("SEM VALOR FISCAL", text)  # homologação avisa no papel
        self.assertIn("Pão".encode("cp860").decode("cp860"), text)
        self.assertIn("152", text)

    def test_danfe_escpos_refuses_unemitted_note(self) -> None:
        self._order("PDV-RS-4", nfce=False)

        response = self.client.get("/api/v1/backstage/pos/orders/PDV-RS-4/danfe-escpos/")

        self.assertEqual(response.status_code, 409)

    def test_resend_email_uses_the_fiscal_provider(self) -> None:
        self._order("PDV-RS-5", nfce=True)
        backend = StubFiscalBackend()
        calls: list[tuple[str, list[str]]] = []
        backend.send_email = lambda *, reference, emails: (calls.append((reference, emails)) or (True, "ok"))
        from unittest.mock import patch

        with patch("shopman.shop.fiscal.fiscal_pool.get_backend", return_value=backend):
            response = self.client.post(
                "/api/v1/backstage/pos/orders/PDV-RS-5/resend-fiscal-email/",
                data=json.dumps({"email": "outro@example.org"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [("PDV-RS-5", ["outro@example.org"])])

    def test_resend_email_falls_back_to_the_receipt_email(self) -> None:
        self._order("PDV-RS-6", nfce=True)
        backend = StubFiscalBackend()
        calls: list[tuple[str, list[str]]] = []
        backend.send_email = lambda *, reference, emails: (calls.append((reference, emails)) or (True, "ok"))
        from unittest.mock import patch

        with patch("shopman.shop.fiscal.fiscal_pool.get_backend", return_value=backend):
            response = self.client.post(
                "/api/v1/backstage/pos/orders/PDV-RS-6/resend-fiscal-email/",
                data=json.dumps({}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [("PDV-RS-6", ["cliente@example.org"])])
