import type {
  AnnouncementProjectionV2,
  MarketingActionProjectionV2,
} from "~/types/campaign";

const TRIGGER_LABELS: Record<
  AnnouncementProjectionV2["facts"]["trigger"],
  string
> = {
  "": "Anúncio",
  production_finished: "Fornada concluída",
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
 * "Fornada concluída · Baguete tradicional". O nome vem de `options.products`
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
  return policy === "operator"
    ? "Decisão de uma pessoa"
    : "Automação ou origem sem autoria registrada";
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
