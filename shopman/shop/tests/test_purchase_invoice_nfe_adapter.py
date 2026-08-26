from __future__ import annotations

import base64
import gzip
from decimal import Decimal

import pytest
from django.test import override_settings
from shopman.buyman.models import Material, MaterialConversion, Supplier

from shopman.shop.adapters.purchase_invoice_nfe import (
    _extract_proc_nfe_xml,
    parse_nfe_xml_to_purchase_draft,
    read_invoice,
)

VALID_ACCESS_KEY = "41260812345678000190550010000012341000123459"


def _nfe_xml(*, access_key: str = VALID_ACCESS_KEY, product_code: str = "FAR-25", product_name: str = "FARINHA T65 25KG", unit: str = "SC") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{access_key}" versao="4.00">
      <ide>
        <cUF>41</cUF>
        <mod>55</mod>
        <serie>1</serie>
        <nNF>1234</nNF>
        <dhEmi>2026-08-25T09:00:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12345678000190</CNPJ>
        <xNome>Moinho Sao Paulo</xNome>
      </emit>
      <dest>
        <CNPJ>99999999000191</CNPJ>
        <xNome>Nelson Boulangerie</xNome>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>{product_code}</cProd>
          <cEAN>SEM GTIN</cEAN>
          <xProd>{product_name}</xProd>
          <NCM>11010010</NCM>
          <CFOP>5102</CFOP>
          <uCom>{unit}</uCom>
          <qCom>2.0000</qCom>
          <vUnCom>180.0000000000</vUnCom>
          <vProd>360.00</vProd>
        </prod>
      </det>
      <total>
        <ICMSTot>
          <vNF>360.00</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
  <protNFe versao="4.00">
    <infProt>
      <chNFe>{access_key}</chNFe>
      <cStat>100</cStat>
    </infProt>
  </protNFe>
</nfeProc>
"""


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        ref="SUP-MOINHO-SP",
        name="Moinho Sao Paulo",
        document="12.345.678/0001-90",
        metadata={
            "purchase": {
                "invoice_product_map": {
                    "FAR-25": {
                        "materialSku": "FARINHA-T65",
                        "conversionLabel": "saco 25 kg",
                    }
                }
            }
        },
    )


@pytest.fixture
def material(db):
    return Material.objects.create(
        sku="FARINHA-T65",
        name="Farinha T65",
        unit="kg",
        shelf_life_days=180,
        metadata={"purchase": {"invoice_codes": ["FAR-25"]}},
    )


@pytest.fixture
def conversion(material, supplier):
    return MaterialConversion.objects.create(
        material=material,
        supplier=supplier,
        label="saco 25 kg",
        to_base_factor=Decimal("25"),
    )


@pytest.mark.django_db
def test_parse_nfe_xml_to_receipt_draft_maps_supplier_material_and_conversion(supplier, material, conversion):
    draft = parse_nfe_xml_to_purchase_draft(_nfe_xml(), access_key=VALID_ACCESS_KEY)

    assert draft["supplierRef"] == supplier.ref
    assert draft["note"].startswith("NF 1234/1 - Moinho Sao Paulo")
    assert draft["lines"] == [
        {
            "id": "nfe-1",
            "materialSku": material.sku,
            "conversionId": str(conversion.pk),
            "requiresConversion": False,
            "purchaseQty": "2",
            "costInput": "360,00",
            "expiryDate": "",
            "lineNote": "NF: FARINHA T65 25KG; cod FAR-25; unidade SC; NCM 11010010; CFOP 5102.",
            "checked": False,
        }
    ]


@pytest.mark.django_db
def test_parse_nfe_xml_keeps_unmapped_item_visible_and_blocked(supplier):
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="QJO-ART", product_name="QUEIJO ARTESANAL MEIA CURA", unit="PC"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert draft["supplierRef"] == supplier.ref
    assert line["materialSku"] == ""
    assert line["conversionId"] is None
    assert line["requiresConversion"] is True
    assert line["lineNote"].startswith("Definir insumo. NF: QUEIJO ARTESANAL")


@pytest.mark.django_db
def test_read_invoice_uses_configured_xml_directory(tmp_path, supplier, material, conversion):
    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(_nfe_xml(), encoding="utf-8")

    with override_settings(SHOPMAN_PURCHASE_NFE={"xml_dir": str(tmp_path)}):
        draft = read_invoice(access_key=VALID_ACCESS_KEY, qr_payload=VALID_ACCESS_KEY)

    assert draft["supplierRef"] == supplier.ref
    assert draft["lines"][0]["materialSku"] == material.sku
    assert draft["lines"][0]["conversionId"] == str(conversion.pk)


def test_extract_proc_nfe_xml_from_distribution_doczip():
    class DocZip:
        schema = "procNFe_v4.00.xsd"
        valueOf_ = base64.b64encode(gzip.compress(_nfe_xml().encode("utf-8"))).decode("ascii")

    class Lote:
        docZip = [DocZip()]

    class Resposta:
        cStat = "138"
        xMotivo = "Documento localizado"
        loteDistDFeInt = Lote()

    class Retorno:
        resposta = Resposta()

    assert _extract_proc_nfe_xml(Retorno(), access_key=VALID_ACCESS_KEY) == _nfe_xml()
