"""Últimas vendas do PDV: o estado fiscal mora numa lista, não na tela da venda.

A emissão é assíncrona e a confirmação da venda some quando a próxima começa.
Estes testes ancoram o contrato da lista e das três ações — imprimir DANFE,
reenviar e-mail, reprocessar falha — todas seguindo o FATO (a nota), nunca o
toggle do operador.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from shopman.cashman.models import Shift
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop
from shopman.shop.tests.danfe_fixtures import xml_for_key


def _brasilia(hour, minute, *, day=30, month=9):
    """Um instante no relógio da loja, devolvido em UTC como o ``timezone.now()``.

    30/09/2026, o dia do CI vermelho. Congelar com o fuso de Brasília embutido
    faria ``now.date()`` acertar por acaso e esconderia um defeito de UTC.
    """
    return timezone.make_aware(datetime(2026, month, day, hour, minute)).astimezone(UTC)


@pytest.fixture(autouse=True)
def authorized_xml(monkeypatch):
    monkeypatch.setattr("shopman.shop.services.danfe_xml.read_authorized_xml", xml_for_key)


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
        # O MESMO vocabulário da resposta do fechamento e da pill do Gestor.
        self.assertEqual(authorized["fiscal_state"], "authorized")
        self.assertTrue(authorized["can_print_danfe"])
        self.assertTrue(authorized["can_resend_email"])
        self.assertFalse(authorized["can_requeue_fiscal"])
        failed = sales["PDV-RS-2"]
        self.assertEqual(failed["fiscal_status"], "failed")
        self.assertEqual(failed["fiscal_state"], "failed")
        self.assertFalse(failed["can_print_danfe"])
        self.assertTrue(failed["can_requeue_fiscal"])

    def test_recent_sales_flag_the_undo_window(self) -> None:
        """`can_cancel` segue o MESMO predicado do cancel (janela + status).

        A ação nas Últimas vendas só aparece para venda ainda cancelável: fresca
        e num status que admite o desfazer — inclusive `completed` quando o
        lifecycle baked declara completed→cancelled (o pdv declara).
        """
        self._order("PDV-RS-W1", nfce=False)
        Order.objects.filter(ref="PDV-RS-W1").update(status=Order.Status.NEW)

        self._order("PDV-RS-W2", nfce=False)
        Order.objects.filter(ref="PDV-RS-W2").update(
            snapshot={
                "items": [],
                "lifecycle": {"transitions": {"completed": ["cancelled"]}},
            },
        )

        # Fresca porém COMPLETED sem a transição declarada: o cancel recusaria.
        self._order("PDV-RS-W3", nfce=False)

        # Fora da janela: fresca no status certo não basta, a idade manda.
        self._order("PDV-RS-W4", nfce=False)
        Order.objects.filter(ref="PDV-RS-W4").update(
            status=Order.Status.NEW,
            created_at=timezone.now() - timedelta(minutes=10),
        )

        from shopman.shop.fiscal import fiscal_pool

        fiscal_pool.reset()
        self.addCleanup(fiscal_pool.reset)
        with self.settings(
            SHOPMAN_FISCAL_ADAPTER="shopman.backstage.tests.test_pos_recent_sales_fiscal.StubFiscalBackend",
        ):
            response = self.client.get("/api/v1/backstage/pos/recent-sales/")

        self.assertEqual(response.status_code, 200)
        sales = {s["order_ref"]: s for s in response.json()["sales"]}
        self.assertTrue(sales["PDV-RS-W1"]["can_cancel"])
        self.assertTrue(sales["PDV-RS-W2"]["can_cancel"])
        self.assertFalse(sales["PDV-RS-W3"]["can_cancel"])
        self.assertFalse(sales["PDV-RS-W4"]["can_cancel"])

    def _recent_sales_at(self, agora):
        """A lista do PDV pedida com o relógio CONGELADO em ``agora``."""
        from shopman.shop.fiscal import fiscal_pool

        fiscal_pool.reset()
        self.addCleanup(fiscal_pool.reset)
        with self.settings(
            SHOPMAN_FISCAL_ADAPTER="shopman.backstage.tests.test_pos_recent_sales_fiscal.StubFiscalBackend",
        ), patch("django.utils.timezone.now", return_value=agora):
            response = self.client.get("/api/v1/backstage/pos/recent-sales/")
        self.assertEqual(response.status_code, 200)
        return response.json()["sales"]

    def _encomenda_paga_ha_dias_e_retirada_hoje_entra_na_lista(self, agora) -> None:
        """A venda FISCAL é a da saída (#1173): a encomenda retirada hoje é de hoje.

        Paga há três dias, ela ficava fora das "últimas 24 horas" — e a emissão
        avulsa, que vale no dia da saída, não tinha onde ser pedida.

        O relógio fica congelado: "há 5 minutos" só é "hoje" longe da meia-noite.
        Lido de verdade, o teste caía às 00:02 de Brasília (CI do #1312), quando
        a entrega das 23:57 já era, com razão, "30/09 às 23:57".
        """
        tres_dias = agora - timedelta(days=3)
        with patch("django.utils.timezone.now", return_value=agora):
            self._order("PDV-ENC-RET", nfce=False)
            dinheiro = {"method": "cash", "amount_q": 1500, "tenders": [{"method": "cash", "amount_q": 1500, "status": "received"}]}
            Order.objects.filter(ref="PDV-ENC-RET").update(
                created_at=tres_dias, completed_at=agora,
                data={**Order.objects.get(ref="PDV-ENC-RET").data, "payment": dinheiro},
            )
            self._order("PDV-ENC-VELHA", nfce=False)
            Order.objects.filter(ref="PDV-ENC-VELHA").update(created_at=tres_dias, completed_at=tres_dias)
            self._order("PDV-ENC-ENTREGA", nfce=False)
            Order.objects.filter(ref="PDV-ENC-ENTREGA").update(
                created_at=tres_dias, dispatched_at=agora - timedelta(minutes=5),
                data={**Order.objects.get(ref="PDV-ENC-ENTREGA").data, "fulfillment_type": "delivery"},
            )
            self._order("PDV-HOJE", nfce=False)
            Order.objects.filter(ref="PDV-HOJE").update(created_at=agora - timedelta(minutes=30))

        sales = self._recent_sales_at(agora)
        refs = [sale["order_ref"] for sale in sales]
        # A retirada de agora vem primeiro; a encomenda que saiu há dias fica fora.
        self.assertEqual(refs, ["PDV-ENC-RET", "PDV-ENC-ENTREGA", "PDV-HOJE"])
        by_ref = {sale["order_ref"]: sale for sale in sales}
        local = timezone.localtime(agora)
        retirada = by_ref["PDV-ENC-RET"]
        self.assertEqual(retirada["created_at_display"], timezone.localtime(tres_dias).strftime("%d/%m %H:%M"))
        self.assertEqual(retirada["handoff_display"], f"Retirada hoje às {local.strftime('%H:%M')}")
        entrega = (local - timedelta(minutes=5)).strftime("%H:%M")
        self.assertEqual(by_ref["PDV-ENC-ENTREGA"]["handoff_display"], f"Saiu para entrega hoje às {entrega}")
        self.assertEqual(by_ref["PDV-HOJE"]["handoff_display"], "")
        # A emissão avulsa vale no dia da SAÍDA, não no do pagamento.
        self.assertTrue(retirada["can_emit_fiscal"])

    def test_encomenda_paga_ha_dias_e_retirada_hoje_entra_na_lista(self) -> None:
        self._encomenda_paga_ha_dias_e_retirada_hoje_entra_na_lista(_brasilia(12, 0))

    def test_encomenda_paga_ha_dias_e_retirada_hoje_entra_na_lista_as_23h30(self) -> None:
        # 23:30 de Brasília já é 02:30 UTC do dia seguinte: "hoje" é o da loja.
        self._encomenda_paga_ha_dias_e_retirada_hoje_entra_na_lista(_brasilia(23, 30))

    def test_saida_as_20h_e_nota_as_23h30_sao_o_mesmo_dia_da_loja(self) -> None:
        """A retirada das 20:00 e a nota avulsa pedida às 23:30 são do MESMO dia.

        Em UTC não seriam (23:00 de 30/09 e 02:30 de 01/10): contado assim, o
        botão sumiria no fim do expediente com "Só dá para emitir nota de venda
        do mesmo dia." Prova que a régua fiscal conta o dia da loja.
        """
        agora = _brasilia(23, 30)
        with patch("django.utils.timezone.now", return_value=agora):
            self._order("PDV-ENC-20H", nfce=False)
        dinheiro = {"method": "cash", "amount_q": 1500, "tenders": [{"method": "cash", "amount_q": 1500, "status": "received"}]}
        Order.objects.filter(ref="PDV-ENC-20H").update(
            created_at=agora - timedelta(days=3), completed_at=_brasilia(20, 0),
            data={**Order.objects.get(ref="PDV-ENC-20H").data, "payment": dinheiro},
        )

        [venda] = self._recent_sales_at(agora)

        self.assertEqual(venda["handoff_display"], "Retirada hoje às 20:00")
        self.assertTrue(venda["can_emit_fiscal"])

    def test_entrega_das_23h57_vista_as_00h02_e_de_ontem(self) -> None:
        """Passada a meia-noite, a saída das 23:57 diz a data, e não "hoje".

        É o que o CI do #1312 viu às 00:02 de Brasília: o produto estava certo.
        E a régua fiscal é o dia de OPERAÇÃO (padrão: mesmo dia), então a nota
        avulsa da entrega de ontem já não sai, como para a venda das 23h com a
        nota das 0h10 (``fiscal.issue_override_refusal``).
        """
        agora = _brasilia(0, 2, day=1, month=10)
        with patch("django.utils.timezone.now", return_value=agora):
            self._order("PDV-ENC-NOITE", nfce=False)
        Order.objects.filter(ref="PDV-ENC-NOITE").update(
            created_at=agora - timedelta(days=3), dispatched_at=_brasilia(23, 57),
            data={**Order.objects.get(ref="PDV-ENC-NOITE").data, "fulfillment_type": "delivery"},
        )

        [venda] = self._recent_sales_at(agora)

        self.assertEqual(venda["handoff_display"], "Saiu para entrega 30/09 às 23:57")
        self.assertFalse(venda["can_emit_fiscal"])

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
        with patch("shopman.shop.fiscal.fiscal_pool.get_backend", return_value=backend):
            response = self.client.post(
                "/api/v1/backstage/pos/orders/PDV-RS-6/resend-fiscal-email/",
                data=json.dumps({}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [("PDV-RS-6", ["cliente@example.org"])])
