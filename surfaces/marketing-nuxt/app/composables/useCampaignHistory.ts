import {
  marketingHistoryHref,
  type MarketingEnvelopeV2,
  type MarketingHistoryActor,
  type MarketingHistoryOutcome,
  type MarketingHistoryPeriod,
  type MarketingHistoryPlatform,
  type MarketingV2HistoryOptions,
} from "~/generated/marketingClient";

const PAGE_SIZE = 25;
const OUTCOMES = new Set<MarketingHistoryOutcome>([
  "not_started",
  "fanout_pending",
  "delivering",
  "succeeded",
  "completed_with_failures",
  "unknown",
  "cancelled",
  "expired",
  "legacy_untracked",
]);
const PLATFORMS = new Set<MarketingHistoryPlatform>([
  "instagram",
  "facebook",
  "google_business",
  "whatsapp",
]);
const ACTORS = new Set<MarketingHistoryActor>(["operator", "automation"]);
const PERIODS = new Set<MarketingHistoryPeriod>(["today", "7d", "30d", "all"]);

export type MarketingHistoryFilterName =
  "outcome" | "platform" | "actor" | "period";

function firstQueryValue(value: unknown): string {
  return Array.isArray(value) ? String(value[0] || "") : String(value || "");
}

function allowedValue<T extends string>(
  value: unknown,
  allowed: Set<T>,
): T | undefined {
  const candidate = firstQueryValue(value);
  return allowed.has(candidate as T) ? (candidate as T) : undefined;
}

export function useCampaignHistory() {
  const route = useRoute();
  const router = useRouter();
  const appended = ref<MarketingEnvelopeV2[]>([]);
  const loadingMore = ref(false);
  const loadMoreError = ref<unknown>(null);

  const filters = computed<MarketingV2HistoryOptions>(() => ({
    outcome: allowedValue(route.query.outcome, OUTCOMES),
    platform: allowedValue(route.query.platform, PLATFORMS),
    actor: allowedValue(route.query.actor, ACTORS),
    period: allowedValue(route.query.period, PERIODS) ?? "all",
  }));
  const filterSignature = computed(() => JSON.stringify(filters.value));
  const requestHref = computed(() =>
    marketingHistoryHref({ ...filters.value, limit: PAGE_SIZE }),
  );
  const {
    data,
    refresh: refreshFirstPage,
    pending,
    error,
  } = useFetch<MarketingEnvelopeV2>(requestHref, {
    key: "marketing-history-v2",
    server: true,
    onResponseError: operatorSessionOnError,
  });

  const firstPage = computed(() =>
    data.value?.data.kind === "history" ? data.value.data : null,
  );
  const appendedPages = computed(() =>
    appended.value.flatMap((envelope) =>
      envelope.data.kind === "history" ? [envelope.data] : [],
    ),
  );
  const announcements = computed(() => [
    ...(firstPage.value?.items ?? []),
    ...appendedPages.value.flatMap((page) => page.items),
  ]);
  const actions = computed(() => [
    ...(data.value?.actions ?? []),
    ...appended.value.flatMap((envelope) => envelope.actions),
  ]);
  const currentPage = computed(
    () => appendedPages.value.at(-1)?.page ?? firstPage.value?.page,
  );
  const shopTimezone = computed(() => data.value?.shop_timezone ?? "UTC");
  const hasActiveFilters = computed(
    () =>
      Boolean(filters.value.outcome) ||
      Boolean(filters.value.platform) ||
      Boolean(filters.value.actor) ||
      filters.value.period !== "all",
  );

  watch(filterSignature, () => {
    appended.value = [];
    loadMoreError.value = null;
    void refreshFirstPage();
  });

  async function loadMore() {
    const cursor = currentPage.value?.next_cursor;
    if (!cursor || loadingMore.value) return;
    loadingMore.value = true;
    loadMoreError.value = null;
    try {
      const envelope = await $fetch<MarketingEnvelopeV2>(
        marketingHistoryHref({
          ...filters.value,
          cursor,
          limit: PAGE_SIZE,
        }),
      );
      if (envelope.data.kind !== "history") {
        throw new Error("unexpected Marketing history projection");
      }
      appended.value.push(envelope);
    } catch (caught) {
      flagMarketingSessionError(caught);
      loadMoreError.value = caught;
    } finally {
      loadingMore.value = false;
    }
  }

  async function refresh() {
    appended.value = [];
    loadMoreError.value = null;
    await refreshFirstPage();
  }

  async function setFilter(name: MarketingHistoryFilterName, value: string) {
    const query = Object.fromEntries(
      Object.entries(route.query).filter(
        ([key]) => key !== "cursor" && key !== name,
      ),
    );
    if (value && !(name === "period" && value === "all")) query[name] = value;
    await router.replace({ query });
  }

  async function clearFilters() {
    const historyKeys = new Set([
      "outcome",
      "platform",
      "actor",
      "period",
      "cursor",
    ]);
    const query = Object.fromEntries(
      Object.entries(route.query).filter(([key]) => !historyKeys.has(key)),
    );
    await router.replace({ query });
  }

  return {
    announcements,
    actions,
    filters,
    hasActiveFilters,
    hasMore: computed(() => currentPage.value?.has_more ?? false),
    shopTimezone,
    loading: pending,
    loadingMore,
    error,
    loadMoreError,
    loadMore,
    refresh,
    setFilter,
    clearFilters,
  };
}
