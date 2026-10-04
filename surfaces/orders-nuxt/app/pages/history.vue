<script setup lang="ts">
// Histórico — os pedidos que já saíram do quadro (concluídos, cancelados, devolvidos).
//
// Pedido do dono (03/10/2026): "acesso a um histórico dos pedidos concluídos e
// cancelados, com filtro por data, status, forma de pagamento". O período é o seletor
// do kit; os recortes são a FilterBar universal ("+ Filtro" → campo → valores, chip
// que reabre a edição) e tudo mora na URL, então voltar do detalhe devolve a mesma
// lista. Filtrar e paginar é do servidor: a casa tem milhares de pedidos fechados.
import { todayIso, type PeriodSelection } from "../../../operator-kit/app/presentation/dates";
import { useRouteFilters } from "../../../operator-kit/app/composables/useRouteFilters";
import {
  HISTORY_PRESETS,
  historyDimensions,
  historyQueryFromRoute,
  historyStatusClass,
  routeQueryFromHistory,
} from "~/presentation/history";

useHead({ title: "Histórico" });

const route = useRoute();
const router = useRouter();
const today = ref(todayIso());
const historyQuery = computed(() => historyQueryFromRoute(route.query));
const { history, pending, error, refresh, readMetadata } = useOrderHistory(historyQuery, today);

// O detalhe do pedido volta para cá (e não para o quadro) com o mesmo recorte.
const historyLocation = useState<{ path: string; query: Record<string, string> } | null>("orders-history-location", () => null);
watch(historyQuery, (query) => { historyLocation.value = { path: "/history", query: routeQueryFromHistory(query) }; }, { immediate: true });

const dimensions = computed(() => historyDimensions(history.value?.facets ?? []));
const filters = useRouteFilters(dimensions, { resetKeys: ["page"] });

const period = computed<PeriodSelection>({
  get: () => historyQuery.value.period,
  set: (next) => router.replace({ query: routeQueryFromHistory({ ...historyQuery.value, period: next, page: 1 }) }),
});

const search = ref(historyQuery.value.q);
watch(() => historyQuery.value.q, (q) => { if (q !== search.value.trim()) search.value = q; });
watchDebounced(search, (q) => {
  if (q.trim() === historyQuery.value.q) return;
  router.replace({ query: routeQueryFromHistory({ ...historyQuery.value, q: q.trim(), page: 1 }) });
}, { debounce: 300 });

function goToPage(page: number) {
  router.replace({ query: routeQueryFromHistory({ ...historyQuery.value, page }) });
}

const items = computed(() => history.value?.items ?? []);
const loading = computed(() => pending.value && !history.value);
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Histórico">
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline">Pedidos concluídos e cancelados</span>
      </template>
      <template #search>
        <UiSearchInput v-model="search" placeholder="Pedido, nome ou telefone" aria-label="Buscar pedido no histórico" />
      </template>
      <template #actions>
        <OperatorPeriodPicker
          v-model="period"
          :presets="HISTORY_PRESETS"
          custom
          :today="today"
          :max="today"
          label="Período do histórico"
        />
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </OperatorPageHeader>
    <ReadFreshness :metadata="readMetadata" :failed="Boolean(error)" />

    <section class="min-h-0 flex-1 overflow-auto p-4">
      <div class="mb-3 flex items-center gap-2">
        <FilterBar v-model="filters" :dimensions="dimensions" touch class="min-w-0 flex-1" />
        <span v-if="history" class="shrink-0 text-xs text-muted-foreground tabular-nums" data-history-total>{{ history.total_label }}</span>
      </div>

      <div v-if="error" role="alert" class="mb-3 rounded-md border border-destructive p-3 text-sm">
        {{ httpErrorMessage(error, "Não foi possível carregar o histórico.") }}
        {{ history ? "Exibindo a última lista carregada." : "" }}
        <button type="button" class="ml-2 min-h-11 underline" @click="refresh()">Tentar de novo</button>
      </div>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 6" :key="i" class="h-14 animate-pulse rounded-lg border bg-muted/40"></div>
      </div>

      <ul v-else-if="items.length" class="divide-y rounded-lg border bg-card" data-history-list>
        <li v-for="row in items" :key="row.ref">
          <NuxtLink
            :to="{ path: `/${encodeURIComponent(row.ref)}`, query: { from: 'history' } }"
            class="grid gap-1 px-4 py-3 transition hover:bg-accent sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_auto] sm:items-center sm:gap-4"
            :data-history-row="row.ref"
          >
            <span class="min-w-0">
              <span class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-sm font-semibold tabular-nums">{{ row.ref }}</span>
                <span class="rounded px-1.5 py-0.5 text-xs font-medium" :class="historyStatusClass(row.status_tone)">{{ row.status_label }}</span>
              </span>
              <span class="block text-xs text-muted-foreground tabular-nums">{{ row.closed_display }} · {{ row.channel_label }}</span>
            </span>
            <span class="min-w-0 text-sm">
              <span class="block truncate" :class="row.customer_label ? '' : 'text-muted-foreground'">{{ row.customer_label || "Cliente não identificado" }}</span>
              <span v-if="row.fulfillment_label" class="text-xs text-muted-foreground">{{ row.fulfillment_label }}</span>
            </span>
            <span class="text-sm text-muted-foreground">{{ row.payment_label }}</span>
            <span class="text-sm font-semibold tabular-nums sm:text-right">{{ row.total_display }}</span>
          </NuxtLink>
        </li>
      </ul>

      <p v-else-if="history" class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground" data-history-empty>
        {{ history.total_label }}.
      </p>

      <nav v-if="history && (history.page > 1 || history.has_next)" class="mt-3 flex items-center justify-between" aria-label="Páginas">
        <button
          type="button"
          class="min-h-control rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-40"
          :disabled="history.page <= 1 || pending"
          @click="goToPage(history.page - 1)"
        >
          Anteriores
        </button>
        <span class="text-xs text-muted-foreground tabular-nums">Página {{ history.page }}</span>
        <button
          type="button"
          class="min-h-control rounded-md border px-3 text-sm font-medium transition hover:bg-accent disabled:opacity-40"
          :disabled="!history.has_next || pending"
          @click="goToPage(history.page + 1)"
        >
          Próximos
        </button>
      </nav>
    </section>
  </main>
</template>
