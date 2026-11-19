// Presentation — o aviso de página "Promessa em risco" (WP-G08). Puro.
//
// A encomenda de amanhã que perdeu o lote ficava quieta, abaixo da dobra, numa lista
// que ninguém abre no meio do turno (P0-1, lado do Gestor). Enquanto houver pedido com
// a promessa em risco, o cabeçalho do painel diz quantos são e leva ao primeiro.
// Quem diz que há risco, e o que fazer, é o servidor (`card.promise`, com `next_step`
// e `recommended_action`); aqui só se conta e se escreve. O aviso diz o que fazer, não
// só quem: com um pedido, a frase do próximo passo do servidor; com vários, um título
// que a tela compõe (`manyOrdersStep`), a única frase que nasce aqui.
import type { OrderCardProjection } from "~/types/orders";
import { splitRef } from "./board";
import { OPEN_PRODUCTION, SUGGESTIONS_HEADING, promiseRisk } from "./orderPromise";
import { preorderFocusKey } from "./preorderList";

type AlertSource = Pick<OrderCardProjection, "ref"> &
  Partial<Pick<OrderCardProjection, "promise">>;

export interface PromiseRiskAlert {
  /** A identidade do aviso leva os pedidos: outro pedido em risco é aviso novo, e o
   *  que foi dispensado no X volta. */
  id: string;
  title: string;
  description: string;
  actionLabel: string;
  /** Os pedidos em risco, na ordem em que a tela os recebeu (o combinado mais próximo
   *  primeiro: os de hoje e, depois, as encomendas por data). */
  refs: string[];
  firstRef: string;
  /** Um pedido só, e a conta abre o detalhe: o aviso abre o pedido, na faixa que tem
   *  as saídas. Senão, a tela vai até o primeiro. */
  opensOrder: boolean;
}

/** Quantos códigos o aviso escreve antes de resumir o resto num número. */
const NAMED_ORDERS = 3;

/**
 * O que fazer quando são vários pedidos em risco, para o título do aviso.
 *
 * Quando TODOS pedem só a Produção (sem lote planejado, plano que não cobre), o passo é
 * dela. Basta um pedido cujo item não vai existir ou está atrasado para o passo ser
 * falar com os clientes: é o que protege quem comprou, e vence o misto.
 */
export function manyOrdersStep(
  recommendedActions: readonly string[],
): string {
  return recommendedActions.length > 0 &&
    recommendedActions.every((action) => action === OPEN_PRODUCTION)
    ? "peça à Produção para planejar"
    : "avise os clientes e remarque";
}

function listed(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names.at(-1)}`;
}

/**
 * O aviso de página, ou `null` quando nenhum pedido está com a promessa em risco.
 *
 * `canOpen`: a conta abre o detalhe do pedido (quem só expede não abre). O rótulo do
 * botão diz o que o toque faz: "Abrir o pedido" só quando ele abre.
 */
export function promiseRiskAlert(
  cards: readonly AlertSource[],
  options: { canOpen?: boolean } = {},
): PromiseRiskAlert | null {
  const canOpen = options.canOpen ?? true;
  const seen = new Set<string>();
  const risky = cards.flatMap((card) => {
    if (seen.has(card.ref)) return [];
    const risk = promiseRisk(card);
    if (!risk) return [];
    seen.add(card.ref);
    return [{ ref: card.ref, code: splitRef(card.ref).code, risk }];
  });
  const first = risky[0];
  if (!first) return null;
  const refs = risky.map((entry) => entry.ref);
  const id = `promise-risk:${[...refs].sort().join(",")}`;
  if (risky.length === 1)
    return {
      id,
      title: `${first.risk.label} no pedido ${first.code}`,
      // O item, o porquê, as sugestões e a frase do servidor, um depois do outro. O
      // aviso do cabeçalho é uma frase corrida (o kit não desenha lista nele): as
      // sugestões vão na mesma linha, e a lista com marcador mora no pedido.
      description: [
        ...first.risk.items.map((item) =>
          [
            [item.label, item.detail].filter(Boolean).join(". "),
            item.suggestions.length
              ? `${SUGGESTIONS_HEADING} ${item.suggestions.join("; ")}.`
              : "",
          ]
            .filter(Boolean)
            .join(" "),
        ),
        first.risk.nextStep,
      ]
        .filter(Boolean)
        .join(" "),
      actionLabel: canOpen ? "Abrir o pedido" : `Ver o ${first.code}`,
      refs,
      firstRef: first.ref,
      opensOrder: canOpen,
    };
  const codes = risky.map((entry) => entry.code);
  const named = codes.slice(0, NAMED_ORDERS);
  const rest = codes.length - named.length;
  return {
    id,
    title: `${first.risk.label} em ${risky.length} pedidos: ${manyOrdersStep(
      risky.map((entry) => entry.risk.recommendedAction),
    )}`,
    description: rest
      ? `${named.join(", ")} e mais ${rest} ${rest === 1 ? "pedido" : "pedidos"}.`
      : `${listed(named)}.`,
    actionLabel: `Ver o ${first.code}`,
    refs,
    firstRef: first.ref,
    opensOrder: false,
  };
}

/** A chave do próximo foco de um pedido no painel, na Fila e na Tabela. */
export const orderFocusKey = (ref: string) => `order:${ref}`;

/** Onde o pedido pode estar na tela, na ordem em que se procura: o quadro (ou a Fila,
 *  ou a Tabela) e, depois, a lista de Encomendas. */
export function orderFocusKeys(ref: string): string[] {
  return [orderFocusKey(ref), preorderFocusKey(ref)];
}
