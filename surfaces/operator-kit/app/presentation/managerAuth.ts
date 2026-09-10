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
  | "sale_approval";

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
  sale_approval: {
    title: "Autorizar a venda",
    reason: "",  // o motivo vem do servidor, em `approval_reasons`
  },
};

/**
 * Copy por código de `approval_reasons`. O motivo sai do servidor, não de um
 * chute da tela: antes o diálogo afirmava "descontos acima de R$ X" em todos os
 * casos, e o gerente autorizava sem saber o que estava assinando.
 */
const REASON_COPY: Record<string, (thresholdQ: number) => string> = {
  discount_over_threshold: (q) => `Desconto acima de ${formatBRL(q)}.`,
};

export interface ManagerAuthReasonInput {
  /** O ato, quando a tela sabe qual é. */
  action?: ManagerAction;
  /** Códigos vindos da review (`approval_reasons`). */
  reasons?: string[];
  thresholdQ?: number;
}

/** O título: o ATO, nomeado. Nunca "Autorização" genérico se der para nomear. */
export function managerAuthTitle(action?: ManagerAction): string {
  return (action && MANAGER_ACTIONS[action]?.title) || "Autorização do gerente";
}

export function managerAuthReason(input: ManagerAuthReasonInput): string {
  const listed = (input.reasons ?? [])
    .map((code) => REASON_COPY[code]?.(input.thresholdQ ?? 0))
    .filter(Boolean);
  if (listed.length) return listed.join(" ");
  const fixa = input.action && MANAGER_ACTIONS[input.action]?.reason;
  if (fixa) return fixa;
  // Genérico é a última linha, nunca a primeira: dizer pouco é melhor que dizer
  // errado, e o gerente ainda sabe que está autorizando alguma coisa.
  return "Precisa de um gerente.";
}
