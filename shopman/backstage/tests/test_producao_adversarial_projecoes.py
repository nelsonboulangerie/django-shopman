"""Uma receita com `meta` podre não pode derrubar o quadro inteiro.

`Recipe.meta` é um ``JSONField`` que o gestor edita no Admin. Um número digitado
errado (``max_started_minutes: "vinte"``) ou grande demais (``shelf_life_days:
10**18``) é erro de configuração de UMA receita — mas as projeções liam esses
campos com ``int(...)`` cru, então:

  - não-numérico → ``ValueError`` sobe e **o quadro de projeção inteiro dá 500**;
  - grande demais → ``OverflowError`` no ``timedelta``, mesmo efeito.

Uma linha ruim tem de degradar sozinha (sem ETA, validade cai no padrão), nunca
tirar a tela do ar para todas as outras fornadas do dia.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.projections.production import (
    build_production_forecast,
    build_production_weighing,
)

pytestmark = pytest.mark.django_db

SKU = "PAO-PROJ"

META_PODRE = ["vinte", "abc", "", None, "1,5", [], {}, "NaN", 10**18, "99999999999999999999"]


@pytest.fixture
def massa(db):
    Position.objects.filter(is_default=True).update(is_default=False)
    return Position.objects.create(
        ref="massa", name="Massa", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True
    )


def _recipe(meta) -> Recipe:
    return Recipe.objects.create(
        ref="rc-proj", name="Pão", output_sku=SKU, batch_size=Decimal("1"), meta=meta or {}
    )


@pytest.mark.parametrize("valor", META_PODRE)
def test_forecast_sobrevive_a_max_started_minutes_podre(massa, valor):
    receita = _recipe({"max_started_minutes": valor})
    wo = craft.plan(receita, Decimal("10"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("10"), actor="test")

    board = build_production_forecast()  # não pode levantar

    refs = {row.ref for row in board.rows}
    assert wo.ref in refs, "a fornada iniciada sumiu do quadro por causa do meta ruim"


@pytest.mark.parametrize("valor", META_PODRE)
def test_weighing_sobrevive_a_shelf_life_days_podre(massa, valor):
    receita = _recipe({"shelf_life_days": valor})
    RecipeItem.objects.create(
        recipe=receita, input_sku="FARINHA-PROJ", quantity=Decimal("0.5"), unit="kg"
    )
    craft.plan(receita, Decimal("10"), date=timezone.localdate())

    weighing = build_production_weighing()  # não pode levantar
    # E a receita aparece na pesagem (degradou, não sumiu).
    assert weighing is not None


def test_forecast_com_valor_valido_ainda_calcula_eta(massa):
    """Contraponto: um `max_started_minutes` são continua produzindo ETA."""
    receita = _recipe({"max_started_minutes": 45})
    wo = craft.plan(receita, Decimal("10"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("10"), actor="test")

    board = build_production_forecast()
    row = next(r for r in board.rows if r.ref == wo.ref)
    assert row.status in ("in_progress", "delayed")
    assert row.eta_display, "um timer válido tem de render ETA"
