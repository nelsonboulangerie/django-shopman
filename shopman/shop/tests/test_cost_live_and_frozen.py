"""ADR-023 de ponta a ponta (F3): custo VIVO no catálogo, custo CONGELADO na fornada.

- vivo: ``Product.reference_cost_q`` resolve pelo ``OFFERMAN["COST_BACKEND"]`` real
  (``RecipeCostBackend``) a partir do custo preferencial do ``Material`` (Buyman):
  pela ficha no produto feito aqui, pelo próprio ``Material`` na revenda;
- sem custo, a lacuna GRITA com motivo (Admin), nunca zero;
- congelado: o ``finish`` grava ``WorkOrder.meta["cost_snapshot"]``, e mudar o
  preço no Compras depois não reescreve a fornada.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.buyman.models import Material, Supplier, SupplierMaterialCost
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.craftsman.service import craft
from shopman.offerman.models import Product

from shopman.shop.adapters.cost import SNAPSHOT_KEY, RecipeCostBackend

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def real_cost_backend():
    """O provedor que o settings liga, sem singleton de outro teste no meio."""
    from shopman.offerman.conf import get_cost_backend, reset_cost_backend

    reset_cost_backend()
    assert isinstance(get_cost_backend(), RecipeCostBackend)
    yield
    reset_cost_backend()


@pytest.fixture
def supplier():
    return Supplier.objects.create(ref="moinho-f3", name="Moinho")


def _material(sku: str, unit: str, supplier=None, cost_q: int | None = None) -> Material:
    material = Material.objects.create(sku=sku, name=sku.title(), unit=unit)
    if cost_q is not None:
        SupplierMaterialCost.objects.create(supplier=supplier, material=material, cost_q=cost_q, is_preferred=True)
    return material


def _croissant(supplier) -> Recipe:
    """Rende 10; farinha R$ 10/kg × 1000 g + manteiga R$ 60/kg × 0,5 kg = R$ 40."""
    _material("FARINHA-F3", "g", supplier, cost_q=1000)
    _material("MANTEIGA-F3", "g", supplier, cost_q=6000)
    Product.objects.create(sku="CROISSANT-F3", name="Croissant", base_price_q=1000)
    recipe = Recipe.objects.create(ref="croissant-f3", name="Croissant", output_sku="CROISSANT-F3", batch_size=Decimal("10"))
    RecipeItem.objects.create(recipe=recipe, input_sku="FARINHA-F3", quantity=Decimal("1000"), unit="g")
    RecipeItem.objects.create(recipe=recipe, input_sku="MANTEIGA-F3", quantity=Decimal("0.5"), unit="kg")
    return recipe


# ── Custo vivo ──────────────────────────────────────────────────────────────


def test_produced_product_cost_comes_from_the_recipe_and_the_materials(supplier):
    _croissant(supplier)
    product = Product.objects.get(sku="CROISSANT-F3")

    assert product.reference_cost_q == 400
    assert product.margin_percent == Decimal("60.0")
    assert product.reference_cost_gap is None


def test_live_cost_follows_the_preferred_material_cost(supplier):
    _croissant(supplier)
    SupplierMaterialCost.objects.filter(material__sku="FARINHA-F3").update(cost_q=2000)

    assert Product.objects.get(sku="CROISSANT-F3").reference_cost_q == 500


def test_resale_product_cost_is_its_own_material_cost(supplier):
    """Mesmo SKU nos dois cadastros, sem ficha: o custo é o do próprio Material."""
    _material("GELEIA-F3", "un", supplier, cost_q=1200)
    product = Product.objects.create(sku="GELEIA-F3", name="Geleia", base_price_q=1800, unit="un")

    assert product.reference_cost_q == 1200
    assert product.margin_percent == Decimal("33.3")


def test_resale_product_sold_by_weight_is_priced_per_kg(supplier):
    _material("QUEIJO-F3", "kg", supplier, cost_q=8000)
    product = Product.objects.create(sku="QUEIJO-F3", name="Queijo", base_price_q=12000, unit="kg")

    assert product.reference_cost_q == 8000


def test_missing_preferred_cost_screams_with_a_reason_never_zero(supplier):
    _material("CHA-F3", "un")  # comprável, sem fornecedor ainda
    product = Product.objects.create(sku="CHA-F3", name="Chá", base_price_q=3000, unit="un")

    assert product.reference_cost_q is None
    assert product.margin_percent is None
    assert product.reference_cost_gap == "CHA-F3 não tem custo preferencial no Compras."


def test_recipe_with_an_uncosted_input_names_the_input(supplier):
    _croissant(supplier)
    SupplierMaterialCost.objects.filter(material__sku="MANTEIGA-F3").delete()
    product = Product.objects.get(sku="CROISSANT-F3")

    assert product.reference_cost_q is None
    assert product.reference_cost_gap == "MANTEIGA-F3 não tem custo preferencial no Compras."


def test_unconvertible_unit_screams(supplier):
    _material("LEITE-F3", "ml", supplier, cost_q=500)
    Product.objects.create(sku="PUDIM-F3", name="Pudim", base_price_q=1000)
    recipe = Recipe.objects.create(ref="pudim-f3", name="Pudim", output_sku="PUDIM-F3", batch_size=Decimal("1"))
    RecipeItem.objects.create(recipe=recipe, input_sku="LEITE-F3", quantity=Decimal("2"), unit="un")

    gap = Product.objects.get(sku="PUDIM-F3").reference_cost_gap
    assert gap == "LEITE-F3: a unidade 'un' não converte para 'ml', a do cadastro de compra."


def test_product_without_recipe_or_material_says_so():
    product = Product.objects.create(sku="SOLTO-F3", name="Solto", base_price_q=1000)

    assert product.reference_cost_q is None
    assert product.reference_cost_gap == "SOLTO-F3 não tem ficha técnica ativa nem cadastro de compra."


def test_admin_cost_column_shows_the_gap_instead_of_a_dash():
    from django.contrib.admin.sites import AdminSite
    from shopman.offerman.contrib.admin_unfold.admin import ProductAdmin

    _material("CHA2-F3", "un")
    product = Product.objects.create(sku="CHA2-F3", name="Chá", base_price_q=3000, unit="un")
    admin = ProductAdmin(Product, AdminSite())

    cell = str(admin.cost_display(product))
    assert "Sem custo" in cell
    assert "CHA2-F3 não tem custo preferencial no Compras." in cell
    assert admin.margin_percent_readonly(product) == "Sem custo: CHA2-F3 não tem custo preferencial no Compras."


# ── Custo congelado ─────────────────────────────────────────────────────────


def _bake(recipe, *, planned="10", finished="10") -> WorkOrder:
    wo = craft.plan(recipe, Decimal(planned), date=timezone.localdate())
    craft.start(wo, quantity=Decimal(planned), actor="test")
    craft.finish(wo, finished=Decimal(finished), actor="test")
    wo.refresh_from_db()
    return wo


def test_finish_freezes_the_batch_cost(supplier):
    wo = _bake(_croissant(supplier))

    snapshot = wo.meta[SNAPSHOT_KEY]
    assert snapshot["total_q"] == 4000
    assert snapshot["unit_cost_q"] == 400
    assert snapshot["output_quantity"] == "10"
    assert snapshot["gaps"] == []
    by_sku = {line["sku"]: line for line in snapshot["lines"]}
    assert by_sku["FARINHA-F3"]["cost_q"] == 1000
    assert by_sku["MANTEIGA-F3"]["cost_q"] == 3000
    assert snapshot["frozen_at"]


def test_price_change_after_production_does_not_rewrite_the_frozen_cost(supplier):
    from shopman.shop.handlers import production_cost

    wo = _bake(_croissant(supplier))
    frozen = dict(wo.meta[SNAPSHOT_KEY])

    SupplierMaterialCost.objects.filter(material__sku="FARINHA-F3").update(cost_q=5000)
    # Um segundo "finished" (correção de qualidade, replay) não reescreve.
    production_cost.on_production_changed(
        sender=WorkOrder, product_ref=wo.output_sku, date=wo.target_date, action="finished", work_order=wo
    )
    assert production_cost.freeze_work_order_cost(wo) is None

    wo.refresh_from_db()
    assert wo.meta[SNAPSHOT_KEY] == frozen
    assert wo.meta[SNAPSHOT_KEY]["total_q"] == 4000
    # O vivo, este sim, segue o Compras.
    assert Product.objects.get(sku="CROISSANT-F3").reference_cost_q == 800


def test_frozen_cost_registers_the_gap_and_no_total(supplier):
    recipe = _croissant(supplier)
    SupplierMaterialCost.objects.filter(material__sku="MANTEIGA-F3").delete()

    wo = _bake(recipe)

    snapshot = wo.meta[SNAPSHOT_KEY]
    assert snapshot["total_q"] is None
    assert snapshot["unit_cost_q"] is None
    assert snapshot["gaps"] == ["MANTEIGA-F3 não tem custo preferencial no Compras."]
    by_sku = {line["sku"]: line for line in snapshot["lines"]}
    assert by_sku["FARINHA-F3"]["cost_q"] == 1000
    assert "cost_q" not in by_sku["MANTEIGA-F3"]
    assert by_sku["MANTEIGA-F3"]["gap"] == "MANTEIGA-F3 não tem custo preferencial no Compras."


def test_unit_cost_divides_by_what_came_out_of_the_oven(supplier):
    wo = _bake(_croissant(supplier), planned="10", finished="8")

    snapshot = wo.meta[SNAPSHOT_KEY]
    assert snapshot["total_q"] == 4000
    assert snapshot["unit_cost_q"] == 500


def test_cost_lines_add_up_to_the_frozen_total(supplier):
    """Contrato: cada linha arredonda ao centavo e o total é a soma delas."""
    _material("SAL-F3", "g", supplier, cost_q=6)  # R$ 0,06/kg: 100 g = 0,6 centavo
    _material("ACUCAR-F3", "g", supplier, cost_q=6)
    Product.objects.create(sku="PITADA-F3", name="Pitada", base_price_q=100)
    recipe = Recipe.objects.create(ref="pitada-f3", name="Pitada", output_sku="PITADA-F3", batch_size=Decimal("1"))
    RecipeItem.objects.create(recipe=recipe, input_sku="SAL-F3", quantity=Decimal("100"), unit="g")
    RecipeItem.objects.create(recipe=recipe, input_sku="ACUCAR-F3", quantity=Decimal("100"), unit="g")

    snapshot = _bake(recipe, planned="1", finished="1").meta[SNAPSHOT_KEY]

    assert [line["cost_q"] for line in snapshot["lines"]] == [1, 1]
    assert snapshot["total_q"] == 2
    assert snapshot["unit_cost_q"] == 2


def test_unit_cost_comes_from_the_frozen_total(supplier):
    """2,5 centavos em 2 unidades: total gravado 3, unitário 3 ÷ 2 = 2 (não 1,25 → 1)."""
    _material("FERMENTO-F3", "g", supplier, cost_q=25)  # 100 g = 2,5 centavos
    Product.objects.create(sku="MINI-F3", name="Mini", base_price_q=100)
    recipe = Recipe.objects.create(ref="mini-f3", name="Mini", output_sku="MINI-F3", batch_size=Decimal("2"))
    RecipeItem.objects.create(recipe=recipe, input_sku="FERMENTO-F3", quantity=Decimal("100"), unit="g")

    snapshot = _bake(recipe, planned="2", finished="2").meta[SNAPSHOT_KEY]

    assert snapshot["total_q"] == 3
    assert snapshot["unit_cost_q"] == 2


def test_finish_replay_freezes_the_cost_the_signal_failed_to_freeze(supplier, monkeypatch):
    """O receiver blindado estourou; o retry idempotente do operador congela o custo."""
    from shopman.stockman import stock
    from shopman.stockman.models import Move, Position, PositionKind

    from shopman.shop.adapters import cost as cost_adapter
    from shopman.shop.services.production import finish_work_order

    recipe = _croissant(supplier)
    deposito = Position.objects.create(ref="deposito-f3", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=False)
    Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True}
    )
    for sku in ("FARINHA-F3", "MANTEIGA-F3"):
        stock.receive(quantity=Decimal("5000"), sku=sku, position=deposito, reason="compra", kind=Move.Kind.BUY)
    wo = craft.plan(recipe, Decimal("10"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("10"), actor="test")

    real_snapshot = cost_adapter.work_order_cost_snapshot
    calls = {"n": 0}

    def fails_twice(work_order):
        # A primeira tentativa é a do receiver; a segunda, a da rede de segurança.
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("falha no cálculo do custo")
        return real_snapshot(work_order)

    monkeypatch.setattr(cost_adapter, "work_order_cost_snapshot", fails_twice)
    finish_work_order(work_order_id=wo.pk, quantity="10", actor="test", idempotency_key="f3-replay")
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.FINISHED
    assert SNAPSHOT_KEY not in wo.meta

    finish_work_order(work_order_id=wo.pk, quantity="10", actor="test", idempotency_key="f3-replay")
    finish_work_order(work_order_id=wo.pk, quantity="10", actor="test", idempotency_key="f3-replay")
    wo.refresh_from_db()
    assert wo.meta[SNAPSHOT_KEY]["total_q"] == 4000
    assert calls["n"] == 3  # congelou uma vez; o segundo replay não recalcula
