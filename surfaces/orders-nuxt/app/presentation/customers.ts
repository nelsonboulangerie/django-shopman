// Presentation — Clientes do Gestor. Transforms puros: a query da lista na URL e a
// decisão de quem FICA numa unificação. Sem rede e sem DOM.

export const CUSTOMER_FILTERS = ["all", "possible_duplicates", "ifood", "no_phone"] as const;
export type CustomerFilter = (typeof CUSTOMER_FILTERS)[number];

export interface CustomerListQuery {
  q: string;
  filter: CustomerFilter;
  page: number;
}

type RouteQueryValue = string | null | (string | null)[] | undefined;

function first(value: RouteQueryValue): string {
  return String((Array.isArray(value) ? value[0] : value) ?? "").trim();
}

/** A URL é a fonte da busca: voltar da ficha devolve a mesma lista, na mesma página. */
export function listQueryFromRoute(query: Record<string, RouteQueryValue>): CustomerListQuery {
  const filter = first(query.filter) as CustomerFilter;
  const page = Number.parseInt(first(query.page), 10);
  return {
    q: first(query.q),
    filter: CUSTOMER_FILTERS.includes(filter) ? filter : "all",
    page: Number.isFinite(page) && page > 1 ? page : 1,
  };
}

/** O inverso, sem os valores padrão — a URL limpa é `/customers`. */
export function routeQueryFromList(list: CustomerListQuery): Record<string, string> {
  const out: Record<string, string> = {};
  if (list.q) out.q = list.q;
  if (list.filter !== "all") out.filter = list.filter;
  if (list.page > 1) out.page = String(list.page);
  return out;
}

export interface MergeCandidateSide {
  ref: string;
  phone_display: string;
  source_label: string;
}

export type Keeper = "current" | "other";

/**
 * Quem a tela sugere que FIQUE. É só o ponto de partida do seletor — a decisão é
 * de quem confirma.
 *
 * 1. Fica quem tem telefone: é por ele que a casa fala com a pessoa, e o cadastro
 *    do iFood nasce sem (o iFood manda o 0800 da central).
 * 2. Os dois com telefone, ou nenhum: fica quem NÃO veio do iFood — o cadastro da
 *    casa é o que alguém conferiu com a pessoa na frente.
 * 3. Empate: fica o cadastro que está aberto na tela.
 */
export function suggestedKeeper(current: MergeCandidateSide, other: MergeCandidateSide): Keeper {
  const currentPhone = Boolean(current.phone_display);
  const otherPhone = Boolean(other.phone_display);
  if (currentPhone !== otherPhone) return currentPhone ? "current" : "other";
  const currentIFood = current.source_label === "iFood";
  const otherIFood = other.source_label === "iFood";
  if (currentIFood !== otherIFood) return currentIFood ? "other" : "current";
  return "current";
}

/** O par que o servidor recebe: `source` SAI (fica desativado), `target` FICA. */
export function mergePair(currentRef: string, otherRef: string, keeper: Keeper) {
  return keeper === "current"
    ? { source_ref: otherRef, target_ref: currentRef }
    : { source_ref: currentRef, target_ref: otherRef };
}
