"""A perna de output da produção não pode falhar em silêncio.

O drift do audit pré-alpha: quando ``StockPlanning.realize`` levanta, os
insumos JÁ foram consumidos e a WorkOrder JÁ está ``finished`` — mas a vitrine
fica zero. O ``except Exception`` do handler engolia tudo num
``logger.warning`` e o ``finish()`` voltava com sucesso: o operador via
"fornada concluída", a loja seguia vendendo pelo bucket ``in_production``, e
ninguém nunca soube (Sentry só captura ``ERROR``; o retry morre em
``TERMINAL_STATUS``).

Aqui a divergência grita: propaga para fora do ``finish()`` e chega ao
operador como erro de estoque, com alerta.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import craft
from shopman.stockman.exceptions import StockError
from shopman.stockman.models import Position, PositionKind, Quant
from shopman.stockman.services.planning import StockPlanning

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import production as backstage_production
from shopman.backstage.services.exceptions import ProductionError

pytestmark = pytest.mark.django_db

SKU = "PAO-REALIZE-FAIL"


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
        ref="rc-realize-fail", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )


@pytest.fixture
def realize_explodes(monkeypatch):
    """Falha genuína na perna de output (queda de DB, bug no realize)."""

    def _boom(*args, **kwargs):
        raise StockError("QUANT_NOT_FOUND", product=SKU)

    monkeypatch.setattr(StockPlanning, "realize", classmethod(_boom))


def _vitrine_qty(vitrine) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, position=vitrine, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


def test_realize_failure_propagates_out_of_finish(recipe, vitrine, realize_explodes):
    """O silêncio era o bug: o finish voltava OK com a vitrine zerada."""
    today = timezone.localdate()
    work_order = craft.plan(recipe, Decimal("40"), date=today)
    craft.start(work_order, quantity=Decimal("40"), actor="test")

    with pytest.raises(StockError):
        craft.finish(work_order, finished=Decimal("40"), actor="test")

    # A vitrine continua zerada — a diferença é que agora isso é audível.
    assert _vitrine_qty(vitrine) == Decimal("0")


def test_operator_sees_error_and_alert_when_realize_fails(recipe, vitrine, realize_explodes):
    """A borda do operador já sabia lidar; era código morto para esta falha."""
    today = timezone.localdate()
    work_order = craft.plan(recipe, Decimal("40"), date=today)
    craft.start(work_order, quantity=Decimal("40"), actor="test")

    with pytest.raises(ProductionError):
        backstage_production.apply_finish(
            work_order_id=work_order.pk, quantity="40", actor="test"
        )

    assert OperatorAlert.objects.filter(type="production_stock_short").exists()
