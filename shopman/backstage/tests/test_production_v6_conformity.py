"""Conformidade V6 da Produção com a v4 (auditoria pdv-prod-compras, ids R*).

O dado que as telas da v4 pedem e que o quadro não trazia: a hora do compromisso
no chip das encomendas (R05), a hora do plano (R06), a unidade da linha (R07), a
ocasião e o clima do dia planejado (R04), o desfecho de cada dia da amostra no
"Por quê" (R09), o nome do forno do lote (R18) e o QR do lote na etiqueta de
preparo (R19).
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.craftsman.services.queries import Suggestion
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.models import DayContext
from shopman.backstage.projections.production import (
    _build_suggestion,
    _order_due_time,
    _production_day_context,
    build_production_board,
)
from shopman.backstage.services.receipt_escpos import lot_label_payload, production_label_run

pytestmark = pytest.mark.django_db


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(ref="croissant", name="Croissant", output_sku="CRO", batch_size=1)


class TestDayContext:
    def test_previsao_para_o_dia_planejado(self):
        day = timezone.localdate() + timedelta(days=1)
        DayContext.objects.create(
            date=day, has_calendar=True, temp_max_c=Decimal("23.6"), rain_mm=Decimal("0")
        )
        context = _production_day_context(day)
        assert context is not None
        assert context.occasion.endswith("comum, sem feriado")
        assert (context.weather, context.weather_kind) == ("24 °C e sol", "forecast")

    def test_vespera_e_chuva_medida_no_passado(self):
        day = timezone.localdate() - timedelta(days=3)
        DayContext.objects.create(
            date=day, has_calendar=True, eve_of="Dia das Mães", temp_max_c=Decimal("18.2"), rain_mm=Decimal("6")
        )
        context = _production_day_context(day)
        assert "véspera de Dia das Mães" in context.occasion
        assert (context.weather, context.weather_kind) == ("18 °C e chuva", "measured")

    def test_sem_dado_nenhuma_afirmacao(self):
        assert _production_day_context(timezone.localdate() + timedelta(days=9)) is None
        day = timezone.localdate() + timedelta(days=10)
        DayContext.objects.create(date=day)  # sem calendário e sem clima
        assert _production_day_context(day) is None

    def test_o_quadro_leva_o_contexto(self, recipe):
        day = timezone.localdate() + timedelta(days=1)
        DayContext.objects.create(date=day, has_calendar=True, temp_max_c=Decimal("24"))
        board = build_production_board(selected_date=day)
        assert board.day_context is not None
        assert board.day_context.weather == "24 °C"


class TestRecentDays:
    def test_ultimos_quatro_dias_com_o_desfecho(self, recipe):
        days = [
            {"date": date(2026, 9, 5), "sold": Decimal("40"), "wasted": Decimal("0"), "soldout_at": time(10, 40)},
            {"date": date(2026, 8, 29), "sold": Decimal("40"), "wasted": Decimal("0"), "soldout_at": None},
            {"date": date(2026, 9, 12), "sold": Decimal("40"), "wasted": Decimal("10"), "soldout_at": None},
            {"date": date(2026, 9, 19), "sold": Decimal("40"), "wasted": Decimal("1"), "soldout_at": None},
            {"date": date(2026, 9, 26), "sold": Decimal("40"), "wasted": Decimal("0"), "soldout_at": time(11, 5)},
        ]
        suggestion = Suggestion(
            recipe=recipe,
            quantity=Decimal("52"),
            basis={"avg_demand": Decimal("44"), "committed": Decimal("6"), "days": tuple(days)},
        )
        projection = _build_suggestion(suggestion)
        assert [(d.date_display, d.outcome, d.soldout_at) for d in projection.recent_days] == [
            ("05/09", "soldout", "10:40"),
            ("12/09", "leftover", ""),
            ("19/09", "ok", ""),
            ("26/09", "soldout", "11:05"),
        ]

    def test_o_core_entrega_os_dias_da_amostra(self):
        from shopman.craftsman.services import queries

        source = open(queries.__file__).read()
        assert '"days": tuple(' in source


class TestBoardFacts:
    def test_unidade_hora_do_plano_e_nome_do_posto(self, recipe):
        Position.objects.create(ref="forno-2", name="Forno 2", kind=PositionKind.PHYSICAL)
        from django.core.cache import cache

        cache.delete("production:position_names")
        wo = WorkOrder.objects.create(
            recipe=recipe,
            output_sku="CRO",
            quantity=Decimal("52"),
            target_date=timezone.localdate(),
            position_ref="forno-2",
        )
        board = build_production_board(selected_date=timezone.localdate())
        card = next(card for card in board.work_orders if card.pk == wo.pk)
        assert card.position_name == "Forno 2"
        assert card.created_at_time == timezone.localtime(wo.created_at).strftime("%H:%M")
        row = next(row for row in board.matrix_rows if row.output_sku == "CRO")
        assert row.output_unit == ""  # ficha sem unidade declarada: a tela cai em peça

    def test_unidade_da_ficha_chega_na_linha(self):
        base = Recipe.objects.create(
            ref="massa", name="Massa", output_sku="MASSA", batch_size=1, meta={"output_unit": "g"}
        )
        WorkOrder.objects.create(
            recipe=base, output_sku="MASSA", quantity=Decimal("1230.77"), target_date=timezone.localdate()
        )
        board = build_production_board(selected_date=timezone.localdate())
        row = next(row for row in board.matrix_rows if row.output_sku == "MASSA")
        assert row.output_unit == "g"

    def test_hora_do_compromisso_pela_janela_combinada(self):
        class FakeOrder:
            ref = "P-1"
            data = {"delivery_time_slot": "08:30-09:00"}

        assert _order_due_time(FakeOrder()) == "08:30"
        FakeOrder.data = {}
        assert _order_due_time(FakeOrder()) == ""


class TestLotLabelQr:
    def test_etiqueta_de_preparo_leva_o_qr_do_lote_e_a_cega_nao(self):
        ticket = {
            "name": "Croissant",
            "output_sku": "CRO",
            "made_display": "04/10",
            "expiry_display": "06/10",
            "ingredients": [],
        }
        explicit = production_label_run({"mode": "explicit", "tickets": [ticket]})
        assert lot_label_payload("CRO").encode() in explicit
        blind = production_label_run(
            {"mode": "blind", "tickets": [{"blind_code": "K7", "made_display": "04/10", "ingredients": []}]}
        )
        assert b"shopman-lote:" not in blind
