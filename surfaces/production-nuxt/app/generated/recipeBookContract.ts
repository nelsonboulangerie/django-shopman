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
  is_active: boolean;
  is_favorite: boolean;
  rating_display: string;
  rating_count: number;
  provenance_kind: string;
  provenance_label: string;
  review_status: string;
  review_label: string;
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
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  sort: string;
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
  final_mix_differs: boolean;
  bom: FormulaItemProjection[];
  bom_differs: boolean;
  parts: FormulaPartProjection[];
  metrics: FormulaMetricProjection[];
  warnings: FormulaWarningProjection[];
}

/** One production step of a version (``shopman.craftsman.recipe_steps``). */
export interface RecipeStepProjection {
  name: string;
  instructions: string;
  target_seconds: number | null;
  target_display: string;
  temperature_celsius: number | null;
  temperature_display: string;
  note: string;
}

/** A frozen formula version of a recipe entry. */
export interface RecipeVersionProjection {
  id: number;
  revision: string;
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
  steps: RecipeStepProjection[];
  lens: FormulaLensProjection;
  formula: Record<string, unknown>;
  origin: Record<string, unknown>;
  provenance_kind: string;
  provenance_label: string;
  provenance_detail: string;
  review_status: string;
  review_label: string;
  review_by_name: string;
  review_at_display: string;
}

/** A warning that travels with the usage numbers (what they do NOT measure). */
export interface UsageCaveatProjection {
  code: string;
  message: string;
}

/** Units of one quality grade among a version's executed batches. */
export interface QualityShareProjection {
  grade_ref: string;
  label: string;
  quantity_display: string;
  share_display: string;
}

/** What the house produced with one version (or with no version stamp). */
export interface VersionUsageProjection {
  version_ref: string;
  version_number: number | null;
  is_versioned: boolean;
  label: string;
  batches: number;
  batches_display: string;
  planned_display: string;
  finished_display: string;
  loss_display: string;
  yield_pct: string;
  yield_display: string;
  started_assumed_batches: number;
  avg_loss: string;
  avg_loss_display: string;
  loss_pct_display: string;
  summary_display: string;
  quality: QualityShareProjection[];
}

/** Executed batches of a recipe entry, by version, read from the work orders. */
export interface RecipeUsageProjection {
  date_from: string;
  date_to: string;
  bake_loss_basis: string;
  caveats: UsageCaveatProjection[];
  versions: VersionUsageProjection[];
  unversioned: VersionUsageProjection | null;
}

/** A book, video or article the recipe came from (``RecipeEntry.meta["external_references"]``). */
export interface ExternalReferenceProjection {
  title: string;
  url: string;
  host_display: string;
  note: string;
}

/** An active rating criterion (editable in the Admin, ``RecipeRatingCriterion``). */
export interface RatingCriterionProjection {
  id: number;
  name: string;
  description: string;
}

/** The average of one criterion for one version, and the score of who asked. */
export interface CriterionAverageProjection {
  criterion_id: number;
  name: string;
  average_display: string;
  count: number;
  my_score: number | null;
}

/** The 0 to 5 rating of one version: averages per criterion and overall. */
export interface VersionRatingProjection {
  version_number: number;
  version_ref: string;
  ratings_count: number;
  ratings_count_display: string;
  overall_display: string;
  criteria: CriterionAverageProjection[];
  rated_by_me: boolean;
  my_rated_at_display: string;
}

/** Uma variante de coordenação disponível para a ficha de execução. */
export interface LifecycleOptionProjection {
  value: string;
  label: string;
}

/** Configuração operacional da ficha que a versão publicada materializa. */
export interface ExecutionSheetProjection {
  exists: boolean;
  ref: string;
  revision: string;
  max_started_minutes: number | null;
  capacity_per_day: string;
  requires_batch_tracking: boolean;
  shelf_life_days: number | null;
  shelf_life_reviewed: boolean;
  shelf_life_reviewed_by: string;
  production_lifecycle: string;
  lifecycle_options: LifecycleOptionProjection[];
}

/** Uma linha da ficha de execução: o insumo e o que ele consome do estoque. */
export interface RecipeSheetItemProjection {
  input_sku: string;
  name: string;
  quantity: string;
  unit: string;
  usable_factor: string;
  gross_quantity: string;
  correction_factor: string;
  sort_order: number;
  is_optional: boolean;
  note: string;
}

/** A conta de massa da ficha: o rendimento contra a soma dos insumos. */
export interface RecipeSheetMassBalanceProjection {
  status: string;
  output_unit: string;
  batch_display: string;
  total_display: string;
  message: string;
  tone: string;
}

/** Um cartão de ficha de execução na lista. */
export interface RecipeSheetCardProjection {
  ref: string;
  name: string;
  output_sku: string;
  output_name: string;
  batch_size: string;
  item_count: number;
  is_active: boolean;
  has_entry: boolean;
  updated_at_display: string;
}

/** A lista de fichas de execução. */
export interface RecipeSheetListProjection {
  cards: RecipeSheetCardProjection[];
  count: number;
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
  sort: string;
}

/** A ficha de execução inteira: identidade, itens, massa e operação. */
export interface RecipeSheetDetailProjection {
  ref: string;
  revision: string;
  name: string;
  output_sku: string;
  output_name: string;
  batch_size: string;
  output_unit: string;
  is_active: boolean;
  steps: RecipeStepProjection[];
  items: RecipeSheetItemProjection[];
  mass_balance: RecipeSheetMassBalanceProjection;
  execution: ExecutionSheetProjection;
  has_entry: boolean;
  entry_ref: string;
}

/** A recipe entry with its versions (newest first). */
export interface RecipeEntryDetailProjection {
  ref: string;
  revision: string;
  name: string;
  kind: string;
  kind_label: string;
  output_sku: string;
  output_name: string;
  notes: string;
  is_active: boolean;
  current_version_number: number | null;
  ficha_ref: string;
  execution_in_sync: boolean;
  execution: ExecutionSheetProjection;
  is_favorite: boolean;
  versions: RecipeVersionProjection[];
  usage: RecipeUsageProjection;
  external_references: ExternalReferenceProjection[];
  rating_criteria: RatingCriterionProjection[];
  ratings: VersionRatingProjection[];
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

/** One recipe waiting for the baker's check, in the order of what sells most. */
export interface RecipeReviewItemProjection {
  ref: string;
  name: string;
  kind_label: string;
  output_sku: string;
  output_name: string;
  version_number: number;
  provenance_kind: string;
  provenance_label: string;
  provenance_detail: string;
  review_status: string;
  review_label: string;
  dough_sku: string;
  dough_name: string;
  sold_display: string;
}

/** The baker's check queue: current versions nobody from the house confirmed yet. */
export interface RecipeReviewQueueProjection {
  items: RecipeReviewItemProjection[];
  total: number;
  confirmed_total: number;
  recipe_total: number;
}
