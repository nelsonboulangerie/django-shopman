// Multi-select shaping (spec §2.2, Shopify v11) — pure functions that turn the
// screen-state line selection into the batch affordances the cart toolbar shows.
// A seleção é estado de tela (um conjunto de `line_id`s), e é a MESMA chave que
// fire/unfire mandam ao servidor em `line_ids[]` (Arc 4).
//
// ⚠️ Já foi um conjunto de SKUs, e com duas linhas do mesmo produto na comanda
// isso deixava de ser seleção: marcar o segundo chá marcava os dois, e o lote
// agia sobre a linha errada. No policy here — only derivation from the cart
// items + the selected set.
import type { POSCartItem } from "~/types/pos";

/**
 * ITENS, não linhas — a grandeza que o PDV inteiro fala.
 *
 * Três croissants numa linha e um café noutra são QUATRO itens. A cozinha
 * (`kitchen.ts`), o resumo do pagamento, o quadro de comandas e a tela virada
 * para o cliente já contam assim; o carrinho contava linha, e o operador
 * conferia em voz alta pelo número errado com o cliente lendo o certo.
 */
export function countUnits(items: readonly POSCartItem[]): number {
  return items.reduce((sum, item) => sum + (item.qty || 0), 0);
}

/** As linhas escolhidas, na ordem da comanda. */
export function selectedItems(items: POSCartItem[], selected: ReadonlySet<string>): POSCartItem[] {
  return items.filter((item) => selected.has(item.line_id));
}

/** Selected lines not yet fired → can be sent to the kitchen. */
export function firableLineIds(items: POSCartItem[], selected: ReadonlySet<string>): string[] {
  return selectedItems(items, selected)
    .filter((item) => !item.fired)
    .map((item) => item.line_id);
}

/** Selected lines already fired → can be unfired. */
export function unfirableLineIds(items: POSCartItem[], selected: ReadonlySet<string>): string[] {
  return selectedItems(items, selected)
    .filter((item) => item.fired)
    .map((item) => item.line_id);
}

export interface SelectionView {
  /** Quantas LINHAS estão marcadas. Grandeza interna — decide se a barra de
   *  lote existe e quantos `line_id`s viajam. ⚠️ NUNCA vai para a tela como
   *  "itens": três croissants numa linha são três itens, e o resto do app
   *  (cozinha, pagamento, quadro de comandas, tela do cliente) já conta assim. */
  count: number;
  /** Quantos ITENS estão marcados — Σ qty. É o número que a tela mostra. */
  units: number;
  lineIds: string[];
  firableLineIds: string[];
  unfirableLineIds: string[];
  canFire: boolean;
  canUnfire: boolean;
}

/** Shape the batch toolbar from the current selection (pure). */
export function selectionView(items: POSCartItem[], selected: ReadonlySet<string>): SelectionView {
  const chosen = selectedItems(items, selected);
  const fire = firableLineIds(items, selected);
  const unfire = unfirableLineIds(items, selected);
  return {
    count: chosen.length,
    units: countUnits(chosen),
    lineIds: chosen.map((item) => item.line_id),
    firableLineIds: fire,
    unfirableLineIds: unfire,
    canFire: fire.length > 0,
    canUnfire: unfire.length > 0,
  };
}

/** Toggle a line in a selection set, returning a NEW set (reactive-friendly). */
export function toggleSelected(selected: ReadonlySet<string>, lineId: string): Set<string> {
  const next = new Set(selected);
  if (next.has(lineId)) next.delete(lineId);
  else next.add(lineId);
  return next;
}

/** Drop selected lines no longer present in the cart (keeps selection consistent). */
export function pruneSelection(selected: ReadonlySet<string>, items: POSCartItem[]): Set<string> {
  const present = new Set(items.map((item) => item.line_id));
  const next = new Set<string>();
  selected.forEach((lineId) => {
    if (present.has(lineId)) next.add(lineId);
  });
  return next;
}
