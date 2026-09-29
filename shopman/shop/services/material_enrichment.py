"""Curadoria de insumos a partir do rascunho compartilhado por GTIN.

A busca e a proveniência por campo vivem em :mod:`product_enrichment`; este
módulo só define os destinos próprios de ``buyman.Material`` e o gesto humano
de aceite. O GTIN pertence ao material (a identidade comprável), não ao custo
do fornecedor. Uma embalagem/marca diferente é outro SKU; preço e conversão
por fornecedor continuam em ``SupplierMaterialCost``/``MaterialConversion``.

Nada é aplicado automaticamente. NF-e, Cosmos e Open Food Facts escrevem
somente ``Material.metadata['enrichment']``. O aceite é campo a campo e valor
existente exige ``replace`` explícito.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from shopman.shop.services import gtin_enrichment as enrichment

FIELD_LABELS: dict[str, str] = dict(enrichment.FIELD_LABELS)

_METADATA_DESTINATIONS: dict[str, str] = {
    "gtin": "gtin",
    "brand": "brand",
    "ncm": "ncm",
    "cest": "cest",
    "fiscal_unit": "fiscal_unit",
    "net_weight_g": "net_weight_g",
    "ingredients_text": "ingredients_text",
    "allergens": "allergens",
    "nutrition": "nutrition",
}


def draft(material_or_metadata) -> dict[str, Any]:
    return enrichment.draft(material_or_metadata)


def pending_fields(material_or_metadata) -> dict[str, dict[str, Any]]:
    fields = draft(material_or_metadata).get("fields") or {}
    return {name: fields[name] for name in FIELD_LABELS if name in fields}


def merge_into_metadata(metadata: dict | None, suggestion: enrichment.EnrichmentSuggestion) -> dict:
    return enrichment.merge_into_metadata(metadata, suggestion)


def suggest_from_invoice(material, **invoice_fields: Any) -> bool:
    """Guarda a declaração da NF-e como rascunho do material, sem aceitá-la."""
    suggestion = enrichment.suggestion_from_invoice(**invoice_fields)
    if not suggestion.fields:
        return False
    before = draft(material)
    metadata = merge_into_metadata(material.metadata, suggestion)
    if metadata.get("enrichment") == before:
        return False
    material.metadata = metadata
    material.save(update_fields=["metadata", "updated_at"])
    return True


def current_value(material, name: str) -> Any:
    if name == "name":
        return material.name or ""
    key = _METADATA_DESTINATIONS.get(name)
    if key is None:
        raise KeyError(name)
    value = (material.metadata or {}).get(key)
    if name == "allergens":
        return list(value or [])
    if name == "nutrition":
        return dict(value or {})
    return value if value is not None else ""


def needs_replace(material, name: str, value: Any) -> bool:
    current = current_value(material, name)
    return not _is_empty(current) and not _same(name, current, value)


@dataclass
class AcceptResult:
    applied: list[str] = field(default_factory=list)
    conflicts: dict[str, Any] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)
    recalculated_products: list[str] = field(default_factory=list)


def accept_fields(material, names, *, replace=(), user=None) -> AcceptResult:
    """Aplica somente os campos escolhidos e recalcula rótulos dependentes.

    O recálculo só é aberto quando ``allergens`` muda. A derivação continua
    recusando receita com qualquer folha sem ``diet``; aceitar alérgeno não
    inventa dieta nem afrouxa essa trava.
    """
    from shopman.offerman import gtin_is_valid

    result = AcceptResult()
    replace = set(replace)
    meta = dict(material.metadata or {})
    block = draft(meta)
    fields: dict[str, dict[str, Any]] = dict(block.get("fields") or {})
    accepted: dict[str, dict[str, Any]] = dict(block.get("accepted") or {})
    who = user.get_username() if user is not None and hasattr(user, "get_username") else ""

    with transaction.atomic():
        for name in names:
            entry = fields.get(name)
            if not entry:
                continue
            value = entry["value"]
            previous = current_value(material, name)
            if needs_replace(material, name, value) and name not in replace:
                result.conflicts[name] = previous
                continue

            if name == "gtin":
                if not gtin_is_valid(str(value)):
                    result.refused[name] = "GTIN com dígito verificador inválido."
                    continue
                meta["gtin"] = str(value)
            elif name == "name":
                material.name = str(value)[: material._meta.get_field("name").max_length]
            elif name == "ncm":
                digits = str(value)
                if len(digits) != 8 or not digits.isdigit():
                    result.refused[name] = "NCM deve ter 8 dígitos."
                    continue
                meta["ncm"] = digits
            elif name == "cest":
                digits = str(value)
                if len(digits) != 7 or not digits.isdigit():
                    result.refused[name] = "CEST deve ter 7 dígitos."
                    continue
                meta["cest"] = digits
            elif name == "net_weight_g":
                try:
                    weight = int(value)
                except (TypeError, ValueError):
                    weight = 0
                if weight <= 0:
                    result.refused[name] = "Peso líquido deve ser maior que zero."
                    continue
                meta["net_weight_g"] = weight
            elif name in _METADATA_DESTINATIONS:
                meta[_METADATA_DESTINATIONS[name]] = value
            else:  # pragma: no cover - FIELD_LABELS e destinos andam juntos
                continue

            record = {
                "value": value,
                "source": entry["source"],
                "fetched_at": entry.get("fetched_at", ""),
                "accepted_by": who,
                "accepted_at": timezone.now().isoformat(),
            }
            if entry.get("source_ref"):
                record["source_ref"] = entry["source_ref"]
            if not _is_empty(previous) and not _same(name, previous, value):
                record["replaced"] = previous
            accepted[name] = record
            fields.pop(name, None)
            result.applied.append(name)

        if not result.applied:
            return result

        block["fields"] = fields
        if not fields:
            block.pop("fields")
        block["accepted"] = accepted
        meta["enrichment"] = block
        material.metadata = meta
        material.save()

        if "allergens" in result.applied:
            result.recalculated_products = recalculate_products_using_material(material.sku)
    return result


def recalculate_products_using_material(sku: str) -> list[str]:
    """Reabre a derivação de todo produto cuja ficha usa ``sku`` como folha.

    Varre as fichas ativas porque o uso pode ser transitivo (insumo de uma
    subficha). Não grava Recipe/RecipeItem: a derivação combina o perfil atual
    do Material sobre o snapshot da linha e grava somente o rótulo do produto.
    """
    from shopman.craftsman.models import Recipe
    from shopman.offerman.models import Product

    from shopman.shop.services.dietary_from_recipe import aggregate_dietary_from_recipe
    from shopman.shop.services.recipe_bom import expand_recipe_items

    changed: list[str] = []
    for recipe in Recipe.objects.filter(is_active=True).order_by("ref"):
        if not any(item.input_sku == sku for item in expand_recipe_items(recipe)):
            continue
        product = Product.objects.filter(sku=recipe.output_sku).first()
        if product is not None and aggregate_dietary_from_recipe(product):
            changed.append(product.sku)
    return changed


@dataclass(frozen=True)
class RecipeCoverage:
    ref: str
    output_sku: str
    missing_materials: tuple[str, ...]


@dataclass(frozen=True)
class CoverageReport:
    active_materials: int
    recipe_materials: int
    declared_materials: int
    staged_materials: int
    recipes: int
    derivable_recipes: int
    one_missing: tuple[RecipeCoverage, ...]
    invalid: tuple[str, ...]


def coverage_report() -> CoverageReport:
    """Mede declaração, staging e o funil real da derivação por receita."""
    from shopman.buyman.models import Material
    from shopman.craftsman.dietary import DIET_CLASSES
    from shopman.craftsman.models import Recipe

    from shopman.shop.services.dietary_from_recipe import dietary_profiles_for_items
    from shopman.shop.services.recipe_bom import expand_recipe_items

    materials = list(Material.objects.filter(is_active=True).order_by("sku"))
    declared = {
        material.sku
        for material in materials
        if str((material.metadata or {}).get("diet") or "").strip().lower() in DIET_CLASSES
    }
    staged = sum(bool(pending_fields(material)) for material in materials)
    invalid = tuple(
        f"{material.sku}: {issue}"
        for material in materials
        for issue in validation_issues(material)
    )

    recipe_rows: list[RecipeCoverage] = []
    used: set[str] = set()
    derivable = 0
    recipes = list(Recipe.objects.filter(is_active=True).order_by("ref"))
    for recipe in recipes:
        items = expand_recipe_items(recipe)
        used.update(item.input_sku for item in items)
        _profiles, missing = dietary_profiles_for_items(items)
        missing = tuple(dict.fromkeys(missing))
        if not missing:
            derivable += 1
        elif len(missing) == 1:
            recipe_rows.append(
                RecipeCoverage(
                    ref=recipe.ref,
                    output_sku=recipe.output_sku,
                    missing_materials=missing,
                )
            )
    return CoverageReport(
        active_materials=len(materials),
        recipe_materials=len(used),
        declared_materials=len(declared & used),
        staged_materials=staged,
        recipes=len(recipes),
        derivable_recipes=derivable,
        one_missing=tuple(recipe_rows),
        invalid=invalid,
    )


def validation_issues(material) -> list[str]:
    """Erros locais que tornam GTIN/perfil inseguros, sem consultar rede."""
    from shopman.craftsman.dietary import DIET_CLASSES
    from shopman.offerman import gtin_is_valid

    metadata = material.metadata or {}
    issues: list[str] = []
    gtin = str(metadata.get("gtin") or "").strip()
    if gtin and not gtin_is_valid(gtin):
        issues.append("GTIN com dígito verificador inválido")
    if "allergens" in metadata and not isinstance(metadata.get("allergens"), list):
        issues.append("allergens precisa ser lista")
    if "diet" in metadata:
        diet = str(metadata.get("diet") or "").strip().lower()
        if diet not in DIET_CLASSES:
            issues.append("diet fora do vocabulário fechado")
    return issues


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _same(name: str, left: Any, right: Any) -> bool:
    if name == "allergens":
        return sorted(left or []) == sorted(right or [])
    if name == "nutrition":
        return dict(left or {}) == dict(right or {})
    if isinstance(left, str) and isinstance(right, str):
        return left.strip() == right.strip()
    return left == right
