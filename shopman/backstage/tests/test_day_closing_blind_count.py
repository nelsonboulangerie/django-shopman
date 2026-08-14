from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.stockman import Position, Quant
from shopman.stockman.models import Batch, Move
from shopman.stockman.services.movements import StockMovements

from shopman.backstage.models import DayClosing


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _grant_closing_perm(user):
    ct = ContentType.objects.get_for_model(DayClosing)
    perm = Permission.objects.get(content_type=ct, codename="perform_closing")
    user.user_permissions.add(perm)


class DayClosingBlindCountTests(TestCase):
    """Contagem cega via a API headless do fechamento (antesala do PDV).

    A tela Admin/Unfold foi removida (ADMIN-ROLE-PLAN WP-ADM-3); a superfície é
    `pos-nuxt /session/closing` sobre `GET/POST /api/v1/backstage/closing/`. A
    cegueira visual (não exibir o disponível ao operador) é contrato da PÁGINA
    (vitest do pos-nuxt); aqui garantimos a semântica do registro: reported vs
    applied sem clamp silencioso, o destino da sobra decidido pelo LOTE (C4 —
    write-off, nunca mudança de posição) e o gate por permissão.
    """

    def setUp(self) -> None:
        _make_shop()
        User = get_user_model()
        self.staff = User.objects.create_user(username="closing", password="x", is_staff=True)
        _grant_closing_perm(self.staff)
        self.client.force_login(self.staff)

        self.today = timezone.localdate()
        self.loja = Position.objects.create(ref="loja", name="Loja", is_saleable=True)
        # Pão que aguenta o dia seguinte: shelf_life 1, lote vencendo AMANHÃ.
        self.keeper = Product.objects.create(
            sku="PAO-FICA", name="Pão que fica", shelf_life_days=1,
        )
        Batch.objects.create(
            sku=self.keeper.sku, ref="FICA-LOTE",
            expiry_date=self.today + timedelta(days=1),
        )
        StockMovements.receive(
            quantity=3, sku=self.keeper.sku, position=self.loja,
            batch="FICA-LOTE", reason="fornada de hoje",
        )
        # Pão do dia SEM lote: a validade implícita é o próprio dia.
        self.day_bread = Product.objects.create(
            sku="PAO-DO-DIA", name="Pão do dia", shelf_life_days=0,
        )
        StockMovements.receive(
            quantity=2, sku=self.day_bread.sku, position=self.loja,
            reason="fornada de hoje",
        )

    def test_closing_projection_classifies_by_lot(self) -> None:
        resp = self.client.get("/api/v1/backstage/closing/")

        self.assertEqual(resp.status_code, 200)
        closing = resp.json()["closing"]
        self.assertFalse(closing["already_closed"])
        by_sku = {it["sku"]: it for it in closing["items"]}

        keeper = by_sku[self.keeper.sku]
        self.assertEqual(keeper["classification"], "keep")
        self.assertEqual(keeper["qty_expiring"], 0)

        day = by_sku[self.day_bread.sku]
        self.assertEqual(day["classification"], "expired")
        self.assertEqual(day["qty_expiring"], 2)

    def test_closing_api_requires_perform_closing_permission(self) -> None:
        User = get_user_model()
        other = User.objects.create_user(username="no-perm", password="x", is_staff=True)
        self.client.force_login(other)

        resp = self.client.get("/api/v1/backstage/closing/")

        self.assertEqual(resp.status_code, 403)

    def test_closing_writes_off_by_lot_and_never_moves_the_rest(self) -> None:
        """C4: vencido vira WASTE carimbado; o que tem validade FICA no lugar."""
        resp = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.keeper.sku: "3", self.day_bread.sku: "5"}},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        closing = DayClosing.objects.get()
        rows = {row["sku"]: row for row in closing.data["items"]}

        # O pão com validade fica: nada baixado, nada movido.
        keeper_row = rows[self.keeper.sku]
        self.assertEqual(keeper_row["qty_kept"], 3)
        self.assertEqual(keeper_row["qty_expired"], 0)
        keeper_quant = Quant.objects.get(sku=self.keeper.sku, position=self.loja)
        self.assertEqual(keeper_quant.quantity, 3)

        # O pão do dia vence hoje: write-off SEM clamp silencioso no reporte.
        day_row = rows[self.day_bread.sku]
        self.assertEqual(day_row["qty_reported"], 5)
        self.assertEqual(day_row["qty_applied"], 2)
        self.assertEqual(day_row["qty_discrepancy"], 3)
        self.assertEqual(day_row["qty_expired"], 2)
        day_quant = Quant.objects.get(sku=self.day_bread.sku, position=self.loja)
        self.assertEqual(day_quant.quantity, 0)
        self.assertTrue(
            Move.objects.filter(
                quant=day_quant, reason=f"perda_vencido:{self.today}",
            ).exists()
        )

    def test_nonconforming_leftover_is_written_off_with_its_own_reason(self) -> None:
        """Lote marcado não vai para o dia seguinte — mesmo com validade."""
        Batch.objects.create(
            sku=self.keeper.sku, ref="MARCADO-LOTE",
            expiry_date=self.today + timedelta(days=1),
            nonconformity_reason="Assou demais", nonconformity_percent=20,
        )
        StockMovements.receive(
            quantity=2, sku=self.keeper.sku, position=self.loja,
            batch="MARCADO-LOTE", reason="sublote com desconto",
        )

        resp = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.keeper.sku: "5", self.day_bread.sku: "2"}},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        closing = DayClosing.objects.get()
        row = next(r for r in closing.data["items"] if r["sku"] == self.keeper.sku)
        self.assertEqual(row["qty_nonconforming"], 2)
        self.assertEqual(row["qty_kept"], 3)
        marked_quant = Quant.objects.get(sku=self.keeper.sku, batch="MARCADO-LOTE")
        self.assertEqual(marked_quant.quantity, 0)
        self.assertTrue(
            Move.objects.filter(
                quant=marked_quant, reason=f"perda_nao_conformidade:{self.today}",
            ).exists()
        )

    def test_closing_twice_returns_conflict(self) -> None:
        first = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.keeper.sku: "0", self.day_bread.sku: "0"}},
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/api/v1/backstage/closing/",
            {"quantities": {self.keeper.sku: "0", self.day_bread.sku: "0"}},
            content_type="application/json",
        )

        self.assertEqual(second.status_code, 409)
        self.assertEqual(DayClosing.objects.count(), 1)

    def test_admin_day_closing_route_is_gone(self) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("admin_console_day_closing")
