"""Contexto do dia: feriado e clima entram por injeção, e só quando existem.

A regra que governa tudo aqui: **sem dado, nenhuma afirmação**. Um dia sem
clima carregado não é um dia de temperatura zero, e um período sem calendário
não é um período sem feriados — é um período sobre o qual não sabemos nada. Por
isso a dimensão nem aparece na gramática enquanto o dado não chega.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import DayContext
from shopman.backstage.projections.bi_explore import (
    ExploreError,
    available_context_dimensions,
    build_bi_explore,
    metric_options,
)

pytestmark = pytest.mark.django_db


def _write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _sold_on(day: date, *, qty: int, ref: str) -> None:
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="completed", total_q=qty * 100
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku="PAO", name="Pão", qty=qty,
        unit_price_q=100, line_total_q=qty * 100,
    )
    tz = timezone.get_current_timezone()
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.datetime(day.year, day.month, day.day, 10, tzinfo=tz)
    )


class TestHolidayImport:
    def test_json_calendar_marks_holiday_eve_and_return(self, tmp_path):
        """O que muda o movimento de uma padaria: o dia antes enche, o depois esvazia."""
        calendar = json.dumps([
            {"date": "2026-12-25", "name": "Natal", "scope": "national"},
        ])
        call_command("import_holidays", file=_write(tmp_path, "c.json", calendar))

        natal = DayContext.objects.get(date=date(2026, 12, 25))
        vespera = DayContext.objects.get(date=date(2026, 12, 24))
        volta = DayContext.objects.get(date=date(2026, 12, 26))

        assert natal.day_kind == "holiday"
        assert natal.holiday_scope == "national"
        assert vespera.day_kind == "eve:natal"
        assert vespera.eve_of == "Natal"
        assert volta.day_kind == "post_special"
        assert DayContext.objects.get(date=date(2026, 3, 10)).day_kind == "regular"

    def test_data_comercial_tem_identidade_propria(self, tmp_path):
        """Dia das mães compara com dias das mães, não com "data comercial"."""
        calendar = json.dumps([
            {"date": "2026-05-10", "name": "Dia das Mães", "kind": "comercial"},
            {"date": "2026-06-12", "name": "Dia dos Namorados", "kind": "comercial"},
        ])
        call_command("import_holidays", file=_write(tmp_path, "c.json", calendar))

        maes = DayContext.objects.get(date=date(2026, 5, 10))
        namorados = DayContext.objects.get(date=date(2026, 6, 12))

        assert maes.day_kind == "commercial:dia das mães"
        assert maes.day_kind != namorados.day_kind
        assert maes.day_kind_label == "Dia das Mães"
        # Data comercial não fecha a loja: não é feriado.
        assert not maes.is_holiday

    def test_vespera_sabe_de_que_data_ela_e_vespera(self, tmp_path):
        """Numa casa fechada no domingo, o dia das mães acontece no sábado.

        Por isso a véspera não pode ser um balde genérico: o sábado do dia das
        mães e o sábado antes de um feriado qualquer vendem coisas diferentes.
        """
        calendar = json.dumps([
            {"date": "2026-05-10", "name": "Dia das Mães", "kind": "comercial"},
            {"date": "2026-04-21", "name": "Tiradentes", "scope": "national"},
        ])
        call_command("import_holidays", file=_write(tmp_path, "c.json", calendar))

        sabado = DayContext.objects.get(date=date(2026, 5, 9))
        vespera_feriado = DayContext.objects.get(date=date(2026, 4, 20))

        assert sabado.eve_of == "Dia das Mães"
        assert sabado.day_kind == "eve:dia das mães"
        assert sabado.day_kind_label == "Dia das Mães (véspera)"
        assert sabado.occasion_name == "Dia das Mães"
        assert sabado.occasion_is_eve
        # E não se confunde com a véspera de outra data.
        assert vespera_feriado.day_kind != sabado.day_kind

    def test_um_dia_pode_ser_feriado_e_data_comercial(self, tmp_path):
        """O Natal é os dois, e perder um dos lados perderia uma pergunta."""
        calendar = json.dumps([
            {"date": "2026-12-25", "name": "Natal", "scope": "national"},
            {"date": "2026-12-25", "name": "Natal", "kind": "comercial"},
        ])
        call_command("import_holidays", file=_write(tmp_path, "c.json", calendar))

        natal = DayContext.objects.get(date=date(2026, 12, 25))

        assert natal.is_holiday
        assert natal.holiday_scope == "national"
        assert natal.commercial_name == "Natal"
        assert natal.day_kind == "commercial:natal"

    def test_tipo_desconhecido_diz_o_que_existe(self, tmp_path):
        calendar = json.dumps([{"date": "2026-05-10", "name": "X", "kind": "promoção"}])

        with pytest.raises(CommandError, match="feriado.*comercial"):
            call_command("import_holidays", file=_write(tmp_path, "c.json", calendar))

    def test_data_comercial_nao_tem_abrangencia(self, tmp_path):
        """Abrangência é do feriado, que define quem fecha."""
        calendar = json.dumps([
            {"date": "2026-05-10", "name": "Dia das Mães", "kind": "comercial",
             "scope": "national"},
        ])

        with pytest.raises(CommandError, match="abrangência"):
            call_command("import_holidays", file=_write(tmp_path, "c.json", calendar))

    def test_csv_is_accepted_too(self, tmp_path):
        csv_text = "date,name,scope\n2026-01-01,Confraternização,national\n"
        call_command("import_holidays", file=_write(tmp_path, "c.csv", csv_text))

        assert DayContext.objects.get(date=date(2026, 1, 1)).is_holiday

    def test_reloading_corrects_without_duplicating(self, tmp_path):
        first = json.dumps([{"date": "2026-07-09", "name": "Errado"}])
        call_command("import_holidays", file=_write(tmp_path, "a.json", first))
        second = json.dumps([{"date": "2026-07-09", "name": "Revolução de 32", "scope": "state"}])
        call_command("import_holidays", file=_write(tmp_path, "b.json", second))

        rows = DayContext.objects.filter(date=date(2026, 7, 9))
        assert rows.count() == 1
        assert rows.first().holiday_name == "Revolução de 32"

    def test_holiday_removed_from_the_file_leaves_the_calendar(self, tmp_path):
        """O arquivo é a verdade do ano: tirar de lá tira do banco."""
        call_command("import_holidays", file=_write(
            tmp_path, "a.json", json.dumps([{"date": "2026-05-01", "name": "Trabalho"}])
        ))
        call_command("import_holidays", file=_write(
            tmp_path, "b.json", json.dumps([{"date": "2026-09-07", "name": "Independência"}])
        ))

        assert not DayContext.objects.get(date=date(2026, 5, 1)).is_holiday
        assert DayContext.objects.get(date=date(2026, 9, 7)).is_holiday

    def test_bad_scope_names_the_line_and_the_options(self, tmp_path):
        bad = json.dumps([{"date": "2026-01-01", "name": "X", "scope": "planetario"}])
        with pytest.raises(CommandError) as exc:
            call_command("import_holidays", file=_write(tmp_path, "c.json", bad))

        assert "planetario" in str(exc.value)
        assert "national" in str(exc.value)

    def test_dry_run_writes_nothing(self, tmp_path):
        calendar = json.dumps([{"date": "2026-12-25", "name": "Natal"}])
        call_command(
            "import_holidays", file=_write(tmp_path, "c.json", calendar), dry_run=True
        )

        assert not DayContext.objects.exists()


class TestWeatherImport:
    def test_csv_with_series_headers_is_understood(self, tmp_path):
        """Cabeçalho de arquivo de série histórica entra sem reescrita manual."""
        csv_text = (
            "date,temperature_2m_min,temperature_2m_max,temperature_2m_mean,precipitation_sum\n"
            "2026-08-14,12.5,24.0,18.2,0\n"
            "2026-08-15,14.0,31.5,22.0,12.4\n"
        )
        call_command("import_weather", file=_write(tmp_path, "w.csv", csv_text))

        quente = DayContext.objects.get(date=date(2026, 8, 15))
        assert quente.temp_max_c == Decimal("31.5")
        assert quente.rain_mm == Decimal("12.4")
        assert quente.has_weather is True

    def test_empty_cell_is_absence_not_zero(self, tmp_path):
        csv_text = "date,temp_max,rain_mm\n2026-08-14,,\n"
        call_command("import_weather", file=_write(tmp_path, "w.csv", csv_text))

        row = DayContext.objects.get(date=date(2026, 8, 14))
        assert row.temp_max_c is None
        assert row.rain_mm is None
        assert row.has_weather is False

    def test_weather_and_holidays_coexist_on_the_same_day(self, tmp_path):
        call_command("import_holidays", file=_write(
            tmp_path, "c.json", json.dumps([{"date": "2026-12-25", "name": "Natal"}])
        ))
        call_command("import_weather", file=_write(
            tmp_path, "w.csv", "date,temp_max\n2026-12-25,33.0\n"
        ))

        row = DayContext.objects.get(date=date(2026, 12, 25))
        assert row.is_holiday and row.has_weather
        assert set(row.sources) == {"holiday", "weather"}


class TestGrammarOnlyOffersWhatItKnows:
    def test_without_data_the_dimensions_do_not_exist(self):
        assert available_context_dimensions() == ()
        revenue = next(m for m in metric_options() if m.key == "revenue")
        assert "temperature" not in revenue.dimensions
        assert "day_kind" not in revenue.dimensions

    def test_asking_for_a_dimension_without_data_says_what_to_load(self):
        with pytest.raises(ExploreError) as exc:
            build_bi_explore(metric="revenue", by="temperature")

        assert "import_weather" in str(exc.value)

    def test_loading_weather_makes_the_dimension_appear(self, tmp_path):
        call_command("import_weather", file=_write(
            tmp_path, "w.csv", "date,temp_max\n2026-08-14,24.0\n"
        ))

        assert "temperature" in available_context_dimensions()
        revenue = next(m for m in metric_options() if m.key == "revenue")
        assert "temperature" in revenue.dimensions
        # Produção não ganha a dimensão: a fornada não é função do dia do cliente.
        oven = next(m for m in metric_options() if m.key == "oven_minutes")
        assert "temperature" not in oven.dimensions

    def test_loading_the_calendar_makes_holiday_appear(self, tmp_path):
        call_command("import_holidays", file=_write(
            tmp_path, "c.json", json.dumps([{"date": "2026-12-25", "name": "Natal"}])
        ))

        assert "day_kind" in available_context_dimensions()


class TestReadingByContext:
    def test_revenue_by_temperature_bucket(self, tmp_path):
        today = timezone.localdate()
        cold, hot = today - timedelta(days=2), today - timedelta(days=1)
        _sold_on(cold, qty=10, ref="FRIO")
        _sold_on(hot, qty=40, ref="CALOR")
        call_command("import_weather", file=_write(
            tmp_path, "w.csv",
            f"date,temp_max\n{cold.isoformat()},16.0\n{hot.isoformat()},32.0\n",
        ))

        report = build_bi_explore(
            metric="revenue", by="temperature",
            date_from=today - timedelta(days=5), date_to=today,
        )

        assert [(row.label, row.value) for row in report.rows] == [
            ("15 a 19 °C", 1000.0),
            ("30 a 34 °C", 4000.0),
        ]

    def test_days_without_weather_stay_out_instead_of_becoming_a_bucket(self, tmp_path):
        today = timezone.localdate()
        known, unknown = today - timedelta(days=2), today - timedelta(days=1)
        _sold_on(known, qty=10, ref="SABIDO")
        _sold_on(unknown, qty=99, ref="DESCONHECIDO")
        call_command("import_weather", file=_write(
            tmp_path, "w.csv", f"date,temp_max\n{known.isoformat()},16.0\n",
        ))

        report = build_bi_explore(
            metric="revenue", by="temperature",
            date_from=today - timedelta(days=5), date_to=today,
        )

        assert [row.value for row in report.rows] == [1000.0]

    def test_revenue_by_day_kind(self, tmp_path):
        today = timezone.localdate()
        eve = today - timedelta(days=2)
        holiday = today - timedelta(days=1)
        _sold_on(eve, qty=50, ref="VESPERA")
        _sold_on(holiday, qty=5, ref="FERIADO")
        call_command("import_holidays", file=_write(
            tmp_path, "c.json",
            json.dumps([{"date": holiday.isoformat(), "name": "Feriado de teste"}]),
        ))

        report = build_bi_explore(
            metric="revenue", by="day_kind",
            date_from=today - timedelta(days=5), date_to=today,
        )
        by_label = {row.label: row.value for row in report.rows}

        # A véspera diz de QUE data ela é véspera: é nela que a padaria vende,
        # e "véspera do Natal" não é "véspera de um feriado qualquer".
        assert by_label["Feriado de teste (véspera)"] == 5000.0
        assert by_label["Feriado"] == 500.0
