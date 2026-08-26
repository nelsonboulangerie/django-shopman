// Presentation — tela de resultado pós-venda.
//
// Transforms puros da tela que sucede o Validar: o título (caloroso quando há
// cliente vinculado), o troco congelado e a decisão de avanço (auto-avanço
// curto e Enter). Zero política de dinheiro: o troco chega CONGELADO do
// fechamento (`result.changeQ`, capturado pelo usePosSale) — aqui só se decide
// como a tela se comporta com ele.

import type { PaymentProofView } from "~/presentation/payment";
import type { PosReceiptSnapshot } from "~/presentation/receipt";
import { firstName } from "~/presentation/customerDisplay";
import { formatBRL } from "~/utils/posIntent";

export type PixPollStatus = "idle" | "polling" | "paid" | "expired";

/**
 * O resultado congelado da venda fechada — nasce no `submitSale` (usePosSale) e
 * fica de pé enquanto a tela de resultado existe. `changeQ` é o troco capturado
 * no instante do commit (o cart reseta logo depois): uma fonte só para o palco
 * do operador, a tela do cliente e o recibo.
 */
export interface PosSaleResultSnapshot {
  orderRef: string;
  /** Link do pedido no Gestor de Pedidos (orders app). */
  nextUrl: string;
  payment: PaymentProofView | null;
  receipt: PosReceiptSnapshot;
  fiscalExpected: boolean;
  changeQ: number;
  /** O cliente pediu a nota IMPRESSA? Congelado aqui porque o carrinho já
   *  zerou quando a nota autoriza — e é dela que a impressão automática vive. */
  wantsPrintedInvoice: boolean;
}

export interface SaleResultAdvanceInputs {
  /** Troco congelado no fechamento, em centavos. 0 = pagamento exato/digital. */
  changeQ: number;
  payment: PaymentProofView | null;
  pixStatus: PixPollStatus;
}

/** Com cliente vinculado o obrigado é nominal (frase completa, com ponto e
 *  maiúscula); sem, a confirmação seca. */
export function saleResultTitle(customerName: string): string {
  const nome = firstName(customerName);
  return nome ? `Venda concluída. Obrigado, ${nome}!` : "Venda concluída";
}

/** PIX com prova na tela e confirmação ainda não chegada (polling vivo). */
export function pixAwaiting(payment: PaymentProofView | null, pixStatus: PixPollStatus): boolean {
  return Boolean(payment?.isPix && payment?.hasProof) && pixStatus === "polling";
}

/** Troco pronto para exibir; "" quando não há troco. */
export function changeDisplay(changeQ: number): string {
  return changeQ > 0 ? formatBRL(changeQ) : "";
}

export const AUTO_ADVANCE_SECONDS = 5;

/**
 * Auto-avanço para a próxima venda: só quando NADA na tela pede gesto.
 *
 * - Troco a conferir → NUNCA: a tela não some sozinha em cima do dinheiro.
 * - PIX aguardando ou expirado → NUNCA: prova pendente/não resolvida não é
 *   descartada em silêncio (sair exige toque explícito).
 * - `prefers-reduced-motion` → desliga a contagem (a tela espera o toque).
 *
 * Retorna os segundos da contagem, ou 0 = não avança sozinho.
 */
export function autoAdvanceSeconds(
  inputs: SaleResultAdvanceInputs & { reducedMotion: boolean },
): number {
  if (inputs.reducedMotion) return 0;
  if (inputs.changeQ > 0) return 0;
  if (inputs.payment?.isPix && inputs.payment.hasProof && inputs.pixStatus !== "paid") return 0;
  return AUTO_ADVANCE_SECONDS;
}

/**
 * Enter avança? Nunca com troco pendente de confirmação (o Enter que validou a
 * venda não pode engolir a tela do troco) nem com PIX ainda aguardando — nesses
 * dois casos sair é gesto deliberado no CTA (ou F2).
 */
export function enterAdvances(inputs: SaleResultAdvanceInputs): boolean {
  if (inputs.changeQ > 0) return false;
  if (pixAwaiting(inputs.payment, inputs.pixStatus)) return false;
  return true;
}
