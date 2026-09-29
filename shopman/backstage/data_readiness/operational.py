"""Read-only readiness gate for recipes and their material dependencies."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

OPERATIONAL_AUDIT_SCHEMA_VERSION = "shopman.recipe-material-day1-audit/v1"
MAX_RECIPE_DEPTH = 5


class OperationalAuditError(ValueError):
    """The requested Day-1 scope is absent or cannot be evaluated safely."""


@dataclass(frozen=True)
class OperationalSnapshot:
    """Minimal operational projection consumed by the pure evaluator."""

    products: dict[str, dict[str, Any]]
    recipes: dict[str, dict[str, Any]]
    materials: dict[str, dict[str, Any]]
    versions: dict[str, dict[str, Any]]


def read_sku_scope(values: list[str] | tuple[str, ...], file: str | Path | None = None) -> list[str]:
    """Normalize an explicit output-SKU scope; comments and blanks are ignored."""

    raw = list(values)
    if file:
        source = Path(file)
        if not source.is_file():
            raise OperationalAuditError("O arquivo de escopo não existe ou não é arquivo regular.")
        try:
            raw.extend(source.read_text(encoding="utf-8-sig").splitlines())
        except UnicodeDecodeError as exc:
            raise OperationalAuditError("O arquivo de escopo deve usar UTF-8.") from exc
    normalized = []
    for value in raw:
        sku = str(value or "").split("#", 1)[0].strip().upper()
        if sku and sku not in normalized:
            normalized.append(sku)
    if not normalized:
        raise OperationalAuditError("Informe ao menos um SKU Day-1 com --sku ou --sku-file.")
    return normalized


def database_operational_snapshot() -> OperationalSnapshot:
    """Read the current recipe/material state without mutations or row locks."""

    from shopman.buyman.models import Material, MaterialConversion, SupplierMaterialCost
    from shopman.craftsman.models import Recipe, RecipeEntry
    from shopman.offerman.models import Product

    products = {
        str(product.sku): {
            "name": product.name,
            "is_published": product.is_published,
            "is_sellable": product.is_sellable,
        }
        for product in Product.objects.all().only("sku", "name", "is_published", "is_sellable").iterator()
    }

    recipes = {}
    for recipe in Recipe.objects.filter(is_active=True).prefetch_related("items"):
        recipes[str(recipe.output_sku)] = {
            "ref": recipe.ref,
            "batch_size": str(recipe.batch_size),
            "steps_count": len(recipe.steps or []),
            "items": [
                {
                    "input_sku": str(item.input_sku),
                    "quantity": str(item.quantity),
                    "unit": item.unit,
                    "usable_factor": str(item.usable_factor),
                    "is_optional": item.is_optional,
                }
                for item in recipe.items.all()
            ],
        }

    preferred_cost_material_ids = set(
        SupplierMaterialCost.objects.filter(is_preferred=True).values_list("material_id", flat=True)
    )
    supplier_cost_material_ids = set(
        SupplierMaterialCost.objects.values_list("material_id", flat=True)
    )
    conversions_by_material: Counter[int] = Counter(
        MaterialConversion.objects.filter(is_active=True).values_list("material_id", flat=True)
    )
    approximate_by_material: Counter[int] = Counter(
        MaterialConversion.objects.filter(
            is_active=True,
            kind=MaterialConversion.Kind.APPROXIMATE,
        ).values_list("material_id", flat=True)
    )
    materials = {}
    for material in Material.objects.all().iterator():
        metadata = material.metadata if isinstance(material.metadata, dict) else {}
        materials[str(material.sku)] = {
            "name": material.name,
            "unit": material.unit,
            "is_active": material.is_active,
            "supplier_known": bool(
                metadata.get("supplier")
                or metadata.get("alt_suppliers")
                or material.pk in supplier_cost_material_ids
            ),
            "preferred_cost": material.pk in preferred_cost_material_ids,
            "conversion_count": conversions_by_material[material.pk],
            "approximate_conversion_count": approximate_by_material[material.pk],
        }

    versions = {}
    for entry in RecipeEntry.objects.select_related("current_version").exclude(output_sku=""):
        version = entry.current_version
        if version is None:
            continue
        versions[str(entry.output_sku)] = {
            "version_ref": version.version_ref,
            "published": version.status == version.Status.PUBLISHED,
            "published_at": version.published_at.isoformat() if version.published_at else None,
            "source_present": bool(version.source),
            "origin_present": bool(version.origin),
            "created_by_present": bool(version.created_by),
        }
    return OperationalSnapshot(products=products, recipes=recipes, materials=materials, versions=versions)


def _finding(code: str, domain: str, severity: str, sku: str, message: str, **details) -> dict[str, Any]:
    finding = {"code": code, "domain": domain, "severity": severity, "sku": sku, "message": message}
    finding.update({key: value for key, value in details.items() if value not in (None, "")})
    return finding


def _walk_recipe(
    output_sku: str,
    snapshot: OperationalSnapshot,
    findings: list[dict[str, Any]],
    leaf_materials: set[str],
    *,
    depth: int,
    trail: tuple[str, ...],
) -> None:
    if output_sku in trail:
        findings.append(
            _finding(
                "recipe_cycle",
                "production",
                "block",
                output_sku,
                "A árvore de fichas técnicas contém um ciclo.",
                trail=[*trail, output_sku],
            )
        )
        return
    if depth > MAX_RECIPE_DEPTH:
        findings.append(
            _finding(
                "recipe_depth_exceeded",
                "production",
                "block",
                output_sku,
                f"A árvore ultrapassa a profundidade operacional máxima ({MAX_RECIPE_DEPTH}).",
            )
        )
        return
    recipe = snapshot.recipes.get(output_sku)
    if recipe is None:
        findings.append(
            _finding(
                "missing_active_recipe",
                "production",
                "block",
                output_sku,
                "SKU Day-1 não tem ficha técnica ativa.",
            )
        )
        return
    try:
        batch_size = Decimal(str(recipe.get("batch_size") or ""))
    except Exception as exc:
        raise OperationalAuditError(f"Snapshot inválido: rendimento ilegível em {output_sku}.") from exc
    if batch_size <= 0:
        findings.append(
            _finding(
                "invalid_batch_size",
                "production",
                "block",
                output_sku,
                "Rendimento/lote deve ser maior que zero.",
            )
        )
    items = recipe.get("items") or []
    if not items:
        findings.append(
            _finding("empty_recipe", "production", "block", output_sku, "Ficha técnica não tem insumos.")
        )
    if not recipe.get("steps_count"):
        findings.append(
            _finding(
                "missing_steps",
                "traceability",
                "decision",
                output_sku,
                "Ficha executável existe, mas o modo de preparo não está registrado.",
            )
        )
    version = snapshot.versions.get(output_sku)
    if version is None or not version.get("published"):
        findings.append(
            _finding(
                "missing_published_version",
                "traceability",
                "decision",
                output_sku,
                "Ficha ativa não possui versão publicada no inventário.",
            )
        )
    else:
        missing = [
            field
            for field in ("source_present", "origin_present", "created_by_present", "published_at")
            if not version.get(field)
        ]
        if missing:
            findings.append(
                _finding(
                    "incomplete_recipe_provenance",
                    "traceability",
                    "decision",
                    output_sku,
                    "Versão publicada ainda não comprova toda a proveniência operacional.",
                    missing=missing,
                    version_ref=version.get("version_ref"),
                )
            )

    next_trail = (*trail, output_sku)
    for item in items:
        input_sku = str(item.get("input_sku") or "").strip()
        if not input_sku:
            findings.append(
                _finding("missing_input_sku", "production", "block", output_sku, "Linha de ficha sem SKU de entrada.")
            )
            continue
        try:
            quantity = Decimal(str(item.get("quantity") or ""))
            usable_factor = Decimal(str(item.get("usable_factor") or ""))
        except Exception as exc:
            raise OperationalAuditError(f"Snapshot inválido: quantidade/fator ilegível em {output_sku}.") from exc
        if quantity <= 0 or not Decimal("0") < usable_factor <= Decimal("1"):
            findings.append(
                _finding(
                    "invalid_recipe_item_quantity",
                    "production",
                    "block",
                    input_sku,
                    "Quantidade deve ser positiva e fator de aproveitamento deve estar em (0, 1].",
                    output_sku=output_sku,
                )
            )
        if input_sku in snapshot.recipes:
            _walk_recipe(
                input_sku,
                snapshot,
                findings,
                leaf_materials,
                depth=depth + 1,
                trail=next_trail,
            )
            continue
        material = snapshot.materials.get(input_sku)
        if material is not None:
            leaf_materials.add(input_sku)
            if not material.get("is_active"):
                findings.append(
                    _finding(
                        "inactive_material",
                        "production",
                        "block",
                        input_sku,
                        "Ficha depende de insumo inativo.",
                        output_sku=output_sku,
                    )
                )
            continue
        severity = "warning" if item.get("is_optional") else "block"
        findings.append(
            _finding(
                "unresolved_recipe_input",
                "production",
                severity,
                input_sku,
                "Entrada não corresponde a insumo nem a sub-receita ativa.",
                output_sku=output_sku,
                optional=bool(item.get("is_optional")),
            )
        )


def audit_operational_day1(skus: list[str], snapshot: OperationalSnapshot) -> dict[str, Any]:
    """Audit explicit production outputs and all reachable leaf materials."""

    requested = list(dict.fromkeys(str(sku).strip().upper() for sku in skus if str(sku).strip()))
    if not requested:
        raise OperationalAuditError("O escopo Day-1 está vazio.")
    results = []
    for sku in requested:
        findings: list[dict[str, Any]] = []
        product = snapshot.products.get(sku)
        if product is None:
            findings.append(
                _finding("missing_product", "catalog", "block", sku, "SKU Day-1 não existe no catálogo operacional.")
            )
        elif not product.get("is_published") or not product.get("is_sellable"):
            findings.append(
                _finding(
                    "product_not_commercially_active",
                    "catalog",
                    "decision",
                    sku,
                    "SKU selecionado não está simultaneamente publicado e vendável.",
                )
            )

        leaf_materials: set[str] = set()
        _walk_recipe(sku, snapshot, findings, leaf_materials, depth=0, trail=())
        for material_sku in sorted(leaf_materials):
            material = snapshot.materials[material_sku]
            if not material.get("supplier_known"):
                findings.append(
                    _finding(
                        "supplier_unknown",
                        "procurement",
                        "decision",
                        material_sku,
                        "Insumo usado no Day-1 não tem fornecedor conhecido no snapshot.",
                    )
                )
            if not material.get("preferred_cost"):
                findings.append(
                    _finding(
                        "preferred_cost_unknown",
                        "cost",
                        "decision",
                        material_sku,
                        "Insumo usado no Day-1 não tem custo preferencial vigente comprovado.",
                    )
                )
            if not material.get("conversion_count"):
                findings.append(
                    _finding(
                        "no_declared_purchase_conversion",
                        "procurement",
                        "info",
                        material_sku,
                        "Nenhuma embalagem/conversão foi declarada; compra na unidade-base continua possível.",
                    )
                )
            if material.get("approximate_conversion_count"):
                findings.append(
                    _finding(
                        "approximate_conversion_in_use",
                        "procurement",
                        "warning",
                        material_sku,
                        "Há conversão aproximada; a incerteza deve continuar visível ao operador.",
                    )
                )

        blocking_domains = {finding["domain"] for finding in findings if finding["severity"] == "block"}
        decision_domains = {finding["domain"] for finding in findings if finding["severity"] == "decision"}
        catalog_ready = "catalog" not in blocking_domains | decision_domains
        production_ready = not bool(blocking_domains & {"catalog", "production"})
        traceability_ready = "traceability" not in decision_domains
        procurement_ready = "procurement" not in decision_domains
        cost_ready = "cost" not in decision_domains
        results.append(
            {
                "sku": sku,
                "day1_ready": all(
                    (catalog_ready, production_ready, traceability_ready, procurement_ready, cost_ready)
                ),
                "catalog_ready": catalog_ready,
                "production_ready": production_ready,
                "traceability_ready": traceability_ready,
                "procurement_ready": procurement_ready,
                "cost_ready": cost_ready,
                "leaf_materials": sorted(leaf_materials),
                "findings": findings,
            }
        )

    finding_counts = Counter(finding["severity"] for result in results for finding in result["findings"])
    return {
        "schema_version": OPERATIONAL_AUDIT_SCHEMA_VERSION,
        "mode": "read_only_dry_run",
        "scope": requested,
        "summary": {
            "outputs": len(results),
            "day1_ready": sum(result["day1_ready"] for result in results),
            "catalog_ready": sum(result["catalog_ready"] for result in results),
            "production_ready": sum(result["production_ready"] for result in results),
            "traceability_ready": sum(result["traceability_ready"] for result in results),
            "procurement_ready": sum(result["procurement_ready"] for result in results),
            "cost_ready": sum(result["cost_ready"] for result in results),
            "findings_by_severity": dict(sorted(finding_counts.items())),
        },
        "outputs": results,
    }
