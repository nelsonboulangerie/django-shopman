// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/production.py + api/_production_mutations.py
// Regenerate with: python manage.py export_production_schema

/** A compact order commitment for a production work order. */
export interface OrderCommitmentProjection {
  ref: string;
  status: string;
  status_label: string;
  qty_required: string;
}

/** How much of a base recipe is used by an output SKU recipe. */
export interface BaseRecipeUsageProjection {
  ref: string;
  output_sku: string;
  name: string;
  quantity_display: string;
  per_unit_display: string;
}

/** A single work order card on the production board. */
export interface WorkOrderCardProjection {
  pk: number;
  ref: string;
  rev: number;
  recipe_pk: number;
  recipe_ref: string;
  recipe_name: string;
  base_usages: BaseRecipeUsageProjection[];
  output_sku: string;
  status: string;
  status_label: string;
  tone: string;
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  yield_rate: string;
  loss: string;
  operator_ref: string;
  position_ref: string;
  target_date_display: string;
  started_at_display: string;
  created_at_display: string;
  progress_pct: number;
  committed_qty: string;
  order_commitments: OrderCommitmentProjection[];
  can_void: boolean;
}

/** Aggregate counts for the production board header. */
export interface ProductionCountsProjection {
  total: number;
  planned: number;
  started: number;
  finished: number;
  void: number;
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  loss_qty: string;
}

/** A recipe available for quick production form. */
export interface RecipeOptionProjection {
  pk: number;
  ref: string;
  name: string;
}

/** A base recipe available as an operational filter. */
export interface BaseRecipeOptionProjection {
  ref: string;
  output_sku: string;
  name: string;
  count: number;
}

/** A stock position available for production form. */
export interface PositionOptionProjection {
  pk: number;
  ref: string;
  name: string;
  is_default: boolean;
}

/** A suggested production row from Craftsman demand planning. */
export interface ProductionSuggestionProjection {
  recipe_pk: number;
  recipe_ref: string;
  recipe_name: string;
  base_usages: BaseRecipeUsageProjection[];
  output_sku: string;
  quantity: string;
  committed: string;
  avg_demand: string;
  confidence: string;
  sample_size: number;
  high_demand_applied: boolean;
  explanation_parts: string[];
}

/** A high-volume production matrix row grouped by SKU. */
export interface ProductionMatrixRowProjection {
  recipe_pk: number | null;
  output_sku: string;
  recipe_name: string;
  base_usages: BaseRecipeUsageProjection[];
  suggestion: ProductionSuggestionProjection | null;
  planned_orders: WorkOrderCardProjection[];
  started_orders: WorkOrderCardProjection[];
  finished_orders: WorkOrderCardProjection[];
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  loss_qty: string;
}

/** A matrix row within a base recipe group. */
export interface ProductionMatrixGroupRowProjection {
  row: ProductionMatrixRowProjection;
  usage: BaseRecipeUsageProjection | null;
}

/** A group of production matrix rows that share a base recipe. */
export interface ProductionMatrixGroupProjection {
  ref: string;
  output_sku: string;
  name: string;
  rows: ProductionMatrixGroupRowProjection[];
}

/** Effective production capabilities for one operator and station context. */
export interface ProductionSurfaceAccess {
  can_manage_all: boolean;
  can_view_suggested: boolean;
  can_edit_suggested: boolean;
  can_view_planned: boolean;
  can_edit_planned: boolean;
  can_view_started: boolean;
  can_edit_started: boolean;
  can_view_finished: boolean;
  can_edit_finished: boolean;
  can_view_unsold: boolean;
  can_edit_unsold: boolean;
  can_view_plan: boolean;
  can_edit_plan: boolean;
  can_start: boolean;
  can_advance_step: boolean;
  can_close_qc: boolean;
  can_quick_finish: boolean;
  can_override_shortage: boolean;
  can_void: boolean;
  can_record_oven_fact: boolean;
  can_view_reports: boolean;
  can_reveal_blind_map: boolean;
}

/** Top-level read model for the production board. */
export interface ProductionBoardProjection {
  selected_date: string;
  selected_date_display: string;
  selected_position_ref: string;
  selected_operator_ref: string;
  selected_base_recipe: string;
  work_orders: WorkOrderCardProjection[];
  counts: ProductionCountsProjection;
  planned_queue: WorkOrderCardProjection[];
  started_queue: WorkOrderCardProjection[];
  finished_queue: WorkOrderCardProjection[];
  recipes: RecipeOptionProjection[];
  base_recipes: BaseRecipeOptionProjection[];
  positions: PositionOptionProjection[];
  suggestions: ProductionSuggestionProjection[];
  matrix_rows: ProductionMatrixRowProjection[];
  matrix_groups: ProductionMatrixGroupProjection[];
  default_position_pk: number | null;
  access: ProductionSurfaceAccess;
}

/** A started work order card for the production KDS. */
export interface ProductionKDSCardProjection {
  pk: number;
  ref: string;
  rev: number;
  output_sku: string;
  recipe_name: string;
  started_qty: string;
  operator_ref: string;
  position_ref: string;
  started_at_display: string;
  elapsed_seconds: number;
  elapsed_minutes: number;
  target_seconds: number;
  timer_status_code: string;
  timer_tone: string;
  current_step: string;
  current_step_index: number | null;
  total_steps: number;
  current_step_name: string;
  step_progress_pct: number;
  next_step_name: string;
  time_remaining_min: number | null;
  can_finish: boolean;
  order_refs: string[];
}

/** Top-level read model for the production KDS. */
export interface ProductionKDSProjection {
  selected_date: string;
  selected_date_display: string;
  cards: ProductionKDSCardProjection[];
  total_count: number;
  late_count: number;
  access: ProductionSurfaceAccess;
}

/** ForecastRowProjection(ref: 'str', output_sku: 'str', recipe_name: 'str', qty: 'str', eta_display: 'str', eta_is_actual: 'bool', status: 'str', status_label: 'str', history_days: 'int') */
export interface ForecastRowProjection {
  ref: string;
  output_sku: string;
  recipe_name: string;
  qty: string;
  eta_display: string;
  eta_is_actual: boolean;
  status: string;
  status_label: string;
  history_days: number;
}

/** ProductionForecastProjection(selected_date: 'str', selected_date_display: 'str', generated_at_display: 'str', rows: 'tuple[ForecastRowProjection, ...]', access: 'ProductionSurfaceAccess') */
export interface ProductionForecastProjection {
  selected_date: string;
  selected_date_display: string;
  generated_at_display: string;
  rows: ForecastRowProjection[];
  access: ProductionSurfaceAccess;
}

/** Quanto deste insumo cada receita do dia consome. */
export interface MiseEnPlaceBreakdownProjection {
  recipe_name: string;
  output_sku: string;
  quantity_display: string;
}

/** One aggregated ingredient line for the day's mise en place. */
export interface MiseEnPlaceLineProjection {
  sku: string;
  name: string;
  quantity_display: string;
  unit: string;
  is_subrecipe: boolean;
  available_display: string;
  is_short: boolean;
  breakdown: MiseEnPlaceBreakdownProjection[];
  annotation: string;
  margin_display: string;
  margin_reason: string;
}

/** Aggregated material needs for the day's open work orders. */
export interface ProductionMiseEnPlaceProjection {
  selected_date: string;
  selected_date_display: string;
  expanded: boolean;
  lines: MiseEnPlaceLineProjection[];
  has_lines: boolean;
  work_order_count: number;
  has_stock_readings: boolean;
  yield_margin_applied: boolean;
  yield_margin_note: string;
  access: ProductionSurfaceAccess;
}

/** One ingredient line for a thermal weighing ticket. */
export interface ProductionWeighingIngredientProjection {
  sku: string;
  name: string;
  quantity_display: string;
  is_subrecipe: boolean;
}

/** A printable 80mm-oriented ticket for one recipe/base recipe. */
export interface ProductionWeighingTicketProjection {
  recipe_ref: string;
  output_sku: string;
  name: string;
  output_quantity_display: string;
  dough_weight_display: string;
  sources_display: string;
  ingredients: ProductionWeighingIngredientProjection[];
  table: Record<string, unknown>;
  blind_code: string;
  made_display: string;
  expiry_display: string;
}

/** Printable weighing tickets for saved production planning. */
export interface ProductionWeighingProjection {
  selected_date: string;
  selected_date_display: string;
  selected_position_ref: string;
  selected_base_recipe: string;
  tickets: ProductionWeighingTicketProjection[];
  access: ProductionSurfaceAccess;
}

/** One blind code ↔ prep row of the manager's correlation map. */
export interface ProductionBlindMapRowProjection {
  code: string;
  name: string;
  output_quantity_display: string;
}

/** Manager-only map of the day's blind codes to their preps. */
export interface ProductionBlindMapProjection {
  selected_date: string;
  selected_date_display: string;
  rows: ProductionBlindMapRowProjection[];
  access: ProductionSurfaceAccess;
}

/** A started work order that exceeded its configured target window. */
export interface ProductionLateWorkOrderProjection {
  pk: number;
  ref: string;
  output_sku: string;
  recipe_name: string;
  operator_ref: string;
  elapsed_minutes: number;
  target_minutes: number;
}

/** Top-level read model for the production dashboard. */
export interface ProductionDashboardProjection {
  selected_date: string;
  selected_date_display: string;
  planned_orders: number;
  started_orders: number;
  finished_orders: number;
  void_orders: number;
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  loss_qty: string;
  average_yield_rate: string;
  capacity_percent: number | null;
  late_orders: ProductionLateWorkOrderProjection[];
  access: ProductionSurfaceAccess;
}

/** Um grau da escala de QC (ADR-017 §6). */
export interface QCGradeProjection {
  ref: string;
  label: string;
  rank: number;
  markdown_percent: number;
  is_default: boolean;
}

/** Um defeito do catálogo de QC — o ``hint`` é a segunda linha do botão. */
export interface QCDefectProjection {
  ref: string;
  label: string;
  hint: string;
  forces_discard: boolean;
}

/** Uma fornada do dia no painel do quiosque de QC. */
export interface QCOrderCardProjection {
  pk: number;
  ref: string;
  rev: number;
  recipe_name: string;
  output_sku: string;
  position_ref: string;
  status: string;
  planned_qty: string;
  started_qty: string;
  started_at_display: string;
  elapsed_minutes: number;
  can_close: boolean;
  closed: boolean;
  committed_qty: string;
  full_price_qty: string;
  discounted_qty: string;
  loss_qty: string;
}

/** O quiosque do fournil (ADR-017 §9): ordens do dia + catálogos de QC. */
export interface QCKioskProjection {
  selected_date: string;
  selected_date_display: string;
  orders: QCOrderCardProjection[];
  closed_count: number;
  total_count: number;
  grades: QCGradeProjection[];
  defects: QCDefectProjection[];
  recipes: RecipeOptionProjection[];
  previous_open_count: number;
  previous_open_date: string;
  access: ProductionSurfaceAccess;
}

/** Normalized filters for production reports. */
export interface ProductionReportFilters {
  date_from: string;
  date_to: string;
  report_kind: string;
  recipe_ref: string;
  position_ref: string;
  operator_ref: string;
  status: string;
}

/** A work order history row for production audit reports. */
export interface WorkOrderReportRow {
  ref: string;
  date: string;
  recipe_ref: string;
  recipe_name: string;
  position_ref: string;
  qty_planned: string;
  qty_started: string;
  qty_finished: string;
  qty_loss: string;
  yield_rate: string;
  operator_ref: string;
  started_at: string;
  finished_at: string;
  duration_minutes: string;
}

/** Aggregated productivity by production operator. */
export interface OperatorProductivityRow {
  operator_ref: string;
  operator_name: string;
  wo_count: number;
  qty_total: string;
  yield_avg: string;
  duration_avg_minutes: string;
}

/** Aggregated waste by recipe. */
export interface RecipeWasteRow {
  recipe_ref: string;
  recipe_name: string;
  wo_count: number;
  loss_total: string;
  yield_avg: string;
  capacity_utilization: string;
}

/** Partição de qualidade agregada por receita × grau × defeito (ADR-017). */
export interface QualityReportRow {
  recipe_ref: string;
  recipe_name: string;
  grade_ref: string;
  grade_label: string;
  defect_ref: string;
  defect_label: string;
  quantity: string;
  share: string;
}

/** Top-level read model for production reports. */
export interface ProductionReportsProjection {
  filters: ProductionReportFilters;
  history_rows: WorkOrderReportRow[];
  operator_rows: OperatorProductivityRow[];
  waste_rows: RecipeWasteRow[];
  quality_rows: QualityReportRow[];
  available_recipes: RecipeOptionProjection[];
  available_positions: PositionOptionProjection[];
  access: ProductionSurfaceAccess;
}

/** Minimal authoritative WorkOrder state returned after every mutation. */
export interface ProductionMutationCurrent {
  pk: number;
  ref: string;
  status: string;
  rev: number;
}

/** ProductionPlanMutationSuccess(ok: 'bool', result: 'str', output_sku: 'str', wo_ref: 'str', quantity: 'str', current: 'ProductionMutationCurrent | None') */
export interface ProductionPlanMutationSuccess {
  ok: boolean;
  result: string;
  output_sku: string;
  wo_ref: string;
  quantity: string;
  current: ProductionMutationCurrent | null;
}

/** ProductionWorkOrderMutationSuccess(ok: 'bool', wo_ref: 'str', quantity: 'str', current: 'ProductionMutationCurrent | None') */
export interface ProductionWorkOrderMutationSuccess {
  ok: boolean;
  wo_ref: string;
  quantity: string;
  current: ProductionMutationCurrent | null;
}

/** ProductionAdvanceStepMutationSuccess(ok: 'bool', wo_id: 'int', step_index: 'int', current: 'ProductionMutationCurrent | None') */
export interface ProductionAdvanceStepMutationSuccess {
  ok: boolean;
  wo_id: number;
  step_index: number;
  current: ProductionMutationCurrent | null;
}

/** ProductionVoidMutationSuccess(ok: 'bool', wo_ref: 'str', current: 'ProductionMutationCurrent | None') */
export interface ProductionVoidMutationSuccess {
  ok: boolean;
  wo_ref: string;
  current: ProductionMutationCurrent | null;
}

/** ProductionOvenArmMutationSuccess(ok: 'bool', run_id: 'int', current: 'ProductionMutationCurrent | None') */
export interface ProductionOvenArmMutationSuccess {
  ok: boolean;
  run_id: number;
  current: ProductionMutationCurrent | null;
}

/** ProductionOvenConcludeMutationSuccess(ok: 'bool', measured: 'bool', current: 'ProductionMutationCurrent | None') */
export interface ProductionOvenConcludeMutationSuccess {
  ok: boolean;
  measured: boolean;
  current: ProductionMutationCurrent | null;
}

/** ProductionValidationIssue(field: 'str', code: 'str', message: 'str') */
export interface ProductionValidationIssue {
  field: string;
  code: string;
  message: string;
}

/** ProductionValidationErrorBody(code: "Literal['validation_error']", issues: 'tuple[ProductionValidationIssue, ...]') */
export interface ProductionValidationErrorBody {
  code: "validation_error";
  issues: ProductionValidationIssue[];
}

/** ProductionValidationErrorEnvelope(detail: 'str', error: 'ProductionValidationErrorBody') */
export interface ProductionValidationErrorEnvelope {
  detail: string;
  error: ProductionValidationErrorBody;
}

/** ProductionConflictRecovery(action: "Literal['refresh']", label: 'str') */
export interface ProductionConflictRecovery {
  action: "refresh";
  label: string;
}

/** ProductionConflictErrorBody(code: "Literal['conflict', 'state_conflict']", sent_rev: 'int | None', current_rev: 'int | None', current: 'ProductionMutationCurrent | None', recovery: 'ProductionConflictRecovery') */
export interface ProductionConflictErrorBody {
  code: "conflict" | "state_conflict";
  sent_rev: number | null;
  current_rev: number | null;
  current: ProductionMutationCurrent | null;
  recovery: ProductionConflictRecovery;
}

/** ProductionConflictErrorEnvelope(detail: 'str', error: 'ProductionConflictErrorBody') */
export interface ProductionConflictErrorEnvelope {
  detail: string;
  error: ProductionConflictErrorBody;
}

/** ProductionShortagePossibility(kind: "Literal['retry', 'force']", label: 'str', enabled: 'bool') */
export interface ProductionShortagePossibility {
  kind: "retry" | "force";
  label: string;
  enabled: boolean;
}

/** ProductionMaterialShortageItem(sku: 'str', needed: 'str', available: 'str', shortage: 'str') */
export interface ProductionMaterialShortageItem {
  sku: string;
  needed: string;
  available: string;
  shortage: string;
}

/** ProductionMaterialShortageErrorBody(code: "Literal['material_shortage']", work_order_ref: 'str', idempotency_key: 'str', possibilities: 'tuple[ProductionShortagePossibility, ...]', missing: 'tuple[ProductionMaterialShortageItem, ...]') */
export interface ProductionMaterialShortageErrorBody {
  code: "material_shortage";
  work_order_ref: string;
  idempotency_key: string;
  possibilities: ProductionShortagePossibility[];
  missing: ProductionMaterialShortageItem[];
}

/** ProductionMaterialShortageErrorEnvelope(detail: 'str', error: 'ProductionMaterialShortageErrorBody') */
export interface ProductionMaterialShortageErrorEnvelope {
  detail: string;
  error: ProductionMaterialShortageErrorBody;
}

/** ProductionOrderShortageErrorBody(code: "Literal['order_shortage']", work_order_ref: 'str', idempotency_key: 'str', possibilities: 'tuple[ProductionShortagePossibility, ...]', required: 'str', requested: 'str', order_refs: 'tuple[str, ...]') */
export interface ProductionOrderShortageErrorBody {
  code: "order_shortage";
  work_order_ref: string;
  idempotency_key: string;
  possibilities: ProductionShortagePossibility[];
  required: string;
  requested: string;
  order_refs: string[];
}

/** ProductionOrderShortageErrorEnvelope(detail: 'str', error: 'ProductionOrderShortageErrorBody') */
export interface ProductionOrderShortageErrorEnvelope {
  detail: string;
  error: ProductionOrderShortageErrorBody;
}

export interface ProductionPartitionGroupRequest {
  quantity: string;
  quality_grade_ref?: string;
  quality_defect_ref?: string;
  loss?: boolean;
}

export interface ProductionPlanMutationRequest {
  idempotency_key: string;
  recipe_id: number;
  quantity: string;
  target_date: string;
  position_ref?: string;
  operator_ref?: string;
  reason?: string;
  source?: "manual" | "suggested";
  force?: boolean;
  expected_rev: number | null;
}

export interface ProductionStartMutationRequest {
  idempotency_key: string;
  expected_rev: number;
  quantity: string;
  position_id?: string;
  operator_ref?: string;
  note?: string;
}

export interface ProductionFinishMutationRequest {
  idempotency_key: string;
  expected_rev: number;
  quantity: string;
  force?: boolean;
  reason?: string;
  quality?: string;
  partition?: ProductionPartitionGroupRequest[];
}

export interface ProductionAdvanceStepMutationRequest {
  idempotency_key: string;
  expected_rev: number;
}

export interface ProductionQuickFinishMutationRequest {
  idempotency_key: string;
  recipe_id: number;
  quantity: string;
  position_id?: string;
  force?: boolean;
  reason?: string;
  partition?: ProductionPartitionGroupRequest[];
}

export interface ProductionVoidMutationRequest {
  idempotency_key: string;
  expected_rev: number;
  reason: string;
}

export interface ProductionOvenArmMutationRequest {
  idempotency_key: string;
  expected_rev: number;
  planned_seconds: number;
  operator_ref?: string;
}

export interface ProductionOvenConcludeMutationRequest {
  idempotency_key: string;
  expected_rev: number;
}

/** Generated production writer. Errors use the envelopes above. */
async function postProductionMutation<T>(href: string, body: unknown): Promise<T> {
  const post = $fetch as unknown as (
    request: string,
    options: { method: "POST"; body: unknown },
  ) => Promise<T>;
  return post(href, { method: "POST", body });
}

export function planProduction(body: ProductionPlanMutationRequest): Promise<ProductionPlanMutationSuccess> {
  return postProductionMutation<ProductionPlanMutationSuccess>("/api/v1/backstage/production/plan/", body);
}

export function startProductionWorkOrder(workOrderId: number, body: ProductionStartMutationRequest): Promise<ProductionWorkOrderMutationSuccess> {
  return postProductionMutation<ProductionWorkOrderMutationSuccess>(`/api/v1/backstage/production/${workOrderId}/start/`, body);
}

export function finishProductionWorkOrder(workOrderId: number, body: ProductionFinishMutationRequest): Promise<ProductionWorkOrderMutationSuccess> {
  return postProductionMutation<ProductionWorkOrderMutationSuccess>(`/api/v1/backstage/production/${workOrderId}/finish/`, body);
}

export function advanceProductionWorkOrderStep(workOrderId: number, body: ProductionAdvanceStepMutationRequest): Promise<ProductionAdvanceStepMutationSuccess> {
  return postProductionMutation<ProductionAdvanceStepMutationSuccess>(`/api/v1/backstage/production/${workOrderId}/advance-step/`, body);
}

export function quickFinishProduction(body: ProductionQuickFinishMutationRequest): Promise<ProductionWorkOrderMutationSuccess> {
  return postProductionMutation<ProductionWorkOrderMutationSuccess>("/api/v1/backstage/production/quick-finish/", body);
}

export function voidProductionWorkOrder(workOrderId: number, body: ProductionVoidMutationRequest): Promise<ProductionVoidMutationSuccess> {
  return postProductionMutation<ProductionVoidMutationSuccess>(`/api/v1/backstage/production/${workOrderId}/void/`, body);
}

export function armProductionOven(workOrderId: number, body: ProductionOvenArmMutationRequest): Promise<ProductionOvenArmMutationSuccess> {
  return postProductionMutation<ProductionOvenArmMutationSuccess>(`/api/v1/backstage/production/${workOrderId}/oven/arm/`, body);
}

export function concludeProductionOven(workOrderId: number, body: ProductionOvenConcludeMutationRequest): Promise<ProductionOvenConcludeMutationSuccess> {
  return postProductionMutation<ProductionOvenConcludeMutationSuccess>(`/api/v1/backstage/production/${workOrderId}/oven/conclude/`, body);
}
