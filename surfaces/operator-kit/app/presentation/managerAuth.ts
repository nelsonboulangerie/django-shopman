// Presentation — autorização do gerente (o diálogo de PIN das exceções).
//
// ⚠️ **Este diálogo se confunde com o DESTRAVE DE SESSÃO, não com o login.** O
// login acontece uma vez por turno e ninguém erra. O destrave (`OperatorLock`)
// e a autorização aparecem os dois no meio do expediente, os dois são um
// teclado de PIN, e os dois interrompem quem está atendendo. É esse o par
// perigoso, e é contra ele que a copy foi escrita:
//
//   destrave     → "Quem está operando?"  · você ASSUME o balcão
//   autorização  → "Quem autoriza?"       · você CONTINUA quem era; o gerente
//                                            assina UMA coisa e vai embora
//
// Todo o texto mora aqui, e não espalhado pelas telas: eram quatro pontos de
// chamada com frase própria, cada uma mais longa que a outra, e ninguém
// conseguia comparar o conjunto para ver que estava prolixo.

import { formatBRL } from "../utils/money";

/** O ato que o gerente assina. É a chave da copy — uma por exceção do PDV. */
export type ManagerAction =
  | "drawer_unlock"
  | "cash_out"
  | "serve_change"
  | "refund_cash"
  | "cancel_sale"
  | "cancel_order"
  | "order_edit_refund"
  | "card_machine_refund"
  | "close_shift_review"
  | "day_closing_production"
  | "sale_approval"
  | "emit_fiscal"
  | "channel_off"
  | "channel_on";

interface ManagerActionCopy {
  /** O ato, nomeado. Vira o título do diálogo. */
  title: string;
  /** POR QUE precisa de assinatura. Uma frase curta — nunca uma explicação. */
  reason: string;
}

/**
 * ⚠️ Frase curta, sem explicação. A versão anterior explicava a política dentro
 * do diálogo ("Retirar dinheiro da gaveta é exceção auditada: um gerente
 * precisa autorizar") e o dono achou prolixo — com razão: o gerente que está de
 * pé no balcão, com fila, não lê parágrafo. Ele precisa saber O QUE assina.
 */
export const MANAGER_ACTIONS: Record<ManagerAction, ManagerActionCopy> = {
  drawer_unlock: {
    title: "Autorizar destrave da gaveta",
    reason: "Gaveta travada ou sensor com defeito.",
  },
  cash_out: {
    title: "Autorizar retirada da gaveta",
    reason: "Sai dinheiro da gaveta.",
  },
  serve_change: {
    title: "Autorizar troco",
    reason: "Atender abre a gaveta.",
  },
  refund_cash: {
    title: "Autorizar devolução",
    reason: "Sai dinheiro da gaveta.",
  },
  cancel_sale: {
    title: "Autorizar cancelamento",
    reason: "A venda já foi fechada.",
  },
  // Cancelar pedido pago no Gestor. O "A venda já foi fechada." do PDV mentia
  // para um pedido só autorizado; o motivo é o que acontece com o dinheiro, e
  // ele vem da projeção do pedido em `detail` (beta 06/11, F5).
  cancel_order: {
    title: "Autorizar cancelamento",
    reason: "O pedido já foi pago.",
  },
  order_edit_refund: {
    title: "Autorizar a devolução",
    reason: "A encomenda paga ficou mais barata.",
  },
  card_machine_refund: {
    title: "Autorizar o estorno",
    reason: "Volta dinheiro para o cartão do cliente.",
  },
  // Venda sem conexão cobrada por um preço que o catálogo não explica: a venda
  // entrou, e o caixa só fecha com o gerente que conferiu.
  close_shift_review: {
    title: "Autorizar o fechamento",
    reason: "Há venda sem conexão a conferir.",
  },
  // Fechar o dia com produção aberta (decisão do dono, 05/11/2026): impede, e o
  // gerente libera com o PIN e o motivo. O que fica aberto vem em `detail`.
  day_closing_production: {
    title: "Autorizar fechar o dia",
    reason: "Há produção aberta.",
  },
  sale_approval: {
    title: "Autorizar a venda",
    reason: "",  // o motivo vem do servidor, em `approval_reasons`
  },
  emit_fiscal: {
    title: "Autorizar a emissão da NFC-e",
    reason: "A venda não pediu nota.",
  },
  // O toggle "Ativo" dos cards da aba Canais (Gestor). O que muda em cada canal o
  // modal já disse antes de chegar aqui; o gerente só precisa saber O QUE assina.
  channel_off: {
    title: "Autorizar desligar o canal",
    reason: "O canal para até o fim do período.",
  },
  channel_on: {
    title: "Autorizar ligar o canal",
    reason: "O canal volta a funcionar.",
  },
};

/**
 * Copy por código de `approval_reasons`. O motivo sai do servidor, não de um
 * chute da tela: antes o diálogo afirmava "descontos acima de R$ X" em todos os
 * casos, e o gerente autorizava sem saber o que estava assinando.
 */
const REASON_COPY: Record<string, (input: ManagerAuthReasonInput) => string> = {
  // O VALOR primeiro: "Desconto acima de R$ 5,00" fazia o gerente assinar uma
  // cortesia de R$ 12,00 (ou de R$ 300,00) sem ver o número (beta 07/11).
  discount_over_threshold: (input) =>
    typeof input.discountQ === "number" && input.discountQ > 0
      ? `Desconto de ${formatBRL(input.discountQ)}, acima de ${formatBRL(input.thresholdQ ?? 0)}.`
      : `Desconto acima de ${formatBRL(input.thresholdQ ?? 0)}.`,
  // Conta na casa com limite (decisão do dono, 14/10/2026): o gerente vê o saldo
  // de hoje, o limite e quanto esta venda passa ANTES de assinar.
  house_account_over_limit: (input) => {
    const limit = input.houseAccountLimit;
    if (!limit) return "Conta na casa acima do limite.";
    return (
      `Conta na casa acima do limite. Em aberto ${formatBRL(limit.balance_q)}, `
      + `limite ${formatBRL(limit.limit_q)}: esta venda passa ${formatBRL(limit.over_q)}.`
    );
  },
};

/** Os números da conta na casa acima do limite (`review.house_account_limit`). */
export interface HouseAccountLimitInput {
  /** O saldo devedor antes desta venda. */
  balance_q: number;
  limit_q: number;
  /** O que esta venda põe na conta. */
  charge_q: number;
  /** Quanto o saldo passaria do limite. */
  over_q: number;
}

export interface ManagerAuthReasonInput {
  /** O ato, quando a tela sabe qual é. */
  action?: ManagerAction;
  /**
   * O valor que o gerente assina, em centavos. Nos atos em que dinheiro sai, o
   * número é a frase: a sangria de "5000" (R$ 5.000,00 lido de um R$ 50,00)
   * passou pelo PIN porque o diálogo dizia só "Sai dinheiro da gaveta" (beta
   * 05/11, PDV-09).
   */
  amountQ?: number | null;
  /** O complemento do ato, na voz da tela (o motivo da sangria, as ordens abertas). */
  detail?: string;
  /** Códigos vindos da review (`approval_reasons`). */
  reasons?: string[];
  thresholdQ?: number;
  /** Com o motivo `discount_over_threshold`: o desconto manual que a venda leva. */
  discountQ?: number | null;
  /** Com o motivo `house_account_over_limit`: saldo, limite e quanto passa. */
  houseAccountLimit?: HouseAccountLimitInput | null;
}

/** O título: o ATO, nomeado. Nunca "Autorização" genérico se der para nomear. */
export function managerAuthTitle(action?: ManagerAction): string {
  return (action && MANAGER_ACTIONS[action]?.title) || "Autorização do gerente";
}

/**
 * Os atos em que o gerente assina um VALOR: a frase nomeia o valor primeiro.
 * Sem valor (a tela não sabe), cai na frase fixa do ato.
 */
const AMOUNT_COPY: Partial<Record<ManagerAction, (amount: string, detail: string) => string>> = {
  cash_out: (amount, detail) => `Retirada de ${amount}${detail ? ` (${detail})` : ""}.`,
  refund_cash: (amount) => `Devolução de ${amount} em dinheiro.`,
  serve_change: (amount) => `Troco de ${amount}. Atender abre a gaveta.`,
  card_machine_refund: (amount) => `Estorno de ${amount} no cartão do cliente.`,
  order_edit_refund: (amount) => `Devolução de ${amount}: a encomenda paga ficou mais barata.`,
};

export function managerAuthReason(input: ManagerAuthReasonInput): string {
  const listed = (input.reasons ?? [])
    .map((code) => REASON_COPY[code]?.(input))
    .filter(Boolean);
  if (listed.length) return listed.join(" ");
  const detail = String(input.detail ?? "").trim();
  const withAmount = input.action && AMOUNT_COPY[input.action];
  if (withAmount && typeof input.amountQ === "number" && input.amountQ > 0) {
    return withAmount(formatBRL(input.amountQ), detail);
  }
  if (detail && (input.action === "day_closing_production" || input.action === "cancel_order")) return detail;
  const fixa = input.action && MANAGER_ACTIONS[input.action]?.reason;
  if (fixa) return fixa;
  // Genérico é a última linha, nunca a primeira: dizer pouco é melhor que dizer
  // errado, e o gerente ainda sabe que está autorizando alguma coisa.
  return "Precisa de um gerente.";
}
