"""B.I. explorador (F8) — gramática estrita e cruzamentos.

A gramática rejeita o desconhecido com a lista do que existe; os resolvedores
cruzam métrica × até 2 dimensões; ranking é limitado com corte DECLARADO.
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

from shopman.backstage.models import DayClosing, HistoricalSale, HistoricalSaleItem
from shopman.backstage.projections.bi_explore import (
    ExploreError,
    build_bi_explore,
    validate_config,
)
from shopman.backstage.services.production import apply_finish, apply_oven_arm, apply_oven_conclude


@pytest.fixture
def bi_viewer(db):
    user = User.objects.create_user("bi-explore", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi"
        )
    )
    return user


@pytest.fixture
def recipe(db):
    from shopman.shop.models import Shop

    Shop.objects.get_or_create(name="Loja Explore")
    Position.objects.get_or_create(ref="forno", defaults={"name": "Forno", "kind": "oven"})
    return Recipe.objects.create(
        ref="explore-v1", name="Pão Explorado", output_sku="EXP", batch_size=Decimal("10")
    )


# ── Gramática ────────────────────────────────────────────────────────────────


def test_grammar_rejects_unknown_with_the_menu():
    with pytest.raises(ExploreError, match="Métrica desconhecida.*revenue"):
        validate_config("faturamento", "time", "")
    with pytest.raises(ExploreError, match="não vale para Faturamento.*channel"):
        validate_config("revenue", "sku", "")
    with pytest.raises(ExploreError, match="Tempo só pode ser a dimensão principal"):
        validate_config("revenue", "channel", "time")
    with pytest.raises(ExploreError, match="diferentes"):
        validate_config("revenue", "channel", "channel")


@pytest.mark.django_db
def test_endpoint_maps_grammar_error_to_400(client, bi_viewer):
    client.force_login(bi_viewer)
    response = client.get(reverse("api-backstage-bi-explore"), {"metric": "nope"})
    assert response.status_code == 400
    assert "Métrica desconhecida" in response.json()["detail"]
    ok = client.get(reverse("api-backstage-bi-explore"), {"metric": "revenue", "by": "time"})
    assert ok.status_code == 200
    assert ok.json()["bi"]["metric_label"] == "Faturamento"
    assert any(m["key"] == "loss" for m in ok.json()["bi"]["metrics"])


# ── Cruzamentos ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_revenue_by_channel_crossed_with_source(db):
    from shopman.orderman.models import Order

    Order.objects.create(ref="EXP-1", channel_ref="web", status=Order.Status.COMPLETED, total_q=2000)
    HistoricalSale.objects.create(
        source="yooga", external_id=1, occurred_at=timezone.now() - timedelta(days=2),
        total_q=5000, is_delivery=True,
    )
    report = build_bi_explore(metric="revenue", by="channel", by2="source")
    cells = {(row.key, row.key2): row.value for row in report.rows}
    assert cells == {("web", "shopman"): 2000.0, ("yooga · delivery", "yooga"): 5000.0}
    assert report.unit == "q"


@pytest.mark.django_db
def test_loss_by_defect_crossed_with_recipe(recipe):
    wo = craft.plan(recipe, Decimal("40"), date=date.today(), position_ref="forno")
    craft.start(wo, quantity=Decimal("40"), position_ref="forno", expected_rev=0)
    apply_finish(
        work_order_id=wo.pk, quantity="40", actor="t",
        partition=[
            {"quantity": 37, "quality_grade_ref": "standard"},
            {"quantity": 3, "loss": True, "quality_defect_ref": "overbaked"},
        ],
    )
    report = build_bi_explore(metric="loss", by="defect", by2="recipe")
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.key == "overbaked"
    assert row.label == "Assou demais"  # label do catálogo, não o ref cru
    assert row.key2 == recipe.ref
    assert row.label2 == recipe.name
    assert row.value == 3.0


@pytest.mark.django_db
def test_oven_minutes_by_recipe(recipe):
    wo = craft.plan(recipe, Decimal("10"), date=date.today(), position_ref="forno")
    craft.start(wo, quantity=Decimal("10"), position_ref="forno", expected_rev=0)
    apply_oven_arm(work_order_id=wo.pk, planned_seconds=900, actor="t")
    apply_oven_conclude(work_order_id=wo.pk, actor="t")
    report = build_bi_explore(metric="oven_minutes", by="recipe")
    assert len(report.rows) == 1
    assert report.rows[0].label == recipe.name
    assert report.unit == "minutes"


# ── Cenários salvos (F9) ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_saved_views_crud_validated_by_grammar(client, bi_viewer):
    client.force_login(bi_viewer)
    url = reverse("api-backstage-bi-views")

    # Config fora da gramática não salva.
    bad = client.post(url, {"name": "Ruim", "config": {"metric": "nope"}},
                      content_type="application/json")
    assert bad.status_code == 400
    weird = client.post(url, {"name": "Ruim", "config": {"metric": "loss", "hack": 1}},
                        content_type="application/json")
    assert weird.status_code == 400 and "Chaves desconhecidas" in weird.json()["detail"]

    config = {"metric": "loss", "by": "defect", "by2": "recipe", "window": {"preset": "28d"}}
    ok = client.post(url, {"name": "Perda por defeito", "config": config},
                     content_type="application/json")
    assert ok.status_code == 200
    view_id = ok.json()["view"]["id"]

    # Mesmo nome = atualiza, não duplica.
    client.post(url, {"name": "Perda por defeito", "config": config}, content_type="application/json")
    listed = client.get(url).json()["views"]
    assert len(listed) == 1 and listed[0]["config"]["by2"] == "recipe"

    detail = reverse("api-backstage-bi-view", kwargs={"pk": view_id})
    assert client.patch(detail, {"is_favorite": True}, content_type="application/json").json()["view"]["is_favorite"] is True

    # Outro usuário não enxerga nem apaga o cenário alheio.
    other = User.objects.create_user("bi-outro", password="pw", is_staff=True)
    other.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get_for_model(DayClosing), codename="view_bi"))
    client.force_login(other)
    assert client.get(url).json()["views"] == []
    assert client.delete(detail).status_code == 404

    client.force_login(bi_viewer)
    assert client.delete(detail).status_code == 200
    assert client.get(url).json()["views"] == []


@pytest.mark.django_db
def test_qty_sold_by_sku_merges_sources_and_declares_truncation(db):
    for index in range(3):
        sale = HistoricalSale.objects.create(
            source="yooga", external_id=10 + index,
            occurred_at=timezone.now() - timedelta(days=3), total_q=1000,
        )
        HistoricalSaleItem.objects.create(
            sale=sale, seq=1, product_name=f"Produto {index}", sku=f"P{index}",
            qty=Decimal(index + 1), unit_price_q=1000, line_total_q=1000,
        )
    report = build_bi_explore(metric="qty_sold", by="sku")
    assert report.truncated == 0
    assert [row.key for row in report.rows][:1] == ["P2"]  # ranking por valor
    assert report.rows[0].value == 3.0
