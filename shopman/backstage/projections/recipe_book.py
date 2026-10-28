"""Projections do inventário de receitas (RECIPE-INVENTORY-PLAN §7).

A camada de leitura que a superfície de Produção consome em ``/recipes``: o
inventário (cartões), a receita com as suas versões, a **lente** sobre uma
fórmula (porcentagem do padeiro, métricas com faixa de referência, preps,
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
from urllib.parse import urlsplit

from django.db.models import Count, Q
from django.utils import timezone
from shopman.craftsman.models import ProductionMode, Recipe, RecipeEntry, RecipeVersion
from shopman.craftsman.services.recipe_book import (
    BAKERY_KINDS,
    FormulaAnalysis,
    FormulaDiffMetric,
    FormulaDiffRow,
    FormulaItemAnalysis,
    FormulaWarning,
    analyze,
    check_references,
    classify_ingredient,
    diff_versions,
    execution_in_sync,
    ingredient_formulas_for,
    item_grams,
    reference_for,
    suggest_anchor_kind,
)

from shopman.backstage.services import recipe_book as recipe_book_service
from shopman.backstage.services import (
    recipe_external_references,
    recipe_favorites,
    recipe_ratings,
    recipe_review,
)
from shopman.backstage.services.exceptions import RecipeEntryNotFound, RecipeSheetNotFound, RecipeVersionNotFound
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

ANCHOR_LABELS: dict[str, str] = {
    "flour": "Farinhas totais",
    "total": "Massa total",
    "ingredient": "Um ingrediente",
}

METRIC_LABELS: dict[str, str] = {
    "hydration_pct": "Hidratação",
    "salt_pct": "Sal",
    "yeast_pct": "Fermento",
    "fat_pct": "Gordura",
    "sugar_pct": "Açúcar",
    "egg_pct": "Ovos",
}

#: Métricas que valem zero sem ser aviso: pão de levain não leva fermento, massa
#: magra não leva açúcar. Só hidratação e sal em zero merecem atenção.
_METRICS_MEANINGFUL_AT_ZERO = ("hydration_pct", "salt_pct")

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
    #: Modo de produção da ficha vigente (``batch`` | ``made_to_order``); vazio sem ficha.
    production_mode: str
    production_mode_label: str
    current_version_number: int | None
    version_count: int
    draft_count: int
    anchor_kind: str
    hydration_display: str
    updated_at_display: str
    is_active: bool
    #: Estrela do operador que pediu a lista (``OperatorRecipeFavorite``): é
    #: preferência dele, não atributo da receita; outro operador vê a sua.
    is_favorite: bool
    #: Média geral da nota da VERSÃO ATUAL ("4,3"), só dos critérios ativos.
    #: Vazio quando a versão atual ainda não foi avaliada.
    rating_display: str
    rating_count: int
    #: De onde veio a versão atual (``recipe_review.provenance_of``): house,
    #: notebook ou agent. Vazio sem versão publicada.
    provenance_kind: str
    provenance_label: str
    #: Conferência da versão atual: pending, confirmed ou changed. Vazio sem versão.
    review_status: str
    review_label: str


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
    page: int
    page_size: int
    total: int
    has_next: bool
    sort: str


@dataclass(frozen=True)
class RecipeBookAccessProjection:
    """What the current operator may do on the recipe book."""

    can_view: bool
    can_edit: bool
    capture_available: bool


@dataclass(frozen=True)
class FormulaItemProjection:
    """One ingredient line of a formula, with its share of the anchor."""

    ref: str
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
    recipe_version_ref: str
    composition: str
    composition_label: str
    quantity_rule_display: str


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
    """The lens over a formula: anchor, unified ingredients, metrics, final mix and BOM."""

    is_bakery: bool
    anchor_kind: str
    anchor_label: str
    basis_display: str
    standardized: bool
    anchor_total_display: str
    total_mass_display: str
    ingredients: tuple[FormulaItemProjection, ...]
    final_mix: tuple[FormulaItemProjection, ...]
    #: A mistura final diz algo que a receita base já não disse? Sem composições inclusas ela é a
    #: própria base, e mostrar a mesma tabela duas vezes só ensina o padeiro a
    #: parar de ler. A tela pergunta isto antes de desenhar o painel.
    final_mix_differs: bool
    bom: tuple[FormulaItemProjection, ...]
    #: Idem para a ficha técnica: ela difere quando uma receita usada como
    #: ingrediente substitui parte da composição direta.
    bom_differs: bool
    metrics: tuple[FormulaMetricProjection, ...]
    warnings: tuple[FormulaWarningProjection, ...]


@dataclass(frozen=True)
class RecipeStepProjection:
    """One production step of a version (``shopman.craftsman.recipe_steps``)."""

    name: str
    #: O modo de fazer da etapa. Vazio quando não foi escrito.
    instructions: str
    target_seconds: int | None
    #: ``target_seconds`` para ler: "45 min", "1 h 30 min". Vazio sem tempo alvo.
    target_display: str
    #: Temperatura da etapa em °C (inteira ou com uma casa decimal). ``None`` sem temperatura.
    temperature_celsius: float | None
    #: ``temperature_celsius`` para ler: "230 °C", "24,5 °C". Vazio sem temperatura.
    temperature_display: str
    #: Anotação prática da etapa. Vazio quando não há.
    note: str


@dataclass(frozen=True)
class RecipeVersionProjection:
    """A frozen formula version of a recipe entry."""

    id: int
    revision: str
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
    steps: tuple[RecipeStepProjection, ...]
    lens: FormulaLensProjection
    formula: dict
    origin: dict
    provenance_kind: str
    provenance_label: str
    provenance_detail: str
    review_status: str
    review_label: str
    review_by_name: str
    review_at_display: str


@dataclass(frozen=True)
class RecipeReviewItemProjection:
    """One recipe waiting for the baker's check, in the order of what sells most."""

    ref: str
    name: str
    kind_label: str
    output_sku: str
    output_name: str
    version_number: int
    provenance_kind: str
    provenance_label: str
    provenance_detail: str
    review_status: str
    review_label: str
    #: A massa da peça, em destaque (foi ali que as seis fichas erraram). Vazio na massa.
    dough_sku: str
    dough_name: str
    #: "1.240 vendidos em 12 meses" ou, para a massa, "... por 3 produtos". Vazio sem venda.
    sold_display: str


@dataclass(frozen=True)
class RecipeReviewQueueProjection:
    """The baker's check queue: current versions nobody from the house confirmed yet."""

    items: tuple[RecipeReviewItemProjection, ...]
    total: int
    confirmed_total: int
    recipe_total: int


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
    #: Aproveitamento = realizado ÷ previsto das executadas (UX-PROD-AF).
    yield_pct: str
    yield_display: str
    #: Fornadas sem abertura declarada: o previsto delas foi assumido igual ao planejado.
    started_assumed_batches: int
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
class ExternalReferenceProjection:
    """A book, video or article the recipe came from (``RecipeEntry.meta["external_references"]``)."""

    title: str
    #: Só ``http``/``https``; vazio quando a referência não tem link.
    url: str
    #: O host do link para ler ("youtube.com"). Vazio sem link.
    host_display: str
    note: str


@dataclass(frozen=True)
class RatingCriterionProjection:
    """An active rating criterion (editable in the Admin, ``RecipeRatingCriterion``)."""

    id: int
    name: str
    description: str


@dataclass(frozen=True)
class CriterionAverageProjection:
    """The average of one criterion for one version, and the score of who asked."""

    criterion_id: int
    name: str
    #: "4,3"; vazio quando ninguém deu nota neste critério.
    average_display: str
    count: int
    my_score: int | None


@dataclass(frozen=True)
class VersionRatingProjection:
    """The 0 to 5 rating of one version: averages per criterion and overall."""

    version_number: int
    version_ref: str
    ratings_count: int
    #: "Nenhuma avaliação", "1 avaliação", "3 avaliações".
    ratings_count_display: str
    #: Média de todas as notas dos critérios ativos ("4,3"); vazio sem avaliação.
    overall_display: str
    criteria: tuple[CriterionAverageProjection, ...]
    rated_by_me: bool
    my_rated_at_display: str


@dataclass(frozen=True)
class LifecycleOptionProjection:
    """Uma variante de coordenação disponível para a ficha de execução."""

    value: str
    label: str


@dataclass(frozen=True)
class ProductionModeOptionProjection:
    """Uma escolha do modo de produção ("Em lote", "Na hora")."""

    value: str
    label: str


@dataclass(frozen=True)
class ExecutionSheetProjection:
    """Configuração operacional da ficha que a versão publicada materializa."""

    exists: bool
    ref: str
    revision: str
    max_started_minutes: int | None
    capacity_per_day: str
    requires_batch_tracking: bool
    shelf_life_days: int | None
    shelf_life_reviewed: bool
    shelf_life_reviewed_by: str
    production_lifecycle: str
    lifecycle_options: tuple[LifecycleOptionProjection, ...]
    #: ``Recipe.production_mode``: "Em lote" (planejado e estocado) ou "Na hora".
    production_mode: str
    production_mode_options: tuple[ProductionModeOptionProjection, ...]


@dataclass(frozen=True)
class RecipeSheetItemProjection:
    """Uma linha da ficha de execução: o insumo e o que ele consome do estoque."""

    input_sku: str
    name: str
    quantity: str
    unit: str
    usable_factor: str
    gross_quantity: str
    correction_factor: str
    sort_order: int
    is_optional: bool
    note: str


@dataclass(frozen=True)
class RecipeSheetMassBalanceProjection:
    """A conta de massa da ficha: o rendimento contra a soma dos insumos."""

    status: str
    output_unit: str
    batch_display: str
    total_display: str
    message: str
    tone: str


@dataclass(frozen=True)
class RecipeSheetCardProjection:
    """Um cartão de ficha de execução na lista."""

    ref: str
    name: str
    output_sku: str
    output_name: str
    batch_size: str
    item_count: int
    is_active: bool
    production_mode: str
    production_mode_label: str
    has_entry: bool
    updated_at_display: str


@dataclass(frozen=True)
class RecipeSheetListProjection:
    """A lista de fichas de execução."""

    cards: tuple[RecipeSheetCardProjection, ...]
    count: int
    page: int
    page_size: int
    total: int
    has_next: bool
    sort: str


@dataclass(frozen=True)
class RecipeSheetDetailProjection:
    """A ficha de execução inteira: identidade, itens, massa e operação."""

    ref: str
    revision: str
    name: str
    output_sku: str
    output_name: str
    batch_size: str
    output_unit: str
    is_active: bool
    steps: tuple[RecipeStepProjection, ...]
    items: tuple[RecipeSheetItemProjection, ...]
    mass_balance: RecipeSheetMassBalanceProjection
    execution: ExecutionSheetProjection
    has_entry: bool
    entry_ref: str


@dataclass(frozen=True)
class RecipeEntryDetailProjection:
    """A recipe entry with its versions (newest first)."""

    ref: str
    revision: str
    name: str
    kind: str
    kind_label: str
    output_sku: str
    output_name: str
    notes: str
    is_active: bool
    ingredient_defaults: dict[str, Any] | None
    current_version_number: int | None
    ficha_ref: str
    #: A ficha de execução ainda é a que a versão atual escreveu (ADR-027)?
    #: ``False`` também quando não há ficha ou versão atual. A conta é do
    #: Craftsman (``execution_in_sync``): carimbo ``version_ref`` + impressão
    #: digital do conteúdo, que pega a ficha editada pelo Admin.
    execution_in_sync: bool
    execution: ExecutionSheetProjection
    #: Estrela do operador que abriu a receita (ver ``RecipeEntryCardProjection``).
    is_favorite: bool
    versions: tuple[RecipeVersionProjection, ...]
    usage: RecipeUsageProjection
    #: Livros, vídeos e artigos de onde a receita veio. São da receita, não da versão.
    external_references: tuple[ExternalReferenceProjection, ...]
    #: Os critérios ATIVOS, na ordem do Admin: o que a tela de avaliar pergunta.
    rating_criteria: tuple[RatingCriterionProjection, ...]
    #: Uma por versão (rascunho incluído, D24), mais nova primeiro.
    ratings: tuple[VersionRatingProjection, ...]


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
    has_recipe: bool
    recipe_version_ref: str
    default_quantity: dict[str, Any] | None
    default_composition: str


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
    return ROLE_LABELS.get(role, ROLE_LABELS["other"])


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


def _wire_ingredient_defaults(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("quantity"), dict):
        return None
    quantity = dict(value["quantity"])
    for key in ("minimum", "target", "maximum"):
        number = _decimal(quantity.get(key))
        quantity[key] = None if number is None else (int(number) if number == number.to_integral_value() else float(number))
    return {"quantity": quantity, "composition": str(value.get("composition") or "additional")}


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
    analysis = analyze(formula, ingredient_formulas_for(formula))
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
        ingredients=tuple(_lens_item(item, anchor_kind, anchor_sku) for item in analysis.ingredients),
        final_mix=tuple(_lens_item(item, anchor_kind, anchor_sku) for item in analysis.final_mix),
        final_mix_differs=_has_included_composition(analysis),
        bom=tuple(_bom_item(line, analysis.anchor_total_g) for line in analysis.bom),
        bom_differs=_has_recipe_ingredient(analysis),
        metrics=tuple(
            _metric(code, value, kind, flagged) for code, value in analysis.metrics().items()
        ),
        warnings=tuple(_warning(warning) for warning in (*analysis.warnings, *references)),
    )


def _has_included_composition(analysis: FormulaAnalysis) -> bool:
    """Uma receita inclusa substitui parte da composição direta."""
    return any(item.recipe_version_ref and item.composition == "included" for item in analysis.ingredients)


def _has_recipe_ingredient(analysis: FormulaAnalysis) -> bool:
    """A BOM imediata difere quando a fórmula usa outro ingrediente produzido."""
    return any(item.recipe_version_ref for item in analysis.ingredients)


def _anchor_label(anchor_kind: str, anchor_sku: str, analysis: FormulaAnalysis) -> str:
    label = ANCHOR_LABELS.get(anchor_kind, anchor_kind)
    if anchor_kind != "ingredient":
        return label
    name = next((item.name for item in analysis.ingredients if item.sku == anchor_sku), anchor_sku)
    return f"{label} ({name})" if name else label


def _lens_item(item: FormulaItemAnalysis, anchor_kind: str, anchor_sku: str) -> FormulaItemProjection:
    if anchor_kind == "flour":
        is_anchor = item.role == "flour"
    elif anchor_kind == "ingredient":
        is_anchor = bool(item.sku) and item.sku == anchor_sku
    else:
        is_anchor = False
    return FormulaItemProjection(
        ref=item.ingredient_ref,
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
        recipe_version_ref=item.recipe_version_ref,
        composition=item.composition,
        composition_label=_composition_label(item.composition),
        quantity_rule_display=_quantity_rule_display(
            item.minimum,
            item.target,
            item.maximum,
            item.unit,
            kind=item.quantity_kind,
            basis_kind=item.basis_kind,
            basis_sku=item.basis_sku,
        ),
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
        ref=str(line.get("ref") or ""),
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
        recipe_version_ref=str((line.get("meta") or {}).get("recipe_version_ref") or ""),
        composition=str((line.get("meta") or {}).get("composition") or "additional"),
        composition_label=_composition_label(str((line.get("meta") or {}).get("composition") or "additional")),
        quantity_rule_display="",
    )


def _composition_label(composition: str) -> str:
    return "Inclusa" if composition == "included" else "Adicional"


def _quantity_rule_display(
    minimum: Decimal | None,
    target: Decimal | None,
    maximum: Decimal | None,
    unit: str,
    *,
    kind: str = "fixed",
    basis_kind: str = "",
    basis_sku: str = "",
) -> str:
    if target is None:
        return ""
    if kind == "ratio":
        basis = {
            "flour": " das farinhas",
            "total": " da fórmula",
            "ingredient": f" de {basis_sku}" if basis_sku else " do ingrediente-base",
        }.get(basis_kind, "")
        suffix = f"%{basis}"
    else:
        suffix = f" {unit}" if unit else ""
    target_display = f"{_number(target)}{suffix}"
    if minimum == target == maximum:
        return "Exata" if kind == "fixed" else f"Exata: {target_display}"
    if minimum is not None and maximum is not None:
        return f"Faixa: {_number(minimum)} a {_number(maximum)}{suffix}; alvo {target_display}"
    if minimum is not None:
        return f"Mínima: a partir de {_number(minimum)}{suffix}"
    if maximum is not None:
        return f"Máxima: até {_number(maximum)}{suffix}"
    return f"Alvo {target_display}"


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


def build_recipe_book(
    *,
    query: str = "",
    kind: str = "",
    archived: bool = False,
    operator_ref: str = "",
    only_without_sku: bool = False,
    only_with_draft: bool = False,
    only_favorites: bool = False,
    only_unreviewed: bool = False,
    production_mode: str = "",
    sort: str = "updated",
    page: int = 1,
    page_size: int = 48,
) -> RecipeBookListProjection:
    """O inventário: um cartão por receita, com filtro por texto, tipo e arquivadas.

    ``operator_ref`` acende a estrela das receitas que ESTE operador marcou; sem
    ele (comando, seed, teste) nenhuma vem marcada. O filtro "Favoritas" é da
    tela, sobre ``is_favorite``, como "Sem SKU" e "Com rascunho".
    """
    entries_qs = (
        RecipeEntry.objects.filter(is_active=not bool(archived))
        .select_related("current_version")
        .annotate(
            version_total=Count("versions", distinct=True),
            draft_total=Count("versions", filter=Q(versions__status=RecipeVersion.Status.DRAFT), distinct=True),
        )
    )
    if kind:
        entries_qs = entries_qs.filter(kind=kind)
    term = (query or "").strip()
    if term:
        entries_qs = entries_qs.filter(
            Q(name__icontains=term) | Q(ref__icontains=term) | Q(output_sku__icontains=term)
        )
    if production_mode:
        entries_qs = entries_qs.filter(
            ref__in=Recipe.objects.filter(is_active=True, production_mode=production_mode).values("ref")
        )
    if only_without_sku:
        entries_qs = entries_qs.filter(output_sku="")
    if only_with_draft:
        entries_qs = entries_qs.filter(draft_total__gt=0)
    favorites = recipe_favorites.favorite_refs(operator_ref)
    if only_favorites:
        entries_qs = entries_qs.filter(ref__in=favorites)
    if only_unreviewed:
        # A conferência mora no JSON da versão e o "mudou depois" é conta de
        # digital: o recorte sai em Python, sobre o inventário (cem e poucas).
        pending = [
            entry.ref
            for entry in RecipeEntry.objects.filter(current_version__isnull=False).select_related("current_version")
            if recipe_review.review_of(entry.current_version).status != recipe_review.REVIEW_CONFIRMED
        ]
        entries_qs = entries_qs.filter(ref__in=pending)

    ordering = {
        "updated": ("-updated_at", "name", "ref"),
        "name": ("name", "ref"),
        "kind": ("kind", "name", "ref"),
    }.get(sort, ("-updated_at", "name", "ref"))
    entries_qs = entries_qs.order_by(*ordering)
    total = entries_qs.count()
    size = max(1, min(int(page_size or 48), 100))
    current = max(1, int(page or 1))
    start = (current - 1) * size
    entries = list(entries_qs[start : start + size])
    names = _output_names({entry.output_sku for entry in entries if entry.output_sku})
    ficha_modes = dict(
        Recipe.objects.filter(ref__in=[entry.ref for entry in entries], is_active=True).values_list(
            "ref", "production_mode"
        )
    )
    ratings = recipe_ratings.overall_by_entry(
        [entry.ref for entry in entries],
        {entry.ref: entry.current_version.number for entry in entries if entry.current_version is not None},
    )
    cards = tuple(_card(entry, names, ficha_modes, favorites, ratings) for entry in entries)
    return RecipeBookListProjection(
        entries=cards,
        kinds=_kind_options(),
        count=len(cards),
        page=current,
        page_size=size,
        total=total,
        has_next=start + len(cards) < total,
        sort=sort,
    )


def _card(
    entry: RecipeEntry,
    names: dict[str, str],
    ficha_modes: dict[str, str],
    favorites: set[str],
    ratings: dict[str, tuple[Decimal | None, int]],
) -> RecipeEntryCardProjection:
    current = entry.current_version
    formula = dict(current.formula or {}) if current is not None else {}
    anchor = formula.get("anchor") if isinstance(formula.get("anchor"), dict) else {}
    anchor_kind = str(anchor.get("kind") or "") if current is not None else ""
    hydration = ""
    if anchor_kind == "flour":
        hydration = _pct_display(analyze(formula, ingredient_formulas_for(formula)).hydration_pct)
    return RecipeEntryCardProjection(
        ref=entry.ref,
        name=entry.name,
        kind=entry.kind,
        kind_label=_kind_label(entry.kind),
        output_sku=entry.output_sku,
        output_name=names.get(entry.output_sku, "") if entry.output_sku else "",
        has_ficha=entry.ref in ficha_modes,
        production_mode=ficha_modes.get(entry.ref, ""),
        production_mode_label=_production_mode_label(ficha_modes.get(entry.ref, "")),
        current_version_number=current.number if current is not None else None,
        version_count=int(getattr(entry, "version_total", 0) or 0),
        draft_count=int(getattr(entry, "draft_total", 0) or 0),
        anchor_kind=anchor_kind,
        hydration_display=hydration,
        updated_at_display=_date_display(entry.updated_at),
        is_active=entry.is_active,
        is_favorite=entry.ref in favorites,
        rating_display=_rating_display(ratings.get(entry.ref, (None, 0))[0]),
        rating_count=ratings.get(entry.ref, (None, 0))[1],
        **_card_review_fields(current),
    )


def _card_review_fields(current: RecipeVersion | None) -> dict:
    if current is None:
        return {"provenance_kind": "", "provenance_label": "", "review_status": "", "review_label": ""}
    provenance = recipe_review.provenance_of(current)
    review = recipe_review.review_of(current)
    return {
        "provenance_kind": provenance.kind,
        "provenance_label": provenance.label,
        "review_status": review.status,
        "review_label": review.label,
    }


def build_recipe_entry(ref: str, *, operator_ref: str = "") -> RecipeEntryDetailProjection:
    """A receita com todas as versões (mais nova primeiro), cada uma com a lente calculada.

    ``operator_ref`` diz de quem é a estrela (``is_favorite``); sem ele, apagada.
    """
    entry = RecipeEntry.objects.filter(ref=ref).select_related("current_version").first()
    if entry is None:
        raise RecipeEntryNotFound(f"Receita '{ref}' não existe no inventário.")
    criteria = recipe_ratings.active_criteria()
    versions = list(entry.versions.order_by("-number"))
    names = _output_names({entry.output_sku} if entry.output_sku else set())
    ficha = Recipe.objects.filter(ref=entry.ref, is_active=True).first()
    current = entry.current_version
    return RecipeEntryDetailProjection(
        ref=entry.ref,
        revision=entry.updated_at.isoformat(),
        name=entry.name,
        kind=entry.kind,
        kind_label=_kind_label(entry.kind),
        output_sku=entry.output_sku,
        output_name=names.get(entry.output_sku, "") if entry.output_sku else "",
        notes=entry.notes or "",
        is_active=entry.is_active,
        ingredient_defaults=_wire_ingredient_defaults((entry.meta or {}).get("ingredient_defaults")),
        current_version_number=current.number if current is not None else None,
        ficha_ref=entry.ref if ficha is not None else "",
        execution_in_sync=execution_in_sync(current, ficha),
        execution=_execution_sheet(ficha),
        is_favorite=recipe_favorites.is_favorite(operator_ref, entry.ref),
        versions=tuple(build_recipe_version(version, kind=entry.kind) for version in versions),
        usage=build_recipe_usage(entry.ref),
        external_references=build_external_references(entry.meta),
        rating_criteria=tuple(
            RatingCriterionProjection(id=criterion.pk, name=criterion.name, description=criterion.description)
            for criterion in criteria
        ),
        ratings=build_version_ratings(entry.ref, versions, operator_ref=operator_ref, criteria=criteria),
    )


def _execution_sheet(recipe: Recipe | None) -> ExecutionSheetProjection:
    """Lê metadados operacionais sem deixar legado malformado derrubar a ficha."""
    from shopman.shop.production_lifecycle import production_lifecycle_choices

    choices = tuple(
        LifecycleOptionProjection(value=str(value), label=str(label))
        for value, label in production_lifecycle_choices()
    )
    if recipe is None:
        return ExecutionSheetProjection(
            exists=False,
            ref="",
            revision="",
            max_started_minutes=None,
            capacity_per_day="",
            requires_batch_tracking=False,
            shelf_life_days=None,
            shelf_life_reviewed=False,
            shelf_life_reviewed_by="",
            production_lifecycle=choices[0].value if choices else "",
            lifecycle_options=choices,
            production_mode=ProductionMode.BATCH,
            production_mode_options=_production_mode_options(),
        )

    meta = recipe.meta or {}
    max_started = _safe_int(meta.get("max_started_minutes"), minimum=1)
    shelf_life = _safe_int(meta.get("shelf_life_days"), minimum=0)
    capacity = _safe_decimal_text(meta.get("capacity_per_day"), positive=True)
    reviewed = bool(
        shelf_life is not None
        and meta.get("shelf_life_reviewed_days") == shelf_life
        and meta.get("shelf_life_reviewed_by")
        and meta.get("shelf_life_reviewed_at")
    )
    lifecycle = str(meta.get("production_lifecycle") or (choices[0].value if choices else ""))
    return ExecutionSheetProjection(
        exists=True,
        ref=recipe.ref,
        revision=recipe.updated_at.isoformat(),
        max_started_minutes=max_started,
        capacity_per_day=capacity,
        requires_batch_tracking=bool(meta.get("requires_batch_tracking")),
        shelf_life_days=shelf_life,
        shelf_life_reviewed=reviewed,
        shelf_life_reviewed_by=str(meta.get("shelf_life_reviewed_by") or "") if reviewed else "",
        production_lifecycle=lifecycle,
        lifecycle_options=choices,
        production_mode=str(recipe.production_mode),
        production_mode_options=_production_mode_options(),
    )


def _production_mode_options() -> tuple[ProductionModeOptionProjection, ...]:
    return tuple(
        ProductionModeOptionProjection(value=str(value), label=str(label))
        for value, label in ProductionMode.choices
    )


def _production_mode_label(mode: str) -> str:
    return str(dict(ProductionMode.choices).get(mode, "")) if mode else ""


def _safe_int(value: Any, *, minimum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed < minimum:
        return None
    return int(parsed)


def _safe_decimal_text(value: Any, *, positive: bool) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ""
    if not parsed.is_finite() or (positive and parsed <= 0):
        return ""
    return format(parsed.normalize(), "f")


# ── Referências externas (D6) ────────────────────────────────────────────────


def _host_display(url: str) -> str:
    if not url:
        return ""
    return (urlsplit(url).hostname or "").removeprefix("www.")


def build_external_references(meta: Any) -> tuple[ExternalReferenceProjection, ...]:
    """As referências gravadas, já sem link inseguro (``recipe_external_references.read``)."""
    return tuple(
        ExternalReferenceProjection(
            title=reference["title"],
            url=reference["url"],
            host_display=_host_display(reference["url"]),
            note=reference["note"],
        )
        for reference in recipe_external_references.read(meta)
    )


# ── Nota da receita (D7) ─────────────────────────────────────────────────────


def _rating_display(value: Decimal | None) -> str:
    """``Decimal("4.3")`` → ``"4,3"``; inteiro sem casa ("4"). Vazio sem nota."""
    if value is None:
        return ""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value, "f").replace(".", ",")


def _ratings_count_display(count: int) -> str:
    if count == 0:
        return "Nenhuma avaliação"
    return "1 avaliação" if count == 1 else f"{count} avaliações"


def build_version_ratings(
    ref: str, versions: list[RecipeVersion], *, operator_ref: str = "", criteria=None
) -> tuple[VersionRatingProjection, ...]:
    """A nota de cada versão (mais nova primeiro); a de quem pede vem em ``my_score``."""
    criteria = recipe_ratings.active_criteria() if criteria is None else criteria
    summaries = recipe_ratings.summaries(ref, operator_ref=operator_ref, criteria=criteria)
    projections = []
    for version in sorted(versions, key=lambda item: item.number, reverse=True):
        summary = summaries.get(version.number)
        averages = {item.criterion_id: item for item in summary.criteria} if summary else {}
        projections.append(VersionRatingProjection(
            version_number=version.number,
            version_ref=f"{ref}@{version.number}",
            ratings_count=summary.ratings_count if summary else 0,
            ratings_count_display=_ratings_count_display(summary.ratings_count if summary else 0),
            overall_display=_rating_display(summary.overall) if summary else "",
            criteria=tuple(
                CriterionAverageProjection(
                    criterion_id=criterion.pk,
                    name=criterion.name,
                    average_display=_rating_display(averages[criterion.pk].average) if criterion.pk in averages else "",
                    count=averages[criterion.pk].count if criterion.pk in averages else 0,
                    my_score=averages[criterion.pk].my_score if criterion.pk in averages else None,
                )
                for criterion in criteria
            ),
            rated_by_me=bool(summary and summary.my_rated_at),
            my_rated_at_display=_datetime_display(summary.my_rated_at) if summary else "",
        ))
    return tuple(projections)


def _seconds_display(seconds: int | None) -> str:
    """``5400`` → ``"1 h 30 min"``; ``45`` → ``"45 s"``. Vazio sem tempo."""
    if not seconds:
        return ""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    preps = [f"{hours} h" if hours else "", f"{minutes} min" if minutes else "", f"{secs} s" if secs else ""]
    return " ".join(prep for prep in preps if prep)


def _celsius_display(celsius: float | None) -> str:
    """``230`` → ``"230 °C"``; ``24.5`` → ``"24,5 °C"``. Vazio sem temperatura."""
    if celsius is None:
        return ""
    number = int(celsius) if float(celsius).is_integer() else celsius
    return f"{str(number).replace('.', ',')} °C"


def _step_projection(step: dict) -> RecipeStepProjection:
    """Uma etapa gravada (sempre objeto: o ``clean`` da versão normaliza)."""
    seconds = step.get("target_seconds")
    celsius = step.get("temperature_celsius")
    return RecipeStepProjection(
        name=step["name"],
        instructions=step.get("instructions", ""),
        target_seconds=seconds,
        target_display=_seconds_display(seconds),
        temperature_celsius=celsius,
        temperature_display=_celsius_display(celsius),
        note=step.get("note", ""),
    )


def build_recipe_version(version: RecipeVersion, *, kind: str) -> RecipeVersionProjection:
    """Uma versão congelada, com a lente sobre a sua fórmula."""
    from shopman.backstage.services.recipe_book import version_revision

    source = version.source if isinstance(version.source, dict) else {}
    source_kind = str(source.get("kind") or "")
    return RecipeVersionProjection(
        id=version.pk,
        revision=version_revision(version),
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
        steps=tuple(_step_projection(step) for step in (version.steps or [])),
        lens=build_formula_lens(version.formula or {}, kind),
        formula=wire_formula(version.formula),
        origin=dict(version.origin or {}),
        **_version_review_fields(version),
    )


def _version_review_fields(version: RecipeVersion) -> dict:
    provenance = recipe_review.provenance_of(version)
    if version.status == RecipeVersion.Status.DRAFT:
        review_status, review_label, by_name, at_display = "", "", "", ""
    else:
        review = recipe_review.review_of(version)
        review_status, review_label, by_name = review.status, review.label, review.by_name
        at_display = _iso_display(review.at)
    return {
        "provenance_kind": provenance.kind,
        "provenance_label": provenance.label,
        "provenance_detail": provenance.detail,
        "review_status": review_status,
        "review_label": review_label,
        "review_by_name": by_name,
        "review_at_display": at_display,
    }


def _iso_display(value: str) -> str:
    if not value:
        return ""
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(value)
    return _datetime_display(parsed) if parsed is not None else ""


def _sold_display(qty: Decimal, via: int) -> str:
    if qty <= 0:
        return ""
    whole = int(qty.to_integral_value(rounding=ROUND_HALF_UP))
    text = f"{whole:,}".replace(",", ".")
    noun = "vendido" if whole == 1 else "vendidos"
    suffix = ""
    if via == 1:
        suffix = " por 1 produto"
    elif via > 1:
        suffix = f" por {via} produtos"
    return f"{text} {noun} em 12 meses{suffix}"


def build_recipe_review_queue(*, sold: dict | None = None) -> RecipeReviewQueueProjection:
    """A fila do padeiro (WP-RECEITAS-DA-CASA F2): o que falta conferir, do que mais sai."""
    queue = recipe_review.review_queue(sold=sold)
    names = _output_names({item.entry.output_sku for item in queue if item.entry.output_sku})
    recipe_total = RecipeEntry.objects.filter(is_active=True, current_version__isnull=False).count()
    items = tuple(
        RecipeReviewItemProjection(
            ref=item.entry.ref,
            name=item.entry.name,
            kind_label=_kind_label(item.entry.kind),
            output_sku=item.entry.output_sku,
            output_name=names.get(item.entry.output_sku, "") if item.entry.output_sku else "",
            version_number=item.version.number,
            provenance_kind=item.provenance.kind,
            provenance_label=item.provenance.label,
            provenance_detail=item.provenance.detail,
            review_status=item.review.status,
            review_label=item.review.label,
            dough_sku=item.dough_sku,
            dough_name=item.dough_name,
            sold_display=_sold_display(item.sold_qty, item.sold_via),
        )
        for item in queue
    )
    return RecipeReviewQueueProjection(
        items=items,
        total=len(items),
        confirmed_total=recipe_total - len(items),
        recipe_total=recipe_total,
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
    ``version_ref`` congelado no plano. Aproveitamento = realizado ÷ previsto das
    executadas (``WorkOrder.yield_rate``); perda = soma do resíduo
    ``previsto − realizado``. Fornada fechada sem abertura declarada tem o
    previsto assumido igual ao planejado, e o resumo diz quantas foram.

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


_USAGE_SUM_KEYS = ("executed", "executed_planned", "executed_started", "started_assumed", "finished", "loss")


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
    yield_pct = (finished / started * 100) if started else None
    assumed = int(row["started_assumed"])
    avg_loss = (loss / batches) if batches else None
    loss_pct = (loss / started * 100) if started else None
    batches_display = f"{batches} fornada" if batches == 1 else f"{batches} fornadas"
    avg_loss_display = f"{_number(avg_loss)} por fornada" if avg_loss is not None else ""
    summary = batches_display
    if yield_pct is not None:
        summary += f"; aproveitamento médio {_pct_display(yield_pct)}"
        if assumed:
            summary += f" (previsto assumido em {assumed} de {batches})"
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
        started_assumed_batches=assumed,
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


# ── Ingredientes, inclusive os produzidos por outra receita ─────────────────


def _recipe_ingredient_entries() -> list[RecipeEntry]:
    """Receitas com versão atual e SKU que podem ser escolhidas como ingrediente."""
    return list(
        RecipeEntry.objects.filter(current_version__isnull=False, is_active=True)
        .exclude(output_sku="")
        .select_related("current_version")
        .order_by("name", "ref")
    )


def _recipe_ingredient_candidate(entry: RecipeEntry) -> IngredientCandidate:
    return IngredientCandidate(
        sku=entry.output_sku,
        name=entry.name,
        unit=entry.current_version.yield_unit if entry.current_version is not None else "kg",
        role=classify_ingredient(entry.name, entry.output_sku),
        score=0,
    )


def _recipe_ingredient_option(entry: RecipeEntry) -> IngredientOptionProjection:
    candidate = _recipe_ingredient_candidate(entry)
    current = entry.current_version
    defaults = (entry.meta or {}).get("ingredient_defaults") or {}
    return IngredientOptionProjection(
        sku=candidate.sku,
        name=candidate.name,
        unit=candidate.unit,
        role=candidate.role,
        has_recipe=current is not None,
        recipe_version_ref=current.version_ref if current is not None else "",
        default_quantity=(
            (_wire_ingredient_defaults(defaults) or {}).get("quantity")
            if isinstance(defaults.get("quantity"), dict)
            else None
        ),
        default_composition=(
            str(defaults.get("composition"))
            if defaults.get("composition") in {"additional", "included"}
            else "additional"
        ),
    )


def _material_option(candidate: IngredientCandidate, recipe_entries: dict[str, RecipeEntry]) -> IngredientOptionProjection:
    entry = recipe_entries.get(candidate.sku)
    current = entry.current_version if entry is not None else None
    defaults = ((entry.meta or {}).get("ingredient_defaults") or {}) if entry is not None else {}
    return IngredientOptionProjection(
        sku=candidate.sku,
        name=candidate.name,
        unit=candidate.unit,
        role=candidate.role,
        has_recipe=current is not None,
        recipe_version_ref=current.version_ref if current is not None else "",
        default_quantity=(
            (_wire_ingredient_defaults(defaults) or {}).get("quantity")
            if isinstance(defaults.get("quantity"), dict)
            else None
        ),
        default_composition=(
            str(defaults.get("composition"))
            if defaults.get("composition") in {"additional", "included"}
            else "additional"
        ),
    )


def _old_dough_ingredient_options(term: str) -> list[IngredientOptionProjection]:
    """Recovered dough with physical stock appears in the ordinary picker.

    It is neither a purchasable Material nor a special formula kind.  The
    stock lot owns the source recipe/version and composition snapshot.
    """
    from shopman.stockman.models import Batch

    batches = Batch.objects.filter(metadata__resource_kind="old_dough").order_by(
        "sku", "-production_date", "-pk"
    )
    options: list[IngredientOptionProjection] = []
    seen: set[str] = set()
    for batch in batches:
        if batch.sku in seen:
            continue
        metadata = batch.metadata or {}
        name = str(metadata.get("ingredient_name") or batch.sku)
        version_ref = str(metadata.get("recipe_version_ref") or "")
        entry_ref = version_ref.rsplit("@", 1)[0] if "@" in version_ref else ""
        if term and term not in name.lower() and term not in batch.sku.lower() and term not in entry_ref.lower():
            continue
        seen.add(batch.sku)
        options.append(
            IngredientOptionProjection(
                sku=batch.sku,
                name=name,
                unit="g",
                role="other",
                has_recipe=bool(version_ref),
                recipe_version_ref=version_ref,
                default_quantity={
                    "kind": "ratio",
                    "minimum": None,
                    "target": 20,
                    "maximum": 20,
                    "basis": {"kind": "total"},
                },
                default_composition="included",
            )
        )
    return options


def build_ingredient_options(query: str = "") -> tuple[IngredientOptionProjection, ...]:
    """Opções unificadas: insumos comprados e ingredientes produzidos por receita."""
    term = (query or "").strip().lower()
    recipe_entries = [
        entry
        for entry in _recipe_ingredient_entries()
        if not term or term in entry.name.lower() or term in entry.output_sku.lower() or term in entry.ref.lower()
    ]
    recipe_skus = {entry.output_sku for entry in recipe_entries}
    options = [_recipe_ingredient_option(entry) for entry in recipe_entries]
    options.extend(
        _material_option(candidate, {})
        for candidate in search_ingredients(term)
        if candidate.sku not in recipe_skus
    )
    existing_skus = {option.sku for option in options}
    options.extend(option for option in _old_dough_ingredient_options(term) if option.sku not in existing_skus)
    return tuple(options)


# ── Captura ──────────────────────────────────────────────────────────────────


def build_capture_draft(captured: CapturedRecipe) -> RecipeCaptureDraftProjection:
    """O rascunho lido, com cada ingrediente casado com um insumo (ou com candidatos).

    O casamento sugere; abaixo de ``DEFAULT_MIN_SCORE`` o ``sku`` fica vazio e a
    tela pergunta. Ingredientes com receita própria entram como opções extras;
    A ``formula`` inicial já vem com a âncora sugerida pelo conteúdo e os ingredientes
    de massa em grama; volume e contagem ficam como foram lidos.
    """
    recipe_entries = _recipe_ingredient_entries()
    recipe_candidates = tuple(_recipe_ingredient_candidate(entry) for entry in recipe_entries)
    recipe_entries_by_sku = {entry.output_sku: entry for entry in recipe_entries}

    items: list[CaptureItemProjection] = []
    formula_items: list[dict] = []
    for item in captured.items:
        candidates = candidates_for(item.name, extra_options=recipe_candidates)
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
            candidates=tuple(_material_option(candidate, recipe_entries_by_sku) for candidate in candidates),
        ))
        if item.quantity is not None and item.quantity > 0:
            quantity, unit = item.quantity, item.unit
            if unit == "kg":
                quantity, unit = quantity * _THOUSAND, "g"
            line = {
                "ref": f"ingredient-{len(formula_items) + 1}",
                "sku": sku,
                "name": item.name,
                "role": role,
                "quantity": {
                    "kind": "fixed",
                    "minimum": _plain_number(quantity),
                    "target": _plain_number(quantity),
                    "maximum": _plain_number(quantity),
                    "unit": unit,
                },
                "composition": "additional",
            }
            if item.note:
                line["note"] = item.note
            formula_items.append(line)

    grams = [
        (
            line["role"],
            item_grams({"quantity": line["quantity"]["target"], "unit": line["quantity"]["unit"]}),
        )
        for line in formula_items
    ]
    flour_g = sum((g for role, g in grams if role == "flour" and g is not None), Decimal(0))
    total_g = sum((g for _, g in grams if g is not None), Decimal(0))
    formula = {
        "anchor": {"kind": suggest_anchor_kind(flour_g, total_g, captured.kind)},
        "basis_g": None,
        "standardized": False,
        "ingredients": formula_items,
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


# ── Ficha de execução: lista e detalhe ──────────────────────────────────────


def build_recipe_sheet_list(
    *, query="", active="", production_mode="", sort="updated", page=1, page_size=48
) -> RecipeSheetListProjection:
    """As fichas de execução, com busca por nome/ref/SKU e recorte por situação."""
    sheets_qs = Recipe.objects.annotate(item_count=Count("items"))
    if active in ("1", "true", "yes"):
        sheets_qs = sheets_qs.filter(is_active=True)
    elif active in ("0", "false", "no"):
        sheets_qs = sheets_qs.filter(is_active=False)
    if production_mode:
        sheets_qs = sheets_qs.filter(production_mode=production_mode)
    term = (query or "").strip()
    if term:
        sheets_qs = sheets_qs.filter(Q(name__icontains=term) | Q(ref__icontains=term) | Q(output_sku__icontains=term))
    ordering = {
        "updated": ("-updated_at", "name", "ref"),
        "name": ("name", "ref"),
        "output": ("output_sku", "name", "ref"),
        "active": ("-is_active", "name", "ref"),
    }.get(sort, ("-updated_at", "name", "ref"))
    sheets_qs = sheets_qs.order_by(*ordering)
    total = sheets_qs.count()
    size = max(1, min(int(page_size or 48), 100))
    current = max(1, int(page or 1))
    start = (current - 1) * size
    sheets = list(sheets_qs[start : start + size])
    names = _output_names({sheet.output_sku for sheet in sheets if sheet.output_sku})
    entry_refs = set(
        RecipeEntry.objects.filter(ref__in=[sheet.ref for sheet in sheets]).values_list("ref", flat=True)
    )
    cards = tuple(_sheet_card(sheet, names, entry_refs) for sheet in sheets)
    return RecipeSheetListProjection(
        cards=cards,
        count=len(cards),
        page=current,
        page_size=size,
        total=total,
        has_next=start + len(cards) < total,
        sort=sort,
    )


def _sheet_card(sheet: Recipe, names: dict[str, str], entry_refs: set[str]) -> RecipeSheetCardProjection:
    return RecipeSheetCardProjection(
        ref=sheet.ref,
        name=sheet.name,
        output_sku=sheet.output_sku,
        output_name=names.get(sheet.output_sku, "") if sheet.output_sku else "",
        batch_size=_plain_number(sheet.batch_size),
        item_count=int(getattr(sheet, "item_count", 0) or 0),
        is_active=bool(sheet.is_active),
        production_mode=str(sheet.production_mode),
        production_mode_label=_production_mode_label(sheet.production_mode),
        has_entry=sheet.ref in entry_refs,
        updated_at_display=_datetime_display(sheet.updated_at),
    )


def build_recipe_sheet(ref: str) -> RecipeSheetDetailProjection:
    """A ficha inteira: identidade, itens com bruto/aproveitamento, massa e operação."""
    sheet = Recipe.objects.filter(ref=ref).prefetch_related("items").first()
    if sheet is None:
        raise RecipeSheetNotFound(f"Ficha '{ref}' não existe no cadastro.")
    items = list(sheet.items.order_by("sort_order", "input_sku"))
    names = _output_names({item.input_sku for item in items})
    entry = RecipeEntry.objects.filter(ref=ref).only("ref").first()
    return RecipeSheetDetailProjection(
        ref=sheet.ref,
        revision=recipe_book_service.recipe_revision(sheet),
        name=sheet.name,
        output_sku=sheet.output_sku,
        output_name=names.get(sheet.output_sku, "") if sheet.output_sku else "",
        batch_size=_plain_number(sheet.batch_size),
        output_unit=sheet._declared_output_unit(),
        is_active=bool(sheet.is_active),
        steps=tuple(_step_projection(step) for step in sheet.steps or []),
        items=tuple(_sheet_item(item, names) for item in items),
        mass_balance=_sheet_mass_balance(sheet, items),
        execution=_execution_sheet(sheet),
        has_entry=entry is not None,
        entry_ref=entry.ref if entry else "",
    )


def _sheet_item(item, names: dict[str, str]) -> RecipeSheetItemProjection:
    return RecipeSheetItemProjection(
        input_sku=item.input_sku,
        name=names.get(item.input_sku, "") or item.input_sku,
        quantity=_plain_number(item.quantity),
        unit=item.unit,
        usable_factor=_factor_text(item.usable_factor),
        gross_quantity=_plain_number(item.gross_quantity),
        correction_factor=_factor_text(item.correction_factor),
        sort_order=int(item.sort_order or 0),
        is_optional=bool(item.is_optional),
        note=str((item.meta or {}).get("note") or ""),
    )


def _factor_text(value) -> str:
    """Aproveitamento e fator de correção com as quatro casas que o modelo guarda."""
    return format(Decimal(value).quantize(Decimal("0.0001")).normalize(), "f")


def _item_mass_kg(item) -> Decimal | None:
    """Massa do item em kg, com a MESMA física do Core.

    A regra de arquitetura proíbe o import profundo do models/recipe.py, então
    a conta (massa direta; volume pela densidade declarada no item) é espelhada
    aqui. Contagem não atravessa: "6 ovos" só vira grama com peso por unidade.
    """
    from shopman.utils import units

    dimension = units.dimension(item.unit)
    if dimension == units.MASS:
        return units.convert(item.quantity, item.unit, "kg")
    if dimension == units.VOLUME:
        density = (item.meta or {}).get("density_g_per_ml")
        try:
            density = Decimal(str(density))
        except (TypeError, ArithmeticError, ValueError):
            return None
        if density <= 0:
            return None
        return units.convert(item.quantity, item.unit, "ml") * density / Decimal("1000")
    return None


def _sheet_mass_balance(sheet: Recipe, items: list) -> RecipeSheetMassBalanceProjection:
    """Rendimento contra a soma dos insumos, com a mesma régua do modelo.

    Só opina quando as duas pontas estão na mesma dimensão: saída em massa e todo
    insumo convertível (volume pela densidade declarada, contagem fora). Quando
    não dá para comparar, diz que não dá, em vez de aprovar em silêncio.
    """
    from shopman.utils import units

    output_unit = sheet._declared_output_unit()
    total_kg = Decimal("0")
    comparable = True
    has_mass = False
    for item in items:
        if item.is_optional:
            continue
        mass = _item_mass_kg(item)
        if mass is None:
            comparable = False
            break
        total_kg += mass
        has_mass = True
    if not has_mass:
        return RecipeSheetMassBalanceProjection(
            status="empty",
            output_unit=output_unit,
            batch_display=_quantity_display(sheet.batch_size, output_unit),
            total_display="",
            message="Sem ingredientes para somar.",
            tone="muted",
        )
    total_display = _grams_display(total_kg * _THOUSAND)
    if units.dimension(output_unit) != units.MASS or not comparable:
        return RecipeSheetMassBalanceProjection(
            status="incomparable",
            output_unit=output_unit,
            batch_display=_quantity_display(sheet.batch_size, output_unit),
            total_display=total_display,
            message="Esta ficha mistura unidades que não comparam; confira a soma à mão.",
            tone="muted",
        )
    batch_kg = units.convert(sheet.batch_size, output_unit, "kg")
    if batch_kg > total_kg:
        return RecipeSheetMassBalanceProjection(
            status="exceeds",
            output_unit=output_unit,
            batch_display=_quantity_display(sheet.batch_size, output_unit),
            total_display=total_display,
            message=(
                f"O rendimento ({_grams_display(batch_kg * _THOUSAND)}) passa da soma dos "
                f"insumos ({total_display}). Misturar não cria matéria: confira a ficha."
            ),
            tone="warning",
        )
    return RecipeSheetMassBalanceProjection(
        status="ok",
        output_unit=output_unit,
        batch_display=_quantity_display(sheet.batch_size, output_unit),
        total_display=total_display,
        message=f"O rendimento cabe na soma dos insumos ({total_display}).",
        tone="ok",
    )
