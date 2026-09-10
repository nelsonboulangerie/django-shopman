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
  count: number;
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
