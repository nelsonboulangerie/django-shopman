/**
 * O que está encomendado de um lote, em uma frase: "7 un. encomendadas: 4 pedidos".
 *
 * Lê o prometido do produto na data do lote, pela régua das reservas (WP-F08/F10).
 * Sem encomenda, `null`: a tela diz que nenhuma encomenda depende do lote, em vez de
 * um zero.
 */
import { orderedLabel } from "./production";
import type { PromisedOrderProjection } from "~/types/production";

export interface LotStakes {
  headline: string;
  units: number;
  orders: number;
}

function parseQty(value: string): number {
  return parseFloat(String(value ?? "").replace(",", ".")) || 0;
}

export function lotStakes(
  orders: readonly PromisedOrderProjection[],
  unit?: string,
): LotStakes | null {
  const count = new Set(orders.map((order) => order.ref)).size;
  if (!count) return null;
  const units = orders.reduce((total, order) => total + parseQty(order.qty), 0);
  const noun = count === 1 ? "1 pedido" : `${count} pedidos`;
  return { headline: `${orderedLabel(units, unit)}: ${noun}`, units, orders: count };
}
