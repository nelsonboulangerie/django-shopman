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
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
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
    assert reports["waste_rows"][0]["recipe_ref"] == "report-api-pao"
    assert {recipe["ref"] for recipe in reports["available_recipes"]} == {"report-api-pao"}
    assert {position["ref"] for position in reports["available_positions"]} == {"forno"}


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
    text = response.content.decode("utf-8-sig")
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
