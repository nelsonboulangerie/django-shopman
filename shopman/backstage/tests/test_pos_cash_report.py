"""Relatório X/Z da antesala do PDV, lido do livro do ``cashman`` e do ``payman``."""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.services import pos as pos_service

REPORT_URL = "/api/v1/backstage/pos/cash/report/"


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _grant(user, *codenames):
    ct = ContentType.objects.get_for_model(Shift)
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(content_type=ct, codename=codename))


def _manager_approval():
    """Gerente que assina as retiradas de gaveta usadas como cenário do relatório."""
    from shopman.doorman.models import PinCredential

    User = get_user_model()
    user = User.objects.create_user(username="gerente-relatorio", password="x", is_staff=True)
    ct = ContentType.objects.get_for_model(Shift)
    user.user_permissions.add(Permission.objects.get(content_type=ct, codename="adjust_shift"))
    PinCredential.set_for(user, "4321")
    return {"username": user.username, "pin": "4321"}


def _captured_intent(ref: str, *, order_ref: str, method: str, amount_q: int) -> PaymentIntent:
    """Um intent liquidado no ``payman`` — a fonte de "quanto, por método"."""
    intent = PaymentIntent.objects.create(
        ref=ref,
        order_ref=order_ref,
        method=method,
        status=PaymentIntent.Status.CAPTURED,
        amount_q=amount_q,
        gateway="" if method in ("cash", "external") else "test",
    )
    PaymentTransaction.objects.create(intent=intent, type=PaymentTransaction.Type.CAPTURE, amount_q=amount_q)
    return intent


class POSCashReportTests(TestCase):
    """Relatório X/Z da antesala do PDV (ADMIN-ROLE-PLAN WP-ADM-4).

    Leitura X = parcial do turno ABERTO do operador; Z = turnos FECHADOS do
    dia; histórico = totais agregados. BLIND COUNT: o PDV nunca revela o valor
    ESPERADO da gaveta nem a variância — nem no X, nem no Z. A conferência é
    da retaguarda; aqui garantimos por contrato que essas chaves NÃO existem
    na resposta.

    As vendas entram como o WP-3 do CASHMAN-PLAN as grava: uma linha ``sale``
    no turno com ``payment_ref``/``payload.intents`` apontando os intents do
    ``payman``; o valor por método vem de lá, o efeito em dinheiro da linha.
    """

    def setUp(self) -> None:
        _make_shop()
        User = get_user_model()
        self.operator = User.objects.create_user(username="caixa", password="x", is_staff=True)
        _grant(self.operator, "operate_pos", "audit_shift")
        self.client.force_login(self.operator)
        self.terminal = Terminal.default()
        self.manager_approval = _manager_approval()
        # Fechar a gaveta é da gerência (decisão do dono, 21/08/2026): o caixa
        # abre e opera, quem conta no fim é quem fecha o dia.
        self.gerente = User.objects.create_user(username="gerente-z", password="x", is_staff=True)
        _grant(self.gerente, "operate_pos")
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        from shopman.backstage.models import DayClosing

        ct = ContentType.objects.get_for_model(DayClosing)
        self.gerente.user_permissions.add(
            Permission.objects.get(content_type=ct, codename="perform_closing")
        )
        self.gerente = User.objects.get(pk=self.gerente.pk)  # refresca cache de permissão

    # ── helpers ────────────────────────────────────────────────────────

    def _open_shift(self, *, opening="50,00") -> Shift:
        return pos_service.open_cash_shift(
            operator=self.operator,
            opening_amount_raw=opening,
            terminal_ref=self.terminal.ref,
        )

    def _sale(self, ref: str, *, shift: Shift, tenders: list[tuple[str, int]], operator=None) -> Entry:
        """Uma venda no livro do turno, no formato do WP-3: intents no payman + linha ``sale``."""
        intents = {
            method: _captured_intent(f"PI-{ref}-{method}", order_ref=ref, method=method, amount_q=amount_q).ref
            for method, amount_q in tenders
        }
        cash_q = sum(amount_q for method, amount_q in tenders if method == "cash")
        method = "mixed" if len(tenders) > 1 else tenders[0][0]
        return cash.record(
            Entry.Kind.SALE,
            shift=shift,
            operator=operator or self.operator,
            amount_q=cash_q,
            order_ref=ref,
            payment_ref=intents.get(method, "") if method != "mixed" else "",
            payload={"method": method, "collection": "terminal", "intents": intents},
        )

    # ── gate ───────────────────────────────────────────────────────────

    def test_report_requires_a_permission(self) -> None:
        User = get_user_model()
        other = User.objects.create_user(username="sem-perm", password="x", is_staff=True)
        self.client.force_login(other)

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 403)

    def test_operar_o_caixa_nao_da_direito_a_ver_o_faturamento(self) -> None:
        """Quem opera não audita — e é pela API crua que isso tem de valer.

        O relatório mostra `sales_total` e a quebra por método: quanto a casa
        vendeu hoje. Esconder o card na tela e deixar a rota aberta seria fechar
        a porta e esquecer a janela — basta o endereço para ler tudo.

        O `Gerente` cai aqui junto com o balcão: `setup_groups` dá a ele
        `operate_pos`, `adjust_shift` e `manage_operators`, e **não**
        `audit_shift`.
        """
        User = get_user_model()
        balconista = User.objects.create_user(username="so-opera", password="x", is_staff=True)
        _grant(balconista, "operate_pos", "adjust_shift", "manage_operators")
        self.client.force_login(balconista)

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 403)
        self.assertNotIn("report", resp.json())

    # ── leitura X (turno aberto) ───────────────────────────────────────

    def test_x_reading_shows_opening_movements_and_sales_by_method(self) -> None:
        shift = self._open_shift(opening="50,00")
        pos_service.register_cash_movement(
            operator=self.operator, movement_type="sangria", amount_raw="20,00", reason="troco banco",
            manager_approval=self.manager_approval,
        )
        pos_service.register_cash_movement(
            operator=self.operator, movement_type="suprimento", amount_raw="10,00", reason="reforço",
        )
        self._sale("POS-X-CASH", shift=shift, tenders=[("cash", 3000)])
        self._sale("POS-X-PIX", shift=shift, tenders=[("pix", 2500)])

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        report = resp.json()["report"]
        self.assertTrue(report["has_open_shift"])
        x = report["x_reading"]
        self.assertEqual(x["shift_id"], shift.pk)
        self.assertEqual(x["status"], "open")
        self.assertEqual(x["operator"], "caixa")
        self.assertEqual(x["opening_amount_q"], 5000)
        self.assertEqual(x["sales_count"], 2)
        self.assertEqual(x["sales_total_q"], 5500)
        by_method = {row["method"]: row for row in x["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 3000)
        self.assertEqual(by_method["pix"]["amount_q"], 2500)
        kinds = [(m["kind"], m["amount_q"]) for m in x["movements"]]
        self.assertEqual(kinds, [("sangria", 2000), ("suprimento", 1000)])
        self.assertEqual(x["movements_in_q"], 1000)
        self.assertEqual(x["movements_out_q"], 2000)
        # Turno aberto: contagem ainda não existe.
        self.assertIsNone(x["counted_amount_q"])

    def test_mixed_tender_sale_splits_by_method_from_payman(self) -> None:
        """Venda mista: uma linha, dois intents; cada método com o seu valor, contado uma vez."""
        shift = self._open_shift()
        self._sale("POS-X-MIX", shift=shift, tenders=[("cash", 4000), ("card", 2000)])

        x = self.client.get(REPORT_URL).json()["report"]["x_reading"]

        self.assertEqual(x["sales_count"], 1)
        self.assertEqual(x["sales_total_q"], 6000)
        by_method = {row["method"]: row for row in x["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 4000)
        self.assertEqual(by_method["card"]["amount_q"], 2000)

    def test_refund_nets_out_of_the_method_it_returned(self) -> None:
        """Estorno: o payman já liquida o intent; a linha ``refund`` do livro não conta em dobro."""
        shift = self._open_shift()
        sale = self._sale("POS-X-REF", shift=shift, tenders=[("cash", 3000)])
        intent = PaymentIntent.objects.get(order_ref="POS-X-REF")
        PaymentTransaction.objects.create(intent=intent, type=PaymentTransaction.Type.REFUND, amount_q=3000)
        cash.record(
            Entry.Kind.REFUND, shift=shift, operator=self.operator, amount_q=-3000,
            order_ref="POS-X-REF", payment_ref=intent.ref, parent=sale,
        )

        x = self.client.get(REPORT_URL).json()["report"]["x_reading"]

        by_method = {row["method"]: row for row in x["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 0)
        self.assertEqual(x["sales_total_q"], 0)

    def test_sale_without_intent_counts_only_its_cash_effect(self) -> None:
        """Linha sem intent resolvível (dado antigo, seed): o que o livro sabe sozinho é o dinheiro."""
        shift = self._open_shift()
        cash.record(Entry.Kind.SALE, shift=shift, operator=self.operator, amount_q=1500, order_ref="POS-LEGACY")

        x = self.client.get(REPORT_URL).json()["report"]["x_reading"]

        self.assertEqual(x["sales_count"], 1)
        by_method = {row["method"]: row for row in x["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 1500)

    def test_x_reading_never_exposes_expected_drawer_amount(self) -> None:
        """BLIND COUNT: nenhuma chave de esperado/variância na resposta."""
        shift = self._open_shift(opening="100,00")
        self._sale("POS-X-BLIND", shift=shift, tenders=[("cash", 4000)])

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        raw = json.dumps(resp.json())
        self.assertNotIn("expected", raw)
        self.assertNotIn("difference", raw)
        self.assertNotIn("balance", raw)

    def test_x_reading_absent_without_open_shift(self) -> None:
        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        report = resp.json()["report"]
        self.assertFalse(report["has_open_shift"])
        self.assertIsNone(report["x_reading"])
        self.assertEqual(report["z_readings"], [])
        self.assertEqual(report["day_totals"]["shifts_count"], 0)

    def test_x_reading_ignores_sales_of_another_DRAWER(self) -> None:
        """A leitura X é da gaveta em que se está — o totem não entra no balcão.

        Com duas gavetas abertas, a leitura tem de dizer QUAL. Sem o
        ``terminal_ref`` a resolução cai no primeiro terminal por ``ref``, e
        ``pdv-2`` vem antes de ``pdv-main``: o balcão leria o caixa do outro.
        """
        other_operator = get_user_model().objects.create_user(username="outro-caixa", password="x", is_staff=True)
        other_terminal = Terminal.objects.create(ref="pdv-2", label="PDV 2", channel_ref=self.terminal.channel_ref)
        other_shift = pos_service.open_cash_shift(operator=other_operator, terminal_ref=other_terminal.ref)
        shift = self._open_shift()
        self._sale("POS-OTHER-SHIFT", shift=other_shift, tenders=[("cash", 9900)], operator=other_operator)

        resp = self.client.get(REPORT_URL, {"terminal_ref": self.terminal.ref})

        x = resp.json()["report"]["x_reading"]
        self.assertEqual(x["shift_id"], shift.pk)
        self.assertEqual(x["sales_count"], 0)
        self.assertEqual(x["sales_by_method"], [])

        # E a leitura da OUTRA gaveta traz a venda dela — mesma requisição, ref
        # diferente. Sem isto, "ignora a outra" poderia estar apenas quebrado.
        outro = self.client.get(REPORT_URL, {"terminal_ref": other_terminal.ref}).json()["report"]["x_reading"]
        self.assertEqual(outro["shift_id"], other_shift.pk)
        self.assertEqual(outro["sales_count"], 1)

    # ── leituras Z (turnos fechados) + histórico ───────────────────────

    def test_z_readings_list_closed_shifts_with_counted_and_totals(self) -> None:
        shift = self._open_shift(opening="50,00")
        pos_service.register_cash_movement(
            operator=self.operator, movement_type="sangria", amount_raw="15,00", reason="banco",
            manager_approval=self.manager_approval,
        )
        self._sale("POS-Z-CASH", shift=shift, tenders=[("cash", 3000)])
        self._sale("POS-Z-CARD", shift=shift, tenders=[("card", 4500)])
        pos_service.close_cash_shift(actor_user=self.gerente, closing_amount_raw="63,00", notes="ok")

        resp = self.client.get(REPORT_URL)

        self.assertEqual(resp.status_code, 200)
        report = resp.json()["report"]
        self.assertFalse(report["has_open_shift"])
        self.assertTrue(report["has_closed_shifts"])
        self.assertEqual(len(report["z_readings"]), 1)
        z = report["z_readings"][0]
        self.assertEqual(z["status"], "closed")
        self.assertEqual(z["operator"], "caixa")
        self.assertEqual(z["opening_amount_q"], 5000)
        self.assertEqual(z["counted_amount_q"], 6300)
        self.assertEqual(z["sales_count"], 2)
        self.assertEqual(z["sales_total_q"], 7500)
        self.assertEqual(z["movements_out_q"], 1500)
        self.assertEqual(z["notes"], "ok")
        by_method = {row["method"]: row for row in z["sales_by_method"]}
        self.assertEqual(by_method["cash"]["amount_q"], 3000)
        self.assertEqual(by_method["card"]["amount_q"], 4500)

        totals = report["day_totals"]
        self.assertEqual(totals["shifts_count"], 1)
        self.assertEqual(totals["sales_count"], 2)
        self.assertEqual(totals["sales_total_q"], 7500)
        self.assertEqual(totals["counted_total_q"], 6300)

    def test_z_reading_never_exposes_expected_nor_variance(self) -> None:
        """O livro PROVA esperado/diferença; o PDV não os serve."""
        shift = self._open_shift(opening="10,00")
        self._sale("POS-Z-BLIND", shift=shift, tenders=[("cash", 2000)])
        pos_service.close_cash_shift(actor_user=self.gerente, closing_amount_raw="25,00")
        self.assertEqual(cash.expected_before_count(shift), 3000)  # o livro sabe…
        self.assertEqual(cash.difference(shift), -500)

        resp = self.client.get(REPORT_URL)

        raw = json.dumps(resp.json())  # …mas a resposta não carrega.
        self.assertNotIn("expected", raw)
        self.assertNotIn("difference", raw)
        self.assertNotIn("balance", raw)
        z = resp.json()["report"]["z_readings"][0]
        self.assertEqual(z["counted_amount_q"], 2500)
