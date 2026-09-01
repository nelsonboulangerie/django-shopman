"""As fronteiras da Produção com Orderman (encomenda) e Stockman (ledger MAKE).

Dois riscos de go-live que moram na borda, não dentro da Produção:

  1. **Orderman.** Zerar uma célula da matriz (``quantity=0``) apaga a fornada
     planejada. Se essa fornada cobre uma encomenda de cliente, zerar em silêncio
     é prometer e não entregar. O guardrail de cobertura tem de disparar ANTES de
     apagar — reduzir a zero é o caso extremo de reduzir abaixo do comprometido.

  2. **Stockman.** O fechamento credita a vitrine (saída) e baixa o insumo
     (entrada), duas pernas ``kind=MAKE``. O replay do operador depois de um erro
     pós-commit NÃO pode repetir nenhuma das duas — foi assim que "24 madeleines
     viraram 48 e a farinha baixou 1,0 kg onde a receita pede 0,5". Os marcadores
     por perna (``stock_consumed_at``/``stock_realized_at``) sob trava são a
     guarda; aqui provamos as DUAS pernas, não só a saída.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.craftsman.signals import production_changed
from shopman.orderman.models import Order, OrderItem
from shopman.stockman.models import Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services import production as production_service
from shopman.backstage.services.production import ProductionOrderShortError

SKU = "PAO-FRONT"
FARINHA = "FARINHA-T1"


# ── Fronteira com Orderman: a encomenda amarrada ────────────────────────────

@pytest.fixture
def cenario_encomenda(db):
    Position.objects.filter(is_default=True).update(is_default=False)
    Position.objects.create(
        ref="massa", name="Massa", kind=PositionKind.PHYSICAL, is_saleable=False, is_default=True
    )
    receita = Recipe.objects.create(
        ref="pao-front-v1", name="Pão", output_sku=SKU, batch_size=Decimal("100")
    )
    pedido = Order.objects.create(ref="ENC-F1", channel_ref="web", total_q=3000)
    OrderItem.objects.create(
        order=pedido, line_id="1", sku=SKU, name="Pão", qty=Decimal("30"),
        unit_price_q=100, line_total_q=3000,
    )
    production_service.apply_planned(
        recipe_id=receita.pk, quantity=Decimal("50"), target_date_value=None,
        position_ref="", operator_ref="", force=False, actor="op",
    )
    fornada = WorkOrder.objects.filter(
        recipe=receita, target_date=timezone.localdate(), status=WorkOrder.Status.PLANNED
    ).first()
    assert fornada is not None
    fornada.meta = {**(fornada.meta or {}), "committed_order_refs": [pedido.ref]}
    fornada.save(update_fields=["meta"])
    return receita, fornada, pedido


@pytest.mark.django_db
def test_limpar_a_celula_com_encomenda_amarrada_e_recusado(cenario_encomenda):
    """Zerar a célula é reduzir a fornada a zero — e há 30 un. encomendadas."""
    receita, fornada, _pedido = cenario_encomenda

    with pytest.raises(ProductionOrderShortError):
        production_service.apply_planned(
            recipe_id=receita.pk, quantity=Decimal("0"), target_date_value=None,
            position_ref="", operator_ref="", force=False, actor="op",
        )
    # A fornada continua de pé: a recusa veio ANTES de apagar.
    fornada.refresh_from_db()
    assert fornada.status == WorkOrder.Status.PLANNED
    assert fornada.planned_qty == Decimal("50")


@pytest.mark.django_db
def test_force_limpa_a_celula_e_a_encomenda_fica_descoberta(cenario_encomenda):
    """`force` é a saída deliberada do gestor: aí sim zera, sob responsabilidade."""
    receita, fornada, _pedido = cenario_encomenda

    production_service.apply_planned(
        recipe_id=receita.pk, quantity=Decimal("0"), target_date_value=None,
        position_ref="", operator_ref="", force=True, actor="op",
    )
    fornada.refresh_from_db()
    assert fornada.status == WorkOrder.Status.VOID


# ── Fronteira com Stockman: o replay não repete nenhuma perna ────────────────

@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def despensa(db):
    pos, _ = Position.objects.get_or_create(
        ref="despensa",
        defaults={"name": "Despensa", "kind": PositionKind.PHYSICAL, "is_saleable": False},
    )
    return pos


@pytest.fixture
def receita_com_insumo(db, vitrine, despensa):
    from shopman.stockman.services.movements import StockMovements

    receita = Recipe.objects.create(
        ref="rc-front-insumo", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )
    RecipeItem.objects.create(
        recipe=receita, input_sku=FARINHA, quantity=Decimal("0.5"), unit="kg"
    )
    StockMovements.receive(
        quantity=Decimal("100"), sku=FARINHA, position=despensa, reason="seed teste"
    )
    return receita


@pytest.fixture
def receiver_posterior_estoura():
    """Um receiver DEPOIS do de estoque estoura no primeiro finish (o hazard real)."""
    state = {"armed": True}

    def _boom(sender, **kwargs):
        if state["armed"] and kwargs.get("action") == "finished":
            state["armed"] = False
            raise RuntimeError("um receiver posterior estourou")

    production_changed.connect(_boom, dispatch_uid="test-front-later", weak=False)
    try:
        yield state
    finally:
        production_changed.disconnect(dispatch_uid="test-front-later")


def _qty(sku, position):
    quant = Quant.objects.filter(sku=sku, position=position, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


@pytest.mark.django_db
def test_replay_do_finish_nao_repete_saida_nem_consumo(
    receita_com_insumo, vitrine, despensa, receiver_posterior_estoura
):
    from shopman.craftsman import craft

    wo = craft.plan(receita_com_insumo, Decimal("40"), date=timezone.localdate())
    craft.start(wo, quantity=Decimal("40"), actor="test")

    # Primeiro finish: tudo commita, o estoque anda, e um receiver posterior estoura.
    with pytest.raises(RuntimeError):
        production_service.apply_finish(
            work_order_id=wo.pk, quantity="40", actor="test"
        )
    wo.refresh_from_db()
    assert wo.status == WorkOrder.Status.FINISHED

    # As duas pernas já andaram uma vez: +40 na vitrine, -20 (0,5×40) na despensa.
    assert _qty(SKU, vitrine) == Decimal("40")
    assert _qty(FARINHA, despensa) == Decimal("80")

    # O operador aperta de novo, mesmos dados: replay idempotente.
    ref_again, total = production_service.apply_finish(
        work_order_id=wo.pk, quantity="40", actor="test"
    )
    assert ref_again == wo.ref
    assert total == Decimal("40")

    # E nenhuma das pernas repetiu: saída continua 40, insumo continua 80.
    assert _qty(SKU, vitrine) == Decimal("40")
    assert _qty(FARINHA, despensa) == Decimal("80")
