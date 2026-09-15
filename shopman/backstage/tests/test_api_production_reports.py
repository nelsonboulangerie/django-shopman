"""Headless production reports API (api/v1/backstage/production/reports|management|weighing/blind-map).

Covers the manager-persona REST surface that the ``/reports`` page of the
production-nuxt app (``prod.``) consumes: report rows (history, operator
productivity, recipe waste) with CSV export, the day-level management KPIs
(average yield, capacity, late orders) and the blind-code ↔ prep map. Gated by
fine-grained report and blind-map permissions — the coarse floor gate
(``backstage.operate_production``) does NOT open these endpoints, so the kiosk
screens stay blind by design.

Reuses ``build_production_reports``/``build_production_dashboard``/
``export_reports_csv``; no report logic is duplicated here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrderEvent
from shopman.stockman import Position

from shopman.backstage.models import DayClosing


def _perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename=codename,
    )


@pytest.fixture
def floor_operator(db):
    """Operador de chão: só o gate grosso do kiosk — SEM relatórios."""
    user = User.objects.create_user("prod-floor", password="pw", is_staff=True)
    user.user_permissions.add(_perm("operate_production"))
    return user


@pytest.fixture
def manager(db):
    user = User.objects.create_user("prod-manager", password="pw", is_staff=True)
    user.user_permissions.add(
        _perm("view_production_reports"),
        _perm("reveal_production_blind_map"),
    )
    return user


@pytest.fixture
def report_data(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Relatórios")
    Position.objects.create(ref="forno", name="Forno", is_default=True)
    recipe = Recipe.objects.create(
        ref="report-api-pao",
        name="Pão de Relatório",
        output_sku="PAO-REL",
        batch_size=Decimal("10"),
        meta={"capacity_per_day": 100},
    )
    today = date.today()
    finished = craft.plan(recipe, 20, date=today, position_ref="forno", operator_ref="ana")
    craft.start(finished, quantity=20, position_ref="forno", operator_ref="ana", expected_rev=0)
    craft.finish(finished, finished=18, actor="ana")
    planned = craft.plan(recipe, 30, date=today, position_ref="forno", operator_ref="bia")
    return {"today": today, "recipe": recipe, "finished": finished, "planned": planned}


# ── Gate (perm fina ≠ gate grosso do chão) ───────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "api-backstage-production-reports",
        "api-backstage-production-management",
        "api-backstage-production-blind-map",
    ],
)
def test_floor_gate_does_not_open_manager_endpoints(client, floor_operator, url_name):
    client.force_login(floor_operator)
    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url_name",
    [
        "api-backstage-production-reports",
        "api-backstage-production-management",
        "api-backstage-production-blind-map",
    ],
)
def test_manager_perm_opens_endpoints(client, manager, report_data, url_name):
    client.force_login(manager)
    assert client.get(reverse(url_name)).status_code == 200


@pytest.mark.django_db
def test_report_reader_cannot_reveal_blind_map_without_separate_capability(
    client,
    report_data,
):
    reader = User.objects.create_user("reports-without-map", password="pw", is_staff=True)
    reader.user_permissions.add(_perm("view_production_reports"))
    client.force_login(reader)

    assert client.get(reverse("api-backstage-production-reports")).status_code == 200
    assert client.get(reverse("api-backstage-production-blind-map")).status_code == 403


# ── Reports ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_reports_payload_shape(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {"date_from": report_data["today"].isoformat(), "date_to": report_data["today"].isoformat()},
    )
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert reports["filters"]["date_from"] == report_data["today"].isoformat()
    assert reports["filters"]["report_kind"] == "history"

    refs = {row["ref"] for row in reports["history_rows"]}
    assert {report_data["finished"].ref, report_data["planned"].ref} <= refs
    finished_row = next(row for row in reports["history_rows"] if row["ref"] == report_data["finished"].ref)
    assert finished_row["qty_planned"] == "20"
    assert finished_row["qty_finished"] == "18"
    assert finished_row["qty_loss"] == "2"
    assert finished_row["yield_rate"] == "90%"

    assert [row["operator_ref"] for row in reports["operator_rows"]] == ["ana"]
    assert [row["recipe_ref"] for row in reports["waste_rows"]] == ["report-api-pao"]
    assert {recipe["ref"] for recipe in reports["available_recipes"]} == {"report-api-pao"}
    assert {position["ref"] for position in reports["available_positions"]} == {"forno"}

    productivity = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
            "report_kind": "operator_productivity",
            "selected_only": True,
        },
    ).json()["reports"]
    assert [row["operator_ref"] for row in productivity["operator_rows"]] == ["ana"]
    assert productivity["history_rows"] == []


@pytest.mark.django_db
def test_reports_filters_reduce_history(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
            "operator_ref": "bia",
        },
    )
    rows = response.json()["reports"]["history_rows"]
    assert [row["ref"] for row in rows] == [report_data["planned"].ref]


@pytest.mark.django_db
def test_reports_paginate_with_filter_bound_cursor_and_server_sort(client, manager, report_data):
    client.force_login(manager)
    url = reverse("api-backstage-production-reports")
    query = {
        "date_from": report_data["today"].isoformat(),
        "date_to": report_data["today"].isoformat(),
        "report_kind": "history",
        "selected_only": True,
        "sort": "quantity_desc",
        "page_size": 1,
    }

    first = client.get(url, query)
    assert first.status_code == 200
    payload = first.json()
    assert payload["pagination"]["total"] == 2
    assert payload["reports"]["history_rows"][0]["ref"] == report_data["planned"].ref
    assert payload["reports"]["operator_rows"] == []
    cursor = payload["pagination"]["next_cursor"]

    with CaptureQueriesContext(connection) as captured:
        second = client.get(url, {**query, "cursor": cursor})
    assert second.status_code == 200
    assert second.json()["reports"]["history_rows"][0]["ref"] == report_data["finished"].ref
    assert second.json()["pagination"]["previous_cursor"]
    assert len(captured) <= 20
    assert any(
        'FROM "crafting_work_order"' in query["sql"]
        and "LIMIT 1 OFFSET 1" in query["sql"].upper()
        for query in captured.captured_queries
    )

    tampered = client.get(url, {**query, "cursor": f"{cursor}x"})
    assert tampered.status_code == 400
    mismatched = client.get(url, {**query, "operator_ref": "ana", "cursor": cursor})
    assert mismatched.status_code == 400

    craft.adjust(report_data["planned"], Decimal("35"), reason="revisão de página")
    stale = client.get(url, {**query, "cursor": cursor})
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "stale_report_cursor",
        "recovery": "apply_filters",
    }


@pytest.mark.django_db
def test_history_page_does_not_build_unselected_aggregates(client, manager, report_data, monkeypatch):
    from shopman.backstage.projections import production as production_projection

    original_row_builder = production_projection._work_order_report_row
    materialized = []

    def record_row(work_order):
        materialized.append(work_order.pk)
        return original_row_builder(work_order)

    monkeypatch.setattr(production_projection, "_work_order_report_row", record_row)
    monkeypatch.setattr(
        production_projection,
        "_operator_productivity_rows",
        lambda rows: pytest.fail("history must not aggregate operator rows"),
    )
    monkeypatch.setattr(
        production_projection,
        "_recipe_waste_rows",
        lambda rows: pytest.fail("history must not aggregate waste rows"),
    )
    client.force_login(manager)

    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
            "page_size": 1,
            "selected_only": True,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["reports"]["history_rows"]) == 1
    assert len(materialized) == 1


@pytest.mark.django_db
def test_reports_reject_a_dataset_that_changes_while_page_is_built(client, manager, report_data, monkeypatch):
    from shopman.backstage.projections import production as production_projection

    revisions = iter(("before", "after"))
    monkeypatch.setattr(production_projection, "_report_dataset_revision", lambda qs, kind: next(revisions))
    client.force_login(manager)

    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
            "selected_only": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_report_cursor"


@pytest.mark.django_db
def test_quality_page_and_csv_use_latest_correction_and_invalidate_older_cursor(
    client,
    manager,
    report_data,
):
    work_order = report_data["finished"]
    first_correction = [
        {
            "quantity": "10",
            "quality_grade_ref": "fair",
            "quality_defect_ref": "misshapen",
            "loss": False,
            "batch_ref": "",
        },
        {
            "quantity": "8",
            "quality_grade_ref": "standard",
            "quality_defect_ref": "",
            "loss": False,
            "batch_ref": "",
        },
    ]
    WorkOrderEvent.objects.create(
        work_order=work_order,
        seq=work_order.events.order_by("-seq").values_list("seq", flat=True).first() + 1,
        kind=WorkOrderEvent.Kind.QUALITY_CORRECTED,
        actor="manager:test",
        payload={"schema_version": 1, "after_partition": first_correction},
    )
    client.force_login(manager)
    url = reverse("api-backstage-production-reports")
    query = {
        "date_from": report_data["today"].isoformat(),
        "date_to": report_data["today"].isoformat(),
        "report_kind": "quality",
        "selected_only": True,
        "page_size": 1,
    }

    first = client.get(url, query)
    assert first.status_code == 200
    assert first.json()["pagination"]["total"] == 2
    assert first.json()["reports"]["quality_rows"] == [
        {
            "recipe_ref": "report-api-pao",
            "recipe_name": "Pão de Relatório",
            "grade_ref": "fair",
            "grade_label": "Razoável",
            "defect_ref": "misshapen",
            "defect_label": "Deformado",
            "quantity": "10",
            "share": "55%",
        }
    ]
    cursor = first.json()["pagination"]["next_cursor"]

    csv_response = client.get(url, {**query, "format": "csv"})
    csv_text = b"".join(csv_response.streaming_content).decode("utf-8-sig")
    assert "report-api-pao,Pão de Relatório,Razoável,Deformado,10,55%" in csv_text

    WorkOrderEvent.objects.create(
        work_order=work_order,
        seq=work_order.events.order_by("-seq").values_list("seq", flat=True).first() + 1,
        kind=WorkOrderEvent.Kind.QUALITY_CORRECTED,
        actor="manager:test",
        payload={
            "schema_version": 1,
            "after_partition": [
                {
                    "quantity": "18",
                    "quality_grade_ref": "minimal",
                    "quality_defect_ref": "underproofed",
                    "loss": False,
                    "batch_ref": "",
                }
            ],
        },
    )

    stale = client.get(url, {**query, "cursor": cursor})
    assert stale.status_code == 409
    fresh = client.get(url, query)
    assert fresh.json()["reports"]["quality_rows"][0]["grade_ref"] == "minimal"


@pytest.mark.django_db
def test_reports_reject_inverted_or_oversized_ranges(client, manager, report_data):
    client.force_login(manager)
    url = reverse("api-backstage-production-reports")

    inverted = client.get(
        url,
        {
            "date_from": report_data["today"].isoformat(),
            "date_to": date(2026, 1, 1).isoformat(),
        },
    )
    assert inverted.status_code == 400
    assert inverted.json()["error"]["code"] == "validation_error"
    assert inverted.json()["error"]["issues"][0]["field"] == "date_to"

    oversized = client.get(
        url,
        {"date_from": "2026-01-01", "date_to": "2026-09-08"},
    )
    assert oversized.status_code == 400
    assert oversized.json()["error"]["code"] == "validation_error"
    assert oversized.json()["error"]["issues"][0]["field"] == "date_to"


@pytest.mark.django_db
def test_reports_reject_unknown_filter(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {"date_from": report_data["today"].isoformat(), "surprise": "1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["issues"][0]["field"] == "surprise"


@pytest.mark.django_db
def test_reports_csv_download(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-reports"),
        {
            "format": "csv",
            "report_kind": "history",
            "date_from": report_data["today"].isoformat(),
            "date_to": report_data["today"].isoformat(),
        },
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    disposition = response["Content-Disposition"]
    assert disposition.startswith('attachment; filename="producao_history_')
    assert response.streaming
    text = b"".join(response.streaming_content).decode("utf-8-sig")
    assert "Qtd planejada" in text
    assert report_data["finished"].ref in text


@pytest.mark.django_db
def test_reports_csv_requires_manager_perm(client, floor_operator):
    client.force_login(floor_operator)
    response = client.get(reverse("api-backstage-production-reports"), {"format": "csv"})
    assert response.status_code == 403


# ── Management KPIs ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_management_returns_day_kpis(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-management"),
        {"date": report_data["today"].isoformat()},
    )
    assert response.status_code == 200
    management = response.json()["management"]
    assert management["selected_date"] == report_data["today"].isoformat()
    assert management["average_yield_rate"] == "90%"
    # planned 20 + 30 = 50 sobre capacity_per_day 100 → 50%
    assert management["capacity_percent"] == 50
    assert management["finished_orders"] == 1
    assert isinstance(management["late_orders"], list)


# ── Blind map (visão de gestor; o chão segue cego) ──────────────────────────


@pytest.mark.django_db
def test_blind_map_correlates_codes_to_preps(client, manager, report_data):
    client.force_login(manager)
    response = client.get(
        reverse("api-backstage-production-blind-map"),
        {"date": report_data["today"].isoformat()},
    )
    assert response.status_code == 200
    blind_map = response.json()["blind_map"]
    assert blind_map["selected_date"] == report_data["today"].isoformat()
    rows = blind_map["rows"]
    assert len(rows) == 1  # só a OP planejada segue aberta (a concluída não pesa mais)
    assert rows[0]["name"] == "Pão de Relatório"
    assert rows[0]["code"]
    assert set(rows[0]) == {"code", "name", "output_quantity_display"}
