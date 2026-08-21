// Presentation — autorização do gerente (o diálogo de PIN das exceções).
//
// Duas perguntas, ambas puras e por isso testáveis sem montar a tela: O QUE está
// sendo assinado (a copy do motivo, que vem do servidor) e SE dá para assinar
// (quem + PIN). O mesmo diálogo cobre desconto acima do teto, preço alterado à
// mão, cancelamento de venda fechada e retirada de gaveta.

import { formatBRL } from "~/utils/posIntent";

/**
 * Copy por código de `approval_reasons`. O motivo sai do servidor, não de um
 * chute da tela: antes o diálogo afirmava "descontos acima de R$ X" em todos os
 * casos, e o gerente autorizava sem saber o que estava assinando.
 */
const REASON_COPY: Record<string, (thresholdQ: number) => string> = {
  discount_over_threshold: (q) => `Desconto acima de ${formatBRL(q)}.`,
  price_override: () => "Preço alterado à mão.",
};

export interface ManagerAuthReasonInput {
  /** Texto pronto, para quem não vem de uma venda (retirada de gaveta). */
  reasonText?: string;
  /** Códigos vindos da review (`approval_reasons`). */
  reasons?: string[];
  thresholdQ?: number;
}

export function managerAuthReason(input: ManagerAuthReasonInput): string {
  if (input.reasonText) return input.reasonText;
  const listed = (input.reasons ?? [])
    .map((code) => REASON_COPY[code]?.(input.thresholdQ ?? 0))
    .filter(Boolean);
  if (listed.length) return listed.join(" ");
  // Genérico é a última linha, nunca a primeira: dizer pouco é melhor que dizer
  // errado, e o gerente ainda sabe que está autorizando alguma coisa.
  return "Esta operação precisa da autorização de um gerente.";
}

