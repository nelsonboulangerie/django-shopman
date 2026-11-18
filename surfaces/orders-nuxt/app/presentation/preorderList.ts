// A lista de Encomendas do Gestor (WP-G03): o que cada linha responde. Puro, testado em
// `tests/preorderList.test.ts`.
//
// A linha mostrava código, nome, itens e total. Quem conferia a semana não lia quando,
// se era retirada ou entrega, se estava paga nem se a produção cobria; e o único sinal,
// "Precisa de você", aparecia justamente em quem esperava um fato de fora (o pagamento).
// Os fatos já estão no cartão (o combinado do WP-G01, o pagamento, a produção): aqui só
// se escolhe o que a linha diz e com que palavras.
import type {
  OrderCardProjection,
  TwoZoneQueueProjection,
} from "~/types/orders";
import {
  kitchenWait,
  productionLines,
  splitRef,
  type KitchenWait,
} from "./board";

type LineSource = Pick<
  OrderCardProjection,
  | "ref"
  | "customer_name"
  | "items_summary"
  | "total_display"
  | "schedule_label"
  | "fulfillment_label"
  | "payment_method_label"
  | "payment_status_label"
  | "payment_pending"
  | "attention"
  | "awaiting_work_orders"
> &
  Partial<Pick<OrderCardProjection, "kitchen_release_label">>;

export interface PreorderLine {
  ref: string;
  /** O código curto que a tela mostra (NB-261116-W33 vira W33). */
  code: string;
  who: string;
  /** "Amanhã · A partir das 15h": o dia e a janela, a mesma frase do cartão. */
  when: string;
  /** "Vai para a Cozinha às 17h15": a encomenda de hoje que ainda espera a hora dela
   *  (WP-G02). `null` na de outro dia. */
  kitchenWait: KitchenWait | null;
  /** "Retirada" ou "Entrega". */
  how: string;
  /** "Pix · Pago" · "Dinheiro" · "Aguardando pagamento". */
  payment: string;
  /** O pagamento ainda não caiu: a linha diz isso com nome, sem pedir gesto. */
  awaitingPayment: boolean;
  /** "Produção de Kuro Pan: planejada", quando o pedido espera um lote. */
  production: string;
  /** Há um gesto que só uma pessoa faz (nunca o pagamento que ainda não caiu). */
  needsYou: boolean;
  items: string;
  total: string;
}

export const AWAITING_PAYMENT_LABEL = "Aguardando pagamento";

/** O que uma linha da lista de Encomendas diz sobre o pedido. */
export function preorderLine(card: LineSource): PreorderLine {
  const awaitingPayment = Boolean(card.payment_pending);
  const method = String(card.payment_method_label ?? "").trim();
  const status = String(card.payment_status_label ?? "").trim();
  const paid = [method, status].filter(Boolean).join(" · ");
  return {
    ref: card.ref,
    code: splitRef(card.ref).code,
    who: card.customer_name || "Sem cliente",
    when: String(card.schedule_label ?? "").trim(),
    kitchenWait: kitchenWait(card),
    how: card.fulfillment_label,
    // Quem espera o pagamento lê isso com nome; o meio fica ao lado, quando se sabe.
    payment: awaitingPayment
      ? [AWAITING_PAYMENT_LABEL, method].filter(Boolean).join(" · ")
      : paid,
    awaitingPayment,
    production: productionLines(card)
      .map((line) => line.text)
      .join(" · "),
    // "Precisa de você" é de quem espera um gesto. O pagamento que ainda não caiu é
    // fato de fora: avança sozinho, e a linha já diz "Aguardando pagamento".
    needsYou: Boolean(card.attention) && !awaitingPayment,
    items: card.items_summary,
    total: card.total_display,
  };
}

/** A encomenda aberta no PDV, onde mora o remarcar (D-003). Vazio sem o endereço do PDV. */
export function preorderRescheduleHref(posUrl: string, ref: string): string {
  const base = String(posUrl || "").replace(/\/$/, "");
  return base && ref ? `${base}/preorders/${encodeURIComponent(ref)}` : "";
}

export interface AcceptedPreorder {
  ref: string;
  code: string;
  /** "E17 foi para Encomendas: Amanhã · A partir das 15h." */
  message: string;
}

type QueueSides = Pick<TwoZoneQueueProjection, "intake" | "preorders">;

/**
 * As encomendas que acabaram de ser aceitas: estavam em Novos e agora moram na lista.
 *
 * Aceita, a encomenda de outro dia sai das colunas do dia. Sem este aviso o painel
 * dizia só "Nenhum pedido novo agora." e a lista ficava abaixo da dobra (P1-09).
 */
export function acceptedIntoPreorders(
  before: QueueSides | null,
  after: QueueSides | null,
): AcceptedPreorder[] {
  if (!before || !after) return [];
  const wasNew = new Set(before.intake.map((card) => card.ref));
  return (after.preorders ?? [])
    .filter((card) => wasNew.has(card.ref))
    .map((card) => {
      const code = splitRef(card.ref).code;
      const when = String(card.schedule_label ?? "").trim();
      return {
        ref: card.ref,
        code,
        message: when
          ? `${code} foi para Encomendas: ${when}.`
          : `${code} foi para Encomendas.`,
      };
    });
}

/** A chave do próximo foco da linha de uma encomenda (`data-focus-target`). */
export const preorderFocusKey = (ref: string) => `preorder:${ref}`;
