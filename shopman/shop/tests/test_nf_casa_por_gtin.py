"""A linha da NF-e sem cadastro casado procura o GTIN antes do nome.

O código de barras da nota é o impresso no pote que a casa já vende
(``Product.metadata.social.gtin``) — ou o que o cadastro de compra já guardou
(``Material.metadata.gtin``). O item certo é o cadastro de compra do MESMO SKU.
É sugestão: o operador confirma e o recebimento aprende o de-para (cProd).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from shopman.buyman.models import Material, Supplier
from shopman.offerman.models import Product
from shopman.stockman.models import Position
from shopman.stockman.models.enums import PositionKind

from shopman.backstage.services import purchase as purchase_service
from shopman.shop.adapters.purchase_invoice_nfe import NFeItem, _receipt_line_from_item

pytestmark = pytest.mark.django_db

GTIN = "084380959042"
CHAVE = "41260812345678000190550010000012341000123459"


def _item(**extra) -> NFeItem:
    base = {
        "number": "1", "product_code": "DAL-FIG-284", "ean": GTIN, "name": "DOCE DE FIGO ST DALFOUR 284G VD",
        "unit": "UN", "quantity": Decimal("6"), "unit_value": Decimal("25"), "tax_unit": "UN",
        "tax_quantity": Decimal("6"), "tax_unit_value": Decimal("25"), "total_value": Decimal("150"),
        "ncm": "20079910", "cfop": "5102", "expiry_date": "", "lot": "",
    }
    base.update(extra)
    return NFeItem(**base)


@pytest.fixture
def geleia(db):
    Product.objects.create(
        sku="GELEIA-FIGO-STDALFOUR-284", name="Geleia Figo St. Dalfour 284g", unit="un",
        base_price_q=4200, metadata={"social": {"brand": "St. Dalfour", "gtin": GTIN}},
    )
    return Material.objects.create(sku="GELEIA-FIGO-STDALFOUR-284", name="Geleia Figo St. Dalfour 284g", unit="un")


def test_o_gtin_do_produto_sugere_o_cadastro_de_compra_do_mesmo_sku(geleia):
    line = _receipt_line_from_item(_item(), index=0, supplier=None)

    assert line["materialSku"] == ""  # sugestão, não escolha
    assert line["suggestedMaterialSku"] == geleia.sku
    assert (line["suggestionScore"], line["suggestionSource"]) == (100, "gtin")


def test_o_gtin_guardado_no_cadastro_de_compra_tambem_vale(db):
    manteiga = Material.objects.create(
        sku="MANTEIGA-SAL-PRESIDENT-200", name="Manteiga com sal 200g", unit="un",
        metadata={"gtin": "3228020355741"},
    )

    line = _receipt_line_from_item(_item(ean="3228020355741", name="MANT PRES C SAL 200G"), index=0, supplier=None)

    assert line["suggestedMaterialSku"] == manteiga.sku
    assert line["suggestionSource"] == "gtin"


def test_gtin_de_dois_skus_nao_sugere_nenhum_pelo_codigo(geleia):
    Material.objects.create(sku="GELEIA-OUTRA", name="Outra geleia", unit="un", metadata={"gtin": GTIN})

    line = _receipt_line_from_item(_item(name="XYZ"), index=0, supplier=None)

    assert line["suggestionSource"] != "gtin"


def test_produto_sem_cadastro_de_compra_nao_vira_sugestao(db):
    Product.objects.create(sku="SO-VENDA", name="Só venda", unit="un", base_price_q=100,
                           metadata={"social": {"gtin": GTIN}})

    line = _receipt_line_from_item(_item(name="XYZ"), index=0, supplier=None)

    assert line["suggestedMaterialSku"] == ""


def test_confirmar_a_sugestao_ensina_o_de_para_da_nota(geleia):
    Position.objects.create(ref="estoque", name="Estoque", kind=PositionKind.PHYSICAL, is_saleable=False)
    fornecedor = Supplier.objects.create(ref="dalfour", name="Importadora", document="12.345.678/0001-90")
    operador = User.objects.create_user("compras-gtin", password="pw", is_staff=True)
    line = _receipt_line_from_item(_item(), index=0, supplier=fornecedor)

    # O gesto "É este": a sugestão vira a escolha, e a linha é conferida.
    line.update(materialSku=line["suggestedMaterialSku"], checked=True)
    purchase_service.confirm_receipt(
        {"mode": "invoice", "supplierRef": fornecedor.ref, "invoiceAccessKey": CHAVE, "lines": [line]},
        user=operador,
    )

    fornecedor.refresh_from_db()
    assert fornecedor.metadata["purchase"]["invoice_product_map"]["DAL-FIG-284"]["materialSku"] == geleia.sku
    # A próxima nota do mesmo fornecedor já vem casada, sem sugestão.
    seguinte = _receipt_line_from_item(_item(), index=0, supplier=fornecedor)
    assert seguinte["materialSku"] == geleia.sku
