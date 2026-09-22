"""Compras recebendo MERCADORIA DE REVENDA — o chá, a geleia, o queijo.

A entrada nasceu só para insumo. Mas a casa também compra pronto para vender, e
esse pote mora no catálogo, não na tabela de insumo. Inventar um insumo-sombra
com o mesmo nome criaria dois estoques do mesmo pote, divergentes no primeiro
dia — por isso a linha da nota aponta para o produto, e o estoque creditado é o
do SKU que o cliente leva.

O que estes testes travam:
- a entrada credita o SKU do produto, com movimento de COMPRA;
- produto que a casa FAZ não entra pela compra (entra pela Produção);
- produto sem a marca de revenda não entra (a marca é declaração, não palpite);
- insumo e produto na mesma linha é recusado;
- o de-para da nota aprende o produto, para a nota do mês que vem já vir pronta.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material, Supplier
from shopman.craftsman.models import Recipe
from shopman.offerman.models import Product
from shopman.stockman.models import Move, Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.projections.purchase import build_purchase
from shopman.backstage.services import purchase as purchase_service

CHAVE = "41260812345678000190550010000012341000123459"


@pytest.fixture
def operador(db):
    return User.objects.create_user("compras-revenda", password="pw", is_staff=True)


@pytest.fixture
def cenario(db):
    fornecedor = Supplier.objects.create(
        ref="my-chai", name="My Chai Fábrica de Chás", document="12.345.678/0001-90"
    )
    cha = Product.objects.create(
        sku="INTU_P50",
        name="Intuição Chai Kãnfa — Pouch 50g",
        unit="un",
        base_price_q=7300,
        is_published=True,
        is_sellable=True,
        metadata={"purchase": {"resale": True}, "social": {"brand": "Kãnfa"}},
    )
    Position.objects.get_or_create(
        ref="estoque",
        defaults={"name": "Estoque", "kind": PositionKind.PHYSICAL, "is_saleable": False},
    )
    return fornecedor, cha


def _payload(fornecedor, *, linha):
    return {
        "mode": "invoice",
        "supplierRef": fornecedor.ref,
        "invoiceAccessKey": CHAVE,
        "note": "",
        "lines": [linha],
    }


def _linha_do_cha(**extra):
    linha = {
        "id": "l1",
        "productSku": "INTU_P50",
        "purchaseQty": "2",
        "costInput": "84,80",
        "checked": True,
    }
    linha.update(extra)
    return linha


def test_a_entrada_credita_o_sku_do_produto_como_compra(cenario, operador):
    fornecedor, cha = cenario

    purchase_service.confirm_receipt(_payload(fornecedor, linha=_linha_do_cha()), user=operador)

    move = Move.objects.get()
    assert (move.quant.sku, move.kind) == (cha.sku, Move.Kind.BUY)
    assert move.delta == Decimal("2")
    assert move.metadata["purchase_item_kind"] == "product"
    assert move.metadata["purchase_product_sku"] == cha.sku
    # O custo da revenda vive no movimento: a tabela de custo por fornecedor é
    # de insumo, e forçar o pote lá dentro pediria um insumo-sombra.
    assert move.metadata["purchase_unit_cost_q"] == 4240
    assert Quant.objects.get(sku=cha.sku).quantity == Decimal("2")


def test_produto_feito_na_casa_nao_entra_pela_compra(cenario, operador):
    fornecedor, cha = cenario
    pao = Product.objects.create(
        sku="CT", name="Croissant", unit="un", base_price_q=1300,
        metadata={"purchase": {"resale": True}},
    )
    Recipe.objects.create(ref="REC-CT", name="Croissant", output_sku=pao.sku, is_active=True)

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(
            _payload(fornecedor, linha=_linha_do_cha(productSku=pao.sku)), user=operador
        )

    assert erro.value.code == "product_is_produced_here"
    assert "Produção" in str(erro.value)
    assert not Move.objects.exists()


def test_produto_sem_a_marca_de_revenda_nao_entra(cenario, operador):
    fornecedor, cha = cenario
    outro = Product.objects.create(sku="PU", name="Purin à la Mode", unit="un", base_price_q=2000)

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(
            _payload(fornecedor, linha=_linha_do_cha(productSku=outro.sku)), user=operador
        )

    assert erro.value.code == "product_not_resale"
    assert not Move.objects.exists()


def test_linha_com_insumo_e_produto_ao_mesmo_tempo_e_recusada(cenario, operador):
    fornecedor, cha = cenario
    Material.objects.create(sku="CHA-GRANEL", name="Chá a granel", unit="kg")

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(
            _payload(fornecedor, linha=_linha_do_cha(materialSku="CHA-GRANEL")), user=operador
        )

    assert erro.value.code == "receipt_line_ambiguous"


def test_revenda_nao_aceita_conversao_de_unidade(cenario, operador):
    fornecedor, _cha = cenario

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(
            _payload(fornecedor, linha=_linha_do_cha(conversionId="7")), user=operador
        )

    assert erro.value.code == "conversion_not_for_product"


def test_o_de_para_da_nota_aprende_o_produto(cenario, operador):
    fornecedor, cha = cenario

    purchase_service.confirm_receipt(
        _payload(fornecedor, linha=_linha_do_cha(invoiceProductCode="INTU_RV_P50")), user=operador
    )

    fornecedor.refresh_from_db()
    entrada = fornecedor.metadata["purchase"]["invoice_product_map"]["INTU_RV_P50"]
    assert entrada == {"productSku": cha.sku, "conversionLabel": ""}


def test_a_tela_recebe_a_lista_de_revenda_com_estoque(cenario, operador):
    _fornecedor, cha = cenario

    projection = build_purchase()

    revenda = {item.sku: item for item in projection.resaleProducts}
    assert revenda[cha.sku].name == cha.name
    assert revenda[cha.sku].brand == "Kãnfa"
    assert revenda[cha.sku].stockOnHand == 0


def test_produto_perecivel_de_revenda_exige_validade(cenario, operador):
    fornecedor, cha = cenario
    cha.shelf_life_days = 180
    cha.save(update_fields=["shelf_life_days"])

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(_payload(fornecedor, linha=_linha_do_cha()), user=operador)

    assert erro.value.code == "expiry_required"
