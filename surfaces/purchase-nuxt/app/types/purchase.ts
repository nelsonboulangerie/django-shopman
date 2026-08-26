export const PURCHASE_VIEWS = ["panel", "buy", "receive", "base"] as const;
export const PURCHASE_BASE_VIEWS = ["materials", "suppliers", "costs"] as const;

export type PurchaseView = (typeof PURCHASE_VIEWS)[number];
export type PurchaseBaseView = (typeof PURCHASE_BASE_VIEWS)[number];
export type PurchaseRequestStatus = "review" | "approved" | "sent";
export type MaterialUnit = "kg" | "g" | "l" | "ml" | "un";
export type ConversionKind = "conventional" | "approximate";
export type MaterialTone = "ok" | "watch" | "urgent";
export type ReceiptMode = "invoice" | "manual";
export type ReceiptWarningTone = "ok" | "watch" | "block";

export interface Material {
  sku: string;
  name: string;
  unit: MaterialUnit;
  shelfLifeDays: number | null;
  isActive: boolean;
  category: string;
  stockOnHand: number;
  dailyUse: number;
  minStock: number;
  recipes: string[];
  leadTimeDays?: number;
  replenishAtDays?: number;
  suggestedQty?: number;
}

export interface Supplier {
  ref: string;
  name: string;
  document: string;
  contact: string;
  leadTimeDays: number;
  reliabilityPercent: number;
  isActive: boolean;
  lastDeliveryAt: string;
  paymentTerm: string;
}

export interface MaterialConversion {
  id: string;
  materialSku: string;
  supplierRef: string | null;
  label: string;
  toBaseFactor: number;
  kind: ConversionKind;
  isActive: boolean;
}

export interface SupplierMaterialCost {
  id: string;
  materialSku: string;
  supplierRef: string;
  conversionId: string | null;
  costQ: number;
  isPreferred: boolean;
  updatedAt: string;
}

export interface PurchaseProjection {
  materials: Material[];
  suppliers: Supplier[];
  conversions: MaterialConversion[];
  costs: SupplierMaterialCost[];
  purchaseRequestStatuses: Record<string, PurchaseRequestStatus>;
  activeReceipt: {
    mode: ReceiptMode;
    supplierRef: string;
    invoiceInput: string;
    note: string;
    lines: ReceiptLine[];
  };
}

export interface PurchaseResponse {
  purchase: PurchaseProjection;
}

export interface MaterialIssue {
  key: "missing-preferred" | "low-stock" | "approximate-cost" | "inactive-material" | "no-conversion";
  label: string;
  tone: MaterialTone;
}

export interface EnrichedMaterial extends Material {
  coverageDays: number;
  preferredCost: SupplierMaterialCost | null;
  preferredBaseCostQ: number | null;
  supplierCount: number;
  conversionCount: number;
  tone: MaterialTone;
  issues: MaterialIssue[];
}

export interface SupplierCostRow {
  cost: SupplierMaterialCost;
  supplier: Supplier;
  conversion: MaterialConversion | null;
  purchaseUnitLabel: string;
  baseCostQ: number;
  approximate: boolean;
  deltaQ: number;
  deltaPercent: number;
}

export interface QuotePreview {
  costQ: number;
  purchaseUnitLabel: string;
  baseFactor: number;
  baseCostQ: number;
  approximate: boolean;
}

export interface ReceiptLine {
  id: string;
  materialSku: string;
  conversionId: string | null;
  requiresConversion?: boolean;
  purchaseQty: number;
  costInput: string;
  expiryDate: string;
  lineNote: string;
  checked: boolean;
}

export interface ReceiptLinePreview {
  line: ReceiptLine;
  material: Material;
  conversion: MaterialConversion | null;
  purchaseUnitLabel: string;
  baseQty: number;
  baseCostQ: number;
  totalCostQ: number;
  approximate: boolean;
  warnings: ReceiptWarning[];
}

export interface ReceiptWarning {
  key:
    | "missing-material"
    | "missing-conversion"
    | "missing-cost"
    | "missing-expiry"
    | "approximate-conversion"
    | "manual-source"
    | "invalid-qty";
  label: string;
  tone: ReceiptWarningTone;
}

export interface InvoiceProbe {
  raw: string;
  accessKey: string | null;
  valid: boolean;
}

export interface PurchaseScanInvoicePayload {
  qrPayload: string;
}

export interface PurchaseReceiptConfirmPayload {
  mode: ReceiptMode;
  supplierRef: string;
  invoiceAccessKey: string | null;
  note: string;
  lines: ReceiptLine[];
}

export type PurchaseReceiptRejectPayload = PurchaseReceiptConfirmPayload;

export interface PurchaseRequestActionPayload {
  materialSku: string;
}

export interface PurchaseCostUpsertPayload {
  materialSku: string;
  supplierRef: string;
  conversionId: string | null;
  costInput: string;
  makePreferred: boolean;
}

export interface PurchaseActionResponse {
  ok: boolean;
  purchase?: PurchaseProjection;
  message?: string;
}
