// A LINHA QUE JÁ ESTÁ NA COZINHA e muda na conta (WP-PDV-COLUNA-COMANDA).
//
// Um lugar só para o que acontece com a cozinha quando a conta muda numa linha enviada:
//
// · MAIS (+ ou dígito maior): a unidade nova vai numa linha NOVA, a enviar (o mesmo que o
//   produto lançado pela grade já faz).
// · OBSERVAÇÃO nova: oferece "Reenviar com a observação" (cancelar e enviar de novo, o
//   que o servidor já faz), só enquanto a cozinha ainda pode cancelar.
// · MENOS ou REMOVER (decisão do dono, 10/10/2026): cancela na cozinha AUTOMATICAMENTE,
//   pelo caminho canônico do servidor (o "cancelar envio", `unfire_tab`; diminuir manda
//   só a diferença em `quantities`). Se o item já está pronto, sai só da conta, e a
//   tela diz isso. Jamais em silêncio: a coluna diz em palavra o que a cozinha recebeu.
import type { POSCartItem } from "~/types/pos";

export type FiredLineShrinkPolicy = "cancel";

/** Decisão 5 do dono (10/10/2026): linha enviada que sai ou diminui cancela na cozinha. */
export const FIRED_LINE_SHRINK: FiredLineShrinkPolicy = "cancel";

export function firedLineShrinkPolicy(): FiredLineShrinkPolicy {
  return FIRED_LINE_SHRINK;
}

/**
 * Quantas unidades novas vão numa linha nova quando a conta pede `nextQty` numa linha
 * que já foi à cozinha. Zero quando não é aumento (ou a linha não foi enviada).
 */
export function firedLineIncrease(item: Pick<POSCartItem, "fired" | "qty" | "weighed">, nextQty: number): number {
  if (!item.fired || item.weighed) return 0;
  return Math.max(0, Math.floor(nextQty) - item.qty);
}

/** O que a cozinha recebe quando a conta tira unidades de uma linha enviada. */
export type FiredLineShrink =
  /** Cancelar na cozinha `units` (todas, quando `whole`). */
  | { kind: "cancel"; units: number; whole: boolean }
  /** O item já está pronto (ou a cozinha não aceita mais cancelar): sai só da conta. */
  | { kind: "account-only" }
  /** Nada na cozinha muda (a linha não foi enviada, ou ainda sobra o que ela recebeu). */
  | { kind: "none" };

/**
 * A conta passa de `item.qty` para `nextQty` (zero = remover). A cozinha recebeu
 * `fired_qty` (ou a quantidade da linha, quando o servidor não guardou o número).
 * `cancellable`: a cozinha ainda pode cancelar (ticket não pronto e o servidor oferece
 * o "cancelar envio").
 */
export function firedLineShrink(
  item: Pick<POSCartItem, "fired" | "qty" | "fired_qty" | "weighed">,
  nextQty: number,
  cancellable: boolean,
): FiredLineShrink {
  if (!item.fired) return { kind: "none" };
  const sent = item.weighed ? 1 : (item.fired_qty ?? item.qty);
  const next = Math.max(0, item.weighed ? (nextQty > 0 ? 1 : 0) : nextQty);
  const units = sent - next;
  if (units <= 0) return { kind: "none" };
  if (!cancellable) return { kind: "account-only" };
  return { kind: "cancel", units, whole: next === 0 };
}

/** A frase da coluna para o que a cozinha recebeu (ou não). */
export function firedLineShrinkMessage(
  name: string,
  shrink: FiredLineShrink,
  result: "done" | "failed",
): string {
  if (shrink.kind === "account-only") return `${name} já estava pronto: saiu só da conta.`;
  if (shrink.kind !== "cancel") return "";
  if (result === "failed") {
    return `${name} saiu da conta, mas a cozinha não recebeu o cancelamento: avise de voz.`;
  }
  if (shrink.whole) return `${name} removido e cancelado na cozinha.`;
  return shrink.units === 1 ? `1 ${name} cancelado na cozinha.` : `${shrink.units} ${name} cancelados na cozinha.`;
}

/** O fato curto que fica na LINHA depois de cancelar parte dela ("2 cancelados na cozinha"). */
export function cancelledFact(units: number): string {
  return units === 1 ? "1 cancelado na cozinha" : `${units} cancelados na cozinha`;
}

/** A observação mudou numa linha que a cozinha ainda pode cancelar: oferecer reenviar. */
export function offersResendWithNote(args: { fired: boolean; cancellable: boolean; before: string; after: string }): boolean {
  return args.fired && args.cancellable && args.before.trim() !== args.after.trim() && args.after.trim().length > 0;
}
