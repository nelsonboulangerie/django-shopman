// Presentation — Histórico do Gestor. Transforms puros: a URL da tela (período,
// busca, página e recortes) ↔ a query do endpoint, e os campos da FilterBar a partir
// das opções que o servidor contou. Sem rede e sem DOM.
import {
  filtersFromQuery,
  filtersToQuery,
} from "../../../operator-kit/app/presentation/filterBar";
import {
  CUSTOM_PERIOD,
  resolvePeriod,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import type {
  ActiveFilters,
  FilterDimension,
} from "../../../operator-kit/app/types/filters";
import type { HistoryFacet } from "~/generated/ordersContract";

/** As granularidades do seletor de período do Histórico, na ordem da tela. */
export const HISTORY_PRESETS = [
  "day",
  "week",
  "month",
  "7d",
  "28d",
  "3m",
  "1y",
] as const;

/**
 * Os recortes do Histórico, na ordem da barra. As opções chegam do servidor (com a
 * contagem); antes disso os campos existem vazios, para a URL já ser lida.
 */
export const HISTORY_FIELDS: readonly { id: string; label: string }[] = [
  { id: "status", label: "Situação" },
  { id: "channel", label: "Canal" },
  { id: "payment", label: "Pagamento" },
  { id: "fulfillment", label: "Recebimento" },
];

export interface HistoryQuery {
  period: PeriodSelection;
  q: string;
  /** Só os pedidos com este produto (o "Abrir os N pedidos" do B.I.). */
  sku: string;
  page: number;
  filters: ActiveFilters;
}

type RouteQueryValue = string | null | (string | null)[] | undefined;

function first(value: RouteQueryValue): string {
  return String((Array.isArray(value) ? value[0] : value) ?? "").trim();
}

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Campos da FilterBar: o que o servidor contou, na ordem declarada aqui. */
export function historyDimensions(
  facets: readonly HistoryFacet[] = [],
): FilterDimension[] {
  return HISTORY_FIELDS.map(({ id, label }) => {
    const facet = facets.find((f) => f.id === id);
    return {
      id,
      label: facet?.label || label,
      type: "multi-select",
      options: facet ? [...facet.options] : [],
    };
  });
}

/** A URL é a fonte: voltar do detalhe devolve a mesma lista, no mesmo período. */
export function historyQueryFromRoute(
  query: Record<string, RouteQueryValue>,
): HistoryQuery {
  const preset = first(query.period);
  const known =
    preset === CUSTOM_PERIOD ||
    (HISTORY_PRESETS as readonly string[]).includes(preset);
  const from = first(query.from);
  const to = first(query.to);
  const period: PeriodSelection = {
    preset: known ? preset : "day",
    from: known && ISO_DAY.test(from) ? from : "",
    to: known && ISO_DAY.test(to) ? to : "",
  };
  const page = Number.parseInt(first(query.page), 10);
  return {
    period,
    q: first(query.q),
    sku: first(query.sku),
    page: Number.isFinite(page) && page > 1 ? page : 1,
    filters: filtersFromQuery(historyDimensions(), query),
  };
}

/** O inverso, sem os padrões: a URL limpa é `/history` (hoje, sem recorte). */
export function routeQueryFromHistory(
  history: HistoryQuery,
): Record<string, string> {
  const out: Record<string, string> = {};
  const { preset, from, to } = history.period;
  if (preset !== "day" || from) out.period = preset;
  if (from) out.from = from;
  if (to) out.to = to;
  if (history.q) out.q = history.q;
  if (history.sku) out.sku = history.sku;
  if (history.page > 1) out.page = String(history.page);
  return { ...out, ...filtersToQuery(historyDimensions(), history.filters) };
}

/**
 * A query do endpoint: período resolvido em datas (nada depois de hoje: o futuro
 * não tem pedido fechado), recortes separados por vírgula.
 */
export function historyApiQuery(
  history: HistoryQuery,
  today: string,
): Record<string, string | number> {
  const range = resolvePeriod(history.period, { today, max: today });
  return {
    date_from: range.date_from,
    date_to: range.date_to,
    ...(history.q ? { q: history.q } : {}),
    ...(history.sku ? { sku: history.sku } : {}),
    ...(history.page > 1 ? { page: history.page } : {}),
    ...filtersToQuery(historyDimensions(), history.filters),
  };
}

/** Cor da situação (o servidor diz o tom; a tela escolhe a classe). */
export function historyStatusClass(tone: string): string {
  if (tone === "success") return "bg-success/10 text-success";
  if (tone === "danger") return "bg-error/10 text-error";
  if (tone === "warning") return "bg-warning/10 text-warning";
  return "bg-muted text-muted-foreground";
}
