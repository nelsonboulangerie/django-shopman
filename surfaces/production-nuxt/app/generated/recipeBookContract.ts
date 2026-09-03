// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/recipe_book.py
// Regenerate with: python manage.py export_recipe_book_schema

/** A recipe entry card on the recipe book inventory. */
export interface RecipeEntryCardProjection {
  ref: string;
  name: string;
  kind: string;
  kind_label: string;
  output_sku: string;
  output_name: string;
  has_ficha: boolean;
  current_version_number: number | null;
  version_count: number;
  draft_count: number;
  anchor_kind: string;
  hydration_display: string;
  updated_at_display: string;
  is_archived: boolean;
}

/** A recipe kind option (filter chip). */
export interface KindOptionProjection {
  value: string;
  label: string;
}

/** The recipe book inventory list. */
export interface RecipeBookListProjection {
  entries: RecipeEntryCardProjection[];
  kinds: KindOptionProjection[];
  count: number;
}

/** What the current operator may do on the recipe book. */
export interface RecipeBookAccessProjection {
  can_view: boolean;
  can_edit: boolean;
  capture_available: boolean;
}

/** One ingredient line of a formula, with its share of the anchor. */
export interface FormulaItemProjection {
  sku: string;
  name: string;
  role: string;
  role_label: string;
  quantity_display: string;
  quantity_g: string;
  unit: string;
  pct_display: string;
  is_anchor: boolean;
  matched: boolean;
}

/** A part of the base formula (preferment, autolyse, soaker, old dough). */
export interface FormulaPartProjection {
  sku: string;
  entry_ref: string;
  name: string;
  kind: string;
  kind_label: string;
  flour_pct_display: string;
  quantity_display: string;
  cap_pct_display: string;
  has_formula: boolean;
}

/** A bakery metric with its reference range and tone. */
export interface FormulaMetricProjection {
  code: string;
  label: string;
  value_display: string;
  low_display: string;
  high_display: string;
  max_display: string;
  tone: string;
  note: string;
}

/** A warning raised by the formula analysis. */
export interface FormulaWarningProjection {
  code: string;
  message: string;
  tone: string;
}

/** The lens over a formula: anchor, items with percentages, metrics, parts, final mix, BOM. */
export interface FormulaLensProjection {
  is_bakery: boolean;
  anchor_kind: string;
  anchor_label: string;
  basis_display: string;
  standardized: boolean;
  anchor_total_display: string;
  total_mass_display: string;
  items: FormulaItemProjection[];
  final_mix: FormulaItemProjection[];
  bom: FormulaItemProjection[];
  parts: FormulaPartProjection[];
  metrics: FormulaMetricProjection[];
  warnings: FormulaWarningProjection[];
}

/** A frozen formula version of a recipe entry. */
export interface RecipeVersionProjection {
  id: number;
  number: number;
  status: string;
  status_label: string;
  label: string;
  yield_quantity: string;
  yield_unit: string;
  yield_display: string;
  source_kind: string;
  source_label: string;
  created_by: string;
  created_at_display: string;
  published_at_display: string;
  notes: string;
  steps: string[];
  lens: FormulaLensProjection;
  formula: Record<string, unknown>;
  origin: Record<string, unknown>;
}

/** A recipe entry with its versions (newest first). */
export interface RecipeEntryDetailProjection {
  ref: string;
  name: string;
  kind: string;
  kind_label: string;
  output_sku: string;
  output_name: string;
  notes: string;
  is_archived: boolean;
  current_version_number: number | null;
  ficha_ref: string;
  versions: RecipeVersionProjection[];
}

/** One ingredient row of a version comparison. */
export interface RecipeCompareRowProjection {
  name: string;
  sku: string;
  role_label: string;
  a_display: string;
  b_display: string;
  delta_display: string;
  delta_pct_display: string;
  tone: string;
}

/** One metric row of a version comparison. */
export interface RecipeCompareMetricProjection {
  label: string;
  a_display: string;
  b_display: string;
  delta_display: string;
  tone: string;
}

/** Two formula versions side by side. */
export interface RecipeCompareProjection {
  a_title: string;
  b_title: string;
  rows: RecipeCompareRowProjection[];
  metrics: RecipeCompareMetricProjection[];
}

/** A reference range from the literature for a recipe kind. */
export interface ReferenceRangeProjection {
  code: string;
  label: string;
  low_display: string;
  high_display: string;
  max_display: string;
  note: string;
}

/** The reference ranges for a recipe kind. */
export interface RecipeReferenceProjection {
  kind: string;
  kind_label: string;
  ranges: ReferenceRangeProjection[];
}

/** An ingredient option (material or recipe entry with a formula). */
export interface IngredientOptionProjection {
  sku: string;
  name: string;
  unit: string;
  role: string;
  is_part: boolean;
  entry_ref: string;
}

/** One ingredient read from a note or a photo, with its matched material. */
export interface CaptureItemProjection {
  name: string;
  original_text: string;
  quantity: string;
  unit: string;
  role: string;
  sku: string;
  match_confidence: string;
  candidates: IngredientOptionProjection[];
}

/** The structured draft read from a note or a photo. */
export interface RecipeCaptureDraftProjection {
  name: string;
  kind: string;
  language: string;
  yield_quantity: string;
  yield_unit: string;
  items: CaptureItemProjection[];
  steps: string[];
  notes: string;
  formula: Record<string, unknown>;
}
