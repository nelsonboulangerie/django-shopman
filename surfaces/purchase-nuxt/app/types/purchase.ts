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
// De onde a NF tirou o fator. `invoice-tax-pair` e o par tributavel do proprio
// item (declaracao fiscal); `product-description` e a gramatura embutida no
// nome, sinal secundario. A tela diz qual foi — a procedencia e parte da
// informacao, nao enfeite.
export type ConversionSuggestionSource = "invoice-tax-pair" | "product-description";

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
  // O saldo atravessou uma ponte aproximada e carrega o "≈" ate a tela
  // (ADR-024, R3). Vem do carimbo `converted_via.approximate` no Move.
  stockIsApproximate?: boolean;
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
  key:
    | "missing-preferred"
    | "low-stock"
    | "approximate-cost"
    | "approximate-stock"
    | "inactive-material"
    | "no-conversion";
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

export interface ReceiptConversionSuggestion {
  label: string;
  // Texto, e nao numero: o fator volta ao servidor no gesto de declarar, e o
  // campo tem seis casas decimais. Passar por `number` perderia precisao de um
  // valor que multiplica estoque e dinheiro.
  factor: string;
  kind: ConversionKind;
  source: ConversionSuggestionSource;
  note: string;
}

export interface ReceiptLine {
  id: string;
  materialSku: string;
  suggestedMaterialSku?: string;
  suggestionScore?: number;
  conversionId: string | null;
  requiresConversion?: boolean;
  conversionSuggestion?: ReceiptConversionSuggestion | null;
  purchaseQty: number;
  costInput: string;
  expiryDate: string;
  // A validade veio do grupo `rastro` da NF-e, nao da mao do operador.
  expiryFromInvoice?: boolean;
  // Numero do lote do FORNECEDOR (`nLote`). E ele que um recall chama.
  invoiceLot?: string;
  // A OCORRENCIA do operador (avaria, falta, ressalva). Nasce vazia: o que a
  // nota diz mora nos campos `invoice*` abaixo.
  lineNote: string;
  invoiceDescription?: string;
  invoiceQty?: number;
  invoiceUnit?: string;
  invoiceTaxQty?: number;
  invoiceTaxUnit?: string;
  invoiceTotal?: string;
  invoiceProductCode?: string;
  invoiceEan?: string;
  checked: boolean;
}

export interface ReceiptLineSuggestion {
  sku: string;
  name: string;
  scorePercent: number;
}

export interface ReceiptLinePreview {
  line: ReceiptLine;
  material: Material;
  conversion: MaterialConversion | null;
  purchaseUnitLabel: string;
  baseQty: number;
  // A quantidade na unidade-base so e CONHECIDA quando a conversao esta
  // resolvida. Enquanto nao esta, `baseQty` e o produto por fator 1 — que e
  // justamente o numero errado do QA ("10 unidades" lidas como "10 kg"). A tela
  // le esta flag para nao imprimir um total que ninguem apurou ainda.
  baseQtyKnown: boolean;
  baseCostQ: number;
  totalCostQ: number;
  approximate: boolean;
  suggestion: ReceiptLineSuggestion | null;
  // O que a nota diz, em uma linha — a ancora do card. Vazio quando a entrada
  // e manual (sem NF), e ai o card nao finge ter documento.
  invoiceSummary: string;
  // A frase do que fazer AGORA nesta linha. Uma so, a mais urgente.
  nextStep: string;
  // O gesto pendente ja esta escrito no card do proprio campo (insumo ou
  // embalagem), entao o aviso do topo da linha se cala para nao repetir.
  nextStepIsOnField: boolean;
  // Pereciveis nao entram no estoque sem validade — e a nota nem sempre a traz.
  needsExpiry: boolean;
  conversionSuggestion: ReceiptConversionSuggestion | null;
  // A nota traz os dois eixos e a linha ainda espera conversao: da para propor
  // "usar o que a NF diz" mesmo sem o fator calculado aqui.
  invoiceAxes: string;
  conversionDiverges: boolean;
  warnings: ReceiptWarning[];
}

export interface ReceiptWarning {
  key:
    | "missing-material"
    | "confirm-suggestion"
    | "confirm-conversion"
    | "diverging-conversion"
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

export interface PurchaseConversionDeclarePayload {
  materialSku: string;
  supplierRef: string;
  label?: string;
  factor?: string;
  kind?: ConversionKind;
  // Alternativa a label+factor: manda o PAR da nota e o servidor deriva. A
  // fisica mora no Python; uma copia aqui seria a segunda tabela de conversao
  // que a ADR-024 existe para impedir.
  invoiceQty?: number;
  invoiceUnit?: string;
  invoiceTaxQty?: number;
  invoiceTaxUnit?: string;
  invoiceDescription?: string;
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
  // Só a rota de declarar conversão devolve: é por ele que a linha que estava
  // travada seleciona a conversão recém-criada, sem procurar por rótulo.
  conversionId?: string;
}
