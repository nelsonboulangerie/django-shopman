// Estornar UM pedido (#2727, item 5): a exceção financeira do Gerente. A prévia que o
// servidor monta (`GET orders/<ref>/refund/preview/`) e o que o diálogo mostra dela.
//
// Os valores são de UMA cobrança: o que ela recebeu, o que já voltou dela e o que
// ainda pode voltar. A tela não soma nada. Pedido com mais de uma cobrança (#3134,
// decisão da coordenação em 22/11/2026): o Gerente escolhe qual estornar, vendo o
// valor de cada uma separado, e o total do pedido nunca aparece. O servidor decide se
// o gesto vale agora; a tela só confere o valor digitado contra o disponível que ele
// mandou (o servidor confere de novo, sob o lock).

import type { Action } from "~/generated/ordersContract";
import { formatBRL } from "../../../operator-kit/app/utils/money";
import { moneyInput } from "../../../operator-kit/app/presentation/custody";
import { moneyToQ } from "~/presentation/courierCall";

export const REFUND = "refund";

/** "R$ 25,00" com espaço comum, como o servidor escreve (o `Intl` põe espaço duro). */
function brl(amountQ: number): string {
  return formatBRL(amountQ).replace(/\u00a0/g, " ");
}

/** Uma cobrança na escolha do estorno: os valores DELA, e de mais nenhuma. */
export interface OrderRefundCharge {
  intent_ref: string;
  method_label?: string;
  paid_q?: number;
  paid_display: string;
  /** Vazio quando nada voltou dela ainda. */
  returned_display?: string;
  available_q: number;
  available_display: string;
}

export interface OrderRefundPreview {
  order_ref: string;
  /** Mais de uma cobrança e nenhuma escolhida: só a escolha, sem valor a estornar. */
  choose?: boolean;
  /** "Este pedido tem mais de uma cobrança. Escolha qual estornar." */
  choose_reason?: string;
  /** As cobranças a escolher, cada uma com o valor dela (vazio com uma só). */
  charges?: OrderRefundCharge[];
  /** A cobrança destes valores (a escolhida, ou a única). */
  intent_ref?: string;
  /** "Pix", "Cartão": por onde o dinheiro volta. */
  method_label?: string;
  paid_q?: number;
  paid_display?: string;
  returned_q?: number;
  /** Vazio quando nada voltou ainda. */
  returned_display?: string;
  available_q?: number;
  available_display?: string;
  partial_allowed?: boolean;
  blocked: boolean;
  block_reason: string;
  action: Action | null;
}

/** O que o servidor respondeu à tentativa: o recibo DESTA cobrança. */
export interface OrderRefundReceipt {
  outcome: "refunded" | "refused" | "unconfirmed" | "unrecorded" | string;
  amount_q: number;
  refunded_q: number;
  available_q: number;
  message: string;
}

export interface OrderRefundDialogView {
  blocked: boolean;
  blockReason: string;
  /** Mais de uma cobrança e nenhuma escolhida: a tela pede a escolha e não confirma. */
  choosing: boolean;
  chooseLine: string;
  /** "Pago neste pedido: R$ 30,00 (Pix)". */
  paidLine: string;
  /** "Já estornado: R$ 5,00", ou vazio. */
  returnedLine: string;
  /** "Disponível para estorno: R$ 25,00". */
  availableLine: string;
  partialAllowed: boolean;
  /** O valor digitado, em centavos; `null` quando ilegível ou vazio. */
  amountQ: number | null;
  amountError: string;
  confirmLabel: string;
  canConfirm: boolean;
}

/** O campo do valor já vem com o disponível inteiro: estornar tudo é o padrão. */
export function initialRefundAmount(preview: OrderRefundPreview | null): string {
  return preview?.available_q ? moneyInput(preview.available_q) : "";
}

function amountError(amountQ: number | null, availableQ: number): string {
  if (amountQ === null || amountQ <= 0) return "Informe quanto estornar.";
  if (amountQ > availableQ) return `Valor acima do disponível (${brl(availableQ)}).`;
  return "";
}

/**
 * O diálogo inteiro a partir da prévia, do valor digitado e da segunda confirmação.
 * Bloqueado, mostra só o motivo do servidor e não confirma.
 */
export function refundDialogView(
  preview: OrderRefundPreview,
  options: { amount: string; confirmed: boolean; busy?: boolean },
): OrderRefundDialogView {
  const blocked = preview.blocked || !preview.action;
  if (!blocked && preview.choose) {
    return {
      blocked: false,
      blockReason: "",
      choosing: true,
      chooseLine: preview.choose_reason ?? "",
      paidLine: "",
      returnedLine: "",
      availableLine: "",
      partialAllowed: Boolean(preview.partial_allowed),
      amountQ: null,
      amountError: "",
      confirmLabel: "Estornar",
      canConfirm: false,
    };
  }
  const availableQ = preview.available_q ?? 0;
  // Com mais de uma cobrança, o pago é o DESTA cobrança: "neste pedido" insinuaria o total.
  const where = (preview.charges?.length ?? 0) > 1 ? "nesta cobrança" : "neste pedido";
  const parsed = moneyToQ(options.amount);
  const amountQ = parsed === null || parsed === 0 ? null : parsed;
  const error = blocked ? "" : amountError(amountQ, availableQ);
  const method = preview.method_label ? ` (${preview.method_label})` : "";
  return {
    blocked,
    blockReason: blocked ? preview.block_reason : "",
    choosing: false,
    chooseLine: "",
    paidLine: blocked ? "" : `Pago ${where}: ${preview.paid_display ?? ""}${method}`,
    returnedLine: !blocked && preview.returned_display ? `Já estornado: ${preview.returned_display}` : "",
    availableLine: blocked ? "" : `Disponível para estorno: ${preview.available_display ?? ""}`,
    partialAllowed: Boolean(preview.partial_allowed),
    amountQ,
    amountError: error,
    confirmLabel: !error && amountQ ? `Estornar ${brl(amountQ)}` : "Estornar",
    canConfirm:
      !blocked && Boolean(preview.action?.enabled) && !error && options.confirmed && !options.busy,
  };
}

/**
 * As cobranças a escolher (#3134): cada uma com o valor DELA. Nunca um total, nem na
 * soma dos itens: o Gerente vê valores de registros, não o agregado (dono, 21/11/2026).
 */
export function refundChargeOptions(
  preview: OrderRefundPreview | null,
): Array<{ value: string; label: string; description: string }> {
  return (preview?.charges ?? []).map((charge) => ({
    value: charge.intent_ref,
    label: `${charge.method_label || "Cobrança"} · pago ${charge.paid_display}`,
    description: charge.returned_display
      ? `Já estornado: ${charge.returned_display}. Disponível: ${charge.available_display}`
      : `Disponível: ${charge.available_display}`,
  }));
}

/** O aviso depois da tentativa: o dinheiro voltou, ou a frase do balcão do servidor. */
export function refundToast(receipt: OrderRefundReceipt | null | undefined): {
  tone: "success" | "error";
  text: string;
} | null {
  if (!receipt) return null;
  if (receipt.outcome === "refunded")
    return {
      tone: "success",
      text: `${brl(receipt.refunded_q || receipt.amount_q)} devolvidos ao cliente pelo mesmo meio do pagamento.`,
    };
  return { tone: "error", text: receipt.message || "O estorno não saiu. Nada foi devolvido ao cliente." };
}
