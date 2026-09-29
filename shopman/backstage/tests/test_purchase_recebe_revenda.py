"""Compras recebendo MERCADORIA DE REVENDA — o chá, a geleia, o queijo.

Comprável é ter cadastro no Compras (``buyman.Material``); vendável é decisão
explícita (``offerman.Product``). A coisa comprada que também se vende tem os
dois cadastros com **o mesmo SKU**, e por isso o mesmo estoque: o pote que
entra pela nota é o pote que sai pelo PDV.

O que estes testes travam:
- a entrada credita o SKU comum, com movimento de COMPRA e custo por fornecedor;
- a revenda ganha o que pendura no cadastro de compra (conversão de caixa);
- SKU com ficha ativa não entra pela compra (entra pela Produção);
- o de-para da nota aprende o cadastro de compra;
- peso variável (queijo por kg) fecha com kg dos dois lados;
- a migração leva a marca antiga para o cadastro de compra, sem resíduo.
"""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from shopman.buyman.models import Material, MaterialConversion, Supplier, SupplierMaterialCost
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
        metadata={"social": {"brand": "Kãnfa"}},
    )
    Material.objects.create(sku=cha.sku, name=cha.name, unit="un")
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
        "materialSku": "INTU_P50",
        "purchaseQty": "2",
        "costInput": "84,80",
        "checked": True,
    }
    linha.update(extra)
    return linha


def test_a_entrada_credita_o_sku_comum_como_compra(cenario, operador):
    fornecedor, cha = cenario

    purchase_service.confirm_receipt(_payload(fornecedor, linha=_linha_do_cha()), user=operador)

    move = Move.objects.get()
    assert (move.quant.sku, move.kind) == (cha.sku, Move.Kind.BUY)
    assert move.delta == Decimal("2")
    assert move.metadata["purchase_material_sku"] == cha.sku
    assert "purchase_item_kind" not in move.metadata
    assert Quant.objects.get(sku=cha.sku).quantity == Decimal("2")
    # O custo por fornecedor, que a revenda não tinha, vem junto.
    custo = SupplierMaterialCost.objects.get(material__sku=cha.sku, supplier=fornecedor)
    assert custo.cost_q == 4240


def test_revenda_recebe_em_caixa_pela_conversao(cenario, operador):
    fornecedor, cha = cenario
    caixa = MaterialConversion.objects.create(
        material=Material.objects.get(sku=cha.sku), supplier=fornecedor,
        label="caixa com 12", to_base_factor=Decimal("12"),
    )

    purchase_service.confirm_receipt(
        _payload(fornecedor, linha=_linha_do_cha(purchaseQty="1", conversionId=str(caixa.pk))),
        user=operador,
    )

    assert Quant.objects.get(sku=cha.sku).quantity == Decimal("12")


def test_sku_produzido_aqui_nao_entra_pela_compra(cenario, operador):
    fornecedor, _cha = cenario
    Material.objects.create(sku="LEVAIN-LIQUIDO", name="Levain", unit="kg")
    Recipe.objects.create(ref="REC-LEVAIN", name="Levain", output_sku="LEVAIN-LIQUIDO", is_active=True)

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(
            _payload(fornecedor, linha=_linha_do_cha(materialSku="LEVAIN-LIQUIDO")), user=operador
        )

    assert erro.value.code == "material_is_produced_here"
    assert "Produção" in str(erro.value)
    assert not Move.objects.exists()


def test_produto_sem_cadastro_de_compra_nao_entra(cenario, operador):
    fornecedor, _cha = cenario
    Product.objects.create(sku="PU", name="Purin à la Mode", unit="un", base_price_q=2000)

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(
            _payload(fornecedor, linha=_linha_do_cha(materialSku="PU")), user=operador
        )

    assert erro.value.code == "material_not_found"
    assert not Move.objects.exists()


def test_o_de_para_da_nota_aprende_o_cadastro_de_compra(cenario, operador):
    fornecedor, cha = cenario

    purchase_service.confirm_receipt(
        _payload(fornecedor, linha=_linha_do_cha(invoiceProductCode="INTU_RV_P50")), user=operador
    )

    fornecedor.refresh_from_db()
    entrada = fornecedor.metadata["purchase"]["invoice_product_map"]["INTU_RV_P50"]
    assert entrada == {"materialSku": cha.sku, "conversionLabel": ""}


def test_a_revenda_aparece_na_lista_do_compras(cenario, operador):
    _fornecedor, cha = cenario

    projection = build_purchase()

    itens = {item.sku: item for item in projection.materials}
    assert itens[cha.sku].name == cha.name
    assert itens[cha.sku].stockOnHand == 0
    assert not hasattr(projection, "resaleProducts")


def test_revenda_perecivel_exige_validade(cenario, operador):
    fornecedor, cha = cenario
    Material.objects.filter(sku=cha.sku).update(shelf_life_days=180)

    with pytest.raises(purchase_service.PurchaseError) as erro:
        purchase_service.confirm_receipt(_payload(fornecedor, linha=_linha_do_cha()), user=operador)

    assert erro.value.code == "expiry_required"


def test_queijo_por_quilo_fecha_com_kg_dos_dois_lados(cenario, operador):
    """Peso variável: a nota diz 1,235 kg, a prateleira vende por kg."""
    fornecedor, _cha = cenario
    queijo = Product.objects.create(
        sku="QUEIJO-GRUYERE-KG", name="Gruyère (kg)", unit="kg", base_price_q=24900,
    )
    Material.objects.create(sku=queijo.sku, name=queijo.name, unit="kg")

    purchase_service.confirm_receipt(
        _payload(fornecedor, linha=_linha_do_cha(materialSku=queijo.sku, purchaseQty="1,235", costInput="185,25")),
        user=operador,
    )

    assert Quant.objects.get(sku=queijo.sku).quantity == Decimal("1.235")
    custo = SupplierMaterialCost.objects.get(material__sku=queijo.sku)
    assert custo.cost_q == 15000  # R$ 150,00 o quilo


def test_a_migracao_leva_a_marca_antiga_para_o_cadastro_de_compra(db):
    migracao = importlib.import_module("shopman.shop.migrations.0073_revenda_vira_cadastro_de_compra")
    geleia = Product.objects.create(
        sku="GELEIA-FIGO-284", name="Geleia de Figo 284g", unit="un", base_price_q=4200,
        shelf_life_days=365, metadata={"purchase": {"resale": True}, "social": {"brand": "St. Dalfour"}},
    )
    feito_aqui = Product.objects.create(
        sku="CT", name="Croissant", unit="un", base_price_q=1300, metadata={"purchase": {"resale": True}},
    )
    Recipe.objects.create(ref="REC-CT", name="Croissant", output_sku="CT", is_active=True)
    fornecedor = Supplier.objects.create(
        ref="dalfour", name="Importadora",
        metadata={"purchase": {"invoice_product_map": {
            "GF284": {"productSku": geleia.sku, "conversionLabel": ""},
            "FAR": {"materialSku": "FARINHA", "conversionLabel": "saco 25 kg"},
        }}},
    )

    migracao.forward(django_apps, None)

    material = Material.objects.get(sku=geleia.sku)
    assert (material.name, material.unit, material.shelf_life_days) == (geleia.name, "un", 365)
    geleia.refresh_from_db()
    assert geleia.metadata == {"social": {"brand": "St. Dalfour"}}
    assert not Material.objects.filter(sku="CT").exists()
    feito_aqui.refresh_from_db()
    assert "purchase" not in feito_aqui.metadata
    fornecedor.refresh_from_db()
    assert fornecedor.metadata["purchase"]["invoice_product_map"] == {
        "GF284": {"materialSku": geleia.sku, "conversionLabel": ""},
        "FAR": {"materialSku": "FARINHA", "conversionLabel": "saco 25 kg"},
    }


def test_a_nfe_vira_a_primeira_fonte_da_sugestao_de_catalogo(cenario, operador):
    """GTIN, NCM, CEST e unidade da nota vão para o RASCUNHO — nunca para o produto."""
    fornecedor, cha = cenario

    purchase_service.confirm_receipt(
        _payload(
            fornecedor,
            linha=_linha_do_cha(
                invoiceEan="7898708850309",
                invoicePackageEan="17898708850306",
                invoiceNcm="21012010",
                invoiceCest="1709900",
                invoiceUnit="UN",
            ),
        ),
        user=operador,
    )

    cha.refresh_from_db()
    campos = cha.metadata["enrichment"]["fields"]
    assert campos["gtin"]["value"] == "7898708850309"
    assert campos["gtin"]["source"] == "nfe"
    assert campos["gtin"]["source_ref"] == CHAVE
    assert "17898708850306" in campos["gtin"]["detail"]
    assert campos["ncm"]["value"] == "21012010"
    assert campos["cest"]["value"] == "1709900"
    assert campos["fiscal_unit"]["value"] == "UN"
    # nada disso entrou no produto
    assert "gtin" not in cha.metadata["social"]
    assert "fiscal" not in cha.metadata
