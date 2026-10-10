"""Read-only Day-1 audit for a normalized operational catalog candidate.

The consolidated Nelson catalog is an input to a decision, not an instruction
to mutate the database.  This module turns that candidate and a database
snapshot into a deterministic report that can be reviewed before any importer
or publication action exists.
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from shopman.offerman import gtin_is_valid

CATALOG_AUDIT_SCHEMA_VERSION = "shopman.catalog-day1-audit/v1"
REQUIRED_COLUMNS = frozenset(
    {
        "sku",
        "nome_consolidado",
        "situacao_consolidado",
        "preco_consolidado_brl",
        "unidade_consolidado",
    }
)
TARGET_STATUSES = frozenset({"ativo", "novo"})
RESTRICTIVE_STATUSES = frozenset({"despublicar", "excluir", "adicional", "insumo"})
SUPPORTED_UNITS = frozenset({"un", "kg", "g", "l", "lt", "ml"})
NCM_RE = re.compile(r"^\d{8}$")
CEST_RE = re.compile(r"^\d{7}$")


class CatalogAuditError(ValueError):
    """The candidate cannot be audited without guessing its contract."""


@dataclass(frozen=True)
class CatalogSnapshot:
    """Operational state used by the pure evaluator, keyed by SKU."""

    products: dict[str, dict[str, Any]]
    materials: dict[str, dict[str, Any]]
    active_recipe_skus: frozenset[str]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _fold(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value))
    return " ".join("".join(char for char in normalized if not unicodedata.combining(char)).lower().split())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _price_cents(value: Any) -> tuple[int | None, str | None]:
    raw = _text(value).replace("R$", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        price = Decimal(raw)
    except InvalidOperation:
        return None, "Preço ausente ou inválido."
    cents = price * 100
    if price <= 0:
        return None, "Preço deve ser maior que zero."
    if cents != cents.to_integral_value():
        return None, "Preço deve ter no máximo duas casas decimais."
    return int(cents), None


def _positive_int(value: Any) -> tuple[int | None, str | None]:
    raw = _text(value)
    if not raw:
        return None, None
    try:
        parsed = int(Decimal(raw.replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None, "Peso deve ser um inteiro positivo em gramas."
    if parsed <= 0:
        return None, "Peso deve ser um inteiro positivo em gramas."
    return parsed, None


def read_catalog_candidate(path: str | Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Read the normalized CSV contract without returning its filesystem path."""

    source = Path(path)
    if not source.is_file():
        raise CatalogAuditError("O CSV normalizado não existe ou não é arquivo regular.")
    try:
        sample = source.read_text(encoding="utf-8-sig")[:65536]
    except UnicodeDecodeError as exc:
        raise CatalogAuditError("O CSV normalizado deve usar UTF-8.") from exc
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        columns = [str(column or "").strip() for column in (reader.fieldnames or [])]
        if not columns or not all(columns) or len(columns) != len(set(columns)):
            raise CatalogAuditError("Cabeçalho vazio, duplicado ou inválido.")
        missing = sorted(REQUIRED_COLUMNS - set(columns))
        if missing:
            raise CatalogAuditError(f"Colunas obrigatórias ausentes: {', '.join(missing)}.")
        rows = []
        for raw in reader:
            row = {column: _text(raw.get(column)) for column in columns}
            if any(row.values()):
                rows.append(row)
    return rows, {
        "sha256": _sha256(source),
        "logical_name": source.name,
        "columns": columns,
        "rows": len(rows),
    }

def database_catalog_snapshot() -> CatalogSnapshot:
    """Capture only operational catalog fields; never writes or locks rows."""

    from shopman.buyman.models import Material
    from shopman.craftsman.models import Recipe
    from shopman.offerman import get_social_attributes
    from shopman.offerman.models import CollectionItem, ListingItem, Product

    products: dict[str, dict[str, Any]] = {}
    for product in Product.objects.all().iterator():
        social = get_social_attributes(product)
        fiscal = (product.metadata or {}).get("fiscal") or {}
        products[str(product.sku)] = {
            "name": product.name,
            "short_description": product.short_description,
            "unit": product.unit,
            "unit_weight_g": product.unit_weight_g,
            "base_price_q": product.base_price_q,
            "is_published": product.is_published,
            "is_sellable": product.is_sellable,
            "image_url": product.image_url,
            "ncm": _text(fiscal.get("ncm") or fiscal.get("codigo_ncm")),
            "cest": _text(fiscal.get("cest")),
            "brand": social.brand,
            "gtin": social.gtin,
            "collections": [],
            "live_listing": False,
        }

    for sku, collection_ref in CollectionItem.objects.values_list("product__sku", "collection__ref"):
        if str(sku) in products:
            products[str(sku)]["collections"].append(str(collection_ref))
    for sku in ListingItem.objects.filter(
        listing__is_active=True,
        is_published=True,
        is_sellable=True,
    ).values_list("product__sku", flat=True):
        if str(sku) in products:
            products[str(sku)]["live_listing"] = True

    materials = {
        str(material.sku): {"unit": material.unit, "is_active": material.is_active}
        for material in Material.objects.all().iterator()
    }
    active_recipe_skus = frozenset(
        str(sku) for sku in Recipe.objects.filter(is_active=True).values_list("output_sku", flat=True)
    )
    return CatalogSnapshot(products=products, materials=materials, active_recipe_skus=active_recipe_skus)


def _issue(
    code: str,
    severity: str,
    field: str,
    message: str,
    *,
    expected: Any = None,
    observed: Any = None,
) -> dict[str, Any]:
    item = {"code": code, "severity": severity, "field": field, "message": message}
    if expected not in (None, ""):
        item["expected"] = expected
    if observed not in (None, ""):
        item["observed"] = observed
    return item


def _requires_recipe(row: dict[str, str]) -> bool:
    declared = _fold(row.get("receita_consolidado"))
    if declared in {"sim", "s", "yes", "1", "true"}:
        return True
    if declared in {"nao", "n", "no", "0", "false"}:
        return False
    origin = _fold(row.get("origem"))
    operating_profile = _fold(row.get("perfil_fiscal"))
    return operating_profile in {"producao", "producao propria"} or origin in {
        "producao",
        "producao propria",
        "casa",
    }


def _compare(
    issues: list[dict[str, Any]], field: str, expected: Any, observed: Any, *, code: str = "authority_drift"
) -> None:
    if expected not in (None, "") and expected != observed:
        issues.append(
            _issue(
                code,
                "review",
                field,
                "Divergência contra a autoridade Catálogo Nelson (consolidado).",
                expected=expected,
                observed=observed,
            )
        )


def audit_catalog_candidate(
    rows: list[dict[str, str]], snapshot: CatalogSnapshot, *, source: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate a candidate deterministically; no ORM call or mutation occurs."""

    results: list[dict[str, Any]] = []
    seen: Counter[str] = Counter(_text(row.get("sku")).upper() for row in rows if _text(row.get("sku")))

    for number, row in enumerate(rows, start=2):
        sku = _text(row.get("sku")).upper()
        status = _fold(row.get("situacao_consolidado"))
        name = _text(row.get("nome_consolidado"))
        unit = _fold(row.get("unidade_consolidado"))
        issues: list[dict[str, Any]] = []
        price_q, price_error = _price_cents(row.get("preco_consolidado_brl"))
        weight_g, weight_error = _positive_int(row.get("peso_g_consolidado"))
        product = snapshot.products.get(sku)
        material = snapshot.materials.get(sku)

        if not sku:
            issues.append(_issue("missing_sku", "block", "sku", "SKU é obrigatório."))
        elif seen[sku] > 1:
            issues.append(_issue("duplicate_sku", "block", "sku", "SKU duplicado no candidato."))
        if not name:
            issues.append(_issue("missing_name", "block", "nome_consolidado", "Nome é obrigatório."))
        if status not in TARGET_STATUSES | RESTRICTIVE_STATUSES:
            issues.append(
                _issue(
                    "owner_status_decision",
                    "decision",
                    "situacao_consolidado",
                    "Situação não determina inclusão nem retirada do mix Day-1.",
                    observed=status or "vazio",
                )
            )
        if status in TARGET_STATUSES:
            if price_error:
                issues.append(_issue("invalid_price", "block", "preco_consolidado_brl", price_error))
            if unit not in SUPPORTED_UNITS:
                issues.append(
                    _issue(
                        "invalid_unit",
                        "block",
                        "unidade_consolidado",
                        "Unidade ausente ou não suportada.",
                        observed=unit,
                    )
                )
        if weight_error:
            issues.append(_issue("invalid_weight", "block", "peso_g_consolidado", weight_error))

        ncm = re.sub(r"\D", "", _text(row.get("ncm")))
        cest = re.sub(r"\D", "", _text(row.get("cest")))
        gtin = re.sub(r"\D", "", _text(row.get("gtin")))
        if _text(row.get("ncm")) and not NCM_RE.fullmatch(ncm):
            issues.append(_issue("invalid_ncm", "block", "ncm", "NCM deve ter 8 dígitos."))
        if _text(row.get("cest")) and not CEST_RE.fullmatch(cest):
            issues.append(_issue("invalid_cest", "block", "cest", "CEST deve ter 7 dígitos."))
        if _text(row.get("gtin")) and not gtin_is_valid(gtin):
            issues.append(_issue("invalid_gtin", "block", "gtin", "GTIN tem formato ou dígito verificador inválido."))

        if status in TARGET_STATUSES:
            for field, message in (
                ("ncm", "NCM ainda não foi confirmado."),
                ("marca", "Marca ainda não foi confirmada."),
                ("copy_curta", "Copy curta ainda não foi curada."),
                ("foto_consolidado", "Imagem ainda não foi curada."),
            ):
                if not _text(row.get(field)):
                    issues.append(_issue(f"missing_{field}", "block_publish", field, message))
            if unit == "un" and weight_g is None:
                issues.append(
                    _issue(
                        "missing_unit_weight",
                        "block_publish",
                        "peso_g_consolidado",
                        "Produto por unidade precisa do peso operacional aproximado.",
                    )
                )
            if _requires_recipe(row) and sku not in snapshot.active_recipe_skus:
                issues.append(
                    _issue(
                        "missing_active_recipe",
                        "block_publish",
                        "receita_consolidado",
                        "Produção própria declarada sem ficha técnica ativa comprovada.",
                    )
                )

        if product:
            _compare(issues, "name", name, product["name"])
            _compare(issues, "base_price_q", price_q, product["base_price_q"])
            _compare(issues, "unit", unit, _fold(product["unit"]))
            _compare(issues, "unit_weight_g", weight_g, product["unit_weight_g"])
            _compare(issues, "ncm", ncm, product["ncm"])
            _compare(issues, "cest", cest, product["cest"])
            _compare(issues, "brand", _text(row.get("marca")), product["brand"])
            _compare(issues, "gtin", gtin, product["gtin"])
            _compare(issues, "short_description", _text(row.get("copy_curta")), product["short_description"])
            _compare(issues, "image_url", _text(row.get("foto_consolidado")), product["image_url"])
            category = _fold(row.get("categoria_consolidado"))
            current_collections = {_fold(value) for value in product["collections"]}
            if category and category not in current_collections:
                issues.append(
                    _issue(
                        "collection_mapping_missing",
                        "review",
                        "categoria_consolidado",
                        "Categoria consolidada ainda não está mapeada para coleção.",
                        expected=_text(row.get("categoria_consolidado")),
                    )
                )
        elif status in TARGET_STATUSES:
            issues.append(
                _issue(
                    "new_product_draft_only",
                    "info",
                    "sku",
                    "SKU não existe: eventual criação deve nascer como rascunho, nunca publicado automaticamente.",
                )
            )

        if status in RESTRICTIVE_STATUSES and product and (
            product["is_published"] or product["is_sellable"] or product["live_listing"]
        ):
            issues.append(
                _issue(
                    "restrictive_status_still_commercial",
                    "decision",
                    "situacao_consolidado",
                    "Candidato pede retirada, mas o SKU ainda está comercialmente ativo; requer aprovação explícita.",
                )
            )
        if status not in TARGET_STATUSES | RESTRICTIVE_STATUSES and product and (
            product["is_published"] or product["live_listing"]
        ):
            issues.append(
                _issue(
                    "undecided_status_is_live",
                    "decision",
                    "situacao_consolidado",
                    "SKU sem decisão conclusiva está visível em canal ativo.",
                )
            )

        if material and unit and _fold(material["unit"]) != unit:
            issues.append(
                _issue(
                    "shared_sku_unit_mismatch",
                    "block",
                    "unidade_consolidado",
                    "O mesmo SKU pode ser comprado e vendido, mas as unidades operacionais divergem.",
                    expected=unit,
                    observed=material["unit"],
                )
            )

        blocking = {issue["severity"] for issue in issues}
        if status == "novo" and not product:
            readiness = "draft_only" if "block" not in blocking else "blocked"
        elif "block" in blocking or "block_publish" in blocking:
            readiness = "blocked"
        elif "decision" in blocking:
            readiness = "owner_decision"
        elif status in TARGET_STATUSES:
            readiness = "day1_ready"
        else:
            readiness = "not_in_day1_mix"
        results.append({"row": number, "sku": sku, "status": status or "vazio", "readiness": readiness, "issues": issues})

    severity_counts = Counter(
        issue["severity"] for result in results for issue in result["issues"]
    )
    readiness_counts = Counter(result["readiness"] for result in results)
    return {
        "schema_version": CATALOG_AUDIT_SCHEMA_VERSION,
        "mode": "read_only_dry_run",
        "authority": "catalogo_nelson_consolidado",
        "source": source,
        "summary": {
            "rows": len(results),
            "target_rows": sum(result["status"] in TARGET_STATUSES for result in results),
            "issues_by_severity": dict(sorted(severity_counts.items())),
            "readiness": dict(sorted(readiness_counts.items())),
        },
        "candidates": results,
    }
