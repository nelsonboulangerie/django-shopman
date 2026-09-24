"""Markup da revenda: preço sugerido = custo × (1 + markup), por categoria.

Decisão do dono (24/09/2026): markup configurável por categoria (coleção
principal do produto) com padrão da loja de 50%. Arredonda para cima até o real
inteiro. Sem custo conhecido não há sugestão — nunca se inventa custo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
from shopman.offerman.models import Collection, CollectionItem, Product
from shopman.stockman import stock
from shopman.stockman.models import Move, Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.projections.purchase import build_purchase
from shopman.shop.models import Shop
from shopman.shop.resale_markup import ResaleMarkup, suggested_price_q, unit_costs_map

pytestmark = pytest.mark.django_db


def test_semantica_do_markup_e_arredondamento_para_cima_ate_o_real():
    assert suggested_price_q(2800, 50) == 4200  # 28,00 × 1,5 = 42,00
    assert suggested_price_q(2790, 50) == 4200  # 41,85 → 42,00
    assert suggested_price_q(1000, 150) == 2500  # ×2,5
    assert suggested_price_q(0, 50) == 0


def test_categoria_vence_o_padrao_e_valor_torto_cai_no_padrao():
    markup = ResaleMarkup.from_defaults(
        {"purchase": {"resale_markup_pct": 60, "resale_markup_by_collection": {"frios": 80, "x": "abc", "y": -5}}}
    )
    assert markup.pct_for("frios") == (80, "frios")
    assert markup.pct_for("mercearia") == (60, "")
    assert markup.by_collection == {"frios": 80}
    assert ResaleMarkup.from_defaults({}).default_pct == 50


def test_custo_vem_do_fornecedor_preferido_na_unidade_base():
    fornecedor = Supplier.objects.create(ref="dalfour", name="Importadora")
    geleia = Material.objects.create(sku="GELEIA-284", name="Geleia 284g", unit="un")
    caixa = MaterialConversion.objects.create(material=geleia, supplier=fornecedor, label="caixa 6", to_base_factor=6)
    SupplierMaterialCost.objects.create(material=geleia, supplier=fornecedor, conversion=caixa, cost_q=16740, is_preferred=True)

    assert unit_costs_map(["GELEIA-284"]) == {"GELEIA-284": 2790}


def test_sem_custo_de_fornecedor_usa_a_ultima_compra():
    Position.objects.create(ref="estoque", name="Estoque", kind=PositionKind.PHYSICAL, is_saleable=False)
    Material.objects.create(sku="MOSTARDA-215", name="Mostarda", unit="un")
    stock.receive(
        quantity=Decimal("12"), sku="MOSTARDA-215", position=Position.objects.get(ref="estoque"),
        reason="compra", kind=Move.Kind.BUY, purchase_total_cost_q=27600, purchase_base_qty="12",
    )

    assert unit_costs_map(["MOSTARDA-215"]) == {"MOSTARDA-215": 2300}
    assert unit_costs_map(["SEM-CUSTO"]) == {}


def test_a_projecao_do_compras_traz_a_sugestao_com_a_categoria():
    Shop.objects.create(name="Loja", defaults={"purchase": {"resale_markup_by_collection": {"mercearia": 70}}})
    Collection.objects.create(ref="mercearia", name="Mercearia")
    fornecedor = Supplier.objects.create(ref="kanfa", name="My Chai")
    cha = Material.objects.create(sku="CHA-P50", name="Chá 50g", unit="un")
    SupplierMaterialCost.objects.create(material=cha, supplier=fornecedor, cost_q=3650, is_preferred=True)
    Material.objects.create(sku="FARINHA", name="Farinha", unit="kg")  # sem custo: sem sugestão

    itens = {m.sku: m for m in build_purchase().materials}

    sugestao = itens["CHA-P50"].saleSuggestion
    assert (sugestao.costQ, sugestao.markupPct, sugestao.markupCategory) == (3650, 70, "Mercearia")
    assert sugestao.priceQ == 6300  # 36,50 × 1,7 = 62,05 → 63,00
    assert itens["FARINHA"].saleSuggestion is None


def test_item_que_ja_se_vende_nao_recebe_sugestao():
    fornecedor = Supplier.objects.create(ref="pres", name="Laticínios")
    manteiga = Material.objects.create(sku="MANTEIGA-200", name="Manteiga", unit="un")
    SupplierMaterialCost.objects.create(material=manteiga, supplier=fornecedor, cost_q=1000, is_preferred=True)
    produto = Product.objects.create(sku="MANTEIGA-200", name="Manteiga", unit="un", base_price_q=1500)
    colecao = Collection.objects.create(ref="frios", name="Frios")
    CollectionItem.objects.create(collection=colecao, product=produto, is_primary=True)

    item = next(m for m in build_purchase().materials if m.sku == "MANTEIGA-200")

    assert item.saleSuggestion is None
    assert item.salePriceQ == 1500
