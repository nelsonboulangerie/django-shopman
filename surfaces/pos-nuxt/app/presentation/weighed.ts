// Presentation — venda por peso (queijo fracionado, pesado e etiquetado à mão).
//
// O operador digita o VALOR da etiqueta e a tela deriva o peso pelo preço do quilo
// do catálogo (o mesmo preço do produto: com unidade kg ele É o preço do quilo).
// Com balança no balcão a loja liga a entrada pelo PESO
// (`POSProjection.weighed_weight_entry`); desligada, a opção nem aparece. É a
// MESMA conta do servidor (`shop/services/weighed_sale.py`), repetida aqui só
// para a prévia e a confirmação; quem decide o peso é o servidor.
//
// ⚠️ Nada aqui vira preço. O valor da etiqueta vira PESO (a quantidade da linha)
// e o preço continua o do quilo, do catálogo.

import type { POSCartItem, POSProductProjection, POSWeighedEntry } from "~/types/pos";
import { formatBRL } from "../../../operator-kit/app/utils/money";

/** `label`: valor da etiqueta (o padrão) · `weight`: peso (só com a balança ligada). */
export type WeighedEntryKind = "label" | "weight";

/** Teto de uma peça no balcão — o mesmo `MAX_WEIGHT_G` do servidor. */
export const MAX_WEIGHT_G = 20_000;

/** `round_half_up(g × p / 1000)` em inteiros — o `monetary_mult` do kernel. */
export function totalForGrams(weightG: number, pricePerKgQ: number): number {
  if (weightG <= 0 || pricePerKgQ <= 0) return 0;
  return Math.floor((weightG * pricePerKgQ + 500) / 1000);
}

/** O MAIOR peso, em gramas, cujo valor não passa do valor da etiqueta.
 *  Quando a balança usou o mesmo preço do quilo, devolve exatamente o peso dela. */
export function gramsForLabel(labelQ: number, pricePerKgQ: number): number {
  if (labelQ <= 0 || pricePerKgQ <= 0) return 0;
  return Math.floor((labelQ * 1000 + 499) / pricePerKgQ);
}

/** `312` → `"0,312 kg"` — a grafia da etiqueta. */
export function kgDisplay(weightG: number): string {
  return `${(weightG / 1000).toFixed(3).replace(".", ",")} kg`;
}

/** `"0,312"` (kg, vírgula ou ponto) → 312 g. 0 quando não é um peso. */
export function parseKgToGrams(raw: string): number {
  const text = String(raw || "").trim().replace(",", ".");
  if (!/^\d*(\.\d{0,3})?$/.test(text) || text === "" || text === ".") return 0;
  return Math.round(Number.parseFloat(text) * 1000);
}

/** `"28,05"` (reais) → 2805. 0 quando não é um valor. */
export function parseMoneyToQ(raw: string): number {
  const text = String(raw || "").trim().replace(",", ".");
  if (!/^\d*(\.\d{0,2})?$/.test(text) || text === "" || text === ".") return 0;
  return Math.round(Number.parseFloat(text) * 100);
}

/**
 * Uma tecla no campo do diálogo (teclado físico ou o da tela). Vírgula uma vez só;
 * casas decimais no máximo 2 (reais) ou 3 (quilos). Devolve o buffer novo.
 */
export function editWeighedBuffer(buffer: string, key: string, field: "money" | "kg"): string {
  const places = field === "money" ? 2 : 3;
  if (key === "Backspace") return buffer.slice(0, -1);
  if (key === "," || key === ".") {
    if (buffer.includes(",")) return buffer;
    return `${buffer || "0"},`;
  }
  if (!/^[0-9]$/.test(key)) return buffer;
  const [whole = "", decimals] = buffer.split(",");
  if (decimals !== undefined) {
    if (decimals.length >= places) return buffer;
    return `${buffer}${key}`;
  }
  if (whole.length >= 5) return buffer;
  return whole === "0" ? key : `${buffer}${key}`;
}

/** O que o campo MOSTRA: o valor digitado, ou o zero de partida ("0,00"/"0,000"). */
export function bufferDisplay(buffer: string, field: "money" | "kg"): string {
  if (buffer) return buffer;
  return field === "money" ? "0,00" : "0,000";
}

export interface WeighedPreview {
  ok: boolean;
  /** Frase de erro para o operador, quando `ok` é falso e há algo digitado. */
  error: string;
  weightG: number;
  totalQ: number;
  labelQ: number | null;
  /** Quanto a linha ficou ABAIXO da etiqueta (a balança usou outro preço do quilo). */
  gapQ: number;
  /** O aviso da diferença, quando existe. */
  gapNote: string;
}

/** A prévia — o que vai para o carrinho se o operador confirmar. Com o campo
 *  vazio (ou zero) não há o que confirmar: `ok` é falso e o botão fica bloqueado. */
export function weighedPreview(input: {
  kind: WeighedEntryKind;
  buffer: string;
  pricePerKgQ: number;
}): WeighedPreview {
  const empty: WeighedPreview = { ok: false, error: "", weightG: 0, totalQ: 0, labelQ: null, gapQ: 0, gapNote: "" };
  if (input.pricePerKgQ <= 0) {
    return { ...empty, error: "Sem preço do quilo no cadastro: este item não pode ser vendido." };
  }
  if (input.kind === "label") {
    const labelQ = parseMoneyToQ(input.buffer);
    if (labelQ <= 0) return empty;
    const weightG = gramsForLabel(labelQ, input.pricePerKgQ);
    if (weightG <= 0) return { ...empty, error: `${formatBRL(labelQ)} não chega a 1 g. Confira o valor da etiqueta.` };
    if (weightG > MAX_WEIGHT_G) return { ...empty, error: "Passa de 20 kg por peça. Confira o valor da etiqueta." };
    const totalQ = totalForGrams(weightG, input.pricePerKgQ);
    const gapQ = Math.max(0, labelQ - totalQ);
    return {
      ok: true,
      error: "",
      weightG,
      totalQ,
      labelQ,
      gapQ,
      gapNote: gapQ > 0
        ? `A etiqueta diz ${formatBRL(labelQ)}; pelo preço do quilo cadastrado, ${kgDisplay(weightG)} valem ${formatBRL(totalQ)}. Cobramos ${formatBRL(totalQ)} — confira o preço do quilo na balança.`
        : "",
    };
  }
  const weightG = parseKgToGrams(input.buffer);
  if (weightG <= 0) return empty;
  if (weightG > MAX_WEIGHT_G) return { ...empty, error: "Passa de 20 kg por peça. Digite o peso em quilos: 0,312." };
  return { ok: true, error: "", weightG, totalQ: totalForGrams(weightG, input.pricePerKgQ), labelQ: null, gapQ: 0, gapNote: "" };
}

/** O registro que a linha do carrinho leva ao servidor. */
export function weighedEntryFor(kind: WeighedEntryKind, preview: WeighedPreview): POSWeighedEntry {
  if (kind === "weight") return { entry: "weight", weight_g: preview.weightG };
  return { entry: "label", label_q: preview.labelQ ?? 0, weight_g: preview.weightG };
}

/** O que o intent manda: só o que o operador digitou. O peso da etiqueta o servidor recalcula. */
export function weighedIntent(entry: POSWeighedEntry): Record<string, unknown> {
  if (entry.entry === "label") return { entry: "label", label_q: entry.label_q };
  return { entry: "weight", weight_g: entry.weight_g };
}

export function isWeighedLine(item: Pick<POSCartItem, "weighed">): boolean {
  return Boolean(item.weighed && item.weighed.weight_g > 0);
}

/** Produto que não pode entrar no pedido: sem preço no catálogo (nenhum canal
 *  vende preço zero) ou esgotado. "" quando vende. */
export function productBlockedLabel(
  product: Pick<POSProductProjection, "price_q" | "sold_out" | "sold_out_reason">,
): string {
  if (!(product.price_q > 0)) return "Sem preço";
  if (product.sold_out) return product.sold_out_reason || "Esgotado";
  return "";
}

/**
 * Valor de uma linha a um preço por unidade: `preço × qty` na venda por unidade,
 * `peso × preço do quilo` (meio para cima, como o kernel) na pesada. Multiplicar
 * `price_q × 0.312` na tela dava fração de centavo.
 */
export function lineAmountQ(unitQ: number, item: Pick<POSCartItem, "qty" | "weighed">): number {
  if (item.weighed && item.weighed.weight_g > 0) return totalForGrams(item.weighed.weight_g, unitQ);
  return unitQ * item.qty;
}

/** Quantos ITENS a linha conta: a peça pesada é UM item, não 0,312. */
export function lineUnits(item: Pick<POSCartItem, "qty" | "weighed">): number {
  return isWeighedLine(item) ? 1 : item.qty || 0;
}

/** O rótulo da quantidade nas listas: "0,312 kg" na pesada, "2×" na unitária. */
export function lineQtyLabel(item: Pick<POSCartItem, "qty" | "weighed">): string {
  return item.weighed && item.weighed.weight_g > 0 ? kgDisplay(item.weighed.weight_g) : `${item.qty}×`;
}

/** A quantidade como o operador lê: "0,312 kg" na pesada, "2" na unitária. */
export function lineQtyDisplay(item: Pick<POSCartItem, "qty" | "weighed">): string {
  return item.weighed && item.weighed.weight_g > 0 ? kgDisplay(item.weighed.weight_g) : String(item.qty);
}
