import type { ProductionWeighingProjection } from "~/generated/productionContract";

export type ProductionLabelMode = "blind" | "explicit";
export type ProductionLabelTransport = "relay" | "browser";

export type ProductionPrintJobStatus =
  | "prepared"
  | "dispatching"
  | "leased"
  | "awaiting_station"
  | "queued"
  | "accepted"
  | "spooled"
  | "awaiting_confirmation"
  | "confirmed"
  | "failed"
  | "unknown"
  | "uncertain"
  | "cancelled"
  | "expired"
  | string;

export interface ProductionBlindLabel {
  code: string;
  ingredient: string;
  sku: string;
  weight: string;
  annotation?: string;
  date: string;
  key: string;
}

export interface ProductionPreparationLabelTicket {
  ticket_ref?: string;
  name: string;
  output_sku: string;
  output_quantity_display: string;
  total_weight_display?: string;
  /** Alias somente para a projeção viva durante a transição de contrato. */
  dough_weight_display?: string;
  sources_display: string;
  blind_code: string;
  made_display: string;
  expiry_display: string;
  validity_configured?: boolean;
  validity_source?: string;
}

export interface ProductionPrintDocumentIngredient {
  name: string;
  sku: string;
  quantity_display: string;
  target_display?: string;
  annotation?: string;
}

export interface ProductionPrintDocumentTicket {
  ticket_ref: string;
  blind_code: string;
  made_display: string;
  expiry_display?: string;
  ingredients?: ProductionPrintDocumentIngredient[];
  // Ausentes por contrato no documento cego.
  name?: string;
  output_sku?: string;
  output_quantity_display?: string;
  total_weight_display?: string;
  sources_display?: string;
  validity_configured?: boolean;
  validity_source?: string;
}

export interface ProductionLabelPrintDocument {
  contract_version?: number;
  mode: ProductionLabelMode;
  purpose?: "internal_weighing" | "internal_preparation";
  legal_scope?: "internal_only_not_for_sale";
  date_basis?: "planned_production_date";
  selected_date: string;
  scale_precision_g?: string;
  scale_precision_display?: string;
  scale_rounding_note?: string;
  tickets: ProductionPrintDocumentTicket[];
}

/** O contrato gerado é a fonte única da projeção viva de impressão. */
export type ProductionPrintingSourceProjection = ProductionWeighingProjection;

export interface ProductionPrintJobProjection {
  ref: string;
  status: ProductionPrintJobStatus;
  status_label: string;
  message: string;
  target_label: string;
  label_count: number;
  copy_number: number;
  can_retry: boolean;
  can_reprint: boolean;
  can_confirm: boolean;
  poll_after_ms: number;
  print_document: ProductionLabelPrintDocument;
  document_sha256: string;
  payload_b64?: string;
  payload_sha256?: string;
  print_title?: string;
}

export interface ProductionPrintJobResponse {
  print_job: ProductionPrintJobProjection;
}

export interface ProductionPrintJobCreateRequest {
  mode: ProductionLabelMode;
  selected_date: string;
  position: string;
  base_recipe: string;
  ticket_refs: string[];
  transport: ProductionLabelTransport;
  idempotency_key: string;
  projection_generated_at: string;
  source_revision: string;
  fresh_until: string;
  contract_version: number;
  action_ref: string;
  action_proof: string;
}

export type ProductionBrowserPrintResult =
  | "dialog_opened"
  | "dialog_unavailable"
  | "agent_spooled"
  | "agent_failed";
