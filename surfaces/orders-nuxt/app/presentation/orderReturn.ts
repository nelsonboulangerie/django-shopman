// Registrar devolução (WP-G12, decisão 2 do dono, 17/11/2026): a prévia que o
// servidor monta (`GET orders/<ref>/return/preview/`) e as contas puras do diálogo.
//
// O servidor decide o que pode voltar (`returnable_qty`), o preço pago de cada
// unidade (`unit_refund_q`) e para onde o dinheiro vai (`money_destination`). A
// tela só soma o que o Gerente escolheu, pela MESMA regra do `initiate_return`
// (preço pago × quantidade, centavo truncado), para dizer o valor ANTES de
// confirmar.

import type { Action } from "~/generated/ordersContract";
import { formatBRL } from "../../../operator-kit/app/utils/money";

export interface ReturnLine {
  line_id: string;
  sku: string;
  name: string;
  qty: string;
  returned_qty: string;
  returnable_qty: string;
  unit_refund_q: number;
  unit_refund_display: string;
  by_weight: boolean;
}

export interface OrderReturnPreview {
  ref: string;
  allowed: boolean;
  block_reason: string;
  lines: ReturnLine[];
  money_returns: boolean;
  money_destination: string;
  managers: { username: string; name: string }[];
  action: Action;
}

/** Quanto de cada linha volta, pelo `line_id`. */
export type ReturnQuantities = Record<string, number>;

/** Milésimos, para o kg não errar no ponto flutuante (0,35 × 600). */
function milli(qty: number): number {
  return Math.round(qty * 1000);
}

/** A quantidade, sem lixo de ponto flutuante e dentro do que ainda pode voltar. */
export function clampReturnQty(line: ReturnLine, qty: number | null | undefined): number {
  const max = Number(line.returnable_qty) || 0;
  const value = Number(qty) || 0;
  if (value <= 0) return 0;
  const clamped = Math.min(value, max);
  return line.by_weight ? milli(clamped) / 1000 : Math.floor(clamped);
}

/** O valor de uma linha: preço pago × quantidade, centavo truncado (o mesmo do servidor). */
export function lineRefundQ(line: ReturnLine, qty: number): number {
  return Math.trunc((line.unit_refund_q * milli(qty)) / 1000);
}

export function returnRefundQ(lines: ReturnLine[], qtys: ReturnQuantities): number {
  return lines.reduce(
    (sum, line) => sum + lineRefundQ(line, clampReturnQty(line, qtys[line.line_id])),
    0,
  );
}

/** O corpo do comando: só o que volta, em texto decimal ("2", "0.35"). */
export function returnSubmitItems(
  lines: ReturnLine[],
  qtys: ReturnQuantities,
): { line_id: string; qty: string }[] {
  return lines
    .map((line) => ({ line_id: line.line_id, qty: clampReturnQty(line, qtys[line.line_id]) }))
    .filter((item) => item.qty > 0)
    .map((item) => ({ line_id: item.line_id, qty: String(item.qty) }));
}

/**
 * A frase do dinheiro, dita antes de confirmar: "R$ 12,00 serão estornados ao Pix
 * do cliente." Sem nada escolhido, pede a escolha; sem dinheiro recebido, diz
 * que nenhum valor volta (o produto ainda volta ao estoque).
 */
export function returnMoneySentence(preview: OrderReturnPreview, totalQ: number): string {
  if (totalQ <= 0) return "Escolha o que volta para ver o valor.";
  if (!preview.money_returns)
    return "Nada foi cobrado deste pedido: nenhum dinheiro volta. O produto volta ao estoque.";
  return `${formatBRL(totalQ)} ${preview.money_destination}`;
}

/** "3 de 3" ou "1 de 3 (2 já voltaram)": o que a linha ainda deixa devolver. */
export function returnLineHint(line: ReturnLine): string {
  const unit = line.by_weight ? " kg" : "";
  const returned = Number(line.returned_qty) || 0;
  const base = `Pode voltar ${formatQty(line.returnable_qty)}${unit} de ${formatQty(line.qty)}${unit}`;
  return returned > 0 ? `${base} (${formatQty(line.returned_qty)}${unit} já voltou)` : base;
}

function formatQty(text: string): string {
  return String(text).replace(".", ",");
}
