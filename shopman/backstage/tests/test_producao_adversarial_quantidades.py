"""Quantidade hostil na borda de produção não pode virar 500 nem estoque podre.

A fornada fecha por um número que vem do cliente (POST do quiosque). O guardrail
da casa rejeita ``<= 0`` e o lixo textual (``"abc"``), mas o `Decimal` do Python
aceita ``"NaN"`` e ``"Infinity"`` como números legítimos — e é aí que a borda
falhava de dois jeitos, ambos ruins para o go-live:

  - ``"NaN"``: ``Decimal("NaN") <= 0`` **levanta** ``InvalidOperation`` (não é
    ``CraftError``), então a tradução do operador não a pega e o forneiro leva um
    500 cru numa fornada que ele só quer fechar.
  - ``"Infinity"``: ``Decimal("Infinity") <= 0`` é ``False``, então passa reto —
    quantidade infinita entra em ``WorkOrderItem`` e credita a vitrine com um
    número que nenhum relatório sobrevive.

O contrato é um só: número não-finito é quantidade inválida, e a casa recusa com
o dialeto dela (``ProductionError`` → 400 / "Quantidade inválida."), nunca com
uma exceção aritmética vazando pela porta.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman.models import Position, PositionKind, Quant

from shopman.backstage.services import production as backstage_production
from shopman.backstage.services.exceptions import ProductionError

pytestmark = pytest.mark.django_db

SKU = "PAO-ADV"

# Os dois números que o `Decimal` aceita mas a padaria não pode: um estoura na
# comparação, o outro passa calado. E os clássicos, que já eram barrados, para
# provar que o aperto novo não afrouxou os antigos.
NAO_FINITOS = ["NaN", "nan", "Infinity", "inf", "-Infinity", "sNaN"]
NAO_POSITIVOS = ["0", "-1", "-0.5"]
LIXO = ["", "   ", "abc", "1,5", "vinte", None]


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    return Recipe.objects.create(
        ref="rc-adv", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )


def _started(recipe) -> WorkOrder:
    from django.utils import timezone

    wo = craft.plan(recipe, Decimal("40"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("40"), actor="test")
    return wo


def _vitrine_qty(vitrine) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, position=vitrine, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


def _assert_dominio(excinfo):
    """A falha tem de ser do domínio, nunca uma exceção aritmética vazada."""
    assert not isinstance(excinfo.value, (InvalidOperation, ArithmeticError)), (
        f"vazou {type(excinfo.value).__name__} pela borda em vez de ProductionError"
    )


# ── FINISH ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quantity", NAO_FINITOS)
def test_finish_recusa_quantidade_nao_finita(recipe, vitrine, quantity):
    wo = _started(recipe)
    with pytest.raises(ProductionError) as excinfo:
        backstage_production.apply_finish(
            work_order_id=wo.pk, quantity=quantity, actor="test"
        )
    _assert_dominio(excinfo)
    # E nada foi para a vitrine: a fornada continua aberta, não infinita.
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.STARTED
    assert _vitrine_qty(vitrine) == Decimal("0")


@pytest.mark.parametrize("quantity", NAO_POSITIVOS + LIXO)
def test_finish_recusa_quantidade_invalida(recipe, vitrine, quantity):
    wo = _started(recipe)
    with pytest.raises(ProductionError) as excinfo:
        backstage_production.apply_finish(
            work_order_id=wo.pk, quantity=quantity, actor="test"
        )
    _assert_dominio(excinfo)
    assert _vitrine_qty(vitrine) == Decimal("0")


@pytest.mark.parametrize("quantity", NAO_FINITOS)
def test_finish_particionado_recusa_quantidade_nao_finita(recipe, vitrine, quantity):
    """A partição é o caminho que pula o validador do shop e cai direto no core."""
    wo = _started(recipe)
    with pytest.raises(ProductionError) as excinfo:
        backstage_production.apply_finish(
            work_order_id=wo.pk,
            quantity="40",
            actor="test",
            partition=[{"quantity": quantity, "quality_grade_ref": ""}],
        )
    _assert_dominio(excinfo)
    assert _vitrine_qty(vitrine) == Decimal("0")


# ── START ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quantity", NAO_FINITOS + NAO_POSITIVOS)
def test_start_recusa_quantidade_nao_finita(recipe, quantity):
    from django.utils import timezone

    wo = craft.plan(recipe, Decimal("40"), date=timezone.localdate())
    with pytest.raises((ProductionError, ValueError)) as excinfo:
        backstage_production.apply_start(
            work_order_id=wo.pk, quantity=quantity, actor="test"
        )
    _assert_dominio(excinfo)
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.PLANNED


# ── PLANNED (matriz) ────────────────────────────────────────────────────────

@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_planned_recusa_quantidade_nao_finita(recipe, quantity):
    from django.utils import timezone

    with pytest.raises((ProductionError, ValueError)) as excinfo:
        backstage_production.apply_planned(
            recipe_id=recipe.pk,
            quantity=quantity,
            target_date_value=timezone.localdate().isoformat(),
            actor="test",
        )
    _assert_dominio(excinfo)
    # E nenhuma WorkOrder infinita ficou plantada na matriz.
    assert not WorkOrder.objects.filter(recipe=recipe).exclude(
        status=WorkOrder.Status.VOID
    ).exists()


# ── QUICK FINISH (avulsa) ───────────────────────────────────────────────────

@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "sNaN"])
def test_quick_finish_recusa_quantidade_nao_finita(recipe, vitrine, quantity):
    with pytest.raises((ProductionError, ValueError)) as excinfo:
        backstage_production.apply_quick_finish(
            recipe_id=recipe.pk,
            quantity=quantity,
            position_id="",
            actor="test",
        )
    _assert_dominio(excinfo)
    assert _vitrine_qty(vitrine) == Decimal("0")
