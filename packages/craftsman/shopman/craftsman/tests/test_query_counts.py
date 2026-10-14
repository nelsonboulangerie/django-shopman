"""O planejamento lê os itens de ficha UMA vez, não uma por work order.

Antes, ``craft.needs()`` prefetchava ``recipe__items`` e descartava o prefetch ao
chamar ``recipe.items.filter(is_optional=False)`` dentro do laço, porque o
``.filter`` abre um queryset novo. Cada work order voltava ao banco pela própria
ficha: 20 WOs custavam 20 consultas a ``crafting_recipe_item``. O mesmo padrão
vivia em ``scheduling._validate_shared_ingredients`` para as outras WOs do dia.

Estes testes travam as duas coisas que a mudança não pode quebrar: o custo não
pode crescer com N, e a lista devolvida tem de continuar sendo exatamente a
mesma (só ``is_optional=False``, na ordem de ``sort_order``).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder

pytestmark = pytest.mark.django_db

DAY = date(2026, 2, 25)
DAY_LARGE = DAY + timedelta(days=1)
SMALL = 2
LARGE = 20


def _recipe(ref: str, output_sku: str, *, optional: int = 0) -> Recipe:
    recipe = Recipe.objects.create(
        ref=ref,
        name=ref,
        output_sku=output_sku,
        batch_size=Decimal("10"),
    )
    RecipeItem.objects.create(recipe=recipe, input_sku="farinha", quantity=Decimal("5"), unit="kg", sort_order=0)
    RecipeItem.objects.create(recipe=recipe, input_sku="agua", quantity=Decimal("3"), unit="L", sort_order=1)
    for i in range(optional):
        RecipeItem.objects.create(
            recipe=recipe,
            input_sku=f"opcional-{i}",
            quantity=Decimal("1"),
            unit="kg",
            sort_order=100 + i,
            is_optional=True,
        )
    return recipe


def _plan(recipe: Recipe, quantity: int, day: date = DAY) -> WorkOrder:
    return WorkOrder.objects.create(
        recipe=recipe,
        output_sku=recipe.output_sku,
        quantity=Decimal(quantity),
        target_date=day,
    )


def _recipe_item_queries(ctx: CaptureQueriesContext) -> list[dict]:
    return [q for q in ctx.captured_queries if "crafting_recipe_item" in q["sql"]]


class TestNeedsQueryCountDoesNotGrowWithOrders:
    """20 WOs liam os itens em 21 consultas; agora é 1 prefetch para N WOs."""

    def test_recipe_items_are_read_once_no_matter_how_many_orders(self):
        recipe = _recipe("croissant-v1", "croissant")
        for _ in range(SMALL):
            _plan(recipe, 10)

        with CaptureQueriesContext(connection) as small:
            craft.needs(DAY)

        for _ in range(LARGE - SMALL):
            _plan(recipe, 10)

        with CaptureQueriesContext(connection) as large:
            craft.needs(DAY)

        # O gasto não cresce com N: as 18 WOs a mais não compram consulta nova.
        assert len(large.captured_queries) == len(small.captured_queries), (
            f"{SMALL} WOs: {len(small.captured_queries)} consultas; "
            f"{LARGE} WOs: {len(large.captured_queries)} consultas"
        )
        # E os itens de ficha são UMA leitura, não uma por work order.
        assert len(_recipe_item_queries(large)) == 1, [q["sql"] for q in _recipe_item_queries(large)]


class TestNeedsStillReturnsTheSamePlan:
    def test_optional_items_stay_out(self):
        recipe = _recipe("croissant-v1", "croissant", optional=2)
        _plan(recipe, 10)

        needs = craft.needs(DAY)

        assert {n.item_ref for n in needs} == {"farinha", "agua"}

    def test_items_keep_sort_order(self):
        recipe = Recipe.objects.create(
            ref="ordenada",
            name="Ordenada",
            output_sku="ordenada",
            batch_size=Decimal("1"),
        )
        RecipeItem.objects.create(recipe=recipe, input_sku="terceiro", quantity=Decimal("1"), unit="kg", sort_order=2)
        RecipeItem.objects.create(recipe=recipe, input_sku="primeiro", quantity=Decimal("1"), unit="kg", sort_order=0)
        RecipeItem.objects.create(recipe=recipe, input_sku="segundo", quantity=Decimal("1"), unit="kg", sort_order=1)
        _plan(recipe, 1)

        needs = craft.needs(DAY)

        assert [n.item_ref for n in needs] == ["primeiro", "segundo", "terceiro"]

    def test_aggregates_the_same_totals_across_orders(self):
        recipe = _recipe("croissant-v1", "croissant")
        _plan(recipe, 100)
        _plan(recipe, 50)

        by_ref = {n.item_ref: n for n in craft.needs(DAY)}

        assert by_ref["farinha"].quantity == Decimal("75.000")  # 50 + 25
        assert by_ref["agua"].quantity == Decimal("45.000")  # 30 + 15


class _FakeInventoryBackend:
    """Backend inerte: conta as chamadas para provar que a guarda realmente rodou."""

    calls: list[int] = []

    def available(self, needs):
        _FakeInventoryBackend.calls.append(len(needs))

        class Result:
            all_available = True
            materials: list = []

        return Result()


class TestSharedIngredientValidationDoesNotQueryPerWorkOrder:
    """``scheduling._validate_shared_ingredients`` lê as outras fichas uma vez."""

    def test_other_work_orders_items_are_read_once(self, settings):
        from shopman.craftsman.services.scheduling import _validate_shared_ingredients

        settings.CRAFTSMAN = {
            "INVENTORY_BACKEND": f"{__name__}._FakeInventoryBackend",
        }

        def _measure(day, n, sku):
            _FakeInventoryBackend.calls = []
            recipe = _recipe(f"ficha-{sku}", sku)
            order = _plan(recipe, 10, day)
            for _ in range(n - 1):
                _plan(recipe, 10, day)
            with CaptureQueriesContext(connection) as measured:
                _validate_shared_ingredients(order, Decimal("9"))
            assert _FakeInventoryBackend.calls, "a guarda de insumos não rodou"
            return measured

        small = _measure(DAY, SMALL, "sku-pequeno")
        large = _measure(DAY_LARGE, LARGE, "sku-grande")

        # Uma leitura para a própria ficha e uma para as outras WOs do dia, sem
        # crescer com N (antes: 1 + 1 + uma por WO).
        assert len(_recipe_item_queries(small)) == 2, [q["sql"] for q in _recipe_item_queries(small)]
        assert len(_recipe_item_queries(large)) == len(_recipe_item_queries(small)), [
            q["sql"] for q in _recipe_item_queries(large)
        ]
