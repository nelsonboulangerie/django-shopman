"""Quiosque de QC do fournil (ADR-017 §9 / QC-FORNADA §5).

Cobre a projection ``build_qc_kiosk`` (painel de fornadas do dia + catálogos
de grau/defeito) e o endpoint ``GET /api/v1/backstage/production/qc/``, atrás
do gate grosso do chão (``backstage.operate_production``).
"""

from __future__ import annotations

from datetime import date

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.stockman import Position

from shopman.backstage.models import DayClosing
from shopman.backstage.projections.production import build_qc_kiosk
from shopman.backstage.services import production


def _perm(codename: str) -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing),
        codename=codename,
    )


@pytest.fixture
def floor_operator(db):
    user = User.objects.create_user("qc-floor", password="pw", is_staff=True)
    user.user_permissions.add(_perm("operate_production"))
    return user


@pytest.fixture
def recipe(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja QC")
    Position.objects.create(ref="forno", name="Forno", is_default=True)
    return Recipe.objects.create(
        ref="qc-baguete",
        name="Baguete",
        output_sku="BAG-TRAD",
        batch_size=40,
    )


@pytest.mark.django_db
def test_kiosk_carries_catalogs_with_semantics(recipe):
    kiosk = build_qc_kiosk(selected_date=date.today())

    # Escala do seed, do melhor para o pior — rank é a única hierarquia.
    assert [g.ref for g in kiosk.grades] == ["excellent", "standard", "fair", "minimal"]
    assert [g.rank for g in kiosk.grades] == sorted(
        (g.rank for g in kiosk.grades), reverse=True
    )
    default = next(g for g in kiosk.grades if g.is_default)
    assert default.ref == "standard"
    assert default.markdown_percent == 0

    # Defeitos ativos com hint (a segunda linha do botão) e o veto raro.
    defect_refs = {d.ref for d in kiosk.defects}
    assert "contaminated" in defect_refs
    vetoed = [d.ref for d in kiosk.defects if d.forces_discard]
    assert vetoed == ["contaminated"]


@pytest.mark.django_db
def test_kiosk_orders_open_first_closed_carry_partition(recipe, monkeypatch):
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    today = date.today()

    craft.plan(recipe, 24, date=today, position_ref="forno", operator_ref="ana")
    closed = craft.plan(recipe, 40, date=today, position_ref="forno", operator_ref="bia")
    craft.start(closed, quantity=40, position_ref="forno", operator_ref="bia", expected_rev=0)
    production.apply_finish(
        work_order_id=closed.pk, quantity="40", actor="production:bia",
        partition=[
            {"quantity": "32", "quality_grade_ref": "standard"},
            {"quantity": "5", "quality_grade_ref": "minimal", "quality_defect_ref": "overbaked"},
            {"quantity": "3", "quality_defect_ref": "underproofed", "loss": True},
        ],
    )

    kiosk = build_qc_kiosk(selected_date=today)

    assert kiosk.total_count == 2
    assert kiosk.closed_count == 1
    opened, finished = kiosk.orders
    assert opened.can_close and not opened.closed
    assert opened.planned_qty == "24"
    assert finished.closed and not finished.can_close
    assert (finished.full_price_qty, finished.discounted_qty, finished.loss_qty) == ("32", "5", "3")


@pytest.mark.django_db
def test_qc_endpoint_behind_floor_gate(client, floor_operator, recipe):
    url = reverse("api-backstage-production-qc")

    response = client.get(url)
    assert response.status_code in (401, 403)

    client.force_login(floor_operator)
    response = client.get(url)
    assert response.status_code == 200
    payload = response.json()["qc"]
    assert [g["ref"] for g in payload["grades"]][0] == "excellent"
    assert payload["recipes"], "fornada fora do plano precisa da lista de receitas"


@pytest.mark.django_db
def test_quick_finish_accepts_partition(client, floor_operator, recipe, monkeypatch):
    """Fornada fora do plano fechada pelo quiosque: N lotes, veto e perda."""
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    client.force_login(floor_operator)

    response = client.post(
        reverse("api-backstage-wo-quick-finish"),
        {
            "recipe_id": recipe.pk,
            "quantity": "10",
            "position_id": Position.objects.get(ref="forno").pk,
            "partition": [
                {"quantity": "8", "quality_grade_ref": "excellent"},
                {"quantity": "2", "quality_defect_ref": "misshapen", "loss": True},
            ],
        },
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["ok"] is True
    assert body["quantity"] == "8"

    from shopman.craftsman.models import WorkOrder, WorkOrderItem

    wo = WorkOrder.objects.get(ref=body["wo_ref"])
    assert wo.finished == 8
    waste = WorkOrderItem.objects.get(work_order=wo, kind=WorkOrderItem.Kind.WASTE)
    assert waste.quality_defect_ref == "misshapen"
