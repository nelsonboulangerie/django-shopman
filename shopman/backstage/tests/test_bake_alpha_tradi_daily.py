"""A fornada diária da TRADI no alpha: portões e o caminho canônico.

Decisão do dono, 29/10/2026: uma fornada por dia, só a TRADI, só no alpha, por
``WorkOrder`` e ledger (``kind=MAKE``), nunca por ajuste de quant.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import StringIO
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.test import override_settings
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder, WorkOrderEvent
from shopman.stockman.models import Move, Position, PositionKind, Quant

from shopman.backstage.management.commands import bake_alpha_tradi_daily as command

pytestmark = pytest.mark.django_db

DOUGH = "MASSA-TRADICAO"
SP = ZoneInfo("America/Sao_Paulo")
THURSDAY_8H = datetime(2026, 11, 5, 8, 0, tzinfo=SP)


@pytest.fixture
def terrain(db):
    vitrine, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    deposito, _ = Position.objects.get_or_create(
        ref="deposito",
        defaults={"name": "Depósito", "kind": PositionKind.PHYSICAL, "is_saleable": False},
    )
    recipe = Recipe.objects.create(ref="baguete", name="Baguette", output_sku="TRADI", batch_size=Decimal("1"))
    RecipeItem.objects.create(recipe=recipe, input_sku=DOUGH, quantity=Decimal("280"), unit="g")
    return recipe, vitrine, deposito


def _stock_dough(deposito, grams):
    from shopman.stockman.services.movements import StockMovements

    StockMovements.receive(Decimal(grams), DOUGH, position=deposito, reason="teste")


def _run(at=THURSDAY_8H, environment="staging", **opts):
    out = StringIO()
    with override_settings(SHOPMAN_ENVIRONMENT=environment):
        from unittest.mock import patch

        with patch.object(command.timezone, "localtime", return_value=at):
            call_command("bake_alpha_tradi_daily", stdout=out, **opts)
    return out.getvalue()


def _saleable_tradi(vitrine) -> Decimal:
    return sum((q.quantity for q in Quant.objects.filter(sku="TRADI", position=vitrine)), Decimal("0"))


def test_bakes_once_a_day_through_the_ledger(terrain):
    recipe, vitrine, deposito = terrain
    _stock_dough(deposito, 280 * 20)

    _run()
    _run()

    work_order = WorkOrder.objects.get(recipe=recipe)
    assert work_order.status == WorkOrder.Status.FINISHED
    assert work_order.finished == command.DAILY_QUANTITY
    assert _saleable_tradi(vitrine) == command.DAILY_QUANTITY
    assert Move.objects.filter(quant__sku="TRADI", quant__position=vitrine, delta__gt=0).exists()
    assert not WorkOrderEvent.objects.filter(kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN).exists()


def test_short_dough_is_confirmed_with_the_written_reason(terrain):
    recipe, vitrine, deposito = terrain
    _stock_dough(deposito, 280 * 5)

    out = _run()

    work_order = WorkOrder.objects.get(recipe=recipe)
    assert work_order.status == WorkOrder.Status.FINISHED
    assert _saleable_tradi(vitrine) == command.DAILY_QUANTITY
    override = WorkOrderEvent.objects.get(work_order=work_order, kind=WorkOrderEvent.Kind.SHORTAGE_OVERRIDDEN)
    assert override.payload["reason"] == command.SHORTAGE_REASON
    assert "falta de insumo confirmada" in out


@pytest.mark.parametrize("environment", ["production", "development"])
def test_never_bakes_outside_the_alpha(terrain, environment):
    _stock_dough(terrain[2], 280 * 20)
    _run(environment=environment)
    assert not WorkOrder.objects.exists()


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 11, 5, 6, 59, tzinfo=SP),  # antes das 7h
        datetime(2026, 11, 8, 10, 0, tzinfo=SP),  # domingo
    ],
)
def test_waits_for_the_bake_window(terrain, at):
    _stock_dough(terrain[2], 280 * 20)
    _run(at=at)
    assert not WorkOrder.objects.exists()


def test_dry_run_bakes_nothing(terrain):
    _stock_dough(terrain[2], 280 * 20)
    out = _run(dry_run=True)
    assert "Assaria 20 TRADI" in out
    assert not WorkOrder.objects.exists()
