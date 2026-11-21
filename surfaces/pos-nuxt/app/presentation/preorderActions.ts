// ENCOMENDAS · os gestos do detalhe — receber e entregar, cancelar
// (ENCOMENDAS-PDV-PLAN, WP-E3/E4).
//
// A régua é do servidor: se pode entregar, quanto falta, se cancelar pede PIN.
// Receber o saldo é a tela de Pagamento da venda (`presentation/balanceCharge`):
// aqui moram só as frases dos botões e dos avisos do detalhe.

import { formatBRL } from "../../../operator-kit/app/utils/money";
import type { PreorderHandOver, PreorderRedoContext } from "~/types/preorders";

/** O botão do detalhe: o gesto inteiro, com o valor quando há o que cobrar. */
export function handOverCta(handOver: Pick<PreorderHandOver, "needs_payment" | "amount_display">): string {
  return handOver.needs_payment ? `Receber ${handOver.amount_display} e entregar` : "Entregar";
}

/**
 * O cliente pagou online (Pix ou link) segundos antes de o balcão receber: o
 * servidor recusa com `preorder_paid_online` e registra o pagamento. A tela avisa
 * e oferece só "Entregar". Qualquer outro erro não é este aviso.
 */
export const PAID_ONLINE_CODE = "preorder_paid_online";

export function paidOnlineNotice(code: string | null | undefined): string {
  if (code !== PAID_ONLINE_CODE) return "";
  return "O cliente acabou de pagar online. Não receba no balcão: só entregue a encomenda.";
}

/**
 * O que o balcão lê quando a entrega deu certo: o que entrou e, com dinheiro a
 * mais, o troco que a tela de Pagamento mostrou (a resposta da rota traz só o
 * recebido).
 */
export function handOverDoneMessage(receivedQ: number, changeQ = 0, pixQ = 0): string {
  if (pixQ > 0) return `Pix de ${formatBRL(pixQ)} confirmado. Encomenda entregue.`;
  if (receivedQ <= 0) return "Encomenda entregue.";
  const change = changeQ > 0 ? `, com troco de ${formatBRL(changeQ)}` : "";
  return `Recebido ${formatBRL(receivedQ)}${change}. Encomenda entregue.`;
}

// ── Reagendar ───────────────────────────────────────────────────────────────
//
// A troca de data é do orquestrador (`shop/services/reschedule.py`): valida,
// move o despertador, o lembrete, as reservas e a produção, ou recusa com o
// motivo. A tela oferece as datas e janelas que o servidor diz combináveis
// (`/pos/schedule/`, as mesmas da venda) e manda a escolha.

/** Mudou alguma coisa? A mesma data e a mesma janela não viram requisição. */
export function rescheduleChanged(current: { date: string; slot: string }, draft: { date: string; slot: string }): boolean {
  return Boolean(draft.date) && (draft.date !== current.date || draft.slot !== current.slot);
}

/** O botão de confirmar: para onde vai. "Mudar para sáb, 27/09, a partir das 9h". */
export function rescheduleConfirmLabel(target: string): string {
  return target ? `Mudar para ${target}` : "Escolha a nova data";
}

/** O que o balcão lê quando a troca deu certo. */
export function rescheduleDoneMessage(changed: boolean, activatedNow: boolean): string {
  if (!changed) return "A data e o horário já eram esses. Nada mudou.";
  return activatedNow ? "Data trocada para hoje: a encomenda já entrou no preparo de hoje." : "Data trocada.";
}

/** A comanda do refazer leva o nome da encomenda (espelho de `pos_edit_session.redo_tab_ref`). */
export function redoTabLabel(orderRef: string): string {
  return `Refazer ${orderRef}`;
}

/**
 * "Cancelar e refazer", depois do cancelar: onde a venda nova está e o que
 * falta fazer. A data que não valia mais vem dita por extenso (o servidor diz
 * a razão e com que data a comanda veio).
 */
export function redoNotice(
  redo: Pick<PreorderRedoContext, "order_ref" | "schedule_dropped">,
  options: { needsOpenShift?: boolean } = {},
): string {
  // Sem caixa aberto a venda NÃO abre: a tela vai para a antesala abrir o caixa,
  // e a comanda espera no quadro. Dizer "a venda abriu" ali era falso.
  const base = options.needsOpenShift
    ? `Comanda "${redoTabLabel(redo.order_ref)}" pronta no quadro, com os itens da encomenda cancelada. Abra o caixa para continuar a venda.`
    : `A venda nova abriu na comanda "${redoTabLabel(redo.order_ref)}", com os itens da encomenda cancelada: ajuste e feche a venda.`;
  return redo.schedule_dropped ? `${base} ${redo.schedule_dropped}` : base;
}

/**
 * Depois de entregar: há DANFE a esperar e imprimir? Só quando a nota está na
 * fila ou já autorizou. Sem nota esperada (ou com a emissão falhada, que o
 * Gestor reprocessa) a espera de 90s terminaria num aviso falso.
 */
export function danfeExpected(fiscalState: string | undefined | null): boolean {
  return fiscalState === "queued" || fiscalState === "authorized";
}
