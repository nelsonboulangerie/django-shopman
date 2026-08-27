"""NF-e reader for the Compras receipt flow.

This module is an orchestrator adapter: it translates a real NF-e XML into the
Backstage purchase receipt draft. Buyman/Stockman/Craftsman stay agnostic.
"""

from __future__ import annotations

import base64
import logging
import re
import unicodedata
import zlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring as defused_fromstring
from django.apps import apps
from django.conf import settings
from django.db.models import Q

logger = logging.getLogger(__name__)

INVOICE_PRODUCT_MAP_KEYS = ("invoice_product_map", "nfe_product_map", "invoiceProducts", "nfeProducts")
# Fuzzy nunca preenche materialSku: vira sugestão visível que o operador aceita
# ou troca na tela. Por isso é seguro nascer ligado.
DEFAULT_FUZZY_MATCH_MIN_SCORE = 87
MATERIAL_CODE_KEYS = ("invoice_codes", "nfe_codes", "supplier_codes", "barcodes", "gtins", "invoice_names")
BASE_UNIT_ALIASES = {
    "KG": "kg",
    "KGM": "kg",
    "QUILO": "kg",
    "QUILOGRAMA": "kg",
    "G": "g",
    "GR": "g",
    "GRAMA": "g",
    "L": "l",
    "LT": "l",
    "LTR": "l",
    "LITRO": "l",
    "ML": "ml",
    "MILILITRO": "ml",
    "UN": "un",
    "UND": "un",
    "UNID": "un",
    "UNIDADE": "un",
}
PURCHASE_UNIT_WORDS = {
    "SC": "saco",
    "SACO": "saco",
    "CX": "caixa",
    "CAIXA": "caixa",
    "FD": "fardo",
    "FARDO": "fardo",
    "PCT": "pacote",
    "PACOTE": "pacote",
    "CT": "cartela",
    "CARTELA": "cartela",
    "PC": "peca",
    "PECA": "peca",
}


class PurchaseInvoiceConfigError(RuntimeError):
    """Raised when the configured NF-e reader cannot reach SEFAZ safely."""


class PurchaseInvoiceUnavailable(RuntimeError):
    """Raised when SEFAZ returned no full NF-e XML for the access key."""


@dataclass(frozen=True)
class NFeItem:
    number: str
    product_code: str
    ean: str
    name: str
    unit: str
    quantity: Decimal
    unit_value: Decimal
    total_value: Decimal
    ncm: str
    cfop: str
    expiry_date: str


def read_invoice(*, access_key: str, qr_payload: str) -> dict[str, Any]:
    """Read a scanned NF-e/NFC-e key into a purchase receipt draft."""
    key = _normalize_access_key(access_key)
    config = _get_config()
    xml = _local_xml_for_key(key, config) or _download_nfe_xml(key, config)
    return parse_nfe_xml_to_purchase_draft(xml, access_key=key)


def parse_nfe_xml_to_purchase_draft(xml: str | bytes, *, access_key: str = "") -> dict[str, Any]:
    """Parse an NF-e XML string into the Backstage purchase draft contract."""
    root = _xml_root(xml)
    inf = _find_desc(root, "infNFe")
    if inf is None:
        raise ValueError("XML de NF-e sem infNFe.")

    xml_key = _xml_access_key(root, inf)
    key = _normalize_access_key(access_key or xml_key) if (access_key or xml_key) else ""
    if key and xml_key and key != xml_key:
        raise ValueError("A chave informada nao pertence ao XML da NF-e.")

    ide = _find_child(inf, "ide")
    issuer = _find_child(inf, "emit")
    issuer_document = _digits(_first_text(issuer, "CNPJ", "CPF"))
    issuer_name = _text(issuer, "xNome") or "Fornecedor da NF"
    supplier = _supplier_by_document(issuer_document)
    number = _text(ide, "nNF")
    series = _text(ide, "serie")
    issued_at = (_text(ide, "dhEmi") or _text(ide, "dEmi"))[:10]
    total_value = _decimal(_text(_find_desc(inf, "ICMSTot"), "vNF"))

    items = [_item_from_det(det, index=index) for index, det in enumerate(_find_children(inf, "det"), start=1)]
    lines = [
        _receipt_line_from_item(item, index=index, supplier=supplier)
        for index, item in enumerate(items, start=1)
        if item.name or item.product_code
    ]

    note_parts = [f"NF {number or key[-9:]}" if (number or key) else "NF"]
    if series:
        note_parts[0] = f"{note_parts[0]}/{series}"
    note_parts.append(issuer_name)
    if issued_at:
        note_parts.append(issued_at)
    if total_value > 0:
        note_parts.append(f"total {_money_text(total_value)}")
    if supplier is None:
        note_parts.append("fornecedor nao cadastrado")

    return {
        "supplierRef": supplier.ref if supplier else "",
        "note": " - ".join(note_parts),
        "lines": lines,
        "issuer": {
            "document": issuer_document,
            "name": issuer_name,
            "tradeName": _text(issuer, "xFant"),
            "phone": _text(_find_child(issuer, "enderEmit"), "fone"),
        },
    }


def _download_nfe_xml(access_key: str, config: dict[str, Any]) -> str:
    recipient_document = _recipient_document(config)
    certificate_source = _certificate_source(config)
    if not recipient_document:
        raise PurchaseInvoiceConfigError("SHOPMAN_PURCHASE_NFE sem CNPJ/CPF do destinatario.")
    if certificate_source is None:
        raise PurchaseInvoiceConfigError("SHOPMAN_PURCHASE_NFE sem certificado A1/PFX do destinatario.")

    try:
        from erpbrasil.assinatura.certificado import Certificado
        from erpbrasil.edoc.mde import MDe, TransmissaoMDE
    except ImportError as exc:  # pragma: no cover - exercised in deploy/runtime readiness.
        raise PurchaseInvoiceConfigError("Instale erpbrasil.edoc para consultar Distribuicao DF-e.") from exc

    certificate = Certificado(certificate_source, str(config.get("certificate_password") or ""))
    mde = MDe(
        TransmissaoMDE(certificate),
        uf=int(str(config.get("uf") or access_key[:2] or "41")),
        ambiente=_erpbrasil_environment(config),
        mod=_document_model(access_key),
        # O schema distDFeInt do Ambiente Nacional aceita somente versao 1.01;
        # o default herdado de NFe ("4.00") faz a SEFAZ rejeitar com cStat 239.
        versao="1.01",
    )
    response = mde.consultar_distribuicao(recipient_document, chave=access_key)
    xml = _extract_proc_nfe_xml(response, access_key=access_key)
    if xml:
        return xml

    if _truthy(config.get("auto_manifest_ciencia")):
        logger.info("purchase_nfe.auto_manifest_ciencia access_key_suffix=%s", access_key[-8:])
        mde.ciencia_da_operacao(access_key, recipient_document)
        response = mde.consultar_distribuicao(recipient_document, chave=access_key)
        xml = _extract_proc_nfe_xml(response, access_key=access_key)
        if xml:
            return xml

    status = _response_status(response)
    raise PurchaseInvoiceUnavailable(
        f"Distribuicao DF-e nao retornou XML completo para a NF {access_key[-8:]}{status}."
    )


def _extract_proc_nfe_xml(response: Any, *, access_key: str = "") -> str | None:
    """Extract and gunzip the full nfeProc XML from an erpbrasil DF-e response."""
    if isinstance(response, bytes | str):
        text = _decode_text(response)
        if _looks_like_full_nfe_xml(text, access_key=access_key):
            return text
        return None

    resposta = getattr(response, "resposta", response)
    lote = getattr(resposta, "loteDistDFeInt", None)
    doc_zips = _as_list(getattr(lote, "docZip", None))
    full_xmls: list[str] = []
    for doc_zip in doc_zips:
        xml = _decode_doc_zip(doc_zip)
        if not xml:
            continue
        if _looks_like_full_nfe_xml(xml, access_key=access_key):
            full_xmls.append(xml)
    if not full_xmls:
        return None
    if access_key:
        for xml in full_xmls:
            if access_key in xml:
                return xml
    return full_xmls[0]


def _receipt_line_from_item(item: NFeItem, *, index: int, supplier: Any | None) -> dict[str, Any]:
    material, mapping = _material_for_item(item, supplier=supplier)
    suggestion = None if material else _material_suggestion(item.name)
    conversion = _conversion_for_item(item, material=material, supplier=supplier, mapping=mapping)
    requires_conversion = _requires_conversion(item, material=material, conversion=conversion)
    total_value = item.total_value if item.total_value > 0 else item.quantity * item.unit_value
    return {
        "id": f"nfe-{item.number or index}",
        "materialSku": material.sku if material else "",
        "suggestedMaterialSku": suggestion[0].sku if suggestion else "",
        "suggestionScore": suggestion[1] if suggestion else 0,
        "conversionId": str(conversion.pk) if conversion else None,
        "requiresConversion": requires_conversion,
        "purchaseQty": _decimal_text(item.quantity),
        "costInput": _money_text(total_value),
        "expiryDate": item.expiry_date,
        "lineNote": _line_note(item, material=material, requires_conversion=requires_conversion),
        "invoiceProductCode": item.product_code,
        "invoiceEan": item.ean,
        "checked": False,
    }


def _item_from_det(det: ET.Element, *, index: int) -> NFeItem:
    prod = _find_child(det, "prod")
    rastro = _find_desc(prod, "rastro")
    return NFeItem(
        number=str(det.attrib.get("nItem") or index),
        product_code=_text(prod, "cProd"),
        ean=_valid_gtin(_text(prod, "cEAN") or _text(prod, "cEANTrib") or _text(prod, "cBarra")),
        name=_text(prod, "xProd"),
        unit=_text(prod, "uCom") or _text(prod, "uTrib"),
        quantity=_decimal(_text(prod, "qCom") or _text(prod, "qTrib")),
        unit_value=_decimal(_text(prod, "vUnCom") or _text(prod, "vUnTrib")),
        total_value=_decimal(_text(prod, "vProd")),
        ncm=_text(prod, "NCM"),
        cfop=_text(prod, "CFOP"),
        expiry_date=_date_text(_text(rastro, "dVal")),
    )


def _material_for_item(item: NFeItem, *, supplier: Any | None) -> tuple[Any | None, Any | None]:
    mapping = _supplier_mapping_entry(item, supplier=supplier)
    mapped_sku = _mapping_material_sku(mapping)
    if mapped_sku:
        material = _material_by_sku(mapped_sku)
        if material:
            return material, mapping

    metadata_match = _material_by_metadata(item, supplier=supplier)
    if metadata_match:
        return metadata_match, mapping

    exact_name = _material_by_exact_name(item.name)
    if exact_name:
        return exact_name, mapping

    return None, mapping


def _conversion_for_item(
    item: NFeItem,
    *,
    material: Any | None,
    supplier: Any | None,
    mapping: Any | None,
) -> Any | None:
    if material is None:
        return None

    mapped = _mapped_conversion(mapping, material=material, supplier=supplier)
    if mapped:
        return mapped
    if _unit_matches_material(item.unit, material):
        return None
    text_match = _conversion_by_text(item, material=material, supplier=supplier)
    if text_match:
        return text_match
    existing = _single_existing_conversion_cost(material=material, supplier=supplier)
    if existing:
        return existing
    return None


def _mapped_conversion(mapping: Any | None, *, material: Any, supplier: Any | None) -> Any | None:
    if not isinstance(mapping, dict):
        return None
    conversion_id = _first_mapping_value(mapping, "conversionId", "conversion_id", "conversion", "conversionPk")
    if conversion_id:
        conversion = _conversion_queryset(material=material, supplier=supplier).filter(pk=conversion_id).first()
        if conversion:
            return conversion
    label = _first_mapping_value(mapping, "conversionLabel", "conversion_label", "unitLabel", "unit_label")
    if label:
        normalized = _normalize_text(label)
        for conversion in _conversion_queryset(material=material, supplier=supplier):
            if _normalize_text(conversion.label) == normalized:
                return conversion
    return None


def _conversion_by_text(item: NFeItem, *, material: Any, supplier: Any | None) -> Any | None:
    haystack = _normalize_text(" ".join(part for part in (item.name, item.unit) if part))
    unit_word = _purchase_unit_word(item.unit)
    for conversion in _conversion_queryset(material=material, supplier=supplier):
        label = _normalize_text(conversion.label)
        factor_tokens = _factor_tokens(conversion, material.unit)
        if label and label in haystack:
            return conversion
        if factor_tokens and any(token in haystack for token in factor_tokens):
            if not unit_word or unit_word in label:
                return conversion
        if unit_word and unit_word in label and item.quantity == Decimal("1"):
            return conversion
    return None


def _single_existing_conversion_cost(*, material: Any, supplier: Any | None) -> Any | None:
    if supplier is None:
        return None
    SupplierMaterialCost = apps.get_model("buyman", "SupplierMaterialCost")
    costs = list(
        SupplierMaterialCost.objects.filter(material=material, supplier=supplier, conversion__isnull=False)
        .select_related("conversion")
        .order_by("-is_preferred", "-updated_at")[:2]
    )
    return costs[0].conversion if len(costs) == 1 else None


def _conversion_queryset(*, material: Any, supplier: Any | None):
    MaterialConversion = apps.get_model("buyman", "MaterialConversion")
    query = MaterialConversion.objects.filter(material=material, is_active=True)
    if supplier is None:
        return query.filter(supplier__isnull=True)
    return query.filter(Q(supplier=supplier) | Q(supplier__isnull=True)).order_by("-supplier_id", "label")


def _requires_conversion(item: NFeItem, *, material: Any | None, conversion: Any | None) -> bool:
    if conversion is not None:
        return False
    if material is None:
        return bool(item.unit and _canonical_unit(item.unit) is None)
    return not _unit_matches_material(item.unit, material)


def _line_note(item: NFeItem, *, material: Any | None, requires_conversion: bool) -> str:
    details = [f"NF: {item.name}" if item.name else "NF: item sem descricao"]
    if item.product_code:
        details.append(f"cod {item.product_code}")
    if item.ean:
        details.append(f"EAN {item.ean}")
    if item.unit:
        details.append(f"unidade {item.unit}")
    if item.ncm:
        details.append(f"NCM {item.ncm}")
    if item.cfop:
        details.append(f"CFOP {item.cfop}")
    prefix = ""
    if material is None:
        prefix = "Definir insumo. "
    elif requires_conversion:
        prefix = "Definir conversao antes de confirmar. "
    return f"{prefix}{'; '.join(details)}."


def _supplier_mapping_entry(item: NFeItem, *, supplier: Any | None) -> Any | None:
    if supplier is None:
        return None
    mapping = _supplier_invoice_product_map(supplier)
    if not mapping:
        return None
    normalized_mapping = {_normalize_key(key): value for key, value in mapping.items()}
    for candidate in _item_lookup_keys(item):
        if candidate in mapping:
            return mapping[candidate]
        normalized = _normalize_key(candidate)
        if normalized in normalized_mapping:
            return normalized_mapping[normalized]
    return None


def _supplier_invoice_product_map(supplier: Any) -> dict[str, Any]:
    for meta in _metadata_scopes(supplier):
        for key in INVOICE_PRODUCT_MAP_KEYS:
            value = meta.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _mapping_material_sku(mapping: Any | None) -> str:
    if isinstance(mapping, str | int):
        return str(mapping).strip()
    if not isinstance(mapping, dict):
        return ""
    return str(_first_mapping_value(mapping, "materialSku", "material_sku", "sku", "material") or "").strip()


def _material_by_sku(sku: str) -> Any | None:
    Material = apps.get_model("buyman", "Material")
    return Material.objects.filter(sku=str(sku).strip(), is_active=True).first()


def _material_by_exact_name(name: str) -> Any | None:
    normalized = _normalize_text(name)
    if not normalized:
        return None
    Material = apps.get_model("buyman", "Material")
    for material in Material.objects.filter(is_active=True).only("sku", "name"):
        if _normalize_text(material.name) == normalized:
            return material
    return None


def _material_by_metadata(item: NFeItem, *, supplier: Any | None) -> Any | None:
    candidates = {_normalize_key(candidate) for candidate in _item_lookup_keys(item)}
    Material = apps.get_model("buyman", "Material")
    for material in Material.objects.filter(is_active=True):
        for token in _material_invoice_tokens(material, supplier=supplier):
            if _normalize_key(token) in candidates:
                return material
    return None


def _material_suggestion(name: str) -> tuple[Any, int] | None:
    """Fuzzy match the NF item name into a visible suggestion, never a fill.

    O nome de item de NF real é "nome do insumo + marca + embalagem"
    ("AZEITE DE OLIVA EXTRA VIRGEM ANDORINHA VD 500ML"). O WRatio penaliza a
    diferença de comprimento e TETA em 85,5 exatamente nesse caso — abaixo do
    limiar. Por isso a pontuação principal é cobertura de tokens: se todo token
    significativo do insumo aparece na descrição da NF (exato, ou por prefixo
    para abreviação de distribuidor: FERM~fermento, BIOL~biologico), vale 100.
    O WRatio fica de reforço para nomes de vários tokens; nome de UM token só
    ("Sal") nunca pontua por WRatio, senão SALGADINHO sugeriria Sal.
    """
    min_score = _fuzzy_match_min_score()
    normalized = _normalize_text(name)
    if min_score <= 0 or not normalized:
        return None
    try:
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover - optional runtime guard.
        return None

    item_tokens = set(normalized.split())
    best: tuple[float, int, Any] | None = None
    Material = apps.get_model("buyman", "Material")
    for material in Material.objects.filter(is_active=True).only("sku", "name"):
        material_name = _normalize_text(material.name)
        tokens = [token for token in material_name.split() if len(token) > 2 or token.isdigit()]
        if not tokens:
            continue
        covered = sum(1 for token in tokens if _token_in_item(token, item_tokens))
        if covered == len(tokens):
            score = 100.0
        elif len(tokens) == 1:
            continue
        else:
            score = float(fuzz.WRatio(normalized, material_name))
        if score < min_score:
            continue
        # Empate em 100 (ex.: "Azeite" e "Azeite extra virgem"): vence quem
        # cobre mais tokens — a evidência mais específica.
        if best is None or (score, covered) > (best[0], best[1]):
            best = (score, covered, material)
    if best is None:
        return None
    score, _, material = best
    rounded = int(round(score))
    logger.info("purchase_nfe.fuzzy_material_suggestion score=%s material=%s", rounded, material.sku)
    return material, rounded


def _token_in_item(token: str, item_tokens: set[str]) -> bool:
    if token in item_tokens:
        return True
    if len(token) < 4:
        return False
    return any(
        len(item_token) >= 4 and (item_token.startswith(token) or token.startswith(item_token))
        for item_token in item_tokens
    )


def _material_invoice_tokens(material: Any, *, supplier: Any | None) -> list[str]:
    tokens: list[str] = []
    for meta in _metadata_scopes(material):
        for key in MATERIAL_CODE_KEYS:
            tokens.extend(_metadata_tokens(meta.get(key), supplier=supplier))
    return tokens


def _metadata_tokens(value: Any, *, supplier: Any | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str | int | float):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list | tuple | set):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_metadata_tokens(item, supplier=supplier))
        return tokens
    if isinstance(value, dict):
        supplier_keys = _supplier_keys(supplier)
        if supplier_keys & {str(key) for key in value}:
            tokens: list[str] = []
            for key in supplier_keys:
                tokens.extend(_metadata_tokens(value.get(key), supplier=supplier))
            return tokens
        return [
            token
            for item in list(value.keys()) + list(value.values())
            for token in _metadata_tokens(item, supplier=supplier)
        ]
    return []


def _supplier_by_document(document: str) -> Any | None:
    if not document:
        return None
    Supplier = apps.get_model("buyman", "Supplier")
    for supplier in Supplier.objects.filter(is_active=True).only("ref", "document"):
        if _digits(supplier.document) == document:
            return supplier
    return None


def _local_xml_for_key(access_key: str, config: dict[str, Any]) -> str | None:
    xml_dir = str(config.get("xml_dir") or "").strip()
    if not xml_dir:
        return None
    root = Path(xml_dir)
    if not root.exists() or not root.is_dir():
        logger.warning("purchase_nfe.xml_dir_unavailable path=%s", root)
        return None
    for candidate in (
        root / f"{access_key}.xml",
        root / f"NFe{access_key}.xml",
        root / f"procNFe-{access_key}.xml",
        root / f"{access_key}-procNFe.xml",
    ):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    for candidate in sorted(root.glob("*.xml")):
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = candidate.read_text(encoding="latin-1")
        if access_key in text:
            return text
    return None


def _get_config() -> dict[str, Any]:
    return dict(getattr(settings, "SHOPMAN_PURCHASE_NFE", {}) or {})


def _recipient_document(config: dict[str, Any]) -> str:
    configured = _digits(config.get("recipient_document"))
    if configured:
        return configured
    focus = dict(getattr(settings, "SHOPMAN_FOCUS_NFE", {}) or {})
    focus_document = _digits(focus.get("cnpj_emitente"))
    if focus_document:
        return focus_document
    try:
        Shop = apps.get_model("shop", "Shop")
        shop = Shop.load()
    except Exception:
        logger.debug("purchase_nfe.shop_document_lookup_failed", exc_info=True)
        shop = None
    return _digits(getattr(shop, "document", ""))


def _certificate_source(config: dict[str, Any]) -> str | bytes | None:
    path = str(config.get("certificate_path") or "").strip()
    if path:
        return path
    encoded = str(config.get("certificate_pfx_base64") or "").strip()
    if encoded:
        return encoded.encode("ascii")
    return None


def _erpbrasil_environment(config: dict[str, Any]) -> str:
    value = str(config.get("environment") or "").strip().lower()
    if value in {"producao", "produção", "production", "prod", "1"}:
        return "1"
    return "2"


def _document_model(access_key: str) -> str:
    model = access_key[20:22]
    return model if model in {"55", "65"} else "55"


def _response_status(response: Any) -> str:
    resposta = getattr(response, "resposta", response)
    code = str(getattr(resposta, "cStat", "") or "").strip()
    reason = str(getattr(resposta, "xMotivo", "") or "").strip()
    if code or reason:
        return f" ({code} {reason})".rstrip()
    return ""


# O docZip vem do provedor fiscal, mas continua entrada externa: sem teto, um
# gzip malicioso de poucos KB infla para GB e derruba o worker na descompressão.
# 20MB cobre qualquer NF-e real com folga enorme.
MAX_DOC_XML_BYTES = 20 * 1024 * 1024


def _decode_doc_zip(doc_zip: Any) -> str:
    raw = getattr(doc_zip, "valueOf_", None)
    if raw is None:
        raw = getattr(doc_zip, "value", None)
    if raw is None:
        raw = str(doc_zip or "")
    try:
        payload = base64.b64decode(re.sub(r"\s+", "", _decode_text(raw)))
        try:
            # wbits=31 = gzip; decompressobj com max_length aplica o teto SEM
            # materializar o payload inflado inteiro (gzip.decompress não tem
            # limite e alocaria tudo antes de qualquer checagem).
            inflater = zlib.decompressobj(31)
            inflated = inflater.decompress(payload, MAX_DOC_XML_BYTES + 1)
            if len(inflated) > MAX_DOC_XML_BYTES:
                logger.warning("purchase_nfe.doczip_too_large")
                return ""
            payload = inflated
        except zlib.error:
            pass
        return payload.decode("utf-8", errors="replace")
    except Exception:
        logger.warning("purchase_nfe.doczip_decode_failed", exc_info=True)
        return ""


def _looks_like_full_nfe_xml(xml: str, *, access_key: str = "") -> bool:
    if access_key and access_key not in xml:
        return False
    return bool(re.search(r"<(?:\w+:)?nfeProc[\s>]|<(?:\w+:)?NFe[\s>]", xml))


def _xml_root(xml: str | bytes) -> ET.Element:
    try:
        # defusedxml: recusa DTD/entidades (XXE, billion laughs) em vez de
        # depender do comportamento do expat do runtime. Os ataques chegam como
        # DefusedXmlException (subclasse de ValueError).
        return defused_fromstring(xml)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError("XML de NF-e invalido.") from exc


def _xml_access_key(root: ET.Element, inf: ET.Element) -> str:
    for value in (inf.attrib.get("Id", ""), _text(_find_desc(root, "chNFe"), None)):
        match = re.search(r"\d{44}", value or "")
        if match:
            return match.group(0)
    return ""


def _find_desc(node: ET.Element | None, tag: str) -> ET.Element | None:
    if node is None:
        return None
    found = node.find(f".//{{*}}{tag}")
    if found is not None:
        return found
    return node.find(f".//{tag}")


def _find_child(node: ET.Element | None, tag: str) -> ET.Element | None:
    if node is None:
        return None
    found = node.find(f"{{*}}{tag}")
    if found is not None:
        return found
    return node.find(tag)


def _find_children(node: ET.Element | None, tag: str) -> list[ET.Element]:
    if node is None:
        return []
    children = list(node.findall(f"{{*}}{tag}"))
    if children:
        return children
    return list(node.findall(tag))


def _text(node: ET.Element | None, tag: str | None) -> str:
    target = node if tag is None else _find_child(node, tag)
    return str(target.text or "").strip() if target is not None else ""


def _first_text(node: ET.Element | None, *tags: str) -> str:
    for tag in tags:
        value = _text(node, tag)
        if value:
            return value
    return ""


def _date_text(value: str) -> str:
    value = str(value or "").strip()
    return value[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value) else ""


def _normalize_access_key(value: str) -> str:
    key = _digits(value)
    if not _valid_access_key(key):
        raise ValueError("Chave de acesso NF-e invalida.")
    return key


def _valid_access_key(key: str) -> bool:
    if not re.fullmatch(r"\d{44}", key):
        return False
    weights = []
    weight = 2
    for _ in range(43):
        weights.append(weight)
        weight = 2 if weight == 9 else weight + 1
    total = sum(int(digit) * weight for digit, weight in zip(reversed(key[:43]), weights, strict=True))
    remainder = total % 11
    check_digit = 0 if remainder in (0, 1) else 11 - remainder
    return check_digit == int(key[-1])


def _valid_gtin(value: str) -> str:
    digits = _digits(value)
    return digits if digits and set(digits) != {"0"} else ""


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _decimal(value: Any) -> Decimal:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f").rstrip("0").rstrip(".")


def _money_text(value: Decimal) -> str:
    if value <= 0:
        return ""
    return f"{value.quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _normalize_key(value: Any) -> str:
    return _normalize_text(value).replace(" ", "")


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _canonical_unit(value: str) -> str | None:
    return BASE_UNIT_ALIASES.get(_normalize_key(value).upper())


def _unit_matches_material(value: str, material: Any) -> bool:
    canonical = _canonical_unit(value)
    return bool(canonical and canonical == str(getattr(material, "unit", "")))


def _purchase_unit_word(value: str) -> str:
    return PURCHASE_UNIT_WORDS.get(_normalize_key(value).upper(), "")


def _factor_tokens(conversion: Any, unit: str) -> set[str]:
    factor = _decimal_text(Decimal(conversion.to_base_factor))
    return {_normalize_text(f"{factor} {unit}"), _normalize_text(f"{factor}{unit}")}


def _item_lookup_keys(item: NFeItem) -> list[str]:
    return [value for value in (item.product_code, item.ean, item.name) if value]


def _metadata_scopes(obj: Any) -> list[dict[str, Any]]:
    metadata = getattr(obj, "metadata", None)
    if not isinstance(metadata, dict):
        return []
    nested = metadata.get("purchase")
    if isinstance(nested, dict):
        return [nested, metadata]
    return [metadata]


def _supplier_keys(supplier: Any | None) -> set[str]:
    if supplier is None:
        return {"default", "*"}
    return {
        str(getattr(supplier, "ref", "") or ""),
        _digits(getattr(supplier, "document", "")),
        "default",
        "*",
    }


def _first_mapping_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _fuzzy_match_min_score() -> int:
    config = _get_config()
    if "fuzzy_match_min_score" not in config:
        return DEFAULT_FUZZY_MATCH_MIN_SCORE
    try:
        return int(config.get("fuzzy_match_min_score") or 0)
    except (TypeError, ValueError):
        return 0


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return list(value)
    return [value]


def _decode_text(value: bytes | str | Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim", "on"}
