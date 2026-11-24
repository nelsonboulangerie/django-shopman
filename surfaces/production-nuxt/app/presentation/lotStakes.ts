/**
 * O que está encomendado de um lote, em uma frase: "7 un. encomendadas: 4 pedidos".
 *
 * Lê só o que o cartão do lote já traz (`order_commitments`). Sem encomenda, `null`:
 * a tela diz que nenhuma encomenda depende do lote, em vez de um zero.
 */
import { formatQtyUnit } from "./production";
import type { OrderCommitmentProjection } from "~/types/production";

export interface LotStakes {
  headline: string;
  units: number;
  orders: number;
}

function parseQty(value: string): number {
  return parseFloat(String(value ?? "").replace(",", ".")) || 0;
}

export function lotStakes(
  commitments: readonly OrderCommitmentProjection[],
  unit?: string,
): LotStakes | null {
  const orders = new Set(commitments.map((commitment) => commitment.ref)).size;
  if (!orders) return null;
  const units = commitments.reduce(
    (total, commitment) => total + parseQty(commitment.qty_required),
    0,
  );
  const quantity = formatQtyUnit(String(units), unit);
  const noun = orders === 1 ? "1 pedido" : `${orders} pedidos`;
  // "un." é feminino (unidades); peso é masculino (quilos, gramas).
  const counted = quantity.endsWith(" un.");
  const adjective = counted
    ? units === 1
      ? "encomendada"
      : "encomendadas"
    : "encomendados";
  return { headline: `${quantity} ${adjective}: ${noun}`, units, orders };
}
