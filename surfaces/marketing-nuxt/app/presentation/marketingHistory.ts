import type {
  AnnouncementProjectionV2,
  MarketingActionProjectionV2,
} from "~/types/campaign";
import type { ActiveFilters, FilterDimension } from "../../../operator-kit/app/types/filters";

const TRIGGER_LABELS: Record<
  AnnouncementProjectionV2["facts"]["trigger"],
  string
> = {
  "": "Anúncio",
  production_finished: "Produção concluída",
  low_stock: "Estoque baixo",
  stock_back: "Produto de volta ao estoque",
  product_created: "Produto novo",
  manual: "Disparo manual",
  schedule: "Campanha agendada",
};

const RECOVERY_ACTIONS = new Set<MarketingActionProjectionV2["kind"]>([
  "cancel_announcement",
  "reconcile_unknown_delivery",
  "retry_failed_delivery",
]);

/**
 * "Produção concluída · Baguete tradicional". O nome vem de `options.products`
 * (rótulo por SKU); sem rótulo, o SKU é o que há — e aí a frase diz "Produto",
 * para o gestor saber que está lendo um código.
 */
export function historySubject(
  item: AnnouncementProjectionV2,
  productLabels: Record<string, string> = {},
): string {
  const trigger = TRIGGER_LABELS[item.facts.trigger];
  const sku = item.facts.product_ref.startsWith("product:")
    ? item.facts.product_ref.slice("product:".length)
    : "";
  if (!sku) return trigger;
  const label = productLabels[sku];
  return label ? `${trigger} · ${label}` : `${trigger} · Produto ${sku}`;
}

export function historyActorLabel(
  policy: AnnouncementProjectionV2["decision_actor_policy"],
): string {
  return policy === "operator" ? "Decisão de uma pessoa" : "Disparo automático";
}

export function historyOccurredAt(item: AnnouncementProjectionV2): string {
  return (
    item.settled_at ||
    item.published_at ||
    item.rejected_at ||
    item.approved_at ||
    item.created_at
  );
}

export function historyAnnouncementId(ref: string): number | null {
  const match = /^announcement:(\d+)$/.exec(ref);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

export function historyHref(ref: string): string {
  const id = historyAnnouncementId(ref);
  return id ? `/announcements/${id}` : "/history";
}

export function historyActionsFor(
  actions: MarketingActionProjectionV2[],
  resourceRef: string,
): MarketingActionProjectionV2[] {
  return actions.filter(
    (action) =>
      action.resource_ref === resourceRef &&
      action.enabled &&
      RECOVERY_ACTIONS.has(action.kind),
  );
}

export function historyLinkLabel(
  actions: MarketingActionProjectionV2[],
  resourceRef: string,
): string {
  return historyActionsFor(actions, resourceRef).length
    ? "Abrir e resolver"
    : "Ver resultado";
}

/**
 * A data curta da lista (v4: lista calma): "hoje às 09:52", "ontem às 18:10",
 * "01/10 às 08:00", e o ano só quando não é este. A data por extenso cansava a lista.
 */
export function historyWhen(instant: string, timeZone: string, nowMs = Date.now()): string {
  const ms = Date.parse(instant);
  if (!Number.isFinite(ms)) return "";
  const parts = (value: number) => {
    const formatted = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(value));
    const get = (type: string) => formatted.find((part) => part.type === type)?.value ?? "";
    return { year: get("year"), day: `${get("year")}-${get("month")}-${get("day")}`, short: `${get("day")}/${get("month")}`, time: `${get("hour")}:${get("minute")}` };
  };
  const at = parts(ms);
  const today = parts(nowMs);
  if (at.day === today.day) return `hoje às ${at.time}`;
  if (at.day === parts(nowMs - 86_400_000).day) return `ontem às ${at.time}`;
  const date = at.year === today.year ? at.short : `${at.short}/${at.year}`;
  return `${date} às ${at.time}`;
}

/** Os quatro recortes de Enviados (os mesmos valores e a mesma URL de antes). */
export type HistoryFilterName = "outcome" | "platform" | "period" | "actor";

export interface HistoryFilter {
  name: HistoryFilterName;
  label: string;
  options: Array<{ value: string; label: string }>;
}

/**
 * Cada recorte é uma escolha única no painel de filtros da suíte (`OperatorFilterPanel`).
 * "Sem recorte" é a ausência do valor (some da URL), não uma opção da lista.
 */
export const HISTORY_FILTERS: readonly HistoryFilter[] = [
  {
    name: "outcome",
    label: "Situação",
    options: [
      { value: "not_started", label: "Ainda não iniciada" },
      { value: "fanout_pending", label: "Preparando destinos" },
      { value: "delivering", label: "Em andamento" },
      { value: "succeeded", label: "Concluída" },
      { value: "completed_with_failures", label: "Concluída com falhas" },
      { value: "unknown", label: "Resultado incerto" },
      { value: "cancelled", label: "Cancelada" },
      { value: "expired", label: "Expirada" },
      { value: "legacy_untracked", label: "Registro antigo" },
    ],
  },
  {
    name: "platform",
    label: "Plataforma",
    options: [
      { value: "instagram", label: "Instagram" },
      { value: "facebook", label: "Facebook" },
      { value: "google_business", label: "Google" },
      { value: "whatsapp", label: "WhatsApp" },
    ],
  },
  {
    name: "period",
    label: "Criado em",
    options: [
      { value: "today", label: "Hoje" },
      { value: "7d", label: "Últimos 7 dias" },
      { value: "30d", label: "Últimos 30 dias" },
    ],
  },
  {
    name: "actor",
    label: "Origem da decisão",
    options: [
      { value: "operator", label: "Pessoa" },
      { value: "automation", label: "Automação" },
    ],
  },
];

type HistoryFilterValues = Partial<Record<HistoryFilterName, string | undefined | null>>;

/** As dimensões do painel de filtros: uma escolha única por recorte. */
export function historyDimensions(): FilterDimension[] {
  return HISTORY_FILTERS.map((filter) => ({
    id: filter.name,
    label: filter.label,
    type: "single-select",
    options: filter.options,
  }));
}

/** O recorte de hoje na forma do painel (o "Qualquer período" do backend não é recorte). */
export function historyPanelFilters(current: HistoryFilterValues): ActiveFilters {
  const out: ActiveFilters = {};
  for (const filter of HISTORY_FILTERS) {
    const value = current[filter.name];
    if (value && filter.options.some((option) => option.value === value)) out[filter.name] = [value];
  }
  return out;
}

/** O recorte do painel de volta para a URL: os quatro de uma vez (vazio sai dela). */
export function historyFiltersFromPanel(active: ActiveFilters): Record<HistoryFilterName, string> {
  return Object.fromEntries(
    HISTORY_FILTERS.map((filter) => [filter.name, active[filter.name]?.[0] ?? ""]),
  ) as Record<HistoryFilterName, string>;
}

/**
 * Os recortes fora do padrão, um chip cada ("Criado em: Últimos 7 dias"). Valor que a
 * lista não conhece não vira chip (o composable já filtra a URL antes).
 */
export function historyActiveFilters(
  current: HistoryFilterValues,
): Array<{ name: HistoryFilterName; label: string }> {
  return HISTORY_FILTERS.flatMap((filter) => {
    const option = filter.options.find((entry) => entry.value === current[filter.name]);
    return option ? [{ name: filter.name, label: `${filter.label}: ${option.label}` }] : [];
  });
}
