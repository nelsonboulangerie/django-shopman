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


def _nfe_xml(
    *,
    access_key: str = VALID_ACCESS_KEY,
    product_code: str = "FAR-25",
    product_name: str = "FARINHA T65 25KG",
    unit: str = "SC",
    ean: str = "SEM GTIN",
) -> str:
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
          <cEAN>{ean}</cEAN>
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
            "suggestedMaterialSku": "",
            "suggestionScore": 0,
            "conversionId": str(conversion.pk),
            "requiresConversion": False,
            "purchaseQty": "2",
            "costInput": "360,00",
            "expiryDate": "",
            "lineNote": "NF: FARINHA T65 25KG; cod FAR-25; unidade SC; NCM 11010010; CFOP 5102.",
            "invoiceProductCode": "FAR-25",
            "invoiceEan": "",
            "checked": False,
        }
    ]


@pytest.mark.django_db
def test_parse_nfe_xml_keeps_unmapped_item_visible_and_blocked(supplier):
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="QJO-ART", product_name="QUEIJO ARTESANAL MEIA CURA", unit="PC", ean="7891234567895"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert draft["supplierRef"] == supplier.ref
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == ""
    assert line["suggestionScore"] == 0
    assert line["conversionId"] is None
    assert line["requiresConversion"] is True
    assert line["lineNote"].startswith("Definir insumo. NF: QUEIJO ARTESANAL")
    assert line["invoiceProductCode"] == "QJO-ART"
    assert line["invoiceEan"] == "7891234567895"


@pytest.mark.django_db
def test_parse_nfe_xml_turns_fuzzy_match_into_visible_suggestion(supplier):
    Material.objects.create(sku="FARINHA-TRIGO-T65", name="Farinha de trigo T65", unit="kg")

    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="FT65-SC", product_name="FARINHA DE TRIGO T65 SACO 25KG"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == "FARINHA-TRIGO-T65"
    assert line["suggestionScore"] >= 87
    assert line["conversionId"] is None
    assert line["lineNote"].startswith("Definir insumo. NF: FARINHA DE TRIGO T65 SACO 25KG")


@pytest.mark.django_db
def test_material_name_inside_long_distributor_description_is_suggested(supplier):
    """O caso real que o WRatio puro deixava passar: nome + marca + embalagem.

    "AZEITE DE OLIVA EXTRA VIRGEM ANDORINHA VD 500ML" contra "Azeite extra
    virgem" pontua 85,5 no WRatio (redutor de comprimento) — abaixo de 87.
    A cobertura de tokens reconhece o insumo contido na descrição.
    """
    Material.objects.create(sku="AZEITE", name="Azeite extra virgem", unit="l")

    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="AZ-500", product_name="AZEITE DE OLIVA EXTRA VIRGEM ANDORINHA VD 500ML", unit="UN"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == "AZEITE"
    assert line["suggestionScore"] == 100


@pytest.mark.django_db
def test_distributor_abbreviations_still_reach_the_suggestion(supplier):
    Material.objects.create(sku="FERMENTO-BIO", name="Fermento biológico", unit="g")

    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="FERM-500", product_name="FERM BIOL SECO INST FLEISCHMANN 500G", unit="UN"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == "FERMENTO-BIO"
    assert line["suggestionScore"] == 100


@pytest.mark.django_db
def test_single_token_material_never_matches_by_character_overlap(supplier):
    Material.objects.create(sku="SAL", name="Sal", unit="kg")

    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="SGD-50", product_name="SALGADINHO DE MILHO 50G", unit="UN"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == ""
    assert line["suggestionScore"] == 0


@pytest.mark.django_db
def test_tie_between_generic_and_specific_material_prefers_the_specific(supplier):
    Material.objects.create(sku="AZEITE-COMUM", name="Azeite", unit="l")
    Material.objects.create(sku="AZEITE-EV", name="Azeite extra virgem", unit="l")

    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="AZ-500", product_name="AZEITE DE OLIVA EXTRA VIRGEM 500ML", unit="UN"),
        access_key=VALID_ACCESS_KEY,
    )

    assert draft["lines"][0]["suggestedMaterialSku"] == "AZEITE-EV"


@pytest.mark.django_db
def test_fuzzy_suggestion_respects_explicit_zero_threshold(supplier):
    Material.objects.create(sku="FARINHA-TRIGO-T65", name="Farinha de trigo T65", unit="kg")

    with override_settings(SHOPMAN_PURCHASE_NFE={"fuzzy_match_min_score": 0}):
        draft = parse_nfe_xml_to_purchase_draft(
            _nfe_xml(product_code="FT65-SC", product_name="FARINHA DE TRIGO T65 SACO 25KG"),
            access_key=VALID_ACCESS_KEY,
        )

    line = draft["lines"][0]
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == ""
    assert line["suggestionScore"] == 0


@pytest.mark.django_db
def test_fuzzy_suggestion_defaults_on_when_config_omits_threshold(supplier):
    Material.objects.create(sku="FARINHA-TRIGO-T65", name="Farinha de trigo T65", unit="kg")

    with override_settings(SHOPMAN_PURCHASE_NFE={}):
        draft = parse_nfe_xml_to_purchase_draft(
            _nfe_xml(product_code="FT65-SC", product_name="FARINHA DE TRIGO T65 SACO 25KG"),
            access_key=VALID_ACCESS_KEY,
        )

    line = draft["lines"][0]
    assert line["materialSku"] == ""
    assert line["suggestedMaterialSku"] == "FARINHA-TRIGO-T65"
    assert line["suggestionScore"] >= 87


@pytest.mark.django_db
def test_exact_name_match_still_fills_material_without_suggestion(supplier):
    material = Material.objects.create(sku="FARINHA-TRIGO-T65", name="Farinha de trigo T65", unit="kg")

    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_code="FT65-SC", product_name="FARINHA DE TRIGO T65"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == material.sku
    assert line["suggestedMaterialSku"] == ""
    assert line["suggestionScore"] == 0


@pytest.mark.django_db
def test_read_invoice_uses_configured_xml_directory(tmp_path, supplier, material, conversion):
    (tmp_path / f"{VALID_ACCESS_KEY}.xml").write_text(_nfe_xml(), encoding="utf-8")

    with override_settings(SHOPMAN_PURCHASE_NFE={"xml_dir": str(tmp_path)}):
        draft = read_invoice(access_key=VALID_ACCESS_KEY, qr_payload=VALID_ACCESS_KEY)

    assert draft["supplierRef"] == supplier.ref
    assert draft["lines"][0]["materialSku"] == material.sku
    assert draft["lines"][0]["conversionId"] == str(conversion.pk)


@pytest.mark.django_db
def test_download_builds_mde_with_dist_dfe_schema_version(monkeypatch):
    captured: dict[str, object] = {}

    class FakeMDe:
        def __init__(self, transmissao, **kwargs):
            captured.update(kwargs)

        def consultar_distribuicao(self, recipient, chave):
            captured["chave"] = chave
            return _nfe_xml(access_key=chave)

    import erpbrasil.assinatura.certificado as certificado_module
    import erpbrasil.edoc.mde as mde_module

    monkeypatch.setattr(mde_module, "MDe", FakeMDe)
    monkeypatch.setattr(mde_module, "TransmissaoMDE", lambda certificate: certificate)
    monkeypatch.setattr(certificado_module, "Certificado", lambda source, password: object())

    config = {
        "recipient_document": "99999999000191",
        "certificate_pfx_base64": base64.b64encode(b"pfx-bytes").decode("ascii"),
        "certificate_password": "x",
        "uf": "41",
        "environment": "producao",
    }
    with override_settings(SHOPMAN_PURCHASE_NFE=config):
        draft = read_invoice(access_key=VALID_ACCESS_KEY, qr_payload=VALID_ACCESS_KEY)

    assert captured["versao"] == "1.01"
    assert captured["chave"] == VALID_ACCESS_KEY
    assert draft["lines"]


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


def test_xml_root_refuses_dtd_and_entities():
    """XXE/billion-laughs chegam como DTD — o parser recusa em vez de expandir."""
    from shopman.shop.adapters.purchase_invoice_nfe import _xml_root

    hostile = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE nfeProc [<!ENTITY x "AAAA"><!ENTITY y "&x;&x;&x;&x;">]>'
        "<nfeProc>&y;</nfeProc>"
    )
    with pytest.raises(ValueError):
        _xml_root(hostile)


def test_doczip_over_the_cap_is_refused():
    """Bomba de descompressão: gzip pequeno que infla além do teto vira draft vazio."""
    from shopman.shop.adapters.purchase_invoice_nfe import (
        MAX_DOC_XML_BYTES,
        _decode_doc_zip,
    )

    class DocZip:
        valueOf_ = base64.b64encode(
            gzip.compress(b"A" * (MAX_DOC_XML_BYTES + 1024))
        ).decode("ascii")

    assert _decode_doc_zip(DocZip()) == ""


def test_doczip_within_the_cap_still_decodes():
    from shopman.shop.adapters.purchase_invoice_nfe import _decode_doc_zip

    class DocZip:
        valueOf_ = base64.b64encode(gzip.compress(b"<NFe>ok</NFe>")).decode("ascii")

    assert _decode_doc_zip(DocZip()) == "<NFe>ok</NFe>"
