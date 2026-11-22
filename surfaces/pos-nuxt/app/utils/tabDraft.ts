/**
 * O que foi lançado na comanda e ainda não chegou ao servidor, guardado no dispositivo.
 *
 * Com a sessão caída, o salvamento automático da comanda volta 401, a casca sobe o
 * login no lugar da venda e o login recarrega a página: o que o operador lançou
 * depois do último salvamento sumia (achado no #3308, medido na pilha viva). Agora
 * cada mudança ainda não salva fica aqui, no `localStorage` da estação, e sai quando
 * o servidor aceita a gravação. Depois de entrar de novo, a comanda reabre e o
 * rascunho volta por cima dela, se a comanda não mudou no servidor nesse meio tempo.
 *
 * Os campos são os que o salvamento automático observa (`usePosSale`): itens,
 * cliente, recebimento e entrega, observações. Nada de pagamento nem assinatura do
 * gerente. Uma comanda por vez: a tela tem uma comanda aberta.
 */

import type { POSCartItem, StructuredAddressProjection } from "~/types/pos";

export const TAB_DRAFT_STORAGE_KEY = "shopman:pos:unsaved-tab";

/** Rascunho mais velho que isto é de outro turno: não volta sozinho. */
export const TAB_DRAFT_MAX_AGE_MS = 12 * 60 * 60 * 1000;

export interface TabDraftFields {
  items: POSCartItem[];
  customerName: string;
  customerRef: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  salesMode: "counter" | "order";
  fulfillmentConfirmed: boolean;
  fulfillmentType: "pickup" | "delivery";
  deliveryAddress: string;
  deliveryAddressStructured: StructuredAddressProjection;
  deliveryStreetNumber: string;
  deliveryNeighborhood: string;
  deliveryComplement: string;
  deliveryInstructions: string;
  deliveryDate: string;
  deliveryTimeSlot: string;
  deliveryFeeOverrideInput: string;
  deliveryFeeOverride: boolean;
  orderNotes: string;
}

export const TAB_DRAFT_FIELDS: ReadonlyArray<keyof TabDraftFields> = [
  "items",
  "customerName",
  "customerRef",
  "customerPhone",
  "customerTaxId",
  "customerEmail",
  "salesMode",
  "fulfillmentConfirmed",
  "fulfillmentType",
  "deliveryAddress",
  "deliveryAddressStructured",
  "deliveryStreetNumber",
  "deliveryNeighborhood",
  "deliveryComplement",
  "deliveryInstructions",
  "deliveryDate",
  "deliveryTimeSlot",
  "deliveryFeeOverrideInput",
  "deliveryFeeOverride",
  "orderNotes",
];

export interface TabDraft {
  tabRef: string;
  tabSessionKey: string;
  /**
   * Os itens que o servidor tinha quando o rascunho começou (`tabItemsKey`). É contra
   * eles que a volta confere se outra estação mexeu na comanda. Não é a revisão:
   * abrir a comanda grava a sessão e muda a revisão a cada abertura (medido na
   * pilha: v1:4 → v1:5 entre duas aberturas seguidas).
   */
  baseItemsKey: string;
  /** Quem lançava: o rascunho volta para a mesma pessoa, não para quem entrar. */
  operatorId: string;
  /** ISO de quando foi guardado. */
  savedAt: string;
  fields: TabDraftFields;
}

/** Só os campos do rascunho, copiados (o `cart` é reativo; o disco guarda o valor). */
export function pickTabDraftFields(cart: TabDraftFields): TabDraftFields {
  const picked = {} as Record<string, unknown>;
  for (const field of TAB_DRAFT_FIELDS) picked[field] = cart[field];
  return JSON.parse(JSON.stringify(picked)) as TabDraftFields;
}

function isTabDraft(value: unknown): value is TabDraft {
  if (!value || typeof value !== "object") return false;
  const draft = value as Record<string, unknown>;
  const fields = draft.fields as Record<string, unknown> | undefined;
  return typeof draft.tabRef === "string" && draft.tabRef !== ""
    && typeof draft.tabSessionKey === "string" && draft.tabSessionKey !== ""
    && typeof draft.baseItemsKey === "string"
    && typeof draft.operatorId === "string"
    && typeof draft.savedAt === "string" && !Number.isNaN(Date.parse(draft.savedAt))
    && Boolean(fields) && Array.isArray(fields?.items);
}

/** O rascunho guardado, se ainda vale (do turno de agora); `null` senão. */
export function readTabDraft(now: number = Date.now()): TabDraft | null {
  try {
    const raw = globalThis.localStorage?.getItem(TAB_DRAFT_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!isTabDraft(parsed)) return null;
    if (now - Date.parse(parsed.savedAt) > TAB_DRAFT_MAX_AGE_MS) return null;
    return parsed;
  } catch {
    // silêncio-deliberado: sem storage legível não há rascunho a devolver; a
    // comanda abre como o servidor a tem, como sempre abriu.
    return null;
  }
}

export function writeTabDraft(draft: TabDraft): void {
  try {
    globalThis.localStorage?.setItem(TAB_DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch {
    // silêncio-deliberado: storage cheio ou recusado (modo privado). A venda segue
    // na tela e o salvamento automático segue tentando; só a volta depois de uma
    // sessão caída fica sem o rascunho.
  }
}

export function clearTabDraft(): void {
  try {
    globalThis.localStorage?.removeItem(TAB_DRAFT_STORAGE_KEY);
  } catch {
    // silêncio-deliberado: idem, sem storage não há o que apagar.
  }
}

/** A identidade dos itens de uma comanda: linha, SKU, quantidade e observação. */
export function tabItemsKey(items: POSCartItem[] | null | undefined): string {
  return JSON.stringify((items || []).map((item) => [item.line_id || "", item.sku, item.qty, item.notes || ""]));
}

/** O rascunho já é o que o servidor tem (a gravação chegou, a resposta não): nada a reaplicar. */
export function draftMatchesServer(draft: TabDraft, serverItems: POSCartItem[]): boolean {
  return tabItemsKey(draft.fields.items) === tabItemsKey(serverItems);
}
