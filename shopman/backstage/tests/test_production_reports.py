from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman import Position

from shopman.backstage.projections.production import build_production_reports
from shopman.backstage.services.production import export_reports_csv
from shopman.shop.models import Shop


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="report-cafe",
        name="Café especial",
        output_sku="CAFE-ESP",
        batch_size=Decimal("10"),
        meta={"capacity_per_day": 100},
    )


@pytest.fixture
def other_recipe(db):
    return Recipe.objects.create(
        ref="report-pao",
        name="Pão francês",
        output_sku="PAO-FRA",
        batch_size=Decimal("10"),
    )


@pytest.fixture
def report_data(db, recipe, other_recipe):
    Position.objects.create(ref="forno", name="Forno", is_default=True)
    Position.objects.create(ref="balcao", name="Balcão")
    today = date.today()
    planned = craft.plan(recipe, 20, date=today, position_ref="forno", operator_ref="ana")
    started = craft.plan(recipe, 30, date=today, position_ref="forno", operator_ref="bia")
    craft.start(started, quantity=30, position_ref="forno", operator_ref="bia", expected_rev=0)
    finished = craft.plan(recipe, 40, date=today, position_ref="forno", operator_ref="ana")
    craft.start(finished, quantity=40, position_ref="forno", operator_ref="ana", expected_rev=0)
    craft.finish(finished, finished=36, actor="ana")
    old = craft.plan(other_recipe, 10, date=today - timedelta(days=10), position_ref="balcao", operator_ref="caio")
    return {"today": today, "planned": planned, "started": started, "finished": finished, "old": old}


@pytest.mark.django_db
def test_history_report_returns_work_order_shape(report_data):
    report = build_production_reports({"date_from": report_data["today"], "date_to": report_data["today"]})

    assert len(report.history_rows) == 3
    row = next(row for row in report.history_rows if row.ref == report_data["finished"].ref)
    assert row.recipe_ref == "report-cafe"
    assert row.qty_planned == "40"
    assert row.qty_finished == "36"
    assert row.qty_loss == "4"
    assert row.yield_rate == "90%"


@pytest.mark.django_db
def test_operator_productivity_aggregates_finished_only(report_data):
    report = build_production_reports(
        {
            "date_from": report_data["today"],
            "date_to": report_data["today"],
            "report_kind": "operator_productivity",
        }
    )

    assert [row.operator_ref for row in report.operator_rows] == ["ana"]
    assert report.operator_rows[0].wo_count == 1
    assert report.operator_rows[0].qty_total == "36"


def test_report_averages_keep_constant_memory_and_exact_display():
    from shopman.backstage.projections.production import _OnlineAverage

    average = _OnlineAverage()
    for index in range(10_000):
        average.add(Decimal("0.9") if index % 2 else Decimal("0.8"))

    assert not hasattr(average, "__dict__")
    assert average.count == 10_000
    assert average.percent_display() == "85%"

    durations = _OnlineAverage()
    durations.add(10)
    durations.add(11)
    assert durations.integer_display() == "10"


@pytest.mark.django_db
def test_effective_quality_strict_mode_fails_closed_without_changing_fail_soft_default(
    report_data,
    monkeypatch,
):
    from shopman.craftsman.models import WorkOrderEvent

    from shopman.shop.services import quality as quality_service

    def unavailable(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(WorkOrderEvent.objects, "filter", unavailable)
    work_order = report_data["finished"]

    assert quality_service.effective_partitions([work_order]) == {work_order.pk: []}
    with pytest.raises(quality_service.EffectiveQualityPartitionError):
        quality_service.effective_partitions([work_order], strict=True)


@pytest.mark.django_db
def test_recipe_waste_returns_top_waste_rows(report_data):
    report = build_production_reports(
        {
            "date_from": report_data["today"],
            "date_to": report_data["today"],
            "report_kind": "recipe_waste",
        }
    )

    assert report.waste_rows[0].recipe_ref == "report-cafe"
    assert report.waste_rows[0].loss_total == "4"
    # Só a WO FINISHED entra: planejado 40 sobre capacity_per_day 100 × 1 dia.
    assert report.waste_rows[0].capacity_utilization == "40%"


@pytest.mark.django_db
def test_date_range_filter_excludes_old_work_orders(report_data):
    report = build_production_reports({"date_from": report_data["today"], "date_to": report_data["today"]})

    assert report_data["old"].ref not in [row.ref for row in report.history_rows]


@pytest.mark.django_db
def test_recipe_filter_reduces_history_set(report_data):
    report = build_production_reports(
        {
            "date_from": report_data["today"] - timedelta(days=20),
            "date_to": report_data["today"],
            "recipe_ref": "report-pao",
        }
    )

    assert [row.ref for row in report.history_rows] == [report_data["old"].ref]


@pytest.mark.django_db
def test_position_operator_and_status_filters(report_data):
    report = build_production_reports(
        {
            "date_from": report_data["today"],
            "date_to": report_data["today"],
            "position_ref": "forno",
            "operator_ref": "bia",
            "status": WorkOrder.Status.STARTED,
        }
    )

    assert [row.ref for row in report.history_rows] == [report_data["started"].ref]


@pytest.mark.django_db
def test_inverted_range_is_normalized(report_data):
    report = build_production_reports(
        {"date_from": report_data["today"], "date_to": report_data["today"] - timedelta(days=1)}
    )

    assert report.filters.date_from == report_data["today"] - timedelta(days=1)
    assert report.filters.date_to == report_data["today"]


@pytest.mark.django_db
def test_missing_recipe_filter_returns_empty(report_data):
    report = build_production_reports(
        {
            "date_from": report_data["today"],
            "date_to": report_data["today"],
            "recipe_ref": "missing",
        }
    )

    assert report.history_rows == ()


@pytest.mark.django_db
def test_csv_export_has_bom_pt_br_header_and_accents(report_data):
    data = export_reports_csv("history", {"date_from": report_data["today"], "date_to": report_data["today"]})

    assert data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    assert "Qtd planejada" in text
    assert "Café especial" in text
    assert report_data["today"].isoformat() in text


@pytest.mark.django_db
def test_csv_stream_emits_bom_and_header_before_querying_rows(report_data, django_assert_num_queries):
    from shopman.backstage.services.production import iter_reports_csv

    stream = iter_reports_csv(
        "history",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    )
    with django_assert_num_queries(0):
        assert next(stream) == "\ufeff"
        assert "Ref,Data,Receita" in next(stream)
    assert report_data["finished"].ref in "".join(stream)


@pytest.mark.django_db
def test_csv_stream_fails_if_dataset_revision_changes(report_data, monkeypatch):
    from shopman.backstage.projections import production as production_projection
    from shopman.backstage.services.production import (
        ProductionReportChangedDuringExport,
        prepare_reports_csv,
    )

    revisions = iter(("before", "after"))
    monkeypatch.setattr(
        production_projection,
        "_report_dataset_revision",
        lambda qs, kind: next(revisions),
    )
    with pytest.raises(ProductionReportChangedDuringExport):
        prepare_reports_csv(
            "history",
            {"date_from": report_data["today"], "date_to": report_data["today"]},
        )


@pytest.mark.django_db
def test_prepared_csv_spools_to_disk_and_enforces_row_limit(report_data, settings):
    from shopman.backstage.services.production import (
        ProductionReportExportLimitExceeded,
        prepare_reports_csv,
    )

    settings.SHOPMAN_PRODUCTION_REPORT_EXPORT_SPOOL_BYTES = 16
    prepared = prepare_reports_csv(
        "history",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    )
    try:
        assert prepared._rolled is True
        assert prepared.read().startswith(b"\xef\xbb\xbf")
    finally:
        prepared.close()

    settings.SHOPMAN_PRODUCTION_REPORT_EXPORT_MAX_ROWS = 1
    with pytest.raises(ProductionReportExportLimitExceeded) as caught:
        prepare_reports_csv(
            "history",
            {"date_from": report_data["today"], "date_to": report_data["today"]},
        )
    assert caught.value.limit == "rows"

    settings.SHOPMAN_PRODUCTION_REPORT_EXPORT_MAX_ROWS = 50_000
    settings.SHOPMAN_PRODUCTION_REPORT_EXPORT_MAX_BYTES = 8
    with pytest.raises(ProductionReportExportLimitExceeded) as caught:
        prepare_reports_csv(
            "history",
            {"date_from": report_data["today"], "date_to": report_data["today"]},
        )
    assert caught.value.limit == "bytes"


@pytest.mark.django_db
def test_csv_export_operator_productivity_header(report_data):
    text = export_reports_csv(
        "operator_productivity",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    ).decode("utf-8-sig")

    assert "Operador,Nome,Ordens concluídas,Qtd total,Rendimento médio" in text


@pytest.mark.django_db
def test_csv_export_quality_exports_the_quality_table(report_data):
    """O kind 'quality' exporta a partição do QC — antes caía no else e saía
    o HISTÓRICO com o nome de qualidade (a tabela errada, calada)."""
    text = export_reports_csv(
        "quality",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    ).decode("utf-8-sig")

    first_line = text.splitlines()[0]
    assert first_line == "Receita,Nome,Grau,Defeito,Qtd,% da receita"
    # A fornada finalizada do fixture (finish escalar) conta no grau padrão.
    assert "report-cafe" in text
    assert "OP" not in first_line  # nada da tabela de histórico


@pytest.mark.django_db
def test_csv_export_recipe_waste_header(report_data):
    text = export_reports_csv(
        "recipe_waste",
        {"date_from": report_data["today"], "date_to": report_data["today"]},
    ).decode("utf-8-sig")

    first_line = text.splitlines()[0]
    assert "Receita" in first_line
    assert "Perda" in first_line or "Loss" in first_line.lower()


# O console Admin de relatórios saiu (WP-ADM-7d): a superfície é o /reports do
# Produção sobre api/v1/backstage/production/reports/ (permission gate e CSV
# cobertos em test_api_production_reports.py). Ficam aqui os fallbacks de
# parsing de filtro, agora exercidos pela API headless.


@pytest.mark.django_db
def test_invalid_report_kind_is_rejected(client, report_data):
    Shop.objects.create(name="Loja")
    admin = User.objects.create_superuser("admin", "a@test.com", "pw")
    client.force_login(admin)

    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
            "report_kind": "; DROP TABLE",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert {issue["field"] for issue in response.json()["error"]["issues"]} == {"report_kind"}


@pytest.mark.django_db
def test_invalid_dates_are_rejected(client, report_data):
    Shop.objects.create(name="Loja")
    admin = User.objects.create_superuser("admin", "a@test.com", "pw")
    client.force_login(admin)

    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": "not-a-date",
            "date_to": "also-not-a-date",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert {issue["field"] for issue in response.json()["error"]["issues"]} == {
        "date_from",
        "date_to",
    }
