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
import { readingChartCsv } from "../../../operator-kit/app/presentation/readingChart";
import type { BISalesReport } from "~/types/bi";
import {
  SALES_COMPARE_LABELS,
  channelIcon,
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
// SSR fazia o título trocar na hidratação ("Quanto vendemos?" → "Vendas").
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

const { report, pending, error, refresh } = useBiReport<BISalesReport>("sales", extra);

// A hora da leitura. A projeção de vendas não traz `generated_at`; a hora é a da
// resposta que chegou a este dispositivo, e só existe no cliente (no SSR o
// `ReadFreshness` não aparece, em vez de dizer "indisponível" e trocar em seguida).
const readAt = ref("");
function stamp() {
  readAt.value = new Date().toISOString();
}
onMounted(() => {
  if (report.value) stamp();
});
watch(pending, (now, before) => {
  if (before && !now && !error.value) stamp();
});
const readMetadata = computed(() => (readAt.value ? { generated_at: readAt.value } : null));

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
// O CSV leva reais, não centavos: quem abre a planilha faz conta com o número.
const revenueCsv = computed(() => {
  const csv = readingChartCsv("Período", revenueSeries.value, revenue.value.points);
  return { ...csv, rows: csv.rows.map(([label, ...cells]) => [label!, ...cells.map((cell) => (typeof cell === "number" ? cell / 100 : cell))]) };
});

const hourPoints = computed(() => toHourPoints(report.value?.orders_by_hour ?? []));
const hourCsv = computed(() => readingChartCsv("Hora", ORDERS_SERIES, hourPoints.value));
const weekdayPoints = computed(() =>
  toWeekdayPoints(report.value?.orders_by_weekday ?? [], report.value?.closed_weekdays ?? []),
);
const weekdayCsv = computed(() => readingChartCsv("Dia da semana", ORDERS_SERIES, weekdayPoints.value));
const hourSeries = ORDERS_SERIES.map((item) => ({ ...item, tone: "info" as const }));
const weekdaySeries = ORDERS_SERIES.map((item) => ({ ...item, tone: "success" as const }));

// Por canal: NuxtTable, a parte do faturamento num NuxtProgress na célula.
const channelRows = computed(() => (report.value ? toChannelRows(report.value) : []));
const channelMax = computed(() => Math.max(1, ...channelRows.value.map((row) => row.revenue_q)));
const topChannel = computed(() => channelRows.value[0] ?? null);
const channelColumns = [
  { accessorKey: "name", header: "Canal", meta: { class: { td: "whitespace-normal font-medium text-highlighted" } } },
  // No celular os pedidos descem para baixo do nome do canal (a coluna sai).
  { accessorKey: "orders", header: "Pedidos", meta: { class: { th: "text-right max-sm:hidden", td: "text-right tnum max-sm:hidden" } } },
  { accessorKey: "revenue_q", header: "Faturamento", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  // No celular a barra sai e a parte fica só em número (a tabela inteira caber na tela).
  { accessorKey: "share", header: "Parte", meta: { class: { th: "text-right sm:w-32", td: "sm:w-32" } } },
];
const channelCsv = computed(() => ({
  header: ["Canal", "Pedidos", "Faturamento", "Parte"],
  rows: channelRows.value.map((row) => [row.name, row.orders, row.revenue_q / 100, row.share]),
}));

// Top produtos: a parte é um NuxtProgress contra o maior. No celular a coluna da barra
// sai (a tabela inteira caber na tela vale mais; a parte segue no CSV e no nome da barra).
const topColumns = [
  { accessorKey: "name", header: "Produto", meta: { class: { td: "whitespace-normal font-medium text-highlighted" } } },
  { id: "qty", header: "Qtd", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "revenue", header: "Faturamento", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "share", header: "Parte", meta: { class: { th: "w-28 max-sm:hidden", td: "w-28 max-sm:hidden" } } },
];
const topMax = computed(() => Math.max(1, ...(report.value?.top_skus ?? []).map((row) => row.revenue_q)));
const topTotal = computed(() => report.value?.revenue_total_q ?? 0);
const topCsv = computed(() => ({
  header: ["Produto", "Quantidade", "Faturamento", "Parte"],
  rows: (report.value?.top_skus ?? []).map((row) => [
    row.name,
    row.qty,
    row.revenue_q / 100,
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

const retryActions = computed(() => [
  { label: "Tentar de novo", icon: "i-lucide-refresh-cw", color: "error" as const, variant: "outline" as const, onClick: () => refresh() },
]);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader :title="isPhone ? 'Vendas' : 'Quanto vendemos?'">
      <template #phone-actions>
        <BiShareButton class="md:hidden" />
      </template>
      <!-- O período mora no `#actions` do tablet para cima; no celular a barra de 56px
           não o comporta ao lado do título, e ele abre a linha de recortes. -->
      <template #actions>
        <div class="flex items-center gap-2 max-md:hidden">
          <OperatorPeriodPicker
            v-model="selection"
            :presets="presets"
            custom
            :today="bounds.today"
            :max="bounds.max"
            :epoch="bounds.epoch"
            label="Período de análise"
          />
          <OperatorReadingPageMenu />
        </div>
      </template>
      <template #filters>
        <div class="w-full md:hidden">
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
        </div>
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
        <ClientOnly>
          <ReadFreshness v-if="report" inline class="ms-auto" :metadata="readMetadata" :failed="Boolean(error)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pt-3 pb-4">
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="Não deu para carregar as vendas."
        :description="report ? 'Os números na tela são os da leitura anterior.' : undefined"
        :actions="retryActions"
        orientation="horizontal"
        role="alert"
        data-bi-error
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
            :format="formatMoneyCompact"
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
            <NuxtTable
              v-if="channelRows.length"
              :data="channelRows"
              :columns="channelColumns"
              :get-row-id="(row) => row.ref"
              caption="Faturamento por canal"
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
            </NuxtTable>
            <NuxtEmpty v-else icon="i-lucide-store" title="Sem vendas no período" variant="naked" />
          </OperatorReadingCard>
          <OperatorReadingCard title="Top produtos" description="Por faturamento no período" :csv="topCsv">
            <NuxtTable
              v-if="report.top_skus.length"
              :data="report.top_skus"
              :columns="topColumns"
              :get-row-id="(row) => row.sku"
              caption="Top produtos por faturamento"
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
            </NuxtTable>
            <NuxtEmpty v-else icon="i-lucide-package" title="Sem vendas no período" variant="naked" />
          </OperatorReadingCard>
        </div>
      </template>
    </main>
  </div>
</template>
