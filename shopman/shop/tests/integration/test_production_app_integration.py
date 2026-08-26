"""
Integration tests for the Craftsman → Stockman write path.

The `production_changed` signal handlers (craftsman.contrib.stockman) are the
single canonical write path: finishing a WorkOrder both *consumes ingredients*
and *realizes the finished output*, each leg emitted as Move.Kind.MAKE. There is
no InventoryProtocol write backend (that seam is read-only).

Tests:
- finish() deducts the recipe's ingredients from stock (kind=MAKE)
- finish() receives the finished output into the saleable position exactly once
- CraftService.suggest() via management command
- production_changed signal → planned quants → hold materialization
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from shopman.craftsman.models import WorkOrder
from shopman.craftsman.service import CraftService as craft
from shopman.stockman import stock
from shopman.stockman.models import Move, Quant

pytestmark = pytest.mark.django_db


CRAFTING_WITH_BACKENDS = {
    "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
    "CATALOG_BACKEND": "shopman.offerman.adapters.catalog_backend.OffermanCatalogBackend",
}


# =============================================================================
# CraftService.finish() → Stockman ledger (signal-path, kind=MAKE)
# =============================================================================


class TestFinishWorkOrderStockIntegration:
    """finish() consumes ingredients and receives output via the signal-path."""

    def test_finish_consumes_ingredients_as_make(
        self, recipe, ingredient, croissant,
        position_producao, position_loja, today,
    ):
        """Finishing a WO deducts its ingredients from stock (Move.Kind.MAKE)."""
        # Ingredient stock on hand.
        ingredient_quant = stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )
        assert stock.available(
            ingredient, target_date=today, position=position_producao,
        ) == Decimal("10")

        # batch_size=10, 0.5kg flour/batch → qty 20 ⇒ coefficient 2 ⇒ 1kg consumed.
        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)
        craft.finish(wo, finished=18, actor="test")

        assert wo.status == WorkOrder.Status.FINISHED

        # Ingredient was deducted, exactly once, as a MAKE move.
        ingredient_quant.refresh_from_db()
        assert ingredient_quant.quantity == Decimal("9")
        make_issues = Move.objects.filter(
            quant=ingredient_quant, kind=Move.Kind.MAKE, delta__lt=0,
        )
        assert make_issues.count() == 1
        assert make_issues.first().delta == Decimal("-1")

    def test_finish_receives_output_exactly_once(
        self, recipe, ingredient, croissant,
        position_producao, position_loja, today,
    ):
        """Finished output lands in the saleable position once (no double-count)."""
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)
        craft.finish(wo, finished=18, actor="test")

        assert wo.status == WorkOrder.Status.FINISHED

        # Exactly the finished quantity is saleable — not double-received.
        saleable = Quant.objects.get(
            sku=croissant.sku,
            position=position_loja,
            target_date=None,
            batch=f"{croissant.sku}-{today:%Y%m%d}",
        )
        assert saleable.quantity == Decimal("18")

    def test_finish_output_lands_at_the_primary_saleable_not_the_alphabetical(
        self, recipe, ingredient, croissant, position_producao, today,
    ):
        """O destino do realize é a posição de venda PRIMÁRIA (primeira criada).

        Regressão do pão invisível: Position.Meta.ordering=['ref'] fazia o
        .first() escolher por alfabeto, e uma posição interna (excluída dos
        canais remotos) roubava a fornada recém-assada — o storefront
        anunciava "recém saído" e vendia "Indisponível".
        """
        from shopman.stockman.models import Position, PositionKind

        vitrine = Position.objects.create(
            ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL,
            is_saleable=True,
        )
        Position.objects.create(
            # Alfabeticamente ANTES de "vitrine"; criada DEPOIS.
            ref="armario", name="Armário interno", kind=PositionKind.PHYSICAL,
            is_saleable=True,
        )
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)
        craft.finish(wo, finished=18, actor="test")

        saleable = Quant.objects.get(
            sku=croissant.sku,
            position=vitrine,
            target_date=None,
            batch=f"{croissant.sku}-{today:%Y%m%d}",
        )
        assert saleable.quantity == Decimal("18")
        assert not Quant.objects.filter(
            sku=croissant.sku, position__ref="armario",
        ).exists()

        # The only positive moves on the saleable quant are the single realize leg.
        positive_moves = Move.objects.filter(quant=saleable, delta__gt=0)
        assert positive_moves.count() == 1
        assert positive_moves.first().delta == Decimal("18")
        assert positive_moves.first().kind == Move.Kind.MAKE


class TestFinishPartitionLots:
    """A partição de qualidade (ADR-017) chega ao ESTOQUE, não só à rastreabilidade.

    Antes, as linhas de OUTPUT carregavam ``batch_ref`` e os ``Batch`` de
    qualidade eram gravados — mas o realize creditava tudo num quant sem lote.
    O elo quebrado: hold → quant.batch → ``percent_for_lot`` nunca encontrava o
    lote com desconto, e a xepa automática ficava inerte.
    """

    def _arrange(self, ingredient, position_producao, today):
        stock.receive(
            quantity=Decimal("10"),
            sku=ingredient.sku,
            position=position_producao,
            target_date=today,
            reason="Ingredient stock",
        )

    def test_partition_groups_become_separate_lots_in_stock(
        self, recipe, ingredient, croissant, position_producao, position_loja, today,
    ):
        self._arrange(ingredient, position_producao, today)
        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)

        ref_a = f"{croissant.sku}-{today:%Y%m%d}-{wo.pk}"
        ref_b = f"{ref_a}-2"
        craft.finish(
            wo,
            finished=[
                {"item_ref": croissant.sku, "quantity": "15",
                 "quality_grade_ref": "padrao", "batch_ref": ref_a},
                {"item_ref": croissant.sku, "quantity": "3",
                 "quality_grade_ref": "desconto", "batch_ref": ref_b},
            ],
            actor="test",
        )

        lot_a = Quant.objects.get(
            sku=croissant.sku, position=position_loja, target_date=None, batch=ref_a,
        )
        lot_b = Quant.objects.get(
            sku=croissant.sku, position=position_loja, target_date=None, batch=ref_b,
        )
        assert lot_a.quantity == Decimal("15")
        assert lot_b.quantity == Decimal("3")
        # Nada cai no lote diário genérico quando a partição nomeia os lotes.
        assert not Quant.objects.filter(
            sku=croissant.sku, batch=f"{croissant.sku}-{today:%Y%m%d}",
        ).exists()

    def test_partition_lots_get_validity_even_without_tracking_flag(
        self, recipe, ingredient, croissant, position_producao, position_loja, today,
    ):
        """Todo lote que vira estoque ganha produção+validade — a fornada
        esquecida expedida tarde envelhece pelo lote, com ou sem
        ``requires_batch_tracking`` na receita."""
        from shopman.stockman.models import Batch

        self._arrange(ingredient, position_producao, today)
        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)
        ref = f"{croissant.sku}-{today:%Y%m%d}-{wo.pk}"
        craft.finish(
            wo,
            finished=[{"item_ref": croissant.sku, "quantity": "18",
                       "quality_grade_ref": "padrao", "batch_ref": ref}],
            actor="test",
        )

        lot = Batch.objects.get(ref=ref)
        assert lot.sku == croissant.sku
        assert lot.production_date == today
        # croissant fixture: shelf_life_days=0 → vale só no dia.
        assert lot.expiry_date == today

    def test_discounted_lot_prices_from_its_batch(
        self, recipe, ingredient, croissant, position_producao, position_loja, today,
    ):
        """O elo completo: o quant carrega o lote, e o lote carrega o desconto
        congelado — ``percent_for_lot`` resolve o percentual da xepa."""
        from shopman.stockman.models import Batch

        from shopman.shop.services.lot_pricing import percent_for_lot

        self._arrange(ingredient, position_producao, today)
        wo = craft.plan(recipe, quantity=Decimal("20"), date=today)
        ref = f"{croissant.sku}-{today:%Y%m%d}-{wo.pk}"
        # A rastreabilidade congela o desconto no lote (aqui simulada; na
        # superfície é o _record_batch_traceability do fechamento).
        Batch.objects.create(
            ref=ref, sku=croissant.sku, production_date=today,
            expiry_date=today, nonconformity_percent=40,
            nonconformity_reason="Assou demais",
        )
        craft.finish(
            wo,
            finished=[{"item_ref": croissant.sku, "quantity": "18",
                       "quality_grade_ref": "desconto", "batch_ref": ref}],
            actor="test",
        )

        quant = Quant.objects.get(
            sku=croissant.sku, position=position_loja, target_date=None, batch=ref,
        )
        assert quant.quantity == Decimal("18")
        assert percent_for_lot(quant.batch) == 40



# =============================================================================
# production_changed signal → Stockman handlers
# =============================================================================


class TestProductionSignalCreatesPlannedQuant:
    """CraftService.plan() should create planned Quants via production_changed signal."""

    def test_plan_creates_planned_quant(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        # Ensure the craftsman contrib stockman handler is loaded
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        craft.plan(recipe, quantity=Decimal("50"), date=tomorrow)

        # The production_changed signal (action=planned) should create a planned Quant
        quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
        ).first()

        assert quant is not None, "Planned quant should be created by signal handler"
        assert quant._quantity == Decimal("50")

    def test_adjust_updates_planned_quant(
        self, recipe, ingredient, croissant, position_producao, tomorrow,
    ):
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        # Increasing planned production validates ingredient availability (the
        # WP-B5b guardrail, now wired): the recipe's ingredient must be on hand.
        stock.receive(
            quantity=Decimal("100"), sku=ingredient.sku,
            position=position_producao, reason="Insumo disponível",
        )

        wo = craft.plan(recipe, quantity=Decimal("50"), date=tomorrow)

        # Adjust quantity
        craft.adjust(wo, quantity=Decimal("70"), reason="Increased demand")

        quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
        ).first()

        assert quant is not None
        assert quant._quantity == Decimal("70")

    def test_void_cancels_planned_quant(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(recipe, quantity=Decimal("50"), date=tomorrow)

        # Verify quant exists
        assert Quant.objects.filter(
            sku=croissant.sku, target_date=tomorrow,
        ).exists()

        # Void the work order
        craft.void(wo, reason="Cancelled")

        # Quant should be zeroed out
        quant = Quant.objects.filter(
            sku=croissant.sku, target_date=tomorrow,
        ).first()

        assert quant is not None
        assert quant._quantity == Decimal("0")

    def test_start_splits_planned_and_expected_supply(
        self, recipe, croissant, position_producao, tomorrow,
    ):
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(
            recipe,
            quantity=Decimal("50"),
            date=tomorrow,
            position_ref=position_producao.ref,
        )

        craft.start(
            wo,
            quantity=Decimal("30"),
            expected_rev=0,
            position_ref=position_producao.ref,
            operator_ref="user:joao",
        )

        planned_quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
            batch="",
        ).first()
        started_quant = Quant.objects.filter(
            sku=croissant.sku,
            target_date=tomorrow,
            position=position_producao,
            batch="started",
        ).first()

        assert planned_quant is not None
        assert planned_quant._quantity == Decimal("20")
        assert started_quant is not None
        assert started_quant._quantity == Decimal("30")

        decision = stock.promise(croissant.sku, Decimal("25"), target_date=tomorrow)
        assert decision.approved is True
        assert decision.expected == Decimal("30")
        assert decision.planned == Decimal("20")
        assert decision.available_qty == Decimal("50")


# =============================================================================
# Suggest production management command
# =============================================================================


class TestSuggestProductionCommand:
    """Test the suggest_production management command."""

    def test_command_runs_without_error(self, settings, recipe, croissant, tomorrow):
        settings.CRAFTING = CRAFTING_WITH_BACKENDS
        out = StringIO()
        call_command("suggest_production", "--date", str(tomorrow), stdout=out)
        output = out.getvalue()
        # Should produce output (either suggestions or "no suggestions" message)
        assert len(output) > 0

    def test_command_with_no_demand_backend(self, settings, recipe, croissant, tomorrow):
        settings.CRAFTING = {"DEMAND_BACKEND": None}
        out = StringIO()
        call_command("suggest_production", "--date", str(tomorrow), stdout=out)
        output = out.getvalue()
        assert "Nenhuma sugestão" in output

    def test_command_filters_by_sku(self, settings, recipe, croissant, tomorrow):
        settings.CRAFTING = CRAFTING_WITH_BACKENDS
        out = StringIO()
        call_command(
            "suggest_production",
            "--date", str(tomorrow),
            "--skus", croissant.sku,
            stdout=out,
        )
        output = out.getvalue()
        assert len(output) > 0


# =============================================================================
# Planned hold → production materialization
# =============================================================================


class TestPlannedHoldMaterializationFlow:
    """End-to-end: planned hold → production → materialization."""

    def test_planned_hold_exists_for_future_production(
        self, croissant, position_loja, tomorrow,
    ):
        """When production is planned, customers can create holds on planned stock."""
        stock.plan(
            quantity=Decimal("100"),
            product=croissant,
            target_date=tomorrow,
            reason="Morning production",
        )

        available = stock.available(croissant, target_date=tomorrow)
        assert available == Decimal("100")

        hold_id = stock.hold(
            quantity=Decimal("5"),
            product=croissant,
            target_date=tomorrow,
        )
        assert hold_id is not None

        available_after = stock.available(croissant, target_date=tomorrow)
        assert available_after == Decimal("95")

    def test_production_finished_via_craft_service(
        self, recipe, croissant, position_loja, today,
    ):
        """Finishing a work order creates stock through the signal chain."""
        import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

        wo = craft.plan(recipe, quantity=Decimal("50"), date=today)

        # Verify planned quant was created
        planned = Quant.objects.filter(sku=croissant.sku, target_date=today).first()
        assert planned is not None

        # Finish work order (triggers production_changed with action=finished)
        craft.finish(wo, finished=48, actor="test")

        assert wo.status == WorkOrder.Status.FINISHED
