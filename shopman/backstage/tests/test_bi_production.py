"""B.I. de produção (ADR-021, BI-PLAN F3).

Cobre a perm fina ``backstage.view_bi``, a série diária (rendimento, perda e
mix comercial da qualidade via partição ADR-017), o tempo real de forno com
p50/p90 e a COBERTURA declarada (fornadas medidas ÷ fechadas).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman.models import Position

from shopman.backstage.models import DayClosing, OvenRun
from shopman.backstage.projections.bi_production import build_bi_production
from shopman.backstage.services.production import (
    apply_finish,
    apply_oven_arm,
    apply_oven_conclude,
)


def _view_bi_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename="view_bi",
    )


@pytest.fixture
def bi_viewer(db):
    user = User.objects.create_user("bi-viewer", password="pw", is_staff=True)
    user.user_permissions.add(_view_bi_perm())
    return user


@pytest.fixture
def position(db):
    return Position.objects.create(ref="forno", name="Forno", kind="oven", is_default=True)


@pytest.fixture
def recipe(db, position):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja B.I.")
    return Recipe.objects.create(
        ref="bi-prod-v1",
        name="Pão do B.I.",
        output_sku="BI-PROD",
        batch_size=Decimal("10"),
    )


def _finished_wo(recipe, *, partition=None, quantity="40"):
    wo = craft.plan(recipe, Decimal(quantity), date=date.today(), position_ref="forno")
    craft.start(wo, quantity=Decimal(quantity), position_ref="forno", expected_rev=0)
    apply_finish(
        work_order_id=wo.pk,
        quantity=quantity,
        actor="test",
        partition=partition,
    )
    wo.refresh_from_db()
    return wo


# ── Gate ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_bi_production_requires_view_bi(client, recipe):
    bare = User.objects.create_user("bare-bi", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-bi-production")).status_code == 403


@pytest.mark.django_db
def test_bi_production_endpoint_shape(client, recipe, bi_viewer):
    _finished_wo(recipe)
    client.force_login(bi_viewer)
    response = client.get(reverse("api-backstage-bi-production"))
    assert response.status_code == 200
    bi = response.json()["bi"]
    assert bi["batches_finished"] == 1
    assert bi["oven_coverage_percent"] == 0
    assert len(bi["days"]) == 28  # janela default
    assert bi["days"][-1]["date"] == timezone.localdate().isoformat()


# ── Série diária ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_daily_series_yield_loss_and_quality_mix(recipe):
    # 40 previstos: 32 padrão (cheio) + 6 mínima (desconto) + 2 perda declarada.
    _finished_wo(
        recipe,
        partition=[
            {"quantity": 32, "quality_grade_ref": "standard"},
            {"quantity": 6, "quality_grade_ref": "minimal", "quality_defect_ref": "overbaked"},
            {"quantity": 2, "loss": True, "quality_defect_ref": "overbaked"},
        ],
    )
    report = build_bi_production()
    today_row = report.days[-1]
    assert today_row.date == timezone.localdate().isoformat()
    assert today_row.planned == "40"
    assert today_row.finished == "38"
    assert today_row.loss == "2"
    assert today_row.yield_percent == 95
    assert today_row.full_price == "32"
    assert today_row.discounted == "6"


@pytest.mark.django_db
def test_window_normalization_swaps_and_defaults(db):
    today = timezone.localdate()
    report = build_bi_production(date_from=today, date_to=today - timedelta(days=6))
    assert report.date_from == (today - timedelta(days=6)).isoformat()
    assert report.date_to == today.isoformat()
    assert len(report.days) == 7


# ── Tempo de forno ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_oven_time_rows_and_coverage(recipe):
    measured = craft.plan(recipe, Decimal("10"), date=date.today(), position_ref="forno")
    craft.start(measured, quantity=Decimal("10"), position_ref="forno", expected_rev=0)
    apply_oven_arm(work_order_id=measured.pk, planned_seconds=900, actor="test")
    apply_oven_conclude(work_order_id=measured.pk, actor="test")
    apply_finish(work_order_id=measured.pk, quantity="10", actor="test")

    _finished_wo(recipe)  # fechada sem medição — pesa na cobertura

    report = build_bi_production()
    assert report.batches_finished == 2
    assert report.batches_measured == 1
    assert report.oven_coverage_percent == 50

    assert len(report.oven_time_by_recipe) == 1
    recipe_row = report.oven_time_by_recipe[0]
    assert recipe_row.ref == recipe.ref
    assert recipe_row.runs == 1
    assert recipe_row.avg_planned_minutes == "15.0"

    assert len(report.oven_time_by_oven) == 1
    assert report.oven_time_by_oven[0].ref == "forno"


@pytest.mark.django_db
def test_open_and_abandoned_runs_never_measure(recipe):
    wo = craft.plan(recipe, Decimal("10"), date=date.today(), position_ref="forno")
    craft.start(wo, quantity=Decimal("10"), position_ref="forno", expected_rev=0)
    apply_oven_arm(work_order_id=wo.pk, planned_seconds=900, actor="test")  # aberto…
    apply_finish(work_order_id=wo.pk, quantity="10", actor="test")
    # …e nunca concluído (o Confirmar do QC não mede): fora das linhas e da cobertura.
    OvenRun.objects.create(
        work_order_ref=wo.ref, oven_ref="forno", planned_seconds=900, status="abandoned"
    )
    report = build_bi_production()
    assert report.batches_measured == 0
    assert report.oven_time_by_recipe == ()
    assert report.oven_time_by_oven == ()
