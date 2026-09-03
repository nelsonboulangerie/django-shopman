"""Serviços do inventário de receitas: entry, versão, publicação, diff e bootstrap.

Este módulo é a porta única do orquestrador para o inventário: ele re-exporta a
matemática pura de ``contrib/formula/percentages.py`` (``analyze``,
``standardize``, ``scale``, ``derive_bom``, ``check_references``...) para que
quem está fora do Craftsman importe tudo de ``shopman.craftsman.services.recipe_book``.

Publicar é o único verbo que escreve na ficha de execução (``Recipe``). O
bootstrap lê a ficha e não a toca. Ver ``docs/plans/RECIPE-INVENTORY-PLAN.md`` §5.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from shopman.craftsman.contrib.formula.percentages import (
    ANCHOR_KINDS,
    PART_KINDS,
    REFERENCE_RANGES,
    ROLES,
    FormulaAnalysis,
    FormulaItemAnalysis,
    FormulaPartAnalysis,
    FormulaWarning,
    analyze,
    check_references,
    classify_ingredient,
    derive_bom,
    item_grams,
    looks_like_flour,
    normalize_text,
    number_text,
    part_kind_from_name,
    quantize,
    reference_for,
    scale,
    standardize,
    to_decimal,
    validate_formula,
)
from shopman.craftsman.exceptions import RecipeBookError

__all__ = [
    "ANCHOR_KINDS",
    "PART_KINDS",
    "REFERENCE_RANGES",
    "ROLES",
    "FormulaAnalysis",
    "FormulaDiff",
    "FormulaDiffMetric",
    "FormulaDiffRow",
    "FormulaItemAnalysis",
    "FormulaPartAnalysis",
    "FormulaWarning",
    "RecipeBookError",
    "analyze",
    "bootstrap_entry_from_recipe",
    "check_references",
    "classify_ingredient",
    "create_entry",
    "create_version",
    "derive_bom",
    "diff_versions",
    "item_grams",
    "looks_like_flour",
    "part_formulas_for",
    "publish_version",
    "reference_for",
    "scale",
    "standardize",
    "update_draft",
    "validate_formula",
]

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_MASS_UNITS = ("kg", "g", "mg")
_MAX_PART_DEPTH = 5


# ── Diff ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FormulaDiffRow:
    """Um ingrediente nas duas versões, em grama e em porcentagem."""

    key: str
    sku: str
    name: str
    role: str
    a_grams: Decimal | None
    b_grams: Decimal | None
    delta_grams: Decimal | None
    a_pct: Decimal | None
    b_pct: Decimal | None
    delta_pct: Decimal | None


@dataclass(frozen=True)
class FormulaDiffMetric:
    """Uma métrica nas duas versões."""

    code: str
    a: Decimal | None
    b: Decimal | None
    delta: Decimal | None
    unit: str = "%"


@dataclass(frozen=True)
class FormulaDiff:
    """Comparação entre duas versões, na mesma base."""

    a_ref: str
    b_ref: str
    basis: str
    rows: tuple[FormulaDiffRow, ...]
    metrics: tuple[FormulaDiffMetric, ...]


# ── Entry e versão ───────────────────────────────────────────────────────────


def create_entry(*, ref: str, name: str, kind: str = "other", output_sku: str = "",
                 notes: str = "", meta: dict | None = None):
    """Cria uma receita no inventário (sem versão ainda)."""
    from shopman.craftsman.models import RecipeEntry

    ref = str(ref or "").strip()
    if not ref:
        raise RecipeBookError("INVALID_REF", field="ref")
    entry = RecipeEntry(
        ref=ref,
        name=str(name or "").strip(),
        kind=kind or RecipeEntry.Kind.OTHER,
        output_sku=str(output_sku or "").strip(),
        notes=notes or "",
        meta=dict(meta or {}),
    )
    entry.full_clean()
    entry.save()
    return entry


def create_version(entry, *, formula: dict, yield_quantity, yield_unit: str, origin: dict | None = None,
                   source: dict | None = None, steps: list[str] | None = None, notes: str = "",
                   label: str = "", created_by: str = ""):
    """Cria um rascunho com ``number`` = último + 1."""
    from shopman.craftsman.models import RecipeVersion

    if entry.is_archived:
        raise RecipeBookError("ENTRY_ARCHIVED", ref=entry.ref)
    validate_formula(formula)
    quantity = _yield_quantity(yield_quantity)
    unit = _yield_unit(yield_unit)

    with transaction.atomic():
        last = entry.versions.aggregate(m=models.Max("number"))["m"] or 0
        version = RecipeVersion(
            entry=entry,
            number=last + 1,
            status=RecipeVersion.Status.DRAFT,
            label=label or "",
            yield_quantity=quantity,
            yield_unit=unit,
            formula=formula,
            origin=origin if origin is not None else _origin_from(formula, quantity, unit),
            source=source if source is not None else {"kind": "manual"},
            steps=list(steps or []),
            notes=notes or "",
            created_by=created_by or "",
        )
        version.full_clean()
        version.save()
    return version


def update_draft(version, *, formula: dict | None = None, yield_quantity=None, yield_unit: str | None = None,
                 steps: list[str] | None = None, notes: str | None = None, label: str | None = None):
    """Edita um rascunho. Versão publicada ou substituída é imutável."""
    from shopman.craftsman.models import RecipeVersion

    if version.status != RecipeVersion.Status.DRAFT:
        raise RecipeBookError("VERSION_NOT_DRAFT", version_ref=version.version_ref, status=version.status)
    if formula is not None:
        validate_formula(formula)
        version.formula = formula
    if yield_quantity is not None:
        version.yield_quantity = _yield_quantity(yield_quantity)
    if yield_unit is not None:
        version.yield_unit = _yield_unit(yield_unit)
    if steps is not None:
        version.steps = list(steps)
    if notes is not None:
        version.notes = notes
    if label is not None:
        version.label = label
    version.full_clean()
    version.save()
    return version


def publish_version(version, *, actor: str = ""):
    """Publica a versão: escreve a ficha de execução e vira a atual da receita.

    Recusa (``RecipeBookError``): versão que não é rascunho, receita arquivada
    ou sem SKU, ingrediente ou parte sem SKU, parte sem fórmula conhecida e
    parte maior que a base. A unidade de cada item ainda passa pelo
    ``RecipeItem.clean`` (a unidade do SKU no catálogo fala lá) e a ficha pelo
    invariante de massa do ``Recipe.save``.
    """
    from shopman.craftsman.models import RecipeVersion

    if version.status != RecipeVersion.Status.DRAFT:
        raise RecipeBookError("VERSION_NOT_DRAFT", version_ref=version.version_ref, status=version.status)
    entry = version.entry
    if entry.is_archived:
        raise RecipeBookError("ENTRY_ARCHIVED", ref=entry.ref)
    if not str(entry.output_sku or "").strip():
        raise RecipeBookError("ENTRY_WITHOUT_SKU", ref=entry.ref)

    formula = version.formula or {}
    validate_formula(formula)
    for index, item in enumerate(formula.get("items") or []):
        if not str(item.get("sku") or "").strip():
            raise RecipeBookError("ITEM_WITHOUT_SKU", field=f"items[{index}].sku", name=item.get("name", ""))
    for index, part in enumerate(formula.get("parts") or []):
        if part.get("kind") != "old_dough" and not str(part.get("sku") or "").strip():
            raise RecipeBookError("ITEM_WITHOUT_SKU", field=f"parts[{index}].sku", name=part.get("name", ""))

    analysis = analyze(formula, part_formulas_for(formula))
    for warning in analysis.warnings:
        if warning.code in ("PART_WITHOUT_FORMULA", "PART_EXCEEDS_BASE"):
            raise RecipeBookError(warning.code, field=warning.metric, message=warning.message)

    now = timezone.now()
    with transaction.atomic():
        recipe = _write_recipe(entry, version, analysis)
        entry.versions.filter(status=RecipeVersion.Status.PUBLISHED).exclude(pk=version.pk).update(
            status=RecipeVersion.Status.SUPERSEDED,
        )
        version.status = RecipeVersion.Status.PUBLISHED
        version.published_at = now
        if actor:
            version.meta = {**(version.meta or {}), "published_by": actor}
        version.save(update_fields=["status", "published_at", "meta"])
        entry.current_version = version
        entry.save(update_fields=["current_version", "updated_at"])
    return recipe


def _write_recipe(entry, version, analysis: FormulaAnalysis):
    """Upsert da ficha de execução a partir do BOM derivado."""
    from shopman.craftsman.models import Recipe, RecipeItem

    Recipe.objects.filter(output_sku=entry.output_sku, is_active=True).exclude(ref=entry.ref).update(is_active=False)

    recipe = Recipe.objects.filter(ref=entry.ref).first()
    version_meta = {"version_ref": version.version_ref, "output_unit": version.yield_unit}
    if recipe is None:
        recipe = Recipe.objects.create(
            ref=entry.ref,
            name=entry.name,
            output_sku=entry.output_sku,
            batch_size=version.yield_quantity,
            steps=list(version.steps or []),
            is_active=True,
            meta=version_meta,
        )

    existing_meta = {item.input_sku: dict(item.meta or {}) for item in recipe.items.all()}
    recipe.items.all().delete()
    for sort_order, line in enumerate(_merge_bom_lines(analysis.bom, entry, version)):
        quantity, unit = _in_catalog_unit(line["sku"], line["quantity"], line["unit"])
        item = RecipeItem(
            recipe=recipe,
            input_sku=line["sku"],
            quantity=quantity,
            unit=unit,
            sort_order=sort_order,
            is_optional=line["is_optional"],
            meta={**existing_meta.get(line["sku"], {}), **line["meta"]},
        )
        try:
            item.full_clean()
        except ValidationError as exc:
            # A recusa da ficha (unidade do cadastro, SKU inválido) volta apontando a
            # LINHA da fórmula, que é o que o editor consegue acender.
            attribute, message = _first_validation_message(exc)
            raise RecipeBookError(
                "FORMULA_INVALID", field=_formula_field_for_sku(version.formula, line["sku"], attribute),
                message=message,
            ) from exc
        item.save()

    recipe.name = entry.name
    recipe.output_sku = entry.output_sku
    recipe.batch_size = version.yield_quantity
    recipe.steps = list(version.steps or [])
    recipe.is_active = True
    recipe.meta = {**(recipe.meta or {}), **version_meta}
    recipe.save()
    return recipe


def _first_validation_message(exc: ValidationError) -> tuple[str, str]:
    """O primeiro ``(campo, mensagem)`` de um ``ValidationError`` de modelo."""
    if hasattr(exc, "message_dict"):
        for attribute, messages in exc.message_dict.items():
            for message in messages:
                return ("" if attribute == "__all__" else attribute), str(message)
    messages = list(getattr(exc, "messages", []) or [])
    return "", (str(messages[0]) if messages else "A ficha recusou o item.")


def _formula_field_for_sku(formula: dict, sku: str, attribute: str = "") -> str:
    """O caminho na fórmula (``items[2].unit``, ``parts[0]``) do SKU que a ficha recusou."""
    suffix = f".{attribute}" if attribute else ""
    for index, item in enumerate(list((formula or {}).get("items") or [])):
        if str(item.get("sku") or "").strip() == sku:
            return f"items[{index}]{suffix}"
    for index, part in enumerate(list((formula or {}).get("parts") or [])):
        if str(part.get("sku") or "").strip() == sku:
            return f"parts[{index}]{suffix}"
    return "items"


def _in_catalog_unit(sku: str, quantity: Decimal, unit: str) -> tuple[Decimal, str]:
    """A linha na unidade em que o insumo é cadastrado (a ficha fala a unidade do SKU).

    A fórmula fala em grama; o insumo do Buyman é cadastrado em kg ou L, e o
    ``RecipeItem.clean`` exige a unidade do cadastro. Mesma dimensão converte
    pela física; dimensão diferente (contagem, volume sem densidade) fica como
    está, e a ficha recusa com a mensagem dela.
    """
    from shopman.craftsman.models.recipe import _catalog_unit_for_sku, normalize_recipe_item_unit
    from shopman.utils import units

    unit = normalize_recipe_item_unit(unit)
    catalog_unit = normalize_recipe_item_unit(_catalog_unit_for_sku(sku))
    if not catalog_unit or catalog_unit == unit or not units.same_dimension(catalog_unit, unit):
        return quantity, unit
    return quantize(units.convert(quantity, unit, catalog_unit)), catalog_unit


def _merge_bom_lines(bom, entry, version) -> list[dict]:
    """Uma linha por SKU (a ficha tem ``unique(recipe, input_sku)``); massa velha ganha o SKU da própria receita."""
    merged: dict[str, dict] = {}
    for line in bom:
        copy = dict(line)
        if copy["meta"].get("role") == "old_dough":
            copy["sku"] = entry.output_sku
            if version.yield_unit in ("kg", "g"):
                grams = copy["quantity"] if copy["unit"] == "g" else copy["quantity"] * Decimal(1000)
                copy["quantity"] = quantize(grams / (Decimal(1000) if version.yield_unit == "kg" else Decimal(1)))
                copy["unit"] = version.yield_unit
        sku = copy["sku"]
        if sku in merged:
            current = merged[sku]
            if current["unit"] != copy["unit"]:
                raise RecipeBookError(
                    "FORMULA_INVALID", field="items",
                    message=f"O insumo {sku} aparece em duas unidades diferentes ({current['unit']} e {copy['unit']}).",
                )
            current["quantity"] = quantize(current["quantity"] + copy["quantity"])
            current["is_optional"] = current["is_optional"] and copy["is_optional"]
            continue
        merged[sku] = copy
    return list(merged.values())


# ── Partes ───────────────────────────────────────────────────────────────────


def part_formulas_for(formula: dict) -> dict[str, dict]:
    """``sku`` de cada parte → fórmula da versão atual da receita da parte."""
    from shopman.craftsman.models import RecipeEntry

    out: dict[str, dict] = {}
    for part in list((formula or {}).get("parts") or []):
        if part.get("kind") == "old_dough":
            continue
        sku = str(part.get("sku") or "").strip()
        if not sku:
            continue
        entry = None
        entry_ref = str(part.get("entry_ref") or "").strip()
        if entry_ref:
            entry = RecipeEntry.objects.filter(ref=entry_ref).select_related("current_version").first()
        if entry is None or entry.current_version is None:
            entry = (
                RecipeEntry.objects.filter(output_sku=sku, current_version__isnull=False)
                .select_related("current_version")
                .order_by("pk")
                .first()
            )
        if entry is not None and entry.current_version is not None:
            out[sku] = entry.current_version.formula or {}
    return out


# ── Diff ─────────────────────────────────────────────────────────────────────


def diff_versions(a, b) -> FormulaDiff:
    """Compara duas versões na mesma base.

    Com âncora ``flour`` nas duas, padroniza ambas para 1000 g de farinha e
    compara em grama e em % do padeiro. Senão, compara por % da massa total.
    """
    formula_a, formula_b = dict(a.formula or {}), dict(b.formula or {})
    parts_a, parts_b = part_formulas_for(formula_a), part_formulas_for(formula_b)
    both_flour = all(
        (f.get("anchor") or {}).get("kind") == "flour" and (analyze(f).anchor_total_g or _ZERO) > 0
        for f in (formula_a, formula_b)
    )
    if both_flour:
        formula_a = standardize(formula_a, Decimal(1000))
        formula_b = standardize(formula_b, Decimal(1000))
        basis = "flour_1000"
    else:
        basis = "total_pct"
    analysis_a = analyze(formula_a, parts_a)
    analysis_b = analyze(formula_b, parts_b)

    def rows_of(analysis: FormulaAnalysis) -> dict[str, tuple[FormulaItemAnalysis, Decimal | None]]:
        out: dict[str, tuple[FormulaItemAnalysis, Decimal | None]] = {}
        for item in analysis.items:
            key = item.sku or f"name:{normalize_text(item.name)}"
            pct = item.pct if both_flour else _pct_of_total(item.grams, analysis.total_mass_g)
            if key in out:
                previous, previous_pct = out[key]
                item = FormulaItemAnalysis(
                    sku=previous.sku, name=previous.name, role=previous.role,
                    quantity=previous.quantity + item.quantity, unit=previous.unit,
                    grams=_sum(previous.grams, item.grams), pct=_sum(previous_pct, pct),
                )
                pct = item.pct
            out[key] = (item, pct)
        return out

    rows_a, rows_b = rows_of(analysis_a), rows_of(analysis_b)
    rows: list[FormulaDiffRow] = []
    for key in list(rows_a) + [k for k in rows_b if k not in rows_a]:
        item_a, pct_a = rows_a.get(key, (None, None))
        item_b, pct_b = rows_b.get(key, (None, None))
        sample = item_a or item_b
        grams_a = item_a.grams if item_a else None
        grams_b = item_b.grams if item_b else None
        rows.append(FormulaDiffRow(
            key=key, sku=sample.sku, name=sample.name, role=sample.role,
            a_grams=grams_a, b_grams=grams_b, delta_grams=_delta(grams_a, grams_b),
            a_pct=pct_a, b_pct=pct_b, delta_pct=_delta(pct_a, pct_b),
        ))

    metrics = [
        FormulaDiffMetric(code, getattr(analysis_a, code), getattr(analysis_b, code),
                          _delta(getattr(analysis_a, code), getattr(analysis_b, code)))
        for code in ("hydration_pct", "salt_pct", "prefermented_flour_pct")
    ]
    same_unit = a.yield_unit == b.yield_unit
    metrics.append(FormulaDiffMetric(
        "yield", a.yield_quantity, b.yield_quantity,
        _delta(a.yield_quantity, b.yield_quantity) if same_unit else None,
        unit=a.yield_unit if same_unit else f"{a.yield_unit}/{b.yield_unit}",
    ))
    return FormulaDiff(a_ref=a.version_ref, b_ref=b.version_ref, basis=basis, rows=tuple(rows), metrics=tuple(metrics))


def _pct_of_total(grams: Decimal | None, total: Decimal) -> Decimal | None:
    if grams is None or not total:
        return None
    return quantize(grams / total * _HUNDRED)


def _sum(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def _delta(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    if left is None or right is None:
        return None
    return quantize(right - left)


# ── Bootstrap das fichas que já existem ──────────────────────────────────────


def bootstrap_entry_from_recipe(recipe):
    """Cria a entry (versão 1 publicada) a partir de uma ficha de execução. Idempotente.

    Lê a ficha, não a escreve: a versão 1 e a ficha são a mesma coisa por
    construção, então ``Recipe.meta["version_ref"]`` só nasce na primeira
    publicação real. Devolve ``None`` quando não dá para bootstrapar: ficha
    inativa ou sem unidade de saída declarada (catálogo ou
    ``meta["output_unit"]``); deduzir a unidade seria adivinhar.
    """
    from shopman.craftsman.models import RecipeEntry, RecipeVersion

    existing = RecipeEntry.objects.filter(ref=recipe.ref).first()
    if existing is not None:
        return existing
    if not recipe.is_active:
        return None
    output_unit = recipe._declared_output_unit()
    if output_unit not in RecipeVersion.YieldUnit.values:
        return None

    with transaction.atomic():
        base: dict[tuple[str, str], dict] = {}
        parts: list[dict] = []
        origin_items: list[dict] = []
        for item in recipe.items.filter(is_optional=False).order_by("sort_order"):
            origin_items.append({"sku": item.input_sku, "quantity": str(item.quantity), "unit": item.unit})
            sub = _active_mass_recipe_for(item.input_sku, exclude_pk=recipe.pk)
            grams = _mass_grams(item.quantity, item.unit)
            if sub is not None and grams is not None:
                part_entry = bootstrap_entry_from_recipe(sub)
                flour_g = _dissolve(sub, grams, base, depth=1)
                parts.append({
                    "sku": item.input_sku,
                    "entry_ref": part_entry.ref if part_entry is not None else sub.ref,
                    "kind": part_kind_from_name(sub.name, sub.ref, sub.output_sku),
                    "name": sub.name,
                    "quantity": number_text(grams),
                    "unit": "g",
                    "flour_pct": None,
                    "_flour_g": flour_g,
                })
            else:
                _add_to_base(base, item.input_sku, item.quantity, item.unit, dict(item.meta or {}))

        items = [_formula_item(entry) for entry in base.values()]
        flour_total = sum((g for g in (item_grams(it) for it in items if it["role"] == "flour") if g is not None), _ZERO)
        anchor_kind = "flour" if flour_total > 0 else "total"
        for part in parts:
            flour_g = part.pop("_flour_g")
            if anchor_kind == "flour" and flour_g > 0:
                part["flour_pct"] = number_text(flour_g / flour_total * _HUNDRED)
        formula = {
            "anchor": {"kind": anchor_kind},
            "basis_g": None,
            "standardized": False,
            "items": items,
            "parts": parts,
        }
        validate_formula(formula)

        entry = RecipeEntry.objects.create(
            ref=recipe.ref,
            name=recipe.name,
            kind=_entry_kind(recipe.ref, recipe.name),
            output_sku=recipe.output_sku,
            meta={},
        )
        version = RecipeVersion(
            entry=entry,
            number=1,
            status=RecipeVersion.Status.PUBLISHED,
            label="Ficha técnica existente",
            yield_quantity=recipe.batch_size,
            yield_unit=output_unit,
            formula=formula,
            origin={"items": origin_items, "batch_size": str(recipe.batch_size), "output_unit": output_unit},
            source={"kind": "ficha", "recipe_ref": recipe.ref},
            steps=list(recipe.steps or []),
            published_at=timezone.now(),
        )
        version.full_clean()
        version.save()
        entry.current_version = version
        entry.save(update_fields=["current_version", "updated_at"])
    return entry


def _active_mass_recipe_for(sku: str, *, exclude_pk=None):
    """A ficha ativa que produz ``sku`` em massa, ou ``None``: é o que faz de um item uma parte."""
    from shopman.craftsman.models import Recipe
    from shopman.utils import units

    qs = Recipe.objects.filter(output_sku=sku, is_active=True).order_by("pk")
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    sub = qs.first()
    if sub is None:
        return None
    if units.dimension(sub._declared_output_unit()) != units.MASS:
        return None
    return sub


def _dissolve(sub, grams: Decimal, base: dict, *, depth: int) -> Decimal:
    """Soma na base a composição de ``grams`` da parte, proporcional aos insumos dela.

    A proporção é a da composição (soma dos insumos), não do ``batch_size``: a
    perda da ficha da parte é do forno e da bacia, não da fórmula. Devolve a
    farinha (g) que a parte trouxe.
    """
    components = list(sub.items.filter(is_optional=False).order_by("sort_order"))
    weighed = []
    for component in components:
        as_dict = _formula_item(_base_line(component.input_sku, component.quantity, component.unit, dict(component.meta or {})))
        weighed.append((component, as_dict, item_grams(as_dict)))
    total = sum((g for _, _, g in weighed if g is not None), _ZERO)
    if total <= 0:
        return _ZERO
    factor = grams / total
    flour_g = _ZERO
    for component, as_dict, component_grams in weighed:
        nested = _active_mass_recipe_for(component.input_sku, exclude_pk=sub.pk) if depth < _MAX_PART_DEPTH else None
        if nested is not None and component_grams is not None:
            flour_g += _dissolve(nested, component_grams * factor, base, depth=depth + 1)
            continue
        _add_to_base(base, component.input_sku, component.quantity * factor, component.unit, dict(component.meta or {}))
        if as_dict["role"] == "flour" and component_grams is not None:
            flour_g += component_grams * factor
    return flour_g


def _base_line(sku: str, quantity: Decimal, unit: str, meta: dict) -> dict:
    from shopman.craftsman.models.recipe import normalize_recipe_item_unit

    unit = normalize_recipe_item_unit(unit)
    quantity = Decimal(str(quantity))
    if unit == "kg":
        quantity, unit = quantity * Decimal(1000), "g"
    elif unit == "mg":
        quantity, unit = quantity / Decimal(1000), "g"
    line = {"sku": sku, "name": _name_for(sku), "quantity": quantity, "unit": unit}
    if meta.get("density_g_per_ml") not in (None, ""):
        line["density_g_per_ml"] = meta["density_g_per_ml"]
    if meta.get("grams_per_unit") not in (None, ""):
        line["grams_per_unit"] = meta["grams_per_unit"]
    line["role"] = classify_ingredient(line["name"], sku)
    return line


def _add_to_base(base: dict, sku: str, quantity: Decimal, unit: str, meta: dict) -> None:
    line = _base_line(sku, quantity, unit, meta)
    key = (sku, line["unit"])
    if key in base:
        base[key]["quantity"] += line["quantity"]
    else:
        base[key] = line


def _formula_item(line: dict) -> dict:
    out = {**line, "quantity": number_text(line["quantity"])}
    for key in ("density_g_per_ml", "grams_per_unit"):
        if key in out:
            out[key] = number_text(to_decimal(out[key]))
    return out


def _mass_grams(quantity: Decimal, unit: str) -> Decimal | None:
    from shopman.craftsman.models.recipe import normalize_recipe_item_unit

    unit = normalize_recipe_item_unit(unit)
    if unit not in _MASS_UNITS:
        return None
    return Decimal(str(quantity)) * {"kg": Decimal(1000), "g": Decimal(1), "mg": Decimal("0.001")}[unit]


def _name_for(sku: str) -> str:
    from shopman.craftsman.models.recipe import _catalog_product_info

    info = _catalog_product_info(sku)
    name = getattr(info, "name", "") if info is not None else ""
    return str(name or sku)


def _entry_kind(ref: str, name: str) -> str:
    text = normalize_text(f"{ref} {name}")
    # Pré-fermento e pré-preparo de massa são padaria, antes de qualquer outra
    # pista: "creme-levain" não é creme, é o levain.
    if any(word in text for word in ("levain", "poolish", "biga", "yudane", "tangzhong", "autoliz", "autolys", "massa velha")):
        return "bread"
    if any(word in text for word in ("croissant", "folhad", "brioche", "danish", "viennois")):
        return "viennoiserie"
    if text.startswith("recheio") or "recheio" in text:
        return "filling"
    if text.startswith("creme") or " creme" in text:
        return "cream"
    if text.startswith("molho") or "vinagrete" in text:
        return "sauce"
    if any(word in text for word in ("cafe", "cha ", "espresso", "latte", "bebida", "gelado", "suco")):
        return "beverage"
    if text.startswith("massa") or "pao" in text or "pain" in text or "bread" in text:
        return "bread"
    return "other"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _yield_quantity(value: Any) -> Decimal:
    quantity = to_decimal(value)
    if quantity is None or quantity <= 0:
        raise RecipeBookError("FORMULA_INVALID", field="yield_quantity", message="O rendimento precisa ser maior que zero.")
    return quantity.quantize(Decimal("0.001"))


def _yield_unit(value: str) -> str:
    from shopman.craftsman.models import RecipeVersion
    from shopman.craftsman.models.recipe import normalize_recipe_item_unit

    unit = normalize_recipe_item_unit(value)
    if unit not in RecipeVersion.YieldUnit.values:
        raise RecipeBookError(
            "FORMULA_INVALID", field="yield_unit",
            message=f"Unidade de rendimento desconhecida; use uma de: {', '.join(RecipeVersion.YieldUnit.values)}.",
        )
    return unit


def _origin_from(formula: dict, yield_quantity: Decimal, yield_unit: str) -> dict:
    """A receita como foi informada: os itens e o rendimento, sem interpretação."""
    return {
        "items": [
            {"sku": str(it.get("sku") or ""), "name": str(it.get("name") or ""),
             "quantity": str(it.get("quantity", "")), "unit": str(it.get("unit") or "")}
            for it in list(formula.get("items") or [])
        ],
        "yield_quantity": str(yield_quantity),
        "yield_unit": yield_unit,
    }
