"""Production mutation service facade tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderItem
from shopman.stockman.models import Batch

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production
from shopman.backstage.services.production import MissingMaterial, ProductionStockShortError


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="svc-prod-v1",
        name="Serviço Produção",
        output_sku="SVC-PROD",
        batch_size=Decimal("10"),
    )


@pytest.mark.django_db
def test_apply_planned_start_finish_and_void(recipe):
    output_sku, wo_ref, qty, result = production.apply_planned(
        recipe_id=recipe.pk,
        quantity="10",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)

    assert output_sku == recipe.output_sku
    assert qty == Decimal("10")
    assert result == "created"

    started_ref, started_qty = production.apply_start(
        work_order_id=work_order.pk,
        quantity="9",
        actor="production:op",
    )
    assert started_ref == wo_ref
    assert started_qty == Decimal("9")

    finished_ref, finished_qty = production.apply_finish(
        work_order_id=work_order.pk,
        quantity="8",
        actor="production:op",
    )
    assert finished_ref == wo_ref
    assert finished_qty == Decimal("8")

    planned = craft.plan(recipe, 5, date=date.today())
    assert production.apply_void(planned.pk, actor="production:op") == planned.ref


@pytest.mark.django_db
def test_apply_planned_consolidates_duplicate_planned_orders(recipe):
    first = craft.plan(recipe, 20, date=date.today())
    second = craft.plan(recipe, 12, date=date.today())

    output_sku, wo_ref, qty, result = production.apply_planned(
        recipe_id=recipe.pk,
        quantity="32",
        target_date_value=date.today().isoformat(),
        actor="production:op",
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert output_sku == recipe.output_sku
    assert wo_ref == first.ref
    assert qty == Decimal("32")
    assert result == "consolidated"
    assert first.quantity == Decimal("32")
    assert first.status == WorkOrder.Status.PLANNED
    assert second.status == WorkOrder.Status.VOID
    assert WorkOrder.objects.filter(recipe=recipe, target_date=date.today(), status=WorkOrder.Status.PLANNED).count() == 1


@pytest.mark.django_db
def test_apply_quick_finish_creates_finished_work_order(recipe):
    output_sku, wo_ref, qty = production.apply_quick_finish(
        recipe_id=recipe.pk,
        quantity="3",
        position_id="",
        actor="production:op",
    )

    work_order = WorkOrder.objects.get(ref=wo_ref)
    assert output_sku == recipe.output_sku
    assert qty == Decimal("3")
    assert work_order.status == WorkOrder.Status.FINISHED


def test_apply_finish_creates_stock_short_alert_before_reraising(monkeypatch):
    calls = []
    work_order = SimpleNamespace(pk=123, ref="WO-STOCK", output_sku="SKU-STOCK")

    def fail(*args, **kwargs):
        raise RuntimeError("estoque insuficiente")

    monkeypatch.setattr(production, "_get_work_order", lambda work_order_id: work_order)
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    # resolve_partition consulta o catálogo (DB); estes testes são unitários do
    # caminho de erro do finish — a partição entra pronta.
    monkeypatch.setattr(
        production,
        "resolve_partition",
        lambda wo, **kw: ([{"item_ref": wo.output_sku, "quantity": "1"}], []),
    )
    monkeypatch.setattr(production.production_core, "finish_work_order", fail)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(RuntimeError):
        production.apply_finish(work_order_id=123, quantity="1", actor="production:op")

    assert calls == [{"work_order_id": 123, "error": "estoque insuficiente"}]


def test_apply_finish_does_not_alert_for_non_stock_errors(monkeypatch):
    calls = []
    work_order = SimpleNamespace(pk=123, ref="WO-ERR", output_sku="SKU-ERR")

    def fail(*args, **kwargs):
        raise RuntimeError("erro genérico")

    monkeypatch.setattr(production, "_get_work_order", lambda work_order_id: work_order)
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])
    # resolve_partition consulta o catálogo (DB); estes testes são unitários do
    # caminho de erro do finish — a partição entra pronta.
    monkeypatch.setattr(
        production,
        "resolve_partition",
        lambda wo, **kw: ([{"item_ref": wo.output_sku, "quantity": "1"}], []),
    )
    monkeypatch.setattr(production.production_core, "finish_work_order", fail)
    monkeypatch.setattr(
        production,
        "_create_stock_short_alert",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(RuntimeError):
        production.apply_finish(work_order_id=123, quantity="1", actor="production:op")

    assert calls == []


@pytest.mark.django_db
def test_apply_finish_blocks_when_materials_are_missing(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    missing = [MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)

    with pytest.raises(ProductionStockShortError) as exc:
        production.apply_finish(work_order_id=work_order.pk, quantity="10", actor="production:op")

    assert exc.value.missing == missing
    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.PLANNED


@pytest.mark.django_db
def test_apply_finish_force_creates_stock_short_alert(recipe, monkeypatch):
    work_order = craft.plan(recipe, 10, date=date.today())
    missing = [MissingMaterial(sku="FARINHA", needed=Decimal("5"), available=Decimal("2"))]
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: missing)

    production.apply_finish(
        work_order_id=work_order.pk,
        quantity="9",
        actor="production:op",
        force=True,
    )

    work_order.refresh_from_db()
    assert work_order.status == WorkOrder.Status.FINISHED
    assert OperatorAlert.objects.filter(type="production_stock_short", order_ref=work_order.ref).exists()


@pytest.mark.django_db
def test_apply_finish_records_batch_traceability(monkeypatch):
    recipe = Recipe.objects.create(
        ref="svc-batch-v1",
        name="Serviço Lote",
        output_sku="SVC-BATCH",
        batch_size=Decimal("10"),
        meta={"requires_batch_tracking": True, "shelf_life_days": 2},
    )
    work_order = craft.plan(recipe, 10, date=date.today())
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])

    production.apply_finish(work_order_id=work_order.pk, quantity="8", actor="production:op")

    # O lote sai da LINHA de OUTPUT, não de WorkOrder.meta (ADR-017 §5): a
    # fórmula no meta só admitia um lote por ordem.
    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.batch_ref.startswith("SVC-BATCH-")
    batch = Batch.objects.get(ref=line.batch_ref, sku="SVC-BATCH")
    assert batch.expiry_date == date.today() + production.timedelta(days=2)
    work_order.refresh_from_db()
    assert "batch_ref" not in (work_order.meta or {})


# ── qualidade da fornada (derivada das linhas — ADR-017) ─────────────


@pytest.mark.django_db
def test_finish_quality_lands_on_the_output_line(recipe):
    _, wo_ref, _, _ = production.apply_planned(
        recipe_id=recipe.pk, quantity="10",
        target_date_value=date.today().isoformat(), actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    production.apply_start(work_order_id=work_order.pk, quantity="10", actor="production:op")
    production.apply_finish(
        work_order_id=work_order.pk, quantity="10",
        actor="production:op", quality="excellent",
    )

    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.quality_grade_ref == "excellent"
    work_order.refresh_from_db()
    assert "quality" not in (work_order.meta or {})  # meta["quality"] morreu


@pytest.mark.django_db
def test_quality_is_derivable_at_the_finish_signal(recipe):
    """A campanha deriva a qualidade das linhas no production_changed do finish.

    As linhas precisam estar gravadas quando o signal dispara — senão a regra
    ``quality_min`` avaliaria uma fornada sem partição.
    """
    seen = {}

    def _spy(sender, product_ref, date, action, work_order, **kwargs):
        if action == "finished":
            from shopman.shop.services import quality as quality_service

            seen["quality"] = quality_service.derived_quality(work_order)

    from shopman.craftsman.signals import production_changed

    production_changed.connect(_spy, weak=False)
    try:
        _, wo_ref, _, _ = production.apply_planned(
            recipe_id=recipe.pk, quantity="5",
            target_date_value=date.today().isoformat(), actor="production:op",
        )
        work_order = WorkOrder.objects.get(ref=wo_ref)
        production.apply_start(work_order_id=work_order.pk, quantity="5", actor="production:op")
        production.apply_finish(
            work_order_id=work_order.pk, quantity="5",
            actor="production:op", quality="excellent",
        )
    finally:
        production_changed.disconnect(_spy)

    assert seen["quality"] == "excellent"


@pytest.mark.django_db
def test_finish_without_quality_defaults_to_catalog_default(recipe):
    """O operador pode fechar sem pensar; o default não bloqueia nada."""
    _, wo_ref, _, _ = production.apply_planned(
        recipe_id=recipe.pk, quantity="4",
        target_date_value=date.today().isoformat(), actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    production.apply_start(work_order_id=work_order.pk, quantity="4", actor="production:op")
    production.apply_finish(work_order_id=work_order.pk, quantity="4", actor="production:op")

    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.quality_grade_ref == "standard"


@pytest.mark.django_db
def test_unknown_quality_falls_back_to_the_default(recipe):
    """Grau que o catálogo não conhece cai no padrão — a borda valida (ADR-004)."""
    _, wo_ref, _, _ = production.apply_planned(
        recipe_id=recipe.pk, quantity="2",
        target_date_value=date.today().isoformat(), actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    production.apply_start(work_order_id=work_order.pk, quantity="2", actor="production:op")
    production.apply_finish(
        work_order_id=work_order.pk, quantity="2",
        actor="production:op", quality="sublime",
    )

    line = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT)
    assert line.quality_grade_ref == "standard"


@pytest.mark.django_db
def test_partition_splits_lots_and_veto_goes_to_waste(recipe, monkeypatch):
    """A fornada de 10 que produz 6+3+1: dois lotes e uma perda vetada (ADR-017).

    O grupo com desconto grava o percentual RESOLVIDO no lote (congela); o
    grupo vetado (contaminated) nunca vira lote — vira WASTE com o motivo.
    """
    recipe.meta = {"requires_batch_tracking": True, "shelf_life_days": 1}
    recipe.save(update_fields=["meta"])
    monkeypatch.setattr(production, "check_finish_materials", lambda work_order: [])

    _, wo_ref, _, _ = production.apply_planned(
        recipe_id=recipe.pk, quantity="10",
        target_date_value=date.today().isoformat(), actor="production:op",
    )
    work_order = WorkOrder.objects.get(ref=wo_ref)
    production.apply_start(work_order_id=work_order.pk, quantity="10", actor="production:op")
    production.apply_finish(
        work_order_id=work_order.pk, quantity="10", actor="production:op",
        partition=[
            {"quantity": "6", "quality_grade_ref": "standard"},
            {"quantity": "3", "quality_grade_ref": "minimal", "quality_defect_ref": "overbaked"},
            {"quantity": "1", "quality_defect_ref": "contaminated"},
        ],
    )

    outputs = WorkOrderItem.objects.filter(
        work_order=work_order, kind=WorkOrderItem.Kind.OUTPUT
    ).order_by("batch_ref")
    assert outputs.count() == 2
    full, marked = outputs
    assert full.quality_grade_ref == "standard"
    assert marked.quality_grade_ref == "minimal"
    assert marked.batch_ref == f"{full.batch_ref}-2"

    # Dois lotes; o marcado congela o percentual do grau e o motivo do defeito.
    full_batch = Batch.objects.get(ref=full.batch_ref)
    marked_batch = Batch.objects.get(ref=marked.batch_ref)
    assert full_batch.nonconformity_percent == 0
    assert marked_batch.nonconformity_percent == 50
    assert marked_batch.nonconformity_reason == "Assou demais"

    # O veto virou perda com o motivo, nunca lote.
    waste = WorkOrderItem.objects.get(work_order=work_order, kind=WorkOrderItem.Kind.WASTE)
    assert waste.quality_defect_ref == "contaminated"
    assert waste.quantity == Decimal("1")

    work_order.refresh_from_db()
    assert work_order.finished == Decimal("9")  # 6 + 3; a perda fica fora
