// RECEBER O SALDO — a encomenda na tela de Pagamento (EXCELENCIA-PDV, WP-E5).
//
// Gesto de dinheiro tem UMA tela (dono, 16/11/2026): o "Receber e entregar" do
// detalhe abre o mesmo `PosPaymentWorkspace` da venda, com o saldo como total.
// Forma, troco, cédulas, Exato, divisão e a conferência do troco alto são dele;
// aqui mora só o que é da encomenda: o que se cobra (o saldo que o servidor
// apurou), o que a coluna do pedido mostra, e o corpo que vai para a rota
// `pos/preorders/<ref>/hand-over/`.

import { formatBRL } from "../../../operator-kit/app/utils/money";
import type { POSPaymentMethodProjection, POSPaymentTenderDraft } from "~/types/pos";
import type { CounterMethod, PreorderCard, PreorderHandOver } from "~/types/preorders";
import type { OrderDetailDiscountLine, OrderDetailItem } from "../../../operator-kit/app/types/orderDetail";

import { cashTenderSumQ } from "./payment";

/**
 * As formas que recebem o saldo no balcão. Dinheiro, débito e crédito vão pela
 * rota da entrega (`operator_orders._COUNTER_METHODS`); o Pix sozinho, pela
 * cobrança Pix do balcão (`pos/preorders/<ref>/pix/`, #2897), do jeito que a venda
 * cobra Pix; o Pix misto, atestado, pela rota da entrega (#2916).
 * O link não entra: a cliente está na frente do caixa.
 */
export const HAND_OVER_METHODS: readonly string[] = ["cash", "debit", "credit", "pix"];

/** As formas da loja que o saldo da encomenda aceita, na ordem da projeção. */
export function handOverMethods(methods: POSPaymentMethodProjection[]): POSPaymentMethodProjection[] {
  return methods.filter((method) => HAND_OVER_METHODS.includes(method.ref));
}

/**
 * As linhas cobram o saldo pela cobrança Pix do balcão (QR e provedor)?
 *
 * Só quando o Pix vem SOZINHO (uma linha, ou a conta dividida só em Pix): é UMA
 * cobrança Pix do pedido, como na venda que fecha em Pix (#2897). Pix ao lado de
 * dinheiro ou cartão é o Pix MISTO (#2916): sem provedor, o operador atesta com
 * "Recebi o Pix" (o mesmo degrau da venda mista) e ele vai pela rota da entrega.
 */
export function paysBalanceWithPix(tenders: Pick<POSPaymentTenderDraft, "method" | "amount_q">[], dueQ: number): boolean {
  const lines = tenders.filter((tender) => tender.amount_q > 0);
  if (!lines.length || dueQ <= 0) return false;
  return lines.every((tender) => tender.method === "pix");
}

export interface BalanceChargeLine {
  key: string;
  qtyLabel: string;
  name: string;
  totalDisplay: string;
}

/** O que o servidor tirou dos itens (cupom, promoção, grupo): "Cupom BEMVINDO", "−R$ 5,00". */
export interface BalanceChargeAdjustment {
  key: string;
  label: string;
  amountDisplay: string;
}

export interface BalanceChargeNotice {
  key: string;
  icon: string;
  message: string;
  /** `warn` é o que o operador precisa ler antes de receber (a cobrança cancelada). */
  tone?: "warn";
}

/** O que a tela de Pagamento recebe quando cobra o saldo de uma encomenda. */
export interface PosBalanceCharge {
  orderRef: string;
  customerName: string;
  /** O que falta receber: o total desta cobrança. */
  amountQ: number;
  amountDisplay: string;
  /** O total da encomenda. */
  orderTotalDisplay: string;
  /** O que já entrou; "" quando nada foi pago antes. */
  paidDisplay: string;
  lines: BalanceChargeLine[];
  /** Por que o Pix não cobra este saldo agora (a forma fica apagada); "" quando cobra. */
  pixBlockedReason: string;
  /**
   * Os itens vêm a preço de tabela e o desconto em linha própria (o mesmo
   * detalhe do Gestor): sem estas linhas, itens e total não fecham a conta.
   */
  adjustments: BalanceChargeAdjustment[];
  notices: BalanceChargeNotice[];
}

/**
 * A cobrança do saldo, montada da leitura do detalhe. Os números são todos do
 * servidor (`hand_over.amount_q`, `card.total_q`): a tela não recalcula o saldo.
 */
export function balanceCharge(input: {
  orderRef: string;
  customerName: string;
  handOver: Pick<PreorderHandOver, "amount_q" | "amount_display" | "kitchen_notice" | "digital_charge_notice" | "pix_block_reason">;
  card: Pick<PreorderCard, "total_q" | "total_display">;
  items: OrderDetailItem[];
  discountLines?: OrderDetailDiscountLine[];
}): PosBalanceCharge {
  const paidQ = Math.max(0, input.card.total_q - input.handOver.amount_q);
  const notices: BalanceChargeNotice[] = [];
  if (input.handOver.digital_charge_notice) {
    notices.push({ key: "digital-charge", icon: "lucide:link-2-off", message: input.handOver.digital_charge_notice, tone: "warn" });
  }
  if (input.handOver.kitchen_notice) {
    notices.push({ key: "kitchen", icon: "lucide:chef-hat", message: input.handOver.kitchen_notice });
  }
  return {
    orderRef: input.orderRef,
    customerName: input.customerName,
    amountQ: input.handOver.amount_q,
    amountDisplay: input.handOver.amount_display,
    orderTotalDisplay: input.card.total_display,
    paidDisplay: paidQ > 0 ? formatBRL(paidQ) : "",
    pixBlockedReason: input.handOver.pix_block_reason ?? "",
    lines: input.items.map((item, index) => ({
      key: `${item.sku}-${index}`,
      qtyLabel: `${item.qty}x`,
      name: item.name,
      totalDisplay: item.total_display,
    })),
    adjustments: (input.discountLines ?? []).map((line, index) => ({
      key: `${line.kind}-${index}`,
      label: line.label,
      amountDisplay: line.amount_display,
    })),
    notices,
  };
}

/** Onde a espera do Pix do saldo está: a mesma régua da venda em Pix. */
export type BalancePixStatus = "idle" | "polling" | "paid" | "expired";

/** Uma forma do saldo na rota da entrega: o balcão (dinheiro, cartão) ou o Pix atestado. */
export interface HandOverTender {
  method: CounterMethod | "pix";
  amount_q: number;
  /** O Pix misto conferido com "Recebi o Pix" (#2916); o servidor carimba quem e quando. */
  pix_confirmed?: true;
}

export interface HandOverBody {
  tenders?: HandOverTender[];
  cash_tendered_q?: number;
}

/**
 * O corpo da rota, a partir das linhas da tela de Pagamento.
 *
 * A rota quer as formas somando EXATAMENTE o saldo, e a nota que veio na mão à
 * parte (`cash_tendered_q`): o troco é a diferença. As linhas da tela trazem o
 * dinheiro como foi entregue (R$ 50,00 por uma encomenda de R$ 36,00), então o
 * dinheiro vira UMA forma com o que ele paga de fato, e as cédulas vão inteiras
 * como recebido. Cartão vai como está: excedente em cartão a tela não deixa
 * validar. O Pix misto vai com `pix_confirmed`, depois do "Recebi o Pix".
 * Encomenda paga não manda forma nenhuma: só entrega.
 */
export function handOverBody(tenders: POSPaymentTenderDraft[], dueQ: number): HandOverBody {
  if (dueQ <= 0) return {};
  const nonCash: HandOverTender[] = tenders
    .filter((tender) => tender.method !== "cash" && tender.amount_q > 0)
    .map((tender) => (tender.method === "pix" && tender.pix_confirmed
      ? { method: "pix" as const, amount_q: tender.amount_q, pix_confirmed: true as const }
      : { method: tender.method as CounterMethod | "pix", amount_q: tender.amount_q }));
  const cashPartQ = dueQ - nonCash.reduce((sum, tender) => sum + tender.amount_q, 0);
  if (cashPartQ <= 0) return { tenders: nonCash };
  const cash = { method: "cash" as const, amount_q: cashPartQ };
  // A ordem das linhas é a da tela: o dinheiro entra onde a primeira nota entrou.
  const cashFirst = tenders.findIndex((tender) => tender.method === "cash") <= tenders.findIndex((tender) => tender.method !== "cash");
  return {
    tenders: cashFirst ? [cash, ...nonCash] : [...nonCash, cash],
    cash_tendered_q: cashTenderSumQ(tenders),
  };
}
