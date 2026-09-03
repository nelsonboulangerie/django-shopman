// Presentation — kitchen handoff / fire-to-kitchen (spec §2.5, anti-fraud).
//
// Pure transforms for the progressive fire affordance: which lines are still
// firable vs already `fired`, the unfired count, the fire-button view (label
// from the `fire_tab` Action — never an invented CTA — plus the live delta
// count), and the per-line state that drives the badge + the unfire affordance.
//
// Fire is the named, auditable act (food to the kitchen before payment), so the
// state must be unambiguous: the operator always sees exactly what has gone to
// the kitchen and what is still pending. Firing dispatches only the unfired
// delta (the Core dedups by `fired_line_ids_for_session`, so nothing duplicates);
// unfire cancels a single still-cancellable line. Zero policy — capability and
// per-line `fired` come from the Projection; this module only shapes them.

import type { POSCartItem } from "~/types/pos";
import type { ActionAffordance } from "~/presentation/actions";

/** Lines already sent to the kitchen. */
export function firedCount(items: POSCartItem[]): number {
  return items.filter((item) => item.fired).length;
}

/**
 * Quanto DESTA LINHA ainda não foi para a cozinha.
 *
 * ⚠️ A pergunta não é "esta linha já foi?", é "quanto dela já foi". O PDV tem
 * uma linha por SKU (invariante do servidor), então pedir mais um chá AUMENTA a
 * quantidade de uma linha que talvez já esteja na cozinha. Enquanto isto era um
 * booleano, o segundo chá ficava dentro de uma linha marcada "enviada": o botão
 * dizia "Enviado", o fire deduplicava por `line_id`, e ninguém nunca fazia o
 * segundo chá.
 *
 * `fired_qty` ausente (comanda antiga, payload de outra origem) cai no
 * comportamento anterior — linha marcada como enviada conta como enviada
 * inteira.
 */
export function pendingKitchenQty(item: POSCartItem): number {
  const firedQty = item.fired_qty ?? (item.fired ? item.qty : 0);
  return Math.max(0, item.qty - firedQty);
}

/** Unidades ainda a enviar — o que um fire despacharia agora. */
export function unfiredCount(items: POSCartItem[]): number {
  return items.reduce((total, item) => total + pendingKitchenQty(item), 0);
}

/** Nada mais a enviar (e há ao menos uma linha). */
export function allLinesFired(items: POSCartItem[]): boolean {
  return items.length > 0 && items.every((item) => pendingKitchenQty(item) === 0);
}

export type KitchenLineState = "unfired" | "fired" | "fired_cancellable";

/**
 * Per-line kitchen state. A fired line is cancellable only when the channel
 * offers unfire AND the line carries a server `line_id` to target; otherwise it
 * shows as a non-interactive "in the kitchen" marker.
 *
 * Uma linha que a cozinha já ENCERROU (pronta ou cancelada) deixa de ser
 * cancelável: desfazer o envio de algo que já saiu do fogão não é um gesto de
 * tela, é uma conversa com quem está lá dentro.
 */
export function kitchenLineState(item: POSCartItem, options: { canUnfire: boolean }): KitchenLineState {
  if (!item.fired) return "unfired";
  const settled = item.kitchen_status === "done" || item.kitchen_status === "cancelled";
  return options.canUnfire && Boolean(item.line_id) && !settled ? "fired_cancellable" : "fired";
}

/** O que o selo da linha DIZ, e a cor funcional que ele merece.
 *
 * "Na cozinha" era selo fixo: o ticket virava pronto (ou era cancelado) e o
 * balcão continuava anunciando o estado do minuto do disparo. O texto agora seg
 * o ticket, e só duas situações ganham cor — pronto (verde, é dinheiro na mão do
 * cliente) e cancelado (vermelho, exige ação de quem está no caixa). Em
 * andamento é neutro, como o resto do PDV.
 */
export interface KitchenBadgeView {
  label: string;
  tone: "neutral" | "success" | "destructive" | "warning";
}

/**
 * A cozinha está fazendo MAIS do que a conta cobra?
 *
 * ⚠️ O caminho da diferença NEGATIVA: a linha foi para a cozinha com 3 e o
 * operador baixou para 1 (cliente desistiu, digitou errado). Nada é disparado —
 * até aí certo, ninguém quer duplicar —, só que nada é DESFEITO também: o fogão
 * segue com 3 e a conta cobra 1. Dois pães a menos no caixa e ninguém sabe.
 */
export function kitchenSurplusQty(item: POSCartItem): number {
  const firedQty = item.fired_qty ?? (item.fired ? item.qty : 0);
  return Math.max(0, firedQty - item.qty);
}

export function kitchenBadge(item: POSCartItem): KitchenBadgeView {
  // Linha PELA METADE: parte na cozinha, parte ainda não. Um selo que diz só
  // "Na cozinha" numa linha de 2 com 1 feito é a metade da verdade, e é a
  // metade que faz o operador não pedir o resto.
  const firedQty = item.fired_qty ?? (item.fired ? item.qty : 0);
  if (firedQty > 0 && pendingKitchenQty(item) > 0) {
    return { label: `${firedQty} de ${item.qty} na cozinha`, tone: "neutral" };
  }
  // A COZINHA FAZ MAIS DO QUE A CONTA COBRA. Enquanto isto ficava calado, o
  // selo dizia "Na cozinha" — verdade pela metade, e a metade que não avisa
  // ninguém de que há comida saindo sem cobrança.
  if (kitchenSurplusQty(item) > 0) {
    return { label: `${firedQty} na cozinha · ${item.qty} na conta`, tone: "warning" };
  }
  switch (item.kitchen_status) {
    case "done":
      return { label: "Pronto", tone: "success" };
    case "cancelled":
      return { label: "Cancelado na cozinha", tone: "destructive" };
    case "in_progress":
      return { label: "Preparando", tone: "neutral" };
    default:
      return { label: "Na cozinha", tone: "neutral" };
  }
}

// Estado, não relatório: com tudo disparado o botão está desabilitado, e o que
// ele precisa dizer é o que aconteceu com estes itens — "Enviado". "Tudo na
// cozinha" descrevia o LUGAR onde as coisas estão, que é assunto do KDS.
const ALL_FIRED_LABEL = "Enviado";

export interface FireBarView {
  /** The channel offers fire, the tab is open, and there are lines. */
  visible: boolean;
  /** `fire_tab` Action label, or the all-fired label. A CONTAGEM não entra
   *  aqui: ela é um badge na tela (número em destaque, colado no rótulo), e
   *  "Enviar itens (1)" dizia o mesmo com menos leitura. */
  label: string;
  unfired: number;
  fired: number;
  /** Nothing left to fire, or busy, or the Action is currently disabled. */
  disabled: boolean;
  allFired: boolean;
}

/**
 * The progressive fire button. Visible only when the `fire_tab` Action is
 * present, a tab is open, and the ticket has lines. The label is the Action's
 * own copy (the unfired delta rides along in `unfired`, which the screen shows
 * as a badge); when nothing is left to fire it shows the all-fired state and
 * disables. Honors the Action's `enabled` verbatim.
 */
export function fireBarView(args: {
  items: POSCartItem[];
  affordance: ActionAffordance;
  hasOpenTab: boolean;
  busy: boolean;
}): FireBarView {
  const unfired = unfiredCount(args.items);
  const fired = firedCount(args.items);
  const visible = args.affordance.present && args.hasOpenTab && args.items.length > 0;
  return {
    visible,
    label: unfired ? args.affordance.label : ALL_FIRED_LABEL,
    unfired,
    fired,
    disabled: args.busy || !args.affordance.enabled || unfired === 0,
    allFired: allLinesFired(args.items),
  };
}
