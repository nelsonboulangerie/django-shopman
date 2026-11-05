import type { Material, PurchaseList, PurchaseProjection, ReceiptLine, ReceiptMode, Supplier } from "~/types/purchase";
import { receiptIsBlank } from "~/presentation/purchase";

/**
 * A base de TRABALHO e a página da TABELA são duas coisas.
 *
 * A Base pagina de 30 em 30 para exibir. Receber, custear, comprar, o Painel e o
 * detalhe por link direto trabalham sobre todos os insumos ativos, que o servidor
 * manda à parte (`activeMaterials`). Antes, tudo isso lia a página corrente: só os
 * 30 primeiros em ordem alfabética existiam, e a farinha (página 2) não podia ser
 * recebida (beta 05/11, CMP-01/CMP-03).
 */
export interface PurchaseWorkSet {
  materials: Material[];
  materialPage: PurchaseList<Material>;
  suppliers: Supplier[];
  supplierPage: PurchaseList<Supplier>;
}

function asList<T>(value: T[] | PurchaseList<T>): PurchaseList<T> {
  if (!Array.isArray(value)) return { ...value, items: [...value.items] };
  return { items: [...value], total: value.length, has_next: false, page: 1, page_size: value.length || 30, query: "", order: "name" };
}

export function purchaseWorkSet(next: Pick<PurchaseProjection, "materials" | "suppliers" | "activeMaterials" | "activeSuppliers">): PurchaseWorkSet {
  const materialPage = asList(next.materials);
  const supplierPage = asList(next.suppliers);
  return {
    materials: [...(next.activeMaterials ?? materialPage.items)],
    materialPage,
    suppliers: [...(next.activeSuppliers ?? supplierPage.items)],
    supplierPage,
  };
}

/**
 * O insumo pedido pela URL: na base de trabalho, e na página quando é um
 * arquivado aberto pela própria tabela. Nunca "o primeiro da lista" no lugar.
 */
export function materialBySku<T extends { sku: string }>(sku: string, ...lists: T[][]): T | null {
  for (const list of lists) {
    const found = list.find((item) => item.sku === sku);
    if (found) return found;
  }
  return null;
}

/**
 * O rascunho de recebimento sobrevive a recarga, a queda de rede e à sessão que
 * expira (o login promete que ele foi preservado). Mora no dispositivo, que é a
 * bancada onde a entrega está sendo conferida (beta 05/11, CMP-04).
 */
export const RECEIPT_DRAFT_STORAGE_KEY = "shopman.purchase.receipt-draft";
/** Rascunho mais velho que isto é de outra entrega: não volta. */
export const RECEIPT_DRAFT_MAX_AGE_MS = 12 * 60 * 60 * 1000;

export interface ReceiptDraft {
  mode: ReceiptMode;
  supplierRef: string;
  invoiceInput: string;
  note: string;
  lines: ReceiptLine[];
  invoiceVolumes: number;
  savedAt: number;
}

export function receiptDraftToStore(draft: Omit<ReceiptDraft, "savedAt">, now: number): string | null {
  if (receiptIsBlank(draft.lines, draft.invoiceInput, draft.note)) return null;
  return JSON.stringify({ ...draft, savedAt: now });
}

export function receiptDraftFromStore(raw: string | null | undefined, now: number): ReceiptDraft | null {
  if (!raw) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const draft = parsed as Partial<ReceiptDraft>;
  if (draft.mode !== "invoice" && draft.mode !== "manual") return null;
  if (!Array.isArray(draft.lines)) return null;
  if (typeof draft.savedAt !== "number" || now - draft.savedAt > RECEIPT_DRAFT_MAX_AGE_MS) return null;
  const restored: ReceiptDraft = {
    mode: draft.mode,
    supplierRef: String(draft.supplierRef ?? ""),
    invoiceInput: String(draft.invoiceInput ?? ""),
    note: String(draft.note ?? ""),
    lines: draft.lines as ReceiptLine[],
    invoiceVolumes: Number(draft.invoiceVolumes) || 0,
    savedAt: draft.savedAt,
  };
  return receiptIsBlank(restored.lines, restored.invoiceInput, restored.note) ? null : restored;
}
