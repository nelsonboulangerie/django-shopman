// Presentation — ficha de execução (craftsman.Recipe + RecipeItem). Transforms
// puras sobre o contrato de shopman/backstage/projections/recipe_book.py: a
// consulta da lista, a edição imutável das linhas, o corpo do cadastro e a
// PRÉVIA LOCAL da conta de massa. A conta oficial (e a recusa) é do modelo:
// aqui só se mostra, antes de salvar, o que o invariante vai cobrar.

import type {
  RecipeSheetItemDraft,
  RecipeSheetItemPayload,
  RecipeSheetItemProjection,
  RecipeSheetPayload,
  RecipeStepInput,
  RecipeStepProjection,
} from "~/types/recipeBook";
import { PRODUCTION_MODE_BATCH, formatNumber, productionModeQuery, stepsFromText } from "~/presentation/recipeBook";

/** Unidades aceitas pelo RecipeItem (inclui mg, que a fórmula não usa). */
export const SHEET_UNIT_OPTIONS: readonly string[] = ["un", "kg", "g", "mg", "L", "ml"] as const;

/** Unidade do rendimento: as mesmas do RecipeVersion.YieldUnit. */
export const SHEET_YIELD_UNIT_OPTIONS: readonly string[] = ["kg", "g", "un", "L", "ml"] as const;

export const SHEET_SORT_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "updated", label: "Atualizadas recentemente" },
  { value: "name", label: "Nome" },
  { value: "output", label: "SKU de saída" },
  { value: "active", label: "Ativas primeiro" },
] as const;

/**
 * "Todas": o Select do Nuxt UI (Reka) recusa item de valor vazio e derruba a
 * página inteira com 500. O recorte sem filtro tem valor próprio, e a consulta o ignora.
 */
export const SHEET_ALL_FILTER = "all";

export const SHEET_ACTIVE_OPTIONS: readonly { value: string; label: string }[] = [
  { value: SHEET_ALL_FILTER, label: "Todas" },
  { value: "1", label: "Ativas" },
  { value: "0", label: "Inativas" },
] as const;

const MASS_UNITS = new Set<string>(["kg", "g", "mg"]);

// ── Linhas da ficha (edição imutável) ───────────────────────────────────────

export function emptySheetItem(over: Partial<RecipeSheetItemDraft> = {}): RecipeSheetItemDraft {
  return { inputSku: "", quantity: "", unit: "kg", usableFactor: "1", isOptional: false, note: "", ...over };
}

export function itemFromProjection(item: RecipeSheetItemProjection): RecipeSheetItemDraft {
  return {
    inputSku: item.input_sku,
    quantity: item.quantity,
    unit: item.unit,
    usableFactor: item.usable_factor,
    isOptional: item.is_optional,
    note: item.note,
  };
}

export function itemsFromProjection(items: readonly RecipeSheetItemProjection[]): RecipeSheetItemDraft[] {
  return items.map(itemFromProjection);
}

export function addSheetItem(items: readonly RecipeSheetItemDraft[], item = emptySheetItem()): RecipeSheetItemDraft[] {
  return [...items, item];
}

/** O mesmo slug do servidor (Django slugify): sem acento, minúsculo, sem borda. */
export function sheetSlug(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
}

function trimZeros(text: string): string {
  return text.replace(/0+$/, "").replace(/,$/, "");
}

/** Massa em kg/g como a projeção escreve ("1,7 kg", "500 g"). */
function massLabel(kg: number): string {
  if (kg >= 1) return trimZeros(formatNumber(kg, 3)) + " kg";
  return trimZeros(formatNumber(kg * 1000, 3)) + " g";
}

export function updateSheetItem(
  items: readonly RecipeSheetItemDraft[],
  index: number,
  patch: Partial<RecipeSheetItemDraft>,
): RecipeSheetItemDraft[] {
  if (index < 0 || index >= items.length) return [...items];
  return items.map((item, i) => (i === index ? { ...item, ...patch } : item));
}

export function removeSheetItem(items: readonly RecipeSheetItemDraft[], index: number): RecipeSheetItemDraft[] {
  return items.filter((_, i) => i !== index);
}

export function moveSheetItem(
  items: readonly RecipeSheetItemDraft[],
  from: number,
  to: number,
): RecipeSheetItemDraft[] {
  const last = items.length - 1;
  if (from < 0 || from > last || to < 0 || to > last || from === to) return [...items];
  const copy = [...items];
  const [moved] = copy.splice(from, 1);
  copy.splice(to, 0, moved as RecipeSheetItemDraft);
  return copy;
}

function numberOrNull(value: string): number | null {
  const clean = value.trim().replace(",", ".");
  if (!clean) return null;
  const parsed = Number(clean);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function integerOrNull(value: string): number | null {
  const parsed = numberOrNull(value);
  if (parsed === null) return null;
  if (!Number.isInteger(parsed)) return Number.NaN;
  return parsed;
}

// ── Prévia local da massa ───────────────────────────────────────────────────

export interface SheetMassPreview {
  status: "empty" | "incomparable" | "ok" | "exceeds";
  tone: "muted" | "ok" | "warning";
  batchDisplay: string;
  totalDisplay: string;
  message: string;
}

/** Quilos de uma linha da ficha; null quando a dimensão não é massa. */
export function sheetItemKg(item: RecipeSheetItemDraft): number | null {
  const quantity = numberOrNull(item.quantity);
  if (quantity === null || !Number.isFinite(quantity)) return null;
  if (item.unit === "kg") return quantity;
  if (item.unit === "g") return quantity / 1000;
  if (item.unit === "mg") return quantity / 1000000;
  return null;
}

/** A mesma régua do modelo, adiantada para a tela: só opina quando dá para comparar. */
export function massBalancePreview(
  items: readonly RecipeSheetItemDraft[],
  batchSize: string,
  outputUnit: string,
): SheetMassPreview {
  const batch = numberOrNull(batchSize);
  const batchValid = batch !== null && Number.isFinite(batch) && batch > 0;
  const batchDisplay = batchValid ? [formatNumber(batch as number, 3), outputUnit].filter(Boolean).join(" ") : "";
  const nonOptional = items.filter((item) => !item.isOptional);
  if (!nonOptional.length) {
    return { status: "empty", tone: "muted", batchDisplay, totalDisplay: "", message: "Sem ingredientes para somar." };
  }
  let totalKg = 0;
  for (const item of nonOptional) {
    const kg = sheetItemKg(item);
    if (kg === null) {
      return {
        status: "incomparable",
        tone: "muted",
        batchDisplay,
        totalDisplay: "",
        message: "Há volume ou contagem sem conversão: confira a soma à mão.",
      };
    }
    totalKg += kg;
  }
  const totalDisplay = massLabel(totalKg);
  if (!MASS_UNITS.has(outputUnit)) {
    return {
      status: "incomparable",
      tone: "muted",
      batchDisplay,
      totalDisplay,
      message: "A unidade de saída não é massa; a soma fica de referência.",
    };
  }
  if (!batchValid) {
    return { status: "incomparable", tone: "muted", batchDisplay, totalDisplay, message: "Informe o rendimento base." };
  }
  const batchKg = outputUnit === "kg" ? (batch as number) : outputUnit === "g" ? (batch as number) / 1000 : (batch as number) / 1000000;
  if (batchKg > totalKg) {
    return {
      status: "exceeds",
      tone: "warning",
      batchDisplay,
      totalDisplay,
      message: "O rendimento passa da soma dos insumos. Confira a ficha.",
    };
  }
  return { status: "ok", tone: "ok", batchDisplay, totalDisplay, message: "O rendimento cabe na soma dos insumos." };
}

// ── Corpo do cadastro ───────────────────────────────────────────────────────

export interface SheetDraft {
  name: string;
  ref: string;
  outputSku: string;
  batchSize: string;
  isActive: boolean;
  stepsText: string;
  maxStartedMinutes: string;
  capacityPerDay: string;
  requiresBatchTracking: boolean;
  shelfLifeDays: string;
  shelfLifeReviewed: boolean;
  productionLifecycle: string;
  /** `Recipe.production_mode`: "batch" (Em lote) ou "made_to_order" (Na hora). */
  productionMode: string;
  items: RecipeSheetItemDraft[];
}

export function emptySheetDraft(): SheetDraft {
  return {
    name: "",
    ref: "",
    outputSku: "",
    batchSize: "",
    isActive: true,
    stepsText: "",
    maxStartedMinutes: "",
    capacityPerDay: "",
    requiresBatchTracking: false,
    shelfLifeDays: "",
    shelfLifeReviewed: false,
    productionLifecycle: "",
    productionMode: PRODUCTION_MODE_BATCH,
    items: [emptySheetItem()],
  };
}

/** A primeira razão pela qual o cadastro não pode ser salvo; "" quando pode. */
export function sheetDraftError(draft: SheetDraft): string {
  if (!draft.name.trim()) return "Informe o nome da ficha.";
  if (!draft.outputSku.trim()) return "Informe o SKU de saída.";
  const batch = numberOrNull(draft.batchSize);
  if (batch === null || Number.isNaN(batch) || batch <= 0) return "O rendimento base precisa ser maior que zero.";
  if (draft.items.length === 0) return "A ficha precisa de ao menos um ingrediente.";
  for (const [index, item] of draft.items.entries()) {
    if (!item.inputSku.trim()) return "Escolha o insumo da linha " + String(index + 1) + ".";
    const quantity = numberOrNull(item.quantity);
    if (quantity === null || Number.isNaN(quantity) || quantity <= 0) {
      return "A quantidade da linha " + String(index + 1) + " precisa ser maior que zero.";
    }
    const factor = numberOrNull(item.usableFactor || "1");
    if (factor === null || Number.isNaN(factor) || factor <= 0 || factor > 1) {
      return "O aproveitamento da linha " + String(index + 1) + " precisa estar entre 0 e 1.";
    }
  }
  const maxStarted = integerOrNull(draft.maxStartedMinutes);
  if (maxStarted !== null && (Number.isNaN(maxStarted) || maxStarted < 1 || maxStarted > 10080)) {
    return "O tempo máximo precisa ser um número inteiro entre 1 e 10.080 minutos.";
  }
  const capacity = numberOrNull(draft.capacityPerDay);
  if (capacity !== null && (Number.isNaN(capacity) || capacity <= 0)) {
    return "A capacidade precisa ser maior que zero.";
  }
  const shelfLife = integerOrNull(draft.shelfLifeDays);
  if (shelfLife !== null && (Number.isNaN(shelfLife) || shelfLife < 0 || shelfLife > 3650)) {
    return "A validade precisa ser um número inteiro entre 0 e 3.650 dias.";
  }
  if (draft.shelfLifeReviewed && shelfLife === null) {
    return "Informe a validade antes de confirmar a revisão.";
  }
  return "";
}

/** O corpo da API a partir do rascunho; o chamador já validou com sheetDraftError. */
export function sheetPayloadFromDraft(
  draft: SheetDraft,
  previousSteps: readonly (RecipeStepInput | RecipeStepProjection)[] = [],
  expectedRevision?: string,
): RecipeSheetPayload {
  const items: RecipeSheetItemPayload[] = draft.items.map((item, index) => ({
    input_sku: item.inputSku.trim(),
    quantity: item.quantity.trim().replace(",", "."),
    unit: item.unit,
    usable_factor: (item.usableFactor.trim() || "1").replace(",", "."),
    sort_order: index,
    is_optional: item.isOptional,
    note: item.note.trim(),
  }));
  const maxStarted = integerOrNull(draft.maxStartedMinutes);
  const capacity = numberOrNull(draft.capacityPerDay);
  const shelfLife = integerOrNull(draft.shelfLifeDays);
  return {
    name: draft.name.trim(),
    ...(draft.ref.trim() ? { ref: draft.ref.trim() } : {}),
    output_sku: draft.outputSku.trim().toUpperCase(),
    batch_size: draft.batchSize.trim().replace(",", "."),
    is_active: draft.isActive,
    steps: stepsFromText(draft.stepsText, previousSteps),
    items,
    ...(expectedRevision ? { expectedRevision } : {}),
    maxStartedMinutes: maxStarted,
    capacityPerDay: capacity === null ? null : String(capacity),
    requiresBatchTracking: draft.requiresBatchTracking,
    shelfLifeDays: shelfLife,
    shelfLifeReviewed: draft.shelfLifeReviewed,
    productionLifecycle: draft.productionLifecycle,
    productionMode: draft.productionMode,
  };
}

// ── Consulta da lista ───────────────────────────────────────────────────────

export function sheetQuery(
  term: string,
  active: string,
  sort: string,
  page = 1,
  pageSize = 48,
  mode = "",
): Record<string, string> {
  const query: Record<string, string> = {};
  const wantedMode = productionModeQuery(mode);
  if (wantedMode) query.mode = wantedMode;
  const q = term.trim();
  if (q) query.q = q;
  if (active && active !== SHEET_ALL_FILTER) query.active = active;
  if (sort && sort !== "updated") query.sort = sort;
  if (page > 1) query.page = String(page);
  if (pageSize && pageSize !== 48) query.page_size = String(pageSize);
  return query;
}

/** Unidade do rendimento por extenso, para o rótulo do campo. */
export function outputUnitLabel(unit: string): string {
  if (!unit) return "unidade não declarada";
  return unit;
}
