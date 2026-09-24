"""Abrir a embalagem: o tablete que se vende vira gramas que só a produção usa.

Decisão do dono (24/09/2026): na produção a manteiga é consumida em gramas; a
unidade aberta sai do estoque de revenda, e o conteúdo, dentro da validade,
fica para a produção. Revenda nunca vende o aberto.

Cenário do dono: manteiga de 200 g, três fichas de 50 g, 100 g e 80 g →
abre 1 tablete, depois o 2º; sobra certa; estoque vendável certo.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.buyman.models import Material
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.craftsman.service import craft
from shopman.offerman.models import Product
from shopman.stockman import stock
from shopman.stockman.models import Batch, Move, Position, PositionKind, Quant

from shopman.shop.adapters.inventory import InventoryAvailabilityBackend
from shopman.shop.services import production as production_core
from shopman.shop.services.package_opening import openable_content

pytestmark = pytest.mark.django_db

TABLETE = "MANTEIGA-SAL-PRESIDENT-200"
ABERTO = "MANTEIGA-COM-SAL"


@pytest.fixture
def casa(db):
    deposito = Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=False)
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    Material.objects.create(
        sku=TABLETE, name="Manteiga com sal Président 200g", unit="un",
        metadata={"opens_into": {"sku": ABERTO, "quantity": "0.200", "shelf_life_days": 7}},
    )
    Product.objects.create(sku=TABLETE, name="Manteiga com sal Président 200g", unit="un", base_price_q=1500)
    Material.objects.create(sku=ABERTO, name="Manteiga com sal (aberta)", unit="kg")
    stock.receive(quantity=Decimal("3"), sku=TABLETE, position=deposito, reason="compra", kind=Move.Kind.BUY)
    stock.receive(quantity=Decimal("2"), sku=TABLETE, position=vitrine, reason="exposição")
    return deposito, vitrine


def _ficha(ref: str, gramas: str) -> Recipe:
    Product.objects.create(sku=ref.upper(), name=ref, unit="un", base_price_q=1000)
    recipe = Recipe.objects.create(ref=ref, name=ref, output_sku=ref.upper(), batch_size=Decimal("1"))
    RecipeItem.objects.create(recipe=recipe, input_sku=ABERTO, quantity=Decimal(gramas) / 1000, unit="kg")
    return recipe


def _fecha(recipe: Recipe) -> None:
    work_order = craft.plan(recipe, Decimal("1"), date=timezone.localdate())
    craft.start(work_order, quantity=Decimal("1"), actor="test")
    production_core.finish_work_order(work_order_id=work_order.pk, quantity=Decimal("1"), actor="test")


def _saldo(sku: str, position=None) -> Decimal:
    quants = Quant.objects.filter(sku=sku)
    if position is not None:
        quants = quants.filter(position=position)
    return sum((q.quantity for q in quants), Decimal("0"))


def _saldo_do_lote(batch: str) -> Decimal:
    return sum((q.quantity for q in Quant.objects.filter(sku=ABERTO, batch=batch)), Decimal("0"))


def test_tres_fichas_de_50_100_e_80_gramas_abrem_dois_tabletes(casa):
    deposito, vitrine = casa

    _fecha(_ficha("croissant", "50"))
    assert _saldo(TABLETE, deposito) == Decimal("2")  # abriu o 1º
    assert _saldo(ABERTO) == Decimal("0.150")

    _fecha(_ficha("pain-au-chocolat", "100"))
    assert _saldo(TABLETE, deposito) == Decimal("2")  # o aberto bastou
    assert _saldo(ABERTO) == Decimal("0.050")

    _fecha(_ficha("brioche", "80"))
    assert _saldo(TABLETE, deposito) == Decimal("1")  # abriu o 2º só quando o aberto acabou
    assert _saldo(ABERTO) == Decimal("0.170")  # 0,050 + 0,200 − 0,080

    # A vitrine nunca é aberta: o tablete exposto fica para o cliente.
    assert _saldo(TABLETE, vitrine) == Decimal("2")
    # Revenda nunca vende o aberto: ele não tem cadastro de venda.
    assert not Product.objects.filter(sku=ABERTO).exists()


def test_o_aberto_tem_validade_propria_e_o_consumo_sai_do_mais_antigo(casa):
    _fecha(_ficha("croissant", "150"))
    _fecha(_ficha("brioche", "100"))

    lotes = list(Batch.objects.filter(sku=ABERTO).order_by("created_at"))
    assert len(lotes) == 2
    assert lotes[0].expiry_date == timezone.localdate() + timedelta(days=7)
    # O primeiro aberto (sobravam 50 g) foi o primeiro a ser consumido.
    assert _saldo(ABERTO) == Decimal("0.150")
    assert _saldo_do_lote(lotes[0].ref) == Decimal("0")
    assert _saldo_do_lote(lotes[1].ref) == Decimal("0.150")


def test_a_abertura_conta_como_consumo_do_tablete_para_a_reposicao(casa):
    _fecha(_ficha("croissant", "50"))

    saida = Move.objects.get(quant__sku=TABLETE, delta__lt=0)
    entrada = Move.objects.get(quant__sku=ABERTO, delta__gt=0)
    assert (saida.kind, saida.delta) == (Move.Kind.MAKE, Decimal("-1"))
    assert entrada.metadata["opened_from_sku"] == TABLETE


def test_o_guardrail_conta_o_que_ainda_esta_fechado_fora_da_vitrine(casa):
    assert openable_content(ABERTO) == Decimal("0.600")  # 3 tabletes do depósito, não os 2 da vitrine

    from shopman.craftsman.protocols.inventory import MaterialNeed

    result = InventoryAvailabilityBackend().available([MaterialNeed(sku=ABERTO, quantity=Decimal("0.5"))])
    assert result.all_available is True
    result = InventoryAvailabilityBackend().available([MaterialNeed(sku=ABERTO, quantity=Decimal("0.7"))])
    assert result.all_available is False


def test_sem_tablete_fechado_nao_abre_e_a_falta_segue_para_o_guardrail(casa):
    deposito, _vitrine = casa
    from shopman.stockman.services.movements import StockMovements

    StockMovements.issue(quantity=Decimal("3"), quant=Quant.objects.get(sku=TABLETE, position=deposito), reason="venda")

    from shopman.shop.services.package_opening import ensure_open_stock

    assert ensure_open_stock(ABERTO, Decimal("0.05"), reason="teste") == 0
    assert _saldo(ABERTO) == Decimal("0")
