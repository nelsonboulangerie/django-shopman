<script setup lang="ts">
// Histórico — os pedidos que já saíram do quadro (concluídos, cancelados, devolvidos).
//
// Pedido do dono (03/10/2026): "acesso a um histórico dos pedidos concluídos e
// cancelados, com filtro por data, status, forma de pagamento". O período é o seletor
// do kit; os recortes são a FilterBar universal ("+ Filtro" → campo → valores, chip
// que reabre a edição) e tudo mora na URL, então voltar do detalhe devolve a mesma
// lista. Filtrar e paginar é do servidor: a casa tem milhares de pedidos fechados.
import {
  todayIso,
  type PeriodSelection,
} from "../../../operator-kit/app/presentation/dates";
import { useRouteFilters } from "../../../operator-kit/app/composables/useRouteFilters";
import { filterBarActiveFilters } from "../../../operator-kit/app/presentation/filterBar";
import {
  HISTORY_PRESETS,
  historyDimensions,
  historyQueryFromRoute,
  routeQueryFromHistory,
} from "~/presentation/history";
import { ORDERS_HISTORY_TRAIL } from "~/presentation/orderTrails";

useHead({ title: "Histórico" });

const route = useRoute();
const router = useRouter();
const today = ref(todayIso());
const historyQuery = computed(() => historyQueryFromRoute(route.query));
const { history, pending, error, refresh, readMetadata } = useOrderHistory(
  historyQuery,
  today,
);

// O detalhe do pedido volta para cá (e não para o quadro) com o mesmo recorte.
const historyLocation = useState<{
  path: string;
  query: Record<string, string>;
} | null>("orders-history-location", () => null);
watch(
  historyQuery,
  (query) => {
    historyLocation.value = {
      path: "/history",
      query: routeQueryFromHistory(query),
    };
  },
  { immediate: true },
);

const dimensions = computed(() =>
  historyDimensions(history.value?.facets ?? []),
);
const filters = useRouteFilters(dimensions, { resetKeys: ["page"] });

// Celular (abaixo de `sm`, a régua da barra e da toolbar do kit): "Atualizar" vai para
// o ⋯ da barra; o período fica na linha e os recortes no painel "Filtros", com os
// ativos como chips removíveis.
const { belowSm: isNarrow } = useScreen();
const phoneHeaderActions = computed(() =>
  isNarrow.value
    ? [{ label: "Atualizar", icon: "i-lucide-refresh-cw", onSelect: () => void refresh() }]
    : undefined,
);
function clearSku() {
  router.replace({
    query: routeQueryFromHistory({ ...historyQuery.value, sku: "", page: 1 }),
  });
}
const activeFilters = computed(() => [
  ...(historyQuery.value.sku
    ? [{
        key: "sku",
        label: `Produto: ${history.value?.sku_name || historyQuery.value.sku}`,
        remove: clearSku,
      }]
    : []),
  ...filterBarActiveFilters(dimensions.value, filters.value, (next) => {
    filters.value = next;
  }),
]);

const period = computed<PeriodSelection>({
  get: () => historyQuery.value.period,
  set: (next) =>
    router.replace({
      query: routeQueryFromHistory({
        ...historyQuery.value,
        period: next,
        page: 1,
      }),
    }),
});

const search = ref(historyQuery.value.q);
watch(
  () => historyQuery.value.q,
  (q) => {
    if (q !== search.value.trim()) search.value = q;
  },
);
watchDebounced(
  search,
  (q) => {
    if (q.trim() === historyQuery.value.q) return;
    router.replace({
      query: routeQueryFromHistory({
        ...historyQuery.value,
        q: q.trim(),
        page: 1,
      }),
    });
  },
  { debounce: 300 },
);

function goToPage(page: number) {
  router.replace({
    query: routeQueryFromHistory({ ...historyQuery.value, page }),
  });
}

const items = computed(() => history.value?.items ?? []);
// A trilha do anterior/próximo do pedido (fase 2, `OperatorRecordNav`): a página que a
// tela mostra, com o recorte. O detalhe aberto daqui anda dentro destes.
const { remember: rememberTrail } = useRecordTrail(ORDERS_HISTORY_TRAIL);
watch(
  () => items.value.map((item) => item.ref).join("\n"),
  (refs) =>
    rememberTrail(refs ? refs.split("\n") : [], {
      from: route.fullPath,
      label: "Histórico",
    }),
  { immediate: true },
);
type HistoryRow = (typeof items.value)[number];
// Pedido é a chave (fixada, não some); Pagamento é coluna de apoio (some no celular).
// A ordem é a do servidor (paginada): o cabeçalho não ordena só a página da vez.
const historyColumns = [
  { id: "order", header: "Pedido", enableHiding: false },
  { id: "customer", header: "Cliente" },
  { id: "payment", header: "Pagamento", meta: { supporting: true } },
  { id: "total", header: "Total" },
];
function openOrder(ref: string) {
  router.push({ path: `/${encodeURIComponent(ref)}`, query: { from: "history" } });
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Histórico"
      :filters-wrap="false"
      :actions="phoneHeaderActions"
      :active-filters="activeFilters"
    >
      <template #status>
        <span class="hidden op-micro text-muted-foreground lg:inline"
          >Pedidos concluídos e cancelados</span
        >
      </template>
      <template #search>
        <OperatorSuiteSearch
          v-model="search"
          screen-label="filtrando o histórico"
          placeholder="Pedido, nome ou telefone"
          aria-label="Buscar pedido no histórico"
        />
      </template>
      <template #filters>
        <NuxtButton
          v-if="historyQuery.sku"
          type="button"
          :label="`Produto: ${history?.sku_name || historyQuery.sku}`"
          trailing-icon="i-lucide-x"
          color="primary"
          variant="ghost"
          active
          active-variant="soft"
          :aria-label="`Tirar o recorte do produto ${history?.sku_name || historyQuery.sku}`"
          data-history-sku
          @click="clearSku()"
        />
        <FilterBar
          v-model="filters"
          :dimensions="dimensions"
          touch
          class="min-w-0 flex-1"
        />
        <OperatorTableView table-key="orders-history" />
        <!-- No celular, "Atualizar" está no ⋯ da barra (CSS: o servidor já desenha certo). -->
        <NuxtButton
          class="max-sm:hidden"
          icon="i-lucide-refresh-cw"
          label="Atualizar"
          color="neutral"
          variant="outline"
          :loading="pending"
          @click="refresh()"
        />
      </template>
      <!-- O período é o primário da toolbar: no celular fica na linha. -->
      <template #filters-primary>
        <OperatorPeriodPicker
          v-model="period"
          :presets="HISTORY_PRESETS"
          custom
          compact
          :today="today"
          :max="today"
          label="Período do histórico"
        />
      </template>
      <!-- A leitura (total e frescor): no fim da linha na mesa; no celular, numa faixa
           de texto logo abaixo da linha. -->
      <template #filters-end>
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span
            v-if="history"
            class="shrink-0 text-xs text-muted-foreground tabular-nums"
            data-history-total
            >{{ history.total_label }}</span
          >
          <ReadFreshness
            inline
            :metadata="readMetadata"
            :failed="Boolean(error)"
          />
        </div>
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <!-- A tabela da suíte (`OperatorTable`): compacta, com o estado da tela e a forma
           guardada no dispositivo ("Exibir" na toolbar). -->
      <OperatorTable
        :data="items"
        :columns="historyColumns"
        :row-key="(row: HistoryRow) => row.ref"
        :row-label="(row: HistoryRow) => `o pedido ${row.ref}`"
        :on-select="(row: HistoryRow) => openOrder(row.ref)"
        :loading="pending"
        :error="Boolean(error)"
        what="o histórico"
        :error-description="history ? 'Exibindo a última lista carregada.' : ''"
        empty-icon="i-lucide-history"
        empty-title="Nenhum pedido neste recorte."
        :empty-description="history ? `${history.total_label}.` : ''"
        pinned="order"
        view-key="orders-history"
        caption="Pedidos concluídos e cancelados"
        data-history-list
        @retry="refresh()"
      >
        <template #order-cell="{ row }">
          <div :data-history-row="row.original.ref">
            <span class="flex flex-wrap items-center gap-x-2 gap-y-1">
              <NuxtLink
                :to="{
                  path: `/${encodeURIComponent(row.original.ref)}`,
                  query: { from: 'history' },
                }"
                class="font-mono font-semibold tabular-nums hover:underline"
                >{{ row.original.ref }}</NuxtLink
              >
              <NuxtBadge
                :color="
                  row.original.status_tone === 'danger'
                    ? 'error'
                    : row.original.status_tone === 'success'
                      ? 'success'
                      : row.original.status_tone === 'warning'
                        ? 'warning'
                        : 'neutral'
                "
                :label="row.original.status_label"
              />
            </span>
            <span class="block text-xs text-muted-foreground tabular-nums"
              >{{ row.original.closed_display }} ·
              {{ row.original.channel_label }}</span
            >
          </div>
        </template>
        <template #customer-cell="{ row }">
          <span
            class="block min-w-32"
            :class="row.original.customer_label ? '' : 'text-muted-foreground'"
            >{{
              row.original.customer_label || "Cliente não identificado"
            }}</span
          >
          <span
            v-if="row.original.fulfillment_label"
            class="text-xs text-muted-foreground"
            >{{ row.original.fulfillment_label }}</span
          >
        </template>
        <template #payment-cell="{ row }">
          <span class="text-muted-foreground">{{
            row.original.payment_label
          }}</span>
        </template>
        <template #total-cell="{ row }">
          <span class="whitespace-nowrap font-semibold tabular-nums">{{
            row.original.total_display
          }}</span>
        </template>
        <template v-if="history && (history.page > 1 || history.has_next)" #footer>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <span class="op-micro text-muted-foreground tnum">{{
              history.total_label
            }}</span>
            <NuxtPagination
              :page="history.page"
              :total="history.total"
              :items-per-page="history.page_size"
              :disabled="pending"
              aria-label="Páginas"
              @update:page="goToPage"
            />
          </div>
        </template>
      </OperatorTable>
    </section>
  </main>
</template>
