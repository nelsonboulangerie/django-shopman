<script setup lang="ts">
// Vendas: faturamento, ticket e mix. Cancelado fica FORA do faturamento e é contado à
// parte, em todo dispositivo (número escondido é número que mente).
//
// Peças do kit (PR-B3 do WP-BI-CANON-LAUDO): os números são `OperatorMetric`, os
// quadros são `OperatorReadingCard` (o ⋯ "Exportar CSV deste quadro"), os gráficos são
// `OperatorReadingChart` (eixo, legenda, ponto por mouse, toque e teclado, tabela
// equivalente no SSR) e a hora da leitura é o `ReadFreshness`. Um layout só para
// celular e desktop: a grade muda de colunas, o conteúdo não se duplica.
//
// Recortes: "Comparar com" diz contra o quê os deltas são medidos, e as abas de canal
// recortam TODOS os quadros. Os dois moram na URL (`?compare=`, `?channel=`), junto da
// janela: o link colado abre o mesmo recorte.
import { readingChartCsv, readingMoneyFormat } from "../../../operator-kit/app/presentation/readingChart";
import type { BISalesReport } from "~/types/bi";
import {
  SALES_COMPARE_LABELS,
  channelIcon,
  csvMoney,
  delta,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  rangeCaption,
  salesAnswer,
  sharePercent,
  sourceConflictLabel,
  sourcesCaption,
} from "~/presentation/bi";
import {
  ORDERS_SERIES,
  channelRows as toChannelRows,
  hourPoints as toHourPoints,
  revenueReading,
  revenueSeries as toRevenueSeries,
  weekdayPoints as toWeekdayPoints,
} from "~/presentation/sales";

const route = useRoute();
const router = useRouter();

// O celular só é lido depois de montar: o servidor não sabe a largura, e decidir no
// SSR fazia o tamanho do Faturamento e a altura dos gráficos trocarem na hidratação.
const phoneQuery = useMediaQuery("(max-width: 767.98px)");
const mounted = ref(false);
onMounted(() => {
  mounted.value = true;
});
const isPhone = computed(() => mounted.value && phoneQuery.value);

const { selection, bounds, presets } = useBiWindow();

const channel = computed(() => (typeof route.query.channel === "string" ? route.query.channel : ""));
const compare = computed(() => (route.query.compare === "year" ? "year" : "previous"));
const extra = computed(() => ({
  ...(channel.value ? { channel: channel.value } : {}),
  ...(compare.value !== "previous" ? { compare: compare.value } : {}),
}));

function setQuery(key: "channel" | "compare", value: string, empty: string) {
  const rest = Object.fromEntries(Object.entries(route.query).filter(([name]) => name !== key));
  void router.replace({ query: value && value !== empty ? { ...rest, [key]: value } : rest });
}

const { report, freshness, pending, error, refresh } = useBiReport<BISalesReport>("sales", extra);
const shareItems = useBiShareMenuItems();
const { actions: readingActions, label: readingLabel } = useReadingPageActions(shareItems);

const compareItems = [
  { label: "período anterior", value: "previous" },
  { label: "mesmo período do ano passado", value: "year" },
];
function pickCompare(value: string | undefined) {
  setQuery("compare", value ?? "previous", "previous");
}

const against = computed(() => SALES_COMPARE_LABELS[report.value?.compare ?? "previous"] ?? "período anterior");
const hasHistory = computed(() => (report.value?.historical_days ?? 0) > 0);
const sourcesNote = computed(() => sourcesCaption(report.value?.sources ?? []));
const conflicts = computed(() => (report.value?.source_conflicts ?? []).map(sourceConflictLabel));
const compareCaption = computed(() =>
  report.value ? rangeCaption(report.value.previous.date_from, report.value.previous.date_to) : "",
);

// Faturamento por balde, com o traço tracejado do período de comparação.
const revenueSeries = computed(() => toRevenueSeries(against.value));
const revenue = computed(() => (report.value ? revenueReading(report.value) : { points: [], span: "dia" as const }));
const revenueDescription = computed(() =>
  [
    `Por ${revenue.value.span}, contra o ${against.value}`,
    hasHistory.value ? "Antes do Shopman, os dias vêm do histórico Yooga" : "",
  ]
    .filter(Boolean)
    .join(". ")
    .concat("."),
);
const revenueCsv = computed(() => readingChartCsv("Período", revenueSeries.value, revenue.value.points, { money: true }));

const hourPoints = computed(() => toHourPoints(report.value?.orders_by_hour ?? []));
const hourCsv = computed(() => readingChartCsv("Hora", ORDERS_SERIES, hourPoints.value));
const weekdayPoints = computed(() =>
  toWeekdayPoints(report.value?.orders_by_weekday ?? [], report.value?.closed_weekdays ?? []),
);
const weekdayCsv = computed(() => readingChartCsv("Dia da semana", ORDERS_SERIES, weekdayPoints.value));
const hourSeries = ORDERS_SERIES.map((item) => ({ ...item, tone: "info" as const }));
const weekdaySeries = ORDERS_SERIES.map((item) => ({ ...item, tone: "success" as const }));

// Por canal: OperatorTable (`in-card`, ordena pelo cabeçalho), a parte do faturamento num NuxtProgress na célula.
const channelRows = computed(() => (report.value ? toChannelRows(report.value) : []));
const channelMax = computed(() => Math.max(1, ...channelRows.value.map((row) => row.revenue_q)));
const topChannel = computed(() => channelRows.value[0] ?? null);
const channelColumns = [
  { accessorKey: "name", header: "Canal", enableSorting: true, meta: { class: { td: "whitespace-normal font-medium text-highlighted" } } },
  // No celular os pedidos descem para baixo do nome do canal (a coluna sai).
  { accessorKey: "orders", header: "Pedidos", enableSorting: true, meta: { class: { th: "text-right max-sm:hidden", td: "text-right tnum max-sm:hidden" } } },
  { accessorKey: "revenue_q", header: "Faturamento", enableSorting: true, meta: { class: { th: "text-right", td: "text-right tnum" } } },
  // No celular a barra sai e a parte fica só em número (a tabela inteira caber na tela).
  // A parte é texto ("42%"): ordena pelo faturamento, que é o mesmo ranking.
  { id: "share", accessorFn: (row: { revenue_q: number }) => row.revenue_q, header: "Parte", enableSorting: true, meta: { class: { th: "text-right sm:w-32", td: "sm:w-32" } } },
];
const channelCsv = computed(() => ({
  header: ["Canal", "Pedidos", "Faturamento (R$)", "Parte"],
  rows: channelRows.value.map((row) => [row.name, row.orders, csvMoney(row.revenue_q), row.share]),
}));

// Top produtos: a parte é um NuxtProgress contra o maior. No celular a coluna da barra
// sai (a tabela inteira caber na tela vale mais; a parte segue no CSV e no nome da barra).
const topColumns = [
  { accessorKey: "name", header: "Produto", enableSorting: true, meta: { class: { td: "whitespace-normal font-medium text-highlighted" } } },
  { id: "qty", accessorFn: (row: { qty: string | number }) => Number(row.qty), header: "Qtd", enableSorting: true, meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "revenue", accessorFn: (row: { revenue_q: number }) => row.revenue_q, header: "Faturamento", enableSorting: true, meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "share", header: "Parte", meta: { class: { th: "w-28 max-sm:hidden", td: "w-28 max-sm:hidden" } } },
];
const topMax = computed(() => Math.max(1, ...(report.value?.top_skus ?? []).map((row) => row.revenue_q)));
const topTotal = computed(() => report.value?.revenue_total_q ?? 0);
const topCsv = computed(() => ({
  header: ["Produto", "Quantidade", "Faturamento (R$)", "Parte"],
  rows: (report.value?.top_skus ?? []).map((row) => [
    row.name,
    row.qty,
    csvMoney(row.revenue_q),
    sharePercent(row.revenue_q, topTotal.value),
  ]),
}));

// "Maior canal" leva ao quadro Por canal pelo próximo foco da suíte (linha de foco sob
// o chrome fixo e foco de teclado no quadro), não por um scrollIntoView da tela.
const { reveal } = useNextFocus();
function scrollToChannels() {
  reveal("by-channel");
}

// Recorte por canal: NuxtTabs em pílula, como os recortes do Gestor. `all` é o valor do
// "Todos": as Tabs não aceitam valor vazio, e a URL continua sem `?channel=`.
const channelTabs = computed(() => [
  { value: "all", label: "Todos os canais" },
  ...(report.value?.channels ?? []).map((option) => ({
    value: option.ref,
    label: option.name,
    icon: channelIcon(option.kind),
  })),
]);
function pickChannel(value: string | number) {
  setQuery("channel", value === "all" ? "" : String(value), "");
}
// O canal escolhido é o recorte ativo (o "Comparar com" é a régua, não um recorte).
const activeFilters = computed(() => {
  const channel = report.value?.channel;
  if (!channel || channel === "all") return [];
  const label = channelTabs.value.find((tab) => tab.value === channel)?.label ?? channel;
  return [{ key: "channel", label: `Canal: ${label}`, remove: () => pickChannel("all") }];
});

</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Quanto vendemos?" :actions="readingActions" :actions-label="readingLabel" :active-filters="activeFilters">
      <!-- Celular (regra da toolbar do kit): período e frescor na linha; comparar e canal
           no painel "Filtros", com o canal escolhido como chip removível. -->
      <template #filters-primary>
        <OperatorPeriodPicker
          v-model="selection"
          :presets="presets"
          custom
          compact
          :today="bounds.today"
          :max="bounds.max"
          :epoch="bounds.epoch"
          align="start"
          label="Período de análise"
        />
      </template>
      <template #filters>
        <NuxtFormField v-if="report" label="Comparar com" :help="compareCaption" orientation="horizontal" data-bi-sales-compare>
          <NuxtSelect :model-value="compare" :items="compareItems" class="min-w-48" @update:model-value="pickCompare" />
        </NuxtFormField>
        <!-- No celular as abas não cabem numa linha (cortavam o último canal): a mesma
             escolha vira lista curta. Do `sm` para cima, as abas em pílula. -->
        <NuxtFormField v-if="report" label="Canal" orientation="horizontal" class="sm:hidden">
          <NuxtSelect :model-value="report.channel || 'all'" :items="channelTabs" class="min-w-48" @update:model-value="pickChannel" />
        </NuxtFormField>
        <NuxtTabs
          v-if="report"
          class="max-sm:hidden"
          :model-value="report.channel || 'all'"
          :items="channelTabs"
          :content="false"
          variant="pill"
          aria-label="Recorte por canal"
          data-bi-channel-tabs
          @update:model-value="pickChannel"
        />
      </template>
      <template #filters-end>
        <ClientOnly>
          <ReadFreshness inline class="ms-auto" :metadata="freshness" :failed="Boolean(error)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <OperatorScreenState
        v-if="error"
        state="error"
        what="as vendas"
        :description="report ? 'Os números na tela são os da leitura anterior.' : undefined"
        @retry="refresh()"
      />
      <NuxtEmpty
        v-else-if="pending && !report"
        loading
        title="Carregando as vendas"
        description="Faturamento, pedidos e canais do período escolhido."
        variant="naked"
        data-bi-loading
      />

      <template v-if="report">
        <!-- Os números: no celular o Faturamento sozinho e maior, os outros dois a dois;
             do tablet para cima a resposta numa frase e os quatro números lado a lado. -->
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]" data-bi-sales-tiles>
          <!-- `1.4fr`: a resposta (uma frase) pede mais largura que cada número. -->
          <OperatorMetric
            title="A resposta"
            :value="salesAnswer(report)"
            size="statement"
            class="col-span-2 max-md:hidden xl:col-span-1"
          />
          <OperatorMetric
            title="Faturamento"
            icon="i-lucide-banknote"
            :size="isPhone ? 'hero' : 'figure'"
            :value="formatMoneyCompact(report.revenue_total_q)"
            :delta="delta(report.revenue_total_q, report.previous.revenue_total_q, { base: formatMoneyCompact(report.previous.revenue_total_q), against })"
            class="max-md:col-span-2"
          />
          <OperatorMetric
            title="Pedidos"
            icon="i-lucide-receipt"
            :value="formatInt(report.orders_total)"
            :delta="delta(report.orders_total, report.previous.orders_total, { base: formatInt(report.previous.orders_total), against })"
          />
          <OperatorMetric
            title="Ticket médio"
            icon="i-lucide-ticket"
            :value="formatMoney(report.average_ticket_q)"
            :delta="delta(report.average_ticket_q, report.previous.average_ticket_q, { base: formatMoney(report.previous.average_ticket_q), against })"
          />
          <OperatorMetric
            title="Cancelados"
            icon="i-lucide-circle-x"
            :value="formatInt(report.cancelled_total)"
            hint="Fora do faturamento ao lado"
          />
        </div>

        <NuxtButton
          v-if="topChannel"
          color="neutral"
          variant="outline"
          size="xl"
          trailing-icon="i-lucide-chevron-right"
          block
          class="justify-between text-left md:hidden"
          data-bi-top-channel
          @click="scrollToChannels"
        >
          <span class="min-w-0 flex-1 whitespace-normal">Maior canal: {{ topChannel.name }}, {{ topChannel.share }} do faturamento</span>
        </NuxtButton>

        <!-- `shrink-0`: o cartão corta o que transborda (`overflow-hidden` do tema), e
             filho direto de coluna flex que rola encolheria até zero. -->
        <OperatorReadingCard title="Faturamento por dia" :description="revenueDescription" :csv="revenueCsv" class="shrink-0">
          <OperatorReadingChart
            title="Faturamento por dia"
            kind="comparison"
            axis-label="Período"
            :series="revenueSeries"
            :points="revenue.points"
            :format="readingMoneyFormat"
            :height="isPhone ? 160 : 208"
            :max-ticks="isPhone ? 4 : 6"
            empty-title="Sem vendas no período"
          />
          <template v-if="conflicts.length" #footer>
            <p class="text-xs text-muted">
              Dia com pedido no Shopman lê só o Shopman, e o histórico daquele dia sai da conta.
              <span v-for="line in conflicts" :key="line" class="block">{{ line }}.</span>
            </p>
          </template>
        </OperatorReadingCard>

        <div class="grid items-start gap-3 lg:grid-cols-2">
          <OperatorReadingCard title="Pedidos por hora" :description="`Soma do período, hora local${sourcesNote}`" :csv="hourCsv">
            <OperatorReadingChart
              title="Pedidos por hora"
              axis-label="Hora"
              :series="hourSeries"
              :points="hourPoints"
              :format="formatInt"
              empty-title="Sem pedidos no período"
            />
          </OperatorReadingCard>
          <OperatorReadingCard title="Pedidos por dia da semana" :description="`Soma do período${sourcesNote}`" :csv="weekdayCsv">
            <OperatorReadingChart
              title="Pedidos por dia da semana"
              axis-label="Dia da semana"
              :series="weekdaySeries"
              :points="weekdayPoints"
              :format="formatInt"
              :max-ticks="7"
              empty-title="Sem pedidos no período"
            />
          </OperatorReadingCard>
        </div>

        <div class="grid items-start gap-3 lg:grid-cols-2">
          <OperatorReadingCard
            title="Por canal"
            description="Faturamento do período"
            :csv="channelCsv"
            data-bi-by-channel
            data-focus-target="by-channel"
          >
            <OperatorTable
              in-card
              :data="channelRows"
              :columns="channelColumns"
              :row-key="(row) => row.ref"
              caption="Faturamento por canal"
              empty-icon="i-lucide-store"
              empty-title="Sem vendas no período"
            >
              <template #name-cell="{ row }">
                <span class="inline-flex items-center gap-2" :data-bi-channel-row="row.original.ref">
                  <NuxtIcon :name="row.original.icon" class="size-4 shrink-0 text-muted" aria-hidden="true" />{{ row.original.name }}
                </span>
                <span class="block text-xs font-normal tnum text-muted sm:hidden">
                  {{ formatInt(row.original.orders) }} {{ row.original.orders === 1 ? "pedido" : "pedidos" }}
                </span>
              </template>
              <template #orders-cell="{ row }">{{ formatInt(row.original.orders) }}</template>
              <template #revenue_q-cell="{ row }">{{ formatMoney(row.original.revenue_q) }}</template>
              <template #share-cell="{ row }">
                <span class="flex items-center gap-2">
                  <NuxtProgress
                    class="flex-1 max-sm:hidden"
                    :model-value="row.original.revenue_q"
                    :max="channelMax"
                    size="xs"
                    :aria-label="`${row.original.name}: ${row.original.share} do faturamento`"
                  />
                  <span class="ms-auto text-right text-xs tnum text-muted">{{ row.original.share }}</span>
                </span>
              </template>
            </OperatorTable>
          </OperatorReadingCard>
          <OperatorReadingCard title="Top produtos" description="Por faturamento no período" :csv="topCsv">
            <OperatorTable
              in-card
              :data="report.top_skus"
              :columns="topColumns"
              :row-key="(row) => row.sku"
              caption="Top produtos por faturamento"
              empty-icon="i-lucide-package"
              empty-title="Sem vendas no período"
              data-bi-top-products
            >
              <template #qty-cell="{ row }">{{ formatQty(row.original.qty) }}</template>
              <template #revenue-cell="{ row }">{{ formatMoney(row.original.revenue_q) }}</template>
              <template #share-cell="{ row }">
                <NuxtProgress
                  :model-value="row.original.revenue_q"
                  :max="topMax"
                  size="xs"
                  :aria-label="`${sharePercent(row.original.revenue_q, topTotal)} do faturamento`"
                />
              </template>
            </OperatorTable>
          </OperatorReadingCard>
        </div>
      </template>
    </main>
  </div>
</template>
