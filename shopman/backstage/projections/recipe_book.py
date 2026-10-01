"""Projections do inventário de receitas (RECIPE-INVENTORY-PLAN §7).

A camada de leitura que a superfície de Produção consome em ``/recipes``: o
inventário (cartões), a receita com as suas versões, a **lente** sobre uma
fórmula (porcentagem do padeiro, métricas com faixa de referência, partes,
mistura final e BOM), a comparação entre duas versões, as referências da
literatura por tipo, as opções de insumo e o rascunho lido de uma anotação ou
foto.

Tudo chega formatado (ADR-014): a superfície não faz conta. A conta é do
Craftsman (``services.recipe_book``: ``analyze``, ``check_references``,
``diff_versions``); aqui só há leitura, rótulo e formatação. As dataclasses
são o contrato gerado em ``surfaces/production-nuxt/app/generated/
recipeBookContract.ts`` (``export_recipe_book_schema``), na ordem de
dependência.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone
from shopman.craftsman.models import Recipe, RecipeEntry, RecipeVersion
from shopman.craftsman.services.recipe_book import (
    BAKERY_KINDS,
    REFERENCE_RANGES,
    FormulaAnalysis,
    FormulaDiffMetric,
    FormulaDiffRow,
    FormulaItemAnalysis,
    FormulaPartAnalysis,
    FormulaWarning,
    analyze,
    check_references,
    classify_ingredient,
    diff_versions,
    execution_in_sync,
    item_grams,
    part_formulas_for,
    reference_for,
    suggest_anchor_kind,
)

from shopman.backstage.services.exceptions import RecipeEntryNotFound, RecipeVersionNotFound
from shopman.backstage.services.recipe_capture import CapturedRecipe, is_configured
from shopman.backstage.services.recipe_matching import (
    DEFAULT_MIN_SCORE,
    IngredientCandidate,
    candidates_for,
    search_ingredients,
)

logger = logging.getLogger(__name__)

# ── Vocabulário (identificador em inglês, rótulo em pt-BR) ───────────────────

ROLE_LABELS: dict[str, str] = {
    "flour": "Farinha",
    "liquid": "Líquido",
    "salt": "Sal",
    "yeast": "Fermento",
    "fat": "Gordura",
    "sugar": "Açúcar",
    "egg": "Ovos",
    "dairy": "Laticínio",
    "inclusion": "Inclusão",
    "other": "Outro",
}

PART_KIND_LABELS: dict[str, str] = {
    "preferment": "Pré-fermento",
    "autolyse": "Autólise",
    "soaker": "Grãos hidratados",
    "old_dough": "Massa velha",
}

ANCHOR_LABELS: dict[str, str] = {
    "flour": "Farinhas totais",
    "total": "Massa total",
    "ingredient": "Um ingrediente",
}

METRIC_LABELS: dict[str, str] = {
    "hydration_pct": "Hidratação",
    "salt_pct": "Sal",
    "yeast_pct": "Fermento",
    "prefermented_flour_pct": "Farinha pré-fermentada",
    "fat_pct": "Gordura",
    "sugar_pct": "Açúcar",
    "egg_pct": "Ovos",
}

#: Métricas que valem zero sem ser aviso: pão de levain não leva fermento, massa
#: magra não leva açúcar. Só hidratação e sal em zero merecem atenção.
_METRICS_MEANINGFUL_AT_ZERO = ("hydration_pct", "salt_pct")

#: Tipos de receita que ganham as faixas de farinha por parte na tabela de referência.
_KINDS_WITH_PARTS = ("bread", "viennoiserie", "sweet_dough")

PART_REFERENCE_LABELS: dict[str, str] = {
    "levain": "Levain",
    "poolish": "Poolish",
    "biga": "Biga",
    "soaker": "Grãos hidratados (yudane, tangzhong)",
    "old_dough": "Massa velha",
    "autolyse": "Autólise",
}

SOURCE_LABELS: dict[str, str] = {
    "manual": "Manual",
    "note": "Anotação",
    "photo": "Foto",
    "ficha": "Ficha técnica",
    "import": "Importada",
}

#: Avisos informativos: contam o que a conta assumiu, sem pedir ação.
_INFORMATIVE_WARNINGS = ("LIQUID_DENSITY_ASSUMED",)

_ZERO = Decimal("0")
_THOUSAND = Decimal("1000")
_GRAMS_PER_UNIT = {"g": Decimal(1), "kg": _THOUSAND, "mg": Decimal("0.001")}


# ── Contrato (§7) ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecipeEntryCardProjection:
    """A recipe entry card on the recipe book inventory."""

    ref: str
    name: str
    kind: str
    kind_label: str
    output_sku: str
    output_name: str
    has_ficha: bool
    current_version_number: int | None
    version_count: int
    draft_count: int
    anchor_kind: str
    hydration_display: str
    updated_at_display: str
    is_archived: bool


@dataclass(frozen=True)
class KindOptionProjection:
    """A recipe kind option (filter chip)."""

    value: str
    label: str


@dataclass(frozen=True)
class RecipeBookListProjection:
    """The recipe book inventory list."""

    entries: tuple[RecipeEntryCardProjection, ...]
    kinds: tuple[KindOptionProjection, ...]
    count: int


@dataclass(frozen=True)
class RecipeBookAccessProjection:
    """What the current operator may do on the recipe book."""

    can_view: bool
    can_edit: bool
    capture_available: bool


@dataclass(frozen=True)
class FormulaItemProjection:
    """One ingredient line of a formula, with its share of the anchor."""

    sku: str
    name: str
    role: str
    role_label: str
    quantity_display: str
    quantity_g: str
    unit: str
    pct_display: str
    is_anchor: bool
    matched: bool


@dataclass(frozen=True)
class FormulaPartProjection:
    """A part of the base formula (preferment, autolyse, soaker, old dough)."""

    sku: str
    entry_ref: str
    name: str
    kind: str
    kind_label: str
    flour_pct_display: str
    quantity_display: str
    cap_pct_display: str
    has_formula: bool


@dataclass(frozen=True)
class FormulaMetricProjection:
    """A bakery metric with its reference range and tone."""

    code: str
    label: str
    value_display: str
    low_display: str
    high_display: str
    max_display: str
    tone: str
    note: str


@dataclass(frozen=True)
class FormulaWarningProjection:
    """A warning raised by the formula analysis."""

    code: str
    message: str
    tone: str


@dataclass(frozen=True)
class FormulaLensProjection:
    """The lens over a formula: anchor, items with percentages, metrics, parts, final mix, BOM."""

    is_bakery: bool
    anchor_kind: str
    anchor_label: str
    basis_display: str
    standardized: bool
    anchor_total_display: str
    total_mass_display: str
    items: tuple[FormulaItemProjection, ...]
    final_mix: tuple[FormulaItemProjection, ...]
    #: A mistura final diz algo que a receita base já não disse? Sem partes ela é a
    #: própria base, e mostrar a mesma tabela duas vezes só ensina o padeiro a
    #: parar de ler. A tela pergunta isto antes de desenhar o painel.
    final_mix_differs: bool
    bom: tuple[FormulaItemProjection, ...]
    #: Idem para a ficha técnica: ela só difere da base quando há parte pronta
    #: (é aí que a farinha do levain sai da lista e entra como levain).
    bom_differs: bool
    parts: tuple[FormulaPartProjection, ...]
    metrics: tuple[FormulaMetricProjection, ...]
    warnings: tuple[FormulaWarningProjection, ...]


@dataclass(frozen=True)
class RecipeVersionProjection:
    """A frozen formula version of a recipe entry."""

    id: int
    number: int
    status: str
    status_label: str
    label: str
    yield_quantity: str
    yield_unit: str
    yield_display: str
    source_kind: str
    source_label: str
    created_by: str
    created_at_display: str
    published_at_display: str
    notes: str
    steps: tuple[str, ...]
    lens: FormulaLensProjection
    formula: dict
    origin: dict


@dataclass(frozen=True)
class UsageCaveatProjection:
    """A warning that travels with the usage numbers (what they do NOT measure)."""

    code: str
    message: str


@dataclass(frozen=True)
class QualityShareProjection:
    """Units of one quality grade among a version's executed batches."""

    grade_ref: str
    label: str
    quantity_display: str
    share_display: str


@dataclass(frozen=True)
class VersionUsageProjection:
    """What the house produced with one version (or with no version stamp)."""

    version_ref: str
    version_number: int | None
    is_versioned: bool
    label: str
    batches: int
    batches_display: str
    planned_display: str
    finished_display: str
    loss_display: str
    yield_pct: str
    yield_display: str
    avg_loss: str
    avg_loss_display: str
    loss_pct_display: str
    summary_display: str
    quality: tuple[QualityShareProjection, ...]


@dataclass(frozen=True)
class RecipeUsageProjection:
    """Executed batches of a recipe entry, by version, read from the work orders."""

    date_from: str
    date_to: str
    bake_loss_basis: str
    caveats: tuple[UsageCaveatProjection, ...]
    versions: tuple[VersionUsageProjection, ...]
    unversioned: VersionUsageProjection | None


@dataclass(frozen=True)
class RecipeEntryDetailProjection:
    """A recipe entry with its versions (newest first)."""

    ref: str
    name: str
    kind: str
    kind_label: str
    output_sku: str
    output_name: str
    notes: str
    is_archived: bool
    current_version_number: int | None
    ficha_ref: str
    #: A ficha de execução ainda é a que a versão atual escreveu (ADR-027)?
    #: ``False`` também quando não há ficha ou versão atual. A conta é do
    #: Craftsman (``execution_in_sync``): carimbo ``version_ref`` + impressão
    #: digital do conteúdo, que pega a ficha editada pelo Admin.
    execution_in_sync: bool
    versions: tuple[RecipeVersionProjection, ...]
    usage: RecipeUsageProjection


@dataclass(frozen=True)
class RecipeCompareRowProjection:
    """One ingredient row of a version comparison."""

    name: str
    sku: str
    role_label: str
    a_display: str
    b_display: str
    delta_display: str
    delta_pct_display: str
    tone: str


@dataclass(frozen=True)
class RecipeCompareMetricProjection:
    """One metric row of a version comparison."""

    label: str
    a_display: str
    b_display: str
    delta_display: str
    tone: str


@dataclass(frozen=True)
class RecipeCompareProjection:
    """Two formula versions side by side."""

    a_title: str
    b_title: str
    rows: tuple[RecipeCompareRowProjection, ...]
    metrics: tuple[RecipeCompareMetricProjection, ...]


@dataclass(frozen=True)
class ReferenceRangeProjection:
    """A reference range from the literature for a recipe kind."""

    code: str
    label: str
    low_display: str
    high_display: str
    max_display: str
    note: str


@dataclass(frozen=True)
class RecipeReferenceProjection:
    """The reference ranges for a recipe kind."""

    kind: str
    kind_label: str
    ranges: tuple[ReferenceRangeProjection, ...]


@dataclass(frozen=True)
class IngredientOptionProjection:
    """An ingredient option (material or recipe entry with a formula)."""

    sku: str
    name: str
    unit: str
    role: str
    is_part: bool
    entry_ref: str


@dataclass(frozen=True)
class CaptureItemProjection:
    """One ingredient read from a note or a photo, with its matched material."""

    name: str
    original_text: str
    quantity: str
    unit: str
    role: str
    sku: str
    match_confidence: str
    candidates: tuple[IngredientOptionProjection, ...]


@dataclass(frozen=True)
class RecipeCaptureDraftProjection:
    """The structured draft read from a note or a photo."""

    name: str
    kind: str
    language: str
    yield_quantity: str
    yield_unit: str
    items: tuple[CaptureItemProjection, ...]
    steps: tuple[str, ...]
    notes: str
    formula: dict


# ── Formatação ───────────────────────────────────────────────────────────────


def _decimal(value: Any) -> Decimal | None:
    """``Decimal`` de qualquer coisa que pareça número; ``None`` quando não é."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _number(value: Decimal) -> str:
    """Três casas, sem zeros à direita, vírgula decimal (o mesmo dialeto de ``_measure``)."""
    normalized = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP).normalize()
    return format(normalized, "f").replace(".", ",")


def _plain_number(value: Decimal | None) -> str:
    """Texto numérico para VALOR (ponto decimal), não para exibição: rendimento e quantidade."""
    if value is None:
        return ""
    normalized = value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP).normalize()
    return format(normalized, "f")


def _grams_display(grams: Decimal | None) -> str:
    """"850 g" até 999,999 g; "1,2 kg" a partir de 1 kg. Vazio quando não se sabe."""
    if grams is None:
        return ""
    if abs(grams) >= _THOUSAND:
        return f"{_number(grams / _THOUSAND)} kg"
    return f"{_number(grams)} g"


def _quantity_display(quantity: Decimal | None, unit: str) -> str:
    """A quantidade na unidade em que o padeiro a escreveu ("3 un", "700 ml")."""
    if quantity is None:
        return ""
    return f"{_number(quantity)} {unit}".strip()


def _pct_display(value: Decimal | None) -> str:
    """"85%", ou "85,5%" quando não é inteiro. Vazio quando não há valor."""
    if value is None:
        return ""
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return f"{int(rounded)}%"
    return f"{format(rounded, 'f').replace('.', ',')}%"


def _signed(text: str, value: Decimal) -> str:
    return f"+{text}" if value > 0 else text


def _delta_grams_display(delta: Decimal | None) -> str:
    if delta is None:
        return ""
    return _signed(_grams_display(delta), delta)


def _delta_pct_display(delta: Decimal | None) -> str:
    if delta is None:
        return ""
    return _signed(_pct_display(delta), delta)


def _delta_tone(left: Decimal | None, right: Decimal | None, delta: Decimal | None) -> str:
    """Só num lado = destaque; igual = calmo; diferente = normal."""
    if left is None or right is None:
        return "warning"
    if delta is None or delta == _ZERO:
        return "muted"
    return "ok"


def _datetime_display(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d/%m/%Y %H:%M")


def _date_display(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%d/%m/%Y")


def _kind_label(kind: str) -> str:
    return str(dict(RecipeEntry.Kind.choices).get(kind, "") or RecipeEntry.Kind.OTHER.label)


def _status_label(status: str) -> str:
    return str(dict(RecipeVersion.Status.choices).get(status, "") or status)


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role) or PART_KIND_LABELS.get(role) or ROLE_LABELS["other"]


def _kind_options() -> tuple[KindOptionProjection, ...]:
    return tuple(KindOptionProjection(value=value, label=str(label)) for value, label in RecipeEntry.Kind.choices)


def wire_formula(formula: Any) -> dict:
    """A fórmula como a superfície a lê de volta: ``basis_g`` numérico, o resto como está.

    O Craftsman guarda ``basis_g`` como texto de ``Decimal`` (precisão no JSON);
    a superfície declara ``basis_g: number | null`` no payload de escrita e só
    reconhece número ao carregar uma versão no editor.
    """
    if not isinstance(formula, dict):
        return {}
    out = dict(formula)
    basis = _decimal(out.get("basis_g"))
    if basis is None:
        out["basis_g"] = None
    else:
        out["basis_g"] = int(basis) if basis == basis.to_integral_value() else float(basis)
    return out


def _output_names(skus: set[str]) -> dict[str, str]:
    """Nome do SKU produzido: o catálogo responde primeiro; o insumo (pré-preparo) depois."""
    if not skus:
        return {}
    names: dict[str, str] = {}
    try:
        from shopman.offerman.models import Product

        names.update(Product.objects.filter(sku__in=skus).values_list("sku", "name"))
    except Exception:  # silêncio-deliberado: nome é rótulo; sem ele a tela mostra o SKU, nada mais depende dele
        logger.debug("recipe_book.product_names_unavailable", exc_info=True)
    missing = {sku for sku in skus if sku not in names}
    if missing:
        try:
            from shopman.buyman.models import Material

            names.update(Material.objects.filter(sku__in=missing).values_list("sku", "name"))
        except Exception:  # silêncio-deliberado: idem, o nome do insumo é só rótulo
            logger.debug("recipe_book.material_names_unavailable", exc_info=True)
    return names


# ── Lente ────────────────────────────────────────────────────────────────────


def build_formula_lens(formula: dict, kind: str = "") -> FormulaLensProjection:
    """A fórmula lida pela lente do padeiro, pronta para a tela.

    A lente vem do conteúdo (§1): âncora ``flour`` numa receita de padaria liga
    as métricas do padeiro (``is_bakery``); um creme com âncora de farinha
    continua creme, e as métricas saem em tom ``muted``. As faixas de
    referência são as do ``kind`` da receita; fora da faixa é tom ``warning``,
    nunca bloqueio.
    """
    formula = formula if isinstance(formula, dict) else {}
    kind = kind or RecipeEntry.Kind.OTHER
    analysis = analyze(formula, part_formulas_for(formula))
    references = check_references(analysis, kind)
    anchor = formula.get("anchor") if isinstance(formula.get("anchor"), dict) else {}
    anchor_sku = str(anchor.get("sku") or "")
    anchor_kind = analysis.anchor_kind
    flagged = {warning.metric for warning in references}

    basis = _decimal(formula.get("basis_g"))
    return FormulaLensProjection(
        is_bakery=anchor_kind == "flour" and kind in BAKERY_KINDS,
        anchor_kind=anchor_kind,
        anchor_label=_anchor_label(anchor_kind, anchor_sku, analysis),
        basis_display=f"{_number(basis)} g" if basis else "",
        standardized=formula.get("standardized") is True,
        anchor_total_display=_grams_display(analysis.anchor_total_g),
        total_mass_display=_grams_display(analysis.total_mass_g),
        items=tuple(_lens_item(item, anchor_kind, anchor_sku) for item in analysis.items),
        final_mix=tuple(_lens_item(item, anchor_kind, anchor_sku) for item in analysis.final_mix),
        final_mix_differs=_subtracting_parts(analysis),
        bom=tuple(_bom_item(line, analysis.anchor_total_g) for line in analysis.bom),
        bom_differs=_subtracting_parts(analysis) or _capped_old_dough(analysis),
        parts=tuple(_lens_part(part) for part in analysis.parts),
        metrics=tuple(
            _metric(code, value, kind, flagged) for code, value in analysis.metrics().items()
        ),
        warnings=tuple(_warning(warning) for warning in (*analysis.warnings, *references)),
    )


def _subtracting_parts(analysis: FormulaAnalysis) -> bool:
    """Alguma parte de fato tira da base? É ela que faz a mistura final ser outra coisa.

    Parte sem fórmula conhecida fica na base e não tira nada; massa velha é teto,
    não composição. Nos dois casos a mistura final É a receita base.
    """
    return any(part.has_formula and part.quantity_g for part in analysis.parts)


def _capped_old_dough(analysis: FormulaAnalysis) -> bool:
    """Há massa velha com teto? Ela não tira da base, mas entra na ficha como linha opcional."""
    return any(part.kind == "old_dough" and part.cap_pct for part in analysis.parts)


def _anchor_label(anchor_kind: str, anchor_sku: str, analysis: FormulaAnalysis) -> str:
    label = ANCHOR_LABELS.get(anchor_kind, anchor_kind)
    if anchor_kind != "ingredient":
        return label
    name = next((item.name for item in analysis.items if item.sku == anchor_sku), anchor_sku)
    return f"{label} ({name})" if name else label


def _lens_item(item: FormulaItemAnalysis, anchor_kind: str, anchor_sku: str) -> FormulaItemProjection:
    if anchor_kind == "flour":
        is_anchor = item.role == "flour"
    elif anchor_kind == "ingredient":
        is_anchor = bool(item.sku) and item.sku == anchor_sku
    else:
        is_anchor = False
    return FormulaItemProjection(
        sku=item.sku,
        name=item.name,
        role=item.role,
        role_label=_role_label(item.role),
        quantity_display=_quantity_display(item.quantity, item.unit),
        quantity_g="" if item.grams is None else _number(item.grams),
        unit=item.unit,
        pct_display=_pct_display(item.pct),
        is_anchor=is_anchor,
        matched=bool(item.sku),
    )


def _bom_item(line: dict, anchor_total: Decimal | None) -> FormulaItemProjection:
    quantity = _decimal(line.get("quantity"))
    unit = str(line.get("unit") or "g")
    factor = _GRAMS_PER_UNIT.get(unit)
    grams = None if quantity is None or factor is None else quantity * factor
    pct = None
    if grams is not None and anchor_total:
        pct = grams / anchor_total * Decimal(100)
    role = str(line.get("role") or "other")
    sku = str(line.get("sku") or "")
    return FormulaItemProjection(
        sku=sku,
        name=str(line.get("name") or sku),
        role=role,
        role_label=_role_label(role),
        quantity_display=_quantity_display(quantity, unit),
        quantity_g="" if grams is None else _number(grams),
        unit=unit,
        pct_display=_pct_display(pct),
        is_anchor=False,
        matched=bool(sku),
    )


def _lens_part(part: FormulaPartAnalysis) -> FormulaPartProjection:
    return FormulaPartProjection(
        sku=part.sku,
        entry_ref=part.entry_ref,
        name=part.name,
        kind=part.kind,
        kind_label=PART_KIND_LABELS.get(part.kind, part.kind),
        flour_pct_display=_pct_display(part.flour_pct),
        quantity_display=_grams_display(part.quantity_g),
        cap_pct_display=_pct_display(part.cap_pct),
        has_formula=part.has_formula,
    )


def _metric(code: str, value: Decimal | None, kind: str, flagged: set[str]) -> FormulaMetricProjection:
    bounds = reference_for(code, kind) or {}
    if value is None:
        tone = "muted"
    elif code in flagged:
        tone = "warning"
    elif value == _ZERO and code not in _METRICS_MEANINGFUL_AT_ZERO:
        tone = "muted"
    else:
        tone = "ok"
    return FormulaMetricProjection(
        code=code,
        label=METRIC_LABELS.get(code, code),
        value_display=_pct_display(value),
        low_display=_pct_display(bounds.get("low")),
        high_display=_pct_display(bounds.get("high")),
        max_display=_pct_display(bounds.get("max")),
        tone=tone,
        note=str(bounds.get("note") or ""),
    )


def _warning(warning: FormulaWarning) -> FormulaWarningProjection:
    return FormulaWarningProjection(
        code=warning.code,
        message=warning.message,
        tone="muted" if warning.code in _INFORMATIVE_WARNINGS else "warning",
    )


# ── Inventário e receita ─────────────────────────────────────────────────────


def build_recipe_book(*, query: str = "", kind: str = "", archived: bool = False) -> RecipeBookListProjection:
    """O inventário: um cartão por receita, com filtro por texto, tipo e arquivadas."""
    entries_qs = (
        RecipeEntry.objects.filter(is_archived=bool(archived))
        .select_related("current_version")
        .annotate(
            version_total=Count("versions", distinct=True),
            draft_total=Count("versions", filter=Q(versions__status=RecipeVersion.Status.DRAFT), distinct=True),
        )
        .order_by("name", "ref")
    )
    if kind:
        entries_qs = entries_qs.filter(kind=kind)
    term = (query or "").strip()
    if term:
        entries_qs = entries_qs.filter(
            Q(name__icontains=term) | Q(ref__icontains=term) | Q(output_sku__icontains=term)
        )
    entries = list(entries_qs)
    names = _output_names({entry.output_sku for entry in entries if entry.output_sku})
    ficha_refs = set(
        Recipe.objects.filter(ref__in=[entry.ref for entry in entries], is_active=True).values_list("ref", flat=True)
    )
    cards = tuple(_card(entry, names, ficha_refs) for entry in entries)
    return RecipeBookListProjection(entries=cards, kinds=_kind_options(), count=len(cards))


def _card(entry: RecipeEntry, names: dict[str, str], ficha_refs: set[str]) -> RecipeEntryCardProjection:
    current = entry.current_version
    formula = dict(current.formula or {}) if current is not None else {}
    anchor = formula.get("anchor") if isinstance(formula.get("anchor"), dict) else {}
    anchor_kind = str(anchor.get("kind") or "") if current is not None else ""
    hydration = ""
    if anchor_kind == "flour":
        hydration = _pct_display(analyze(formula, part_formulas_for(formula)).hydration_pct)
    return RecipeEntryCardProjection(
        ref=entry.ref,
        name=entry.name,
        kind=entry.kind,
        kind_label=_kind_label(entry.kind),
        output_sku=entry.output_sku,
        output_name=names.get(entry.output_sku, "") if entry.output_sku else "",
        has_ficha=entry.ref in ficha_refs,
        current_version_number=current.number if current is not None else None,
        version_count=int(getattr(entry, "version_total", 0) or 0),
        draft_count=int(getattr(entry, "draft_total", 0) or 0),
        anchor_kind=anchor_kind,
        hydration_display=hydration,
        updated_at_display=_date_display(entry.updated_at),
        is_archived=entry.is_archived,
    )


def build_recipe_entry(ref: str) -> RecipeEntryDetailProjection:
    """A receita com todas as versões (mais nova primeiro), cada uma com a lente calculada."""
    entry = RecipeEntry.objects.filter(ref=ref).select_related("current_version").first()
    if entry is None:
        raise RecipeEntryNotFound(f"Receita '{ref}' não existe no inventário.")
    versions = list(entry.versions.order_by("-number"))
    names = _output_names({entry.output_sku} if entry.output_sku else set())
    ficha = Recipe.objects.filter(ref=entry.ref, is_active=True).first()
    current = entry.current_version
    return RecipeEntryDetailProjection(
        ref=entry.ref,
        name=entry.name,
        kind=entry.kind,
        kind_label=_kind_label(entry.kind),
        output_sku=entry.output_sku,
        output_name=names.get(entry.output_sku, "") if entry.output_sku else "",
        notes=entry.notes or "",
        is_archived=entry.is_archived,
        current_version_number=current.number if current is not None else None,
        ficha_ref=entry.ref if ficha is not None else "",
        execution_in_sync=execution_in_sync(current, ficha),
        versions=tuple(build_recipe_version(version, kind=entry.kind) for version in versions),
        usage=build_recipe_usage(entry.ref),
    )


def build_recipe_version(version: RecipeVersion, *, kind: str) -> RecipeVersionProjection:
    """Uma versão congelada, com a lente sobre a sua fórmula."""
    source = version.source if isinstance(version.source, dict) else {}
    source_kind = str(source.get("kind") or "")
    return RecipeVersionProjection(
        id=version.pk,
        number=version.number,
        status=version.status,
        status_label=_status_label(version.status),
        label=version.label or "",
        yield_quantity=_plain_number(version.yield_quantity),
        yield_unit=version.yield_unit,
        yield_display=_quantity_display(version.yield_quantity, version.yield_unit),
        source_kind=source_kind,
        source_label=SOURCE_LABELS.get(source_kind, source_kind),
        created_by=version.created_by or "",
        created_at_display=_datetime_display(version.created_at),
        published_at_display=_datetime_display(version.published_at),
        notes=version.notes or "",
        steps=tuple(str(step) for step in (version.steps or [])),
        lens=build_formula_lens(version.formula or {}, kind),
        formula=wire_formula(version.formula),
        origin=dict(version.origin or {}),
    )


# ── Uso real por versão (reputação, fatia 1) ─────────────────────────────────

USAGE_CAVEAT_MESSAGES: dict[str, str] = {
    "loss_is_residual": (
        "A perda é o que entrou na fornada menos o que saiu dela, pela conta e não pela balança: "
        "massa na bacia, aparas e peça não anotada entram todas aqui."
    ),
    "unversioned_not_attributed": (
        "Fornada sem carimbo de versão (ficha nunca publicada pelo inventário, ou planejada antes "
        "da publicação) fica em \"Sem versão\" e não conta para versão nenhuma."
    ),
    "bake_loss_house_default": (
        "A perda de forno desta ficha não foi declarada: vale o padrão da casa, uma estimativa "
        "que nunca passou pela balança."
    ),
    "bake_loss_estimated": "A perda de forno desta ficha foi declarada, mas ninguém a pesou.",
}

UNVERSIONED_LABEL = "Sem versão"


def build_recipe_usage(ref: str, *, date_from=None, date_to=None) -> RecipeUsageProjection:
    """As fornadas EXECUTADAS da receita, por versão, num intervalo de datas (inclusivo).

    Lê as ``WorkOrder`` (não os ``DayClosing``): fornada concluída, agrupada pelo
    ``version_ref`` congelado no plano. Rendimento = concluído ÷ planejado das
    executadas; perda = soma do resíduo ``(iniciado ou planejado) − concluído``.

    Os avisos vão no dado (``caveats``), e a ordem é a da linha do tempo (versão
    mais nova primeiro), **nunca** por perda: a perda é resíduo contábil, e
    ordenar por ela ordenaria por quem anota melhor. Fornada sem carimbo, ou com
    carimbo que não é desta receita, cai em ``unversioned`` e não é atribuída.
    """
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.services.closing import VERSION_CAVEATS, aggregate_by_version

    work_orders = WorkOrder.objects.filter(recipe__ref=ref, finished__isnull=False)
    if date_from is not None:
        work_orders = work_orders.filter(target_date__gte=date_from)
    if date_to is not None:
        work_orders = work_orders.filter(target_date__lte=date_to)

    by_number: dict[int, dict] = {}
    unversioned: dict | None = None
    for row in aggregate_by_version(work_orders):
        number = _own_version_number(row["version_ref"], ref)
        if number is None:
            unversioned = _merge_usage_rows(unversioned, row)
        else:
            by_number[number] = _merge_usage_rows(by_number.get(number), row)

    grade_labels = _quality_grade_labels()
    basis = _bake_loss_basis(ref)
    codes = list(VERSION_CAVEATS)
    if basis in ("house_default", "estimated"):
        codes.append(f"bake_loss_{basis}")
    return RecipeUsageProjection(
        date_from=date_from.isoformat() if date_from else "",
        date_to=date_to.isoformat() if date_to else "",
        bake_loss_basis=basis,
        caveats=tuple(UsageCaveatProjection(code=code, message=USAGE_CAVEAT_MESSAGES[code]) for code in codes),
        versions=tuple(
            _version_usage(by_number[number], number=number, ref=ref, grade_labels=grade_labels)
            for number in sorted(by_number, reverse=True)
        ),
        unversioned=(
            _version_usage(unversioned, number=None, ref=ref, grade_labels=grade_labels)
            if unversioned is not None
            else None
        ),
    )


def _own_version_number(version_ref: str, ref: str) -> int | None:
    """O número da versão quando o carimbo é DESTA receita; ``None`` senão (sem versão)."""
    if not version_ref:
        return None
    try:
        stamped_ref, number = parse_version_ref(version_ref)
    except ValueError:
        return None
    return number if stamped_ref == ref else None


_USAGE_SUM_KEYS = ("executed", "executed_planned", "executed_started", "finished", "loss")


def _merge_usage_rows(acc: dict | None, row: dict) -> dict:
    if acc is None:
        return {**{key: row[key] for key in _USAGE_SUM_KEYS}, "quality": dict(row.get("quality") or {})}
    for key in _USAGE_SUM_KEYS:
        acc[key] += row[key]
    for grade, qty in (row.get("quality") or {}).items():
        acc["quality"][grade] = acc["quality"].get(grade, _ZERO) + qty
    return acc


def _version_usage(row: dict, *, number: int | None, ref: str, grade_labels: dict[str, tuple[int, str]]) -> VersionUsageProjection:
    batches = int(row["executed"])
    planned, started, finished, loss = (
        row["executed_planned"], row["executed_started"], row["finished"], row["loss"],
    )
    yield_pct = (finished / planned * 100) if planned else None
    avg_loss = (loss / batches) if batches else None
    loss_pct = (loss / started * 100) if started else None
    batches_display = f"{batches} fornada" if batches == 1 else f"{batches} fornadas"
    avg_loss_display = f"{_number(avg_loss)} por fornada" if avg_loss is not None else ""
    summary = batches_display
    if yield_pct is not None:
        summary += f"; rendimento médio {_pct_display(yield_pct)}"
    if avg_loss_display:
        summary += f"; perda média {avg_loss_display}"

    quality = row.get("quality") or {}
    graded_total = sum(quality.values(), _ZERO)
    # Ordem da ESCALA (melhor grau primeiro), fixa — nunca pelo volume.
    grades = sorted(quality, key=lambda grade: (-grade_labels.get(grade, (0, ""))[0], grade))
    return VersionUsageProjection(
        version_ref=f"{ref}@{number}" if number is not None else "",
        version_number=number,
        is_versioned=number is not None,
        label=f"Versão {number}" if number is not None else UNVERSIONED_LABEL,
        batches=batches,
        batches_display=batches_display,
        planned_display=_number(planned),
        finished_display=_number(finished),
        loss_display=_number(loss),
        yield_pct=_plain_number(yield_pct),
        yield_display=_pct_display(yield_pct),
        avg_loss=_plain_number(avg_loss),
        avg_loss_display=avg_loss_display,
        loss_pct_display=_pct_display(loss_pct),
        summary_display=summary,
        quality=tuple(
            QualityShareProjection(
                grade_ref=grade,
                label=grade_labels.get(grade, (0, grade))[1] or grade,
                quantity_display=_number(quality[grade]),
                share_display=_pct_display(quality[grade] / graded_total * 100) if graded_total else "",
            )
            for grade in grades
        ),
    )


def _quality_grade_labels() -> dict[str, tuple[int, str]]:
    from shopman.shop.models import QualityGrade

    return {grade.ref: (grade.rank, grade.label) for grade in QualityGrade.objects.all()}


def _bake_loss_basis(ref: str) -> str:
    """Espécie da perda de forno da ficha ATIVA desta receita; ``""`` sem ficha."""
    from shopman.shop.services.unit_weight_from_recipe import bake_loss_basis

    recipe = Recipe.objects.filter(ref=ref, is_active=True).first()
    return bake_loss_basis(recipe) if recipe is not None else ""


# ── Comparação ───────────────────────────────────────────────────────────────


def parse_version_ref(value: str) -> tuple[str, int]:
    """``"<ref>@<n>"`` em ``(ref, n)``. Levanta ``ValueError`` quando não tem essa cara."""
    text = str(value or "").strip()
    ref, at, number = text.rpartition("@")
    if not at or not ref or not number.isdigit() or int(number) < 1:
        raise ValueError(f"Referência de versão inválida: '{text}'. Use <ref>@<n>.")
    return ref, int(number)


def resolve_version(value: str) -> RecipeVersion:
    """A versão apontada por ``<ref>@<n>``. 404 por tipo quando não existe."""
    ref, number = parse_version_ref(value)
    entry = RecipeEntry.objects.filter(ref=ref).first()
    if entry is None:
        raise RecipeEntryNotFound(f"Receita '{ref}' não existe no inventário.")
    version = entry.versions.filter(number=number).first()
    if version is None:
        raise RecipeVersionNotFound(f"A receita '{ref}' não tem a versão {number}.")
    return version


def build_recipe_compare(a_ref: str, b_ref: str) -> RecipeCompareProjection:
    """Duas versões lado a lado, na mesma base (``diff_versions``)."""
    a = resolve_version(a_ref)
    b = resolve_version(b_ref)
    diff = diff_versions(a, b)
    return RecipeCompareProjection(
        a_title=_version_title(a),
        b_title=_version_title(b),
        rows=tuple(_compare_row(row) for row in diff.rows),
        metrics=tuple(_compare_metric(metric) for metric in diff.metrics),
    )


def _version_title(version: RecipeVersion) -> str:
    return f"{version.entry.name} (versão {version.number})"


def _compare_row(row: FormulaDiffRow) -> RecipeCompareRowProjection:
    return RecipeCompareRowProjection(
        name=row.name,
        sku=row.sku,
        role_label=_role_label(row.role),
        a_display=_grams_display(row.a_grams),
        b_display=_grams_display(row.b_grams),
        delta_display=_delta_grams_display(row.delta_grams),
        delta_pct_display=_delta_pct_display(row.delta_pct),
        tone=_delta_tone(row.a_grams, row.b_grams, row.delta_grams),
    )


def _compare_metric(metric: FormulaDiffMetric) -> RecipeCompareMetricProjection:
    if metric.code == "yield":
        label = "Rendimento"
        a_display = _quantity_display(metric.a, metric.unit.split("/")[0])
        b_display = _quantity_display(metric.b, metric.unit.split("/")[-1])
        delta_display = "" if metric.delta is None else _signed(_quantity_display(metric.delta, metric.unit), metric.delta)
    else:
        label = METRIC_LABELS.get(metric.code, metric.code)
        a_display = _pct_display(metric.a)
        b_display = _pct_display(metric.b)
        delta_display = _delta_pct_display(metric.delta)
    return RecipeCompareMetricProjection(
        label=label,
        a_display=a_display,
        b_display=b_display,
        delta_display=delta_display,
        tone=_delta_tone(metric.a, metric.b, metric.delta),
    )


# ── Referências da literatura ────────────────────────────────────────────────


def build_recipe_reference(kind: str) -> RecipeReferenceProjection:
    """As faixas da literatura para um tipo de receita. Referência, não regra."""
    kind = kind or RecipeEntry.Kind.OTHER
    ranges: list[ReferenceRangeProjection] = []
    for code, label in METRIC_LABELS.items():
        bounds = reference_for(code, kind)
        if bounds:
            ranges.append(_range(code, label, bounds))
    if kind in _KINDS_WITH_PARTS:
        for key, bounds in REFERENCE_RANGES["part_flour_pct"].items():
            part_label = PART_REFERENCE_LABELS.get(key, key)
            ranges.append(_range(f"part_flour_pct:{key}", f"Farinha na parte: {part_label}", bounds))
    return RecipeReferenceProjection(kind=kind, kind_label=_kind_label(kind), ranges=tuple(ranges))


def _range(code: str, label: str, bounds: dict) -> ReferenceRangeProjection:
    return ReferenceRangeProjection(
        code=code,
        label=label,
        low_display=_pct_display(bounds.get("low")),
        high_display=_pct_display(bounds.get("high")),
        max_display=_pct_display(bounds.get("max")),
        note=str(bounds.get("note") or ""),
    )


# ── Insumos e partes ─────────────────────────────────────────────────────────


def _part_entries() -> list[RecipeEntry]:
    """As receitas com versão atual e SKU: são as partes que outra receita pode consumir."""
    return list(
        RecipeEntry.objects.filter(current_version__isnull=False, is_archived=False)
        .exclude(output_sku="")
        .select_related("current_version")
        .order_by("name", "ref")
    )


def _part_candidate(entry: RecipeEntry) -> IngredientCandidate:
    return IngredientCandidate(
        sku=entry.output_sku,
        name=entry.name,
        unit=entry.current_version.yield_unit if entry.current_version is not None else "kg",
        role=classify_ingredient(entry.name, entry.output_sku),
        score=0,
    )


def _part_option(entry: RecipeEntry) -> IngredientOptionProjection:
    candidate = _part_candidate(entry)
    return IngredientOptionProjection(
        sku=candidate.sku,
        name=candidate.name,
        unit=candidate.unit,
        role=candidate.role,
        is_part=True,
        entry_ref=entry.ref,
    )


def _material_option(candidate: IngredientCandidate, part_refs: dict[str, str]) -> IngredientOptionProjection:
    entry_ref = part_refs.get(candidate.sku, "")
    return IngredientOptionProjection(
        sku=candidate.sku,
        name=candidate.name,
        unit=candidate.unit,
        role=candidate.role,
        is_part=bool(entry_ref),
        entry_ref=entry_ref,
    )


def build_ingredient_options(query: str = "") -> tuple[IngredientOptionProjection, ...]:
    """Opções para casar um ingrediente: as partes (receitas com fórmula) e os insumos."""
    term = (query or "").strip().lower()
    parts = [
        entry
        for entry in _part_entries()
        if not term or term in entry.name.lower() or term in entry.output_sku.lower() or term in entry.ref.lower()
    ]
    part_skus = {entry.output_sku for entry in parts}
    options = [_part_option(entry) for entry in parts]
    options.extend(
        _material_option(candidate, {})
        for candidate in search_ingredients(term)
        if candidate.sku not in part_skus
    )
    return tuple(options)


# ── Captura ──────────────────────────────────────────────────────────────────


def build_capture_draft(captured: CapturedRecipe) -> RecipeCaptureDraftProjection:
    """O rascunho lido, com cada ingrediente casado com um insumo (ou com candidatos).

    O casamento sugere; abaixo de ``DEFAULT_MIN_SCORE`` o ``sku`` fica vazio e a
    tela pergunta. As partes (receitas com fórmula) entram como opções extras.
    A ``formula`` inicial já vem com a âncora sugerida pelo conteúdo e os itens
    de massa em grama; volume e contagem ficam como foram lidos.
    """
    part_entries = _part_entries()
    part_candidates = tuple(_part_candidate(entry) for entry in part_entries)
    part_refs = {entry.output_sku: entry.ref for entry in part_entries}

    items: list[CaptureItemProjection] = []
    formula_items: list[dict] = []
    for item in captured.items:
        candidates = candidates_for(item.name, extra_options=part_candidates)
        best = candidates[0] if candidates and candidates[0].score >= DEFAULT_MIN_SCORE else None
        sku = best.sku if best is not None else ""
        role = item.role if item.role and item.role != "other" else classify_ingredient(item.name, sku)
        items.append(CaptureItemProjection(
            name=item.name,
            original_text=item.original_text,
            quantity=_plain_number(item.quantity),
            unit=item.unit,
            role=role,
            sku=sku,
            match_confidence=f"{best.score}%" if best is not None else "",
            candidates=tuple(_material_option(candidate, part_refs) for candidate in candidates),
        ))
        if item.quantity is not None and item.quantity > 0:
            quantity, unit = item.quantity, item.unit
            if unit == "kg":
                quantity, unit = quantity * _THOUSAND, "g"
            line = {"sku": sku, "name": item.name, "role": role, "quantity": _plain_number(quantity), "unit": unit}
            if item.note:
                line["note"] = item.note
            formula_items.append(line)

    grams = [(line["role"], item_grams(line)) for line in formula_items]
    flour_g = sum((g for role, g in grams if role == "flour" and g is not None), Decimal(0))
    total_g = sum((g for _, g in grams if g is not None), Decimal(0))
    formula = {
        "anchor": {"kind": suggest_anchor_kind(flour_g, total_g, captured.kind)},
        "basis_g": None,
        "standardized": False,
        "items": formula_items,
        "parts": [],
    }
    return RecipeCaptureDraftProjection(
        name=captured.name,
        kind=captured.kind,
        language=captured.language,
        yield_quantity=_plain_number(captured.yield_quantity),
        yield_unit=captured.yield_unit,
        items=tuple(items),
        steps=tuple(captured.steps),
        notes=captured.notes,
        formula=formula,
    )


# ── Acesso ───────────────────────────────────────────────────────────────────


def resolve_recipe_book_access(user) -> RecipeBookAccessProjection:
    """Ler = o gate do app de Produção (ou ver a ficha); escrever = gerir a produção (ou mudar a ficha)."""
    is_superuser = bool(getattr(user, "is_superuser", False))
    can_edit = is_superuser or user.has_perm("shop.manage_production") or user.has_perm("craftsman.change_recipe")
    can_view = can_edit or user.has_perm("backstage.operate_production") or user.has_perm("craftsman.view_recipe")
    return RecipeBookAccessProjection(
        can_view=bool(can_view),
        can_edit=bool(can_edit),
        capture_available=is_configured(),
    )
