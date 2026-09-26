// ENCOMENDAS · os gestos do detalhe — receber e entregar, cancelar
// (ENCOMENDAS-PDV-PLAN, WP-E3/E4).
//
// A régua é do servidor: se pode entregar, quanto falta, se cancelar pede PIN.
// Aqui mora só o que a tela decide sozinha — as formas de balcão, o troco, as
// frases dos botões e o corpo que vai para a rota.

import { formatBRL } from "../../../operator-kit/app/utils/money";
import type { CounterMethod, PreorderHandOver } from "~/types/preorders";

import { amountToQ } from "./cash";

export interface CounterMethodOption {
  key: CounterMethod;
  label: string;
  icon: string;
}

/** As formas do balcão: dinheiro (com troco) ou cartão na maquininha. */
export const COUNTER_METHODS: readonly CounterMethodOption[] = [
  { key: "cash", label: "Dinheiro", icon: "lucide:banknote" },
  { key: "debit", label: "Débito", icon: "lucide:credit-card" },
  { key: "credit", label: "Crédito", icon: "lucide:credit-card" },
];

/** A forma que abre marcada: a que o cliente combinou, senão dinheiro. */
export function initialMethod(handOver: Pick<PreorderHandOver, "suggested_method">): CounterMethod {
  return handOver.suggested_method || "cash";
}

/** O botão do detalhe: o gesto inteiro, com o valor quando há o que cobrar. */
export function handOverCta(handOver: Pick<PreorderHandOver, "needs_payment" | "amount_display">): string {
  return handOver.needs_payment ? `Receber ${handOver.amount_display} e entregar` : "Entregar";
}

export interface ReceiveCheck {
  ok: boolean;
  /** A nota que veio na mão (só dinheiro). */
  tenderedQ: number;
  changeQ: number;
  message: string;
}

/**
 * Dinheiro: o valor recebido cobre o que falta? Campo vazio = o valor exato
 * (sem troco), que é o caso mais comum e não pede digitar nada. Cartão não tem
 * troco: a maquininha cobra o valor exato.
 */
export function checkReceive(method: CounterMethod, amountQ: number, receivedRaw: string): ReceiveCheck {
  if (method !== "cash") return { ok: true, tenderedQ: 0, changeQ: 0, message: "" };
  const typed = receivedRaw.trim();
  if (!typed) return { ok: true, tenderedQ: amountQ, changeQ: 0, message: "" };
  const tenderedQ = amountToQ(typed);
  if (tenderedQ === null) return { ok: false, tenderedQ: 0, changeQ: 0, message: "Digite o valor recebido, por exemplo 50 ou 50,00." };
  if (tenderedQ < amountQ) {
    return { ok: false, tenderedQ, changeQ: 0, message: `O valor recebido não cobre ${formatBRL(amountQ)}.` };
  }
  return { ok: true, tenderedQ, changeQ: tenderedQ - amountQ, message: "" };
}

/** "Troco: R$ 14,00" — ou, sem troco, a frase inteira. */
export function changeLine(changeQ: number): string {
  return changeQ > 0 ? `Troco: ${formatBRL(changeQ)}` : "Sem troco";
}

/** O botão de confirmar do diálogo: o que acontece, com a forma. */
export function receiveConfirmLabel(method: CounterMethod, amountDisplay: string): string {
  if (method === "cash") return `Receber ${amountDisplay} em dinheiro e entregar`;
  return `Receber ${amountDisplay} no ${method === "debit" ? "débito" : "crédito"} e entregar`;
}

export interface HandOverBody {
  tenders?: Array<{ method: CounterMethod; amount_q: number }>;
  cash_tendered_q?: number;
}

/** O corpo da rota. Encomenda paga não manda forma nenhuma: só entrega. */
export function handOverBody(handOver: Pick<PreorderHandOver, "needs_payment" | "amount_q">, method: CounterMethod, check: ReceiveCheck): HandOverBody {
  if (!handOver.needs_payment) return {};
  return {
    tenders: [{ method, amount_q: handOver.amount_q }],
    ...(method === "cash" ? { cash_tendered_q: check.tenderedQ } : {}),
  };
}

/** O que o balcão lê quando a entrega deu certo. */
export function handOverDoneMessage(receivedQ: number): string {
  return receivedQ > 0 ? `Recebido ${formatBRL(receivedQ)}. Encomenda entregue.` : "Encomenda entregue.";
}
