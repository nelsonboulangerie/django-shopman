// A LINHA QUE JÁ ESTÁ NA COZINHA e muda na conta (WP-PDV-COLUNA-COMANDA).
//
// Um lugar só para o que acontece com a cozinha quando a conta muda numa linha enviada,
// para a decisão pendente do dono plugar aqui sem caçar a tela:
//
// · MAIS (+ ou dígito maior): a unidade nova vai numa linha NOVA, a enviar (o mesmo que o
//   produto lançado pela grade já faz). Decidido; não depende da pergunta 5.
// · OBSERVAÇÃO nova: oferece "Reenviar com a observação" (cancelar e enviar de novo, o
//   que o servidor já faz), só enquanto a cozinha ainda pode cancelar.
// · MENOS ou REMOVER (pergunta 5 do estudo, PENDENTE): hoje só avisa, como sempre foi.
//   Quando o dono responder, `FIRED_LINE_SHRINK` vira "ask" e a confirmação de remover
//   (e o − abaixo do que a cozinha recebeu) pergunta "só da conta" ou "da conta e da
//   cozinha". O ponto de leitura é `firedLineShrinkPolicy()` no `PosCartPanel`.
import type { POSCartItem } from "~/types/pos";

export type FiredLineShrinkPolicy = "warn" | "ask";

/** Pergunta 5, pendente (10/10/2026): "warn" mantém o comportamento de hoje. */
export const FIRED_LINE_SHRINK: FiredLineShrinkPolicy = "warn";

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

/** A observação mudou numa linha que a cozinha ainda pode cancelar: oferecer reenviar. */
export function offersResendWithNote(args: { fired: boolean; cancellable: boolean; before: string; after: string }): boolean {
  return args.fired && args.cancellable && args.before.trim() !== args.after.trim() && args.after.trim().length > 0;
}
