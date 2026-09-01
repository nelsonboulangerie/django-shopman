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
    quantity: str = "2.0000",
    unit_value: str = "180.0000000000",
    total: str = "360.00",
    tax_unit: str | None = "KG",
    tax_quantity: str = "50.0000",
    tax_unit_value: str = "7.2000000000",
    ean: str = "SEM GTIN",
    rastro: str = "",
) -> str:
    """NF-e de entrada com os DOIS eixos, que e como a nota real chega.

    ``tax_unit=None`` remove o par tributavel inteiro — nota degradada, para
    provar que a leitura nao passa a depender dele.
    """
    tax_block = (
        ""
        if tax_unit is None
        else f"""
          <uTrib>{tax_unit}</uTrib>
          <qTrib>{tax_quantity}</qTrib>
          <vUnTrib>{tax_unit_value}</vUnTrib>"""
    )
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
          <qCom>{quantity}</qCom>
          <vUnCom>{unit_value}</vUnCom>{tax_block}
          <vProd>{total}</vProd>{rastro}
        </prod>
      </det>
      <total>
        <ICMSTot>
          <vNF>{total}</vNF>
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
        ref="moinho-sp",
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
            "conversionSuggestion": None,
            "purchaseQty": "2",
            "costInput": "360,00",
            "expiryDate": "",
            "expiryFromInvoice": False,
            "invoiceLot": "",
            # A ocorrencia nasce VAZIA: e o campo do operador, nao o despejo da NF.
            "lineNote": "",
            "invoiceDescription": "FARINHA T65 25KG",
            "invoiceQty": "2",
            "invoiceUnit": "SC",
            "invoiceTaxQty": "50",
            "invoiceTaxUnit": "KG",
            "invoiceTotal": "360,00",
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
    assert line["lineNote"] == ""
    assert line["invoiceDescription"] == "QUEIJO ARTESANAL MEIA CURA"
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
    assert line["invoiceDescription"] == "FARINHA DE TRIGO T65 SACO 25KG"


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


@pytest.fixture
def fermento(db):
    """Insumo pesado em kg — e comprado em pacote. E onde os dois eixos brigam."""
    return Material.objects.create(
        sku="FERMENTO-BIO",
        name="Fermento biologico",
        unit="kg",
        metadata={"purchase": {"invoice_codes": ["FERM-500"]}},
    )


@pytest.mark.django_db
def test_commercial_and_tax_axes_derive_a_conversion_suggestion(supplier, fermento):
    """O caso do dono (QA no alpha, 27/08): 10 UNIDADES viravam 10 kg.

    A nota traz os dois eixos — 10 UN no comercial, 5 KG no tributavel — e o
    fator convencionado sai da divisao: 1 UN = 0,5 kg. O adapter propoe, mostra
    de onde tirou, e nao grava nada.
    """
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(
            product_code="FERM-500",
            product_name="FERM BIOL FRESCO MAURI 500G",
            unit="UN",
            quantity="10.0000",
            unit_value="6.0000000000",
            total="60.00",
            tax_unit="KG",
            tax_quantity="5.0000",
            tax_unit_value="12.0000000000",
        ),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == fermento.sku
    # A quantidade continua sendo a comercial: 10 pacotes, nao 10 kg.
    assert line["purchaseQty"] == "10"
    assert line["conversionId"] is None
    assert line["requiresConversion"] is True
    assert line["conversionSuggestion"] == {
        "label": "Un 500 g",
        "factor": "0.5",
        "kind": "conventional",
        "source": "invoice-tax-pair",
        "note": "A NF diz 10 UN = 5 KG (12,00 por KG), então 1 UN = 0,5 kg.",
    }
    # A linha carrega o que a NF diz, para a tela poder ancorar o item.
    assert line["invoiceDescription"] == "FERM BIOL FRESCO MAURI 500G"
    assert (line["invoiceQty"], line["invoiceUnit"]) == ("10", "UN")
    assert (line["invoiceTaxQty"], line["invoiceTaxUnit"]) == ("5", "KG")
    # A nota SUGERE, o dono confirma: nada entrou na tabela.
    assert MaterialConversion.objects.count() == 0


@pytest.mark.django_db
def test_coherent_axes_suggest_nothing(supplier, material):
    """Nota cujos dois eixos dizem a mesma coisa nao tem fator a propor."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(
            product_code="FAR-25",
            product_name="FARINHA T65",
            unit="KG",
            quantity="25.0000",
            tax_unit="KG",
            tax_quantity="25.0000",
        ),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == material.sku
    assert line["purchaseQty"] == "25"
    assert line["requiresConversion"] is False
    assert line["conversionSuggestion"] is None


@pytest.mark.django_db
def test_zero_commercial_quantity_falls_back_to_the_whole_tax_axis(supplier, material):
    """Eixo comercial zerado nao divide por zero: o item passa a ler o outro par INTEIRO."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(unit="SC", quantity="0.0000", tax_unit="KG", tax_quantity="50.0000"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["invoiceUnit"] == "KG"
    assert line["purchaseQty"] == "50"
    assert line["requiresConversion"] is False
    assert line["conversionSuggestion"] is None


@pytest.mark.django_db
def test_note_without_a_usable_pair_refuses_and_says_what_to_register(supplier, material):
    """R4: sem fator declarado o sistema RECUSA — e a recusa diz o que cadastrar."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_name="FARINHA T65 ESPECIAL", unit="CX", quantity="3.0000", tax_unit=None),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["materialSku"] == material.sku
    assert line["requiresConversion"] is True
    assert line["conversionSuggestion"] is None
    assert (line["invoiceQty"], line["invoiceUnit"]) == ("3", "CX")
    # Sem par tributavel util, nao ha o que mostrar do outro eixo.
    assert (line["invoiceTaxQty"], line["invoiceTaxUnit"]) == ("", "")


@pytest.mark.django_db
def test_description_grams_are_the_secondary_signal(supplier, fermento):
    """Par tributavel inutil (repete o comercial) — a gramatura do xProd responde."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(
            product_code="FERM-500",
            product_name="FERM BIOL FRESCO MAURI 500G",
            unit="UN",
            quantity="10.0000",
            tax_unit="UN",
            tax_quantity="10.0000",
            tax_unit_value="0",
        ),
        access_key=VALID_ACCESS_KEY,
    )

    suggestion = draft["lines"][0]["conversionSuggestion"]
    assert suggestion["source"] == "product-description"
    assert suggestion["factor"] == "0.5"
    assert suggestion["label"] == "Un 500 g"
    assert suggestion["note"] == "A descrição da NF diz 500 g, então 1 UN = 0,5 kg."


@pytest.mark.django_db
def test_invoice_unit_the_physics_reaches_converts_the_quantity(supplier, material):
    """kg↔g e fisica, nao convencao: converte sozinho e nao pede conversao a ninguem."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(product_name="FARINHA T65", unit="G", quantity="5000.0000", tax_unit="KG", tax_quantity="5.0000"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["purchaseQty"] == "5"
    assert line["requiresConversion"] is False
    assert line["conversionId"] is None
    assert line["conversionSuggestion"] is None


@pytest.mark.django_db
def test_note_that_contradicts_the_declared_conversion_shows_the_divergence(supplier, material, conversion):
    """Saco declarado de 25 kg, nota dizendo 20: o alerta de ordem de grandeza da ADR-024."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(unit="SC", quantity="2.0000", tax_unit="KG", tax_quantity="40.0000"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["conversionId"] == str(conversion.pk)
    assert line["requiresConversion"] is False
    assert line["conversionSuggestion"]["factor"] == "20"
    assert line["conversionSuggestion"]["label"] == "Saco 20 kg"


@pytest.mark.django_db
def test_real_lactalis_invoice_line_from_the_owner_qa(supplier):
    """Regressao com a linha REAL da nota que o dono mandou (QA de 27/08/2026).

    Identificadores da padaria e a chave estao trocados; o que importa para a
    calibracao veio da nota como esta: a descricao do emissor, o vocabulario de
    embalagem (``CX``) e os dois eixos (7 CX / 35 KG). Foi este item que mostrou
    o buraco que faltava: "MANTEIGA S/SAL CX 5 KG PRESIDENT TEU" nao casa com
    "Manteiga francesa" do cadastro, entao o scan nao tem insumo — e sem insumo
    nao ha unidade-base para o fator existir. A linha tem de sair carregando os
    dois eixos, para o operador poder escolher o insumo e o servidor derivar
    "1 caixa = 5 kg" depois (ver o teste do endpoint no backstage).
    """
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(
            product_code="610402075",
            product_name="MANTEIGA S/SAL CX 5 KG PRESIDENT TEU",
            unit="CX",
            quantity="7.0000",
            unit_value="219.100000",
            total="1533.70",
            tax_unit="KG",
            tax_quantity="35.0000",
            tax_unit_value="43.8200000",
            ean="7891097101342",
        ),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["invoiceDescription"] == "MANTEIGA S/SAL CX 5 KG PRESIDENT TEU"
    assert (line["invoiceQty"], line["invoiceUnit"]) == ("7", "CX")
    assert (line["invoiceTaxQty"], line["invoiceTaxUnit"]) == ("35", "KG")
    assert line["purchaseQty"] == "7"
    assert line["invoiceTotal"] == "1533,70"
    # Sem insumo casado, a linha trava — e trava carregando o que precisa para
    # ser destravada num gesto, em vez de mandar o operador para o Admin.
    assert line["materialSku"] == ""
    assert line["requiresConversion"] is True


@pytest.mark.django_db
def test_invoice_axes_derive_the_conversion_once_a_material_exists(supplier):
    """O mesmo item, agora com insumo: o par da nota vira "Caixa 5 kg"."""
    from shopman.shop.adapters.purchase_invoice_nfe import conversion_from_invoice_axes

    manteiga = Material.objects.create(sku="MANTEIGA-FR", name="Manteiga francesa", unit="kg")

    suggestion = conversion_from_invoice_axes(
        material=manteiga,
        quantity=Decimal("7"),
        unit="CX",
        tax_quantity=Decimal("35"),
        tax_unit="KG",
        name="MANTEIGA S/SAL CX 5 KG PRESIDENT TEU",
    )

    assert suggestion is not None
    assert suggestion.label == "Caixa 5 kg"
    assert suggestion.factor == Decimal("5")
    assert suggestion.source == "invoice-tax-pair"
    assert suggestion.note == "A NF diz 7 CX = 35 KG, então 1 CX = 5 kg."


def _rastro(*lots: tuple[str, str]) -> str:
    """Grupo `rastro` da NF-e: pares (numero do lote, validade)."""
    return "".join(
        f"""
          <rastro><nLote>{lot}</nLote><qLote>1.0000</qLote><dVal>{expiry}</dVal></rastro>"""
        for lot, expiry in lots
    )


@pytest.mark.django_db
def test_invoice_lot_and_expiry_come_from_the_note(supplier, material):
    """Validade e lote existem na NF-e (`rastro`) e nao precisam ser digitados."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(rastro=_rastro(("L2408A", "2027-02-25"))),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["expiryDate"] == "2027-02-25"
    assert line["expiryFromInvoice"] is True
    assert line["invoiceLot"] == "L2408A"


@pytest.mark.django_db
def test_several_lots_keep_the_one_that_expires_first(supplier, material):
    """Manda a validade mais CURTA, nao a primeira do XML.

    A ordem em que o emissor escreveu os lotes nao e informacao. Quem governa o
    que entra e o que vence antes — e o numero do lote tem de sair do MESMO
    grupo, senao a rastreabilidade fica falsa.
    """
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(rastro=_rastro(("L-TARDE", "2027-06-30"), ("L-CEDO", "2027-02-25"), ("L-MEIO", "2027-04-10"))),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["expiryDate"] == "2027-02-25"
    assert line["invoiceLot"] == "L-CEDO"


@pytest.mark.django_db
def test_lot_without_expiry_still_travels(supplier, material):
    """`rastro` so com numero de lote ainda vale pela rastreabilidade."""
    draft = parse_nfe_xml_to_purchase_draft(
        _nfe_xml(rastro="\n          <rastro><nLote>L2408A</nLote><qLote>1.0000</qLote></rastro>"),
        access_key=VALID_ACCESS_KEY,
    )

    line = draft["lines"][0]
    assert line["expiryDate"] == ""
    assert line["expiryFromInvoice"] is False
    assert line["invoiceLot"] == "L2408A"


@pytest.mark.django_db
def test_note_without_rastro_leaves_expiry_to_the_operator(supplier, material):
    """O caso comum: `rastro` e opcional, e a nota da Lactalis nao trazia."""
    draft = parse_nfe_xml_to_purchase_draft(_nfe_xml(), access_key=VALID_ACCESS_KEY)

    line = draft["lines"][0]
    assert line["expiryDate"] == ""
    assert line["expiryFromInvoice"] is False
    assert line["invoiceLot"] == ""
