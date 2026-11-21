// A lista de Encomendas do Gestor (WP-G03): o que cada linha responde. Puro, testado em
// `tests/preorderList.test.ts`.
//
// A linha mostrava código, nome, itens e total. Quem conferia a semana não lia quando,
// se era retirada ou entrega, se estava paga nem se a produção cobria; e o único sinal,
// "Precisa de você", aparecia justamente em quem esperava um fato de fora (o pagamento).
// Os fatos já estão no cartão (o combinado do WP-G01, o pagamento, a produção): aqui só
// se escolhe o que a linha diz e com que palavras.
//
// A encomenda de data futura que perdeu o lastro mora AQUI, e não no quadro (WP-G08): a
// linha diz "Promessa em risco", o item que falta e as sugestões, conta como
// "Precisa de você" e abre o pedido na faixa que tem as saídas.
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
import {
  RESOLVE,
  promiseRisk,
  promiseRiskSummary,
  promiseSuggestionGroups,
} from "./orderPromise";

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
  Partial<
    Pick<
      OrderCardProjection,
      "kitchen_release_label" | "promise" | "status" | "advance_block_reason"
    >
  >;

/** A âncora da faixa "O que falta neste pedido" na linha da promessa (o detalhe a lê). */
export const PROMISE_HASH = "#promise";

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
  /** "Produção de Kuro Pan: não começou", quando o pedido espera um lote. Vazio na
   *  promessa em risco: o item que falta já diz o que há com o lote. */
  production: string;
  /** A promessa em risco: o nome do estado, o item que falta, as sugestões do que
   *  oferecer no lugar (numa linha só: a lista com marcador mora no pedido) e a frase
   *  do servidor, quando há. `null` em quem tem lastro. */
  risk: { label: string; items: string; suggestions: string; nextStep: string } | null;
  /** Há um gesto que só uma pessoa faz (nunca o pagamento que ainda não caiu). */
  needsYou: boolean;
  /** A promessa em risco com o "Resolver" aberto para a conta: o gesto da linha é ele,
   *  no lugar do "Remarcar no PDV" (uma situação, um gesto; #2809 item 4). */
  resolves: boolean;
  /** Para onde a linha leva: o pedido; em risco, o pedido na faixa das saídas. */
  to: string;
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
  const risk = promiseRisk(card);
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
    risk: risk
      ? {
          label: risk.label,
          items: promiseRiskSummary(risk),
          suggestions: promiseSuggestionGroups(risk)
            .map((group) => `${group.heading} ${group.options.join("; ")}`)
            .join(" "),
          nextStep: risk.nextStep,
        }
      : null,
    // "Precisa de você" é de quem espera um gesto. O pagamento que ainda não caiu é
    // fato de fora: avança sozinho, e a linha já diz "Aguardando pagamento". A
    // promessa em risco pede alguém mesmo assim: avisar, remarcar ou cancelar.
    needsYou: Boolean(risk) || (Boolean(card.attention) && !awaitingPayment),
    resolves: Boolean(risk?.exits.some((exit) => exit.ref === RESOLVE && !exit.disabled)),
    to: risk ? `/${card.ref}${PROMISE_HASH}` : `/${card.ref}`,
    items: card.items_summary,
    total: card.total_display,
  };
}

/**
 * O nome do grupo da lista: o dia, com maiúscula ("Hoje", "Amanhã", "Sex, 20/11").
 *
 * O servidor manda o dia em minúscula porque o usa no meio de frase ("combinado para
 * amanhã às 9h"). Aqui ele é valor isolado, e valor isolado começa com maiúscula
 * (dono, 16/11/2026): "hoje" ao lado de "Sex, 20/11" lia como duas regras.
 */
export function preorderGroupLabel(label: string): string {
  const text = String(label ?? "").trim();
  return text ? text.charAt(0).toLocaleUpperCase("pt-BR") + text.slice(1) : "";
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
