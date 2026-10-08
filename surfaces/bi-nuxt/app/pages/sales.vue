<script setup lang="ts">
// Vendas: faturamento, ticket e mix (prévias `depois-bi-vendas` no desktop e
// `depois-marketing-bi-celular` (b) no celular). Cancelado fica FORA do faturamento e
// é contado à parte (número escondido é número que mente).
//
// Linha 2 (pinos 5 e 6): "Comparar com" diz contra o quê os deltas são medidos, e os
// chips de canal recortam TODOS os quadros. Os dois moram na URL (`?compare=`,
// `?channel=`), junto da janela: o link colado abre o mesmo recorte.
import type { BISalesReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  SALES_COMPARE_LABELS,
  WEEKDAY_LABELS,
  bucketLabel,
  bucketSalesDays,
  channelIcon,
  delta,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
  rangeCaption,
  salesAnswer,
  sharePercent,
  sourceConflictLabel,
  sourcesCaption,
} from "~/presentation/bi";

const route = useRoute();
const router = useRouter();
// No celular a barra de 56px leva o nome da seção (a pergunta inteira não cabe ao lado
// do período e do compartilhar, prévia `depois-marketing-bi-celular` (b)).
const isPhone = useMediaQuery("(max-width: 767.98px)");

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

const against = computed(() => SALES_COMPARE_LABELS[report.value?.compare ?? "previous"] ?? "período anterior");
const hasHistory = computed(() => (report.value?.historical_days ?? 0) > 0);
const sourcesNote = computed(() => sourcesCaption(report.value?.sources ?? []));
const conflicts = computed(() => (report.value?.source_conflicts ?? []).map(sourceConflictLabel));

const revenueSeries = computed(() => {
  const previous = report.value?.previous.revenue_by_day ?? [];
  const rows = (report.value?.days ?? []).map((day, index) => ({
    ...day,
    prev_revenue_q: previous[index] ?? 0,
  }));
  return bucketSalesDays(rows).map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    value: bucket.revenue_q,
    previous: bucket.prev_revenue_q,
    muted: bucket.source === "yooga",
    detail: [
      BUCKET_SPAN_LABELS[bucket.span],
      `${formatInt(bucket.orders)} pedido${bucket.orders === 1 ? "" : "s"}`,
      bucket.source === "yooga" ? "histórico Yooga" : "",
    ]
      .filter(Boolean)
      .join(" · "),
  }));
});

const hourSeries = computed(() =>
  (report.value?.orders_by_hour ?? []).map((count, hour) => ({
    label: hourLabel(hour),
    value: count,
  })),
);

const weekdaySeries = computed(() => {
  const closed = new Set(report.value?.closed_weekdays ?? []);
  return (report.value?.orders_by_weekday ?? []).map((count, index) => ({
    label: WEEKDAY_LABELS[index] ?? String(index),
    value: count,
    closed: closed.has(index),
  }));
});

const channelRows = computed(() => {
  const total = report.value?.revenue_total_q ?? 0;
  return (report.value?.by_channel ?? []).map((row) => ({
    ref: row.channel_ref,
    name: row.name,
    icon: channelIcon(row.kind),
    orders: row.orders,
    revenue_q: row.revenue_q,
    share: sharePercent(row.revenue_q, total),
  }));
});
const channelMax = computed(() => Math.max(1, ...channelRows.value.map((row) => row.revenue_q)));
const topChannel = computed(() => channelRows.value[0] ?? null);

// Top produtos: NuxtTable (a tabela é o corpo inteiro do quadro e o tema do kit a
// integra ao cartão, sem padding). A parte é um NuxtProgress contra o maior.
const topColumns = [
  { accessorKey: "name", header: "Produto", meta: { class: { td: "font-medium text-foreground" } } },
  { id: "qty", header: "Qtd", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "revenue", header: "Faturamento", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "share", header: "Parte", meta: { class: { th: "w-28", td: "w-28" } } },
];
const topMax = computed(() => Math.max(1, ...(report.value?.top_skus ?? []).map((row) => row.revenue_q)));
const topTotal = computed(() => report.value?.revenue_total_q ?? 0);

const compareCaption = computed(() =>
  report.value ? rangeCaption(report.value.previous.date_from, report.value.previous.date_to) : "",
);

const revenueCsv = computed(() => revenueSeries.value.map((point) => [point.label, formatMoney(point.value), formatMoney(point.previous ?? 0)]));
const hourCsv = computed(() => hourSeries.value.map((point) => [point.label, point.value]));
const weekdayCsv = computed(() => weekdaySeries.value.map((point) => [point.label, point.value]));
const channelCsv = computed(() => channelRows.value.map((row) => [row.name, row.orders, formatMoney(row.revenue_q), row.share]));
const topCsv = computed(() =>
  (report.value?.top_skus ?? []).map((row) => [row.name, formatQty(row.qty), formatMoney(row.revenue_q), sharePercent(row.revenue_q, topTotal.value)]),
);

// "Maior canal" leva ao quadro Por canal pelo próximo foco da suíte (linha de foco sob
// o chrome fixo e foco de teclado no quadro), não por um scrollIntoView da tela.
const { reveal } = useNextFocus();
function scrollToChannels() {
  reveal("by-channel");
}

// Recorte por canal: NuxtTabs em pílula, como os recortes do Gestor. Cabe nas Tabs
// porque é escolha de UM canal e o "Todos os canais" está na fileira: o recorte se
// desliga tocando "Todos os canais" (antes, tocar de novo o chip aceso também
// desligava; o "Todos" continua a um toque). `all` é o valor do "Todos": as Tabs não
// aceitam valor vazio, e a URL continua sem `?channel=` nesse caso.
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
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader :title="isPhone ? 'Vendas' : 'Quanto vendemos?'">
      <template #status>
        <BiLiveStatus :pending="pending" :error="error" />
      </template>
      <template #actions>
        <BiWindowPicker class="max-md:hidden" />
        <div class="max-md:hidden"><BiPageMenu /></div>
      </template>
      <template #phone-actions>
        <BiPeriodChip />
        <BiShareButton />
      </template>
      <template v-if="report" #filters>
        <!-- Lista curta: UiNativeSelect visível, a peça do kit por decisão do dono
             (operator-kit/README.md, "lista curta"). Antes era um seletor nativo
             invisível sobre um rótulo; as datas da comparação seguem ao lado. -->
        <label class="inline-flex items-center gap-2 op-label text-muted-foreground" data-bi-sales-compare>
          Comparar com
          <UiNativeSelect :value="compare" @change="setQuery('compare', ($event.target as HTMLSelectElement).value, 'previous')">
            <option value="previous">período anterior</option>
            <option value="year">mesmo período do ano passado</option>
          </UiNativeSelect>
          <span class="hidden op-micro tnum sm:inline">{{ compareCaption }}</span>
        </label>
        <NuxtSeparator orientation="vertical" class="h-6" />
        <NuxtTabs
          :model-value="report.channel || 'all'"
          :items="channelTabs"
          :content="false"
          variant="pill"
          aria-label="Recorte por canal"
          data-bi-channel-tabs
          @update:model-value="pickChannel"
        />
      </template>
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <BiPageState :pending="pending && !report" :error="error" @retry="refresh()" />
      <template v-if="report">
        <!-- Celular (v3 b): o Faturamento sozinho e grande, com o "antes"; Pedidos e
             Ticket lado a lado; o gráfico compacto; o atalho "Maior canal". -->
        <div class="flex flex-col gap-3 md:hidden" data-bi-sales-phone>
          <StatTile
            label="Faturamento"
            size="hero"
            :value="formatMoneyCompact(report.revenue_total_q)"
            :delta="delta(report.revenue_total_q, report.previous.revenue_total_q, { against })"
            :hint="report.previous.revenue_total_q ? `antes: ${formatMoneyCompact(report.previous.revenue_total_q)}` : ''"
          />
          <div class="grid grid-cols-2 gap-3">
            <StatTile
              label="Pedidos"
              :value="formatInt(report.orders_total)"
              :delta="delta(report.orders_total, report.previous.orders_total, { base: formatInt(report.previous.orders_total), against: '' })"
            />
            <StatTile
              label="Ticket médio"
              :value="formatMoney(report.average_ticket_q)"
              :delta="delta(report.average_ticket_q, report.previous.average_ticket_q, { base: formatMoney(report.previous.average_ticket_q), against: '' })"
            />
          </div>
          <BiSection title="Faturamento por dia" :caption="report.closed_weekdays.includes(6) ? 'domingo fechado' : ''">
            <ChartBarSeries :points="revenueSeries" :format="formatMoneyCompact" height="compact" />
          </BiSection>
          <NuxtButton
            v-if="topChannel"
            color="neutral"
            variant="outline"
            trailing-icon="i-lucide-chevron-right"
            block
            class="min-h-12 justify-between text-left"
            data-bi-top-channel
            @click="scrollToChannels"
          >
            <span class="min-w-0 flex-1 op-label">Maior canal: <b>{{ topChannel.name }}</b>, {{ topChannel.share }} do faturamento</span>
          </NuxtButton>
        </div>

        <!-- Tablet e desktop (v3): a resposta e os quatro números, cada um com a pílula. -->
        <!-- `xl:grid-cols-[1.4fr_1fr...]`: a resposta (uma frase) pede mais largura que cada número. -->
        <div class="hidden gap-3 md:grid md:grid-cols-2 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]" data-bi-sales-tiles>
          <BiAnswer :text="salesAnswer(report)" class="md:col-span-2 xl:col-span-1" />
          <StatTile
            label="Pedidos"
            icon="lucide:receipt"
            :value="formatInt(report.orders_total)"
            :delta="delta(report.orders_total, report.previous.orders_total, { base: formatInt(report.previous.orders_total), against })"
          />
          <StatTile
            label="Faturamento"
            icon="lucide:banknote"
            :value="formatMoneyCompact(report.revenue_total_q)"
            :delta="delta(report.revenue_total_q, report.previous.revenue_total_q, { base: formatMoneyCompact(report.previous.revenue_total_q), against })"
          />
          <StatTile
            label="Ticket médio"
            icon="lucide:ticket"
            :value="formatMoney(report.average_ticket_q)"
            :delta="delta(report.average_ticket_q, report.previous.average_ticket_q, { base: formatMoney(report.previous.average_ticket_q), against })"
          />
          <StatTile label="Cancelados" icon="lucide:circle-x" :value="formatInt(report.cancelled_total)" hint="Fora do faturamento ao lado" />
        </div>

        <BiSection title="Faturamento por dia" class="hidden md:block">
          <template #caption>
            Janela longa agrega por semana ou mês.<template v-if="report.closed_weekdays.includes(6)"> Domingo: fechado.</template>
          </template>
          <template #aside>
            <div class="flex items-center gap-3">
              <ul class="flex flex-wrap items-center gap-x-3 gap-y-1 op-micro text-muted-foreground" aria-label="Legenda" data-bi-legend>
                <li class="inline-flex items-center gap-1.5"><span class="size-2 rounded-full bg-primary" aria-hidden="true" />Shopman</li>
                <li v-if="hasHistory" class="inline-flex items-center gap-1.5"><span class="size-2 rounded-full bg-primary/35" aria-hidden="true" />Histórico Yooga</li>
                <li class="inline-flex items-center gap-1.5"><span class="h-0.5 w-3 bg-foreground/70" aria-hidden="true" />{{ against.charAt(0).toUpperCase() + against.slice(1) }}</li>
              </ul>
              <BiChartMenu title="Faturamento por dia" :header="['Dia', 'Faturamento', 'Comparação']" :rows="revenueCsv" />
            </div>
          </template>
          <ChartBarSeries :points="revenueSeries" :format="formatMoneyCompact" />
          <p v-if="conflicts.length" class="mt-3 op-micro text-muted-foreground">
            Dia com pedido no Shopman lê só o Shopman, e o histórico daquele dia sai da conta.
            <span v-for="line in conflicts" :key="line" class="block">{{ line }}.</span>
          </p>
        </BiSection>

        <div class="grid items-start gap-3 lg:grid-cols-2">
          <BiSection title="Pedidos por hora" :caption="`Soma do período, hora local${sourcesNote}`">
            <template #aside>
              <BiChartMenu title="Pedidos por hora" :header="['Hora', 'Pedidos']" :rows="hourCsv" />
            </template>
            <ChartBarSeries :points="hourSeries" :format="(v) => formatInt(v)" :tick-every="4" tone="info" />
          </BiSection>
          <BiSection title="Pedidos por dia da semana" :caption="`Soma do período${sourcesNote}`">
            <template #aside>
              <BiChartMenu title="Pedidos por dia da semana" :header="['Dia', 'Pedidos']" :rows="weekdayCsv" />
            </template>
            <ChartBarSeries :points="weekdaySeries" :format="(v) => formatInt(v)" :tick-every="1" tone="success" />
          </BiSection>
        </div>

        <div class="grid items-start gap-3 lg:grid-cols-2">
          <BiSection title="Por canal" caption="Faturamento do período" data-bi-by-channel data-focus-target="by-channel">
            <template #aside>
              <BiChartMenu title="Por canal" :header="['Canal', 'Pedidos', 'Faturamento', 'Parte']" :rows="channelCsv" />
            </template>
            <ul v-if="channelRows.length" class="flex flex-col gap-3">
              <li v-for="row in channelRows" :key="row.ref" class="min-w-0" :data-bi-channel-row="row.ref">
                <div class="flex items-center gap-2 op-label">
                  <Icon :name="row.icon" class="size-4 text-muted-foreground" aria-hidden="true" />
                  <span class="font-semibold text-foreground">{{ row.name }}</span>
                  <span class="op-micro text-muted-foreground">{{ formatInt(row.orders) }} {{ row.orders === 1 ? "pedido" : "pedidos" }}</span>
                  <span class="ml-auto font-semibold tnum">{{ formatMoney(row.revenue_q) }}</span>
                  <span class="w-12 text-right op-micro tnum text-muted-foreground">{{ row.share }}</span>
                </div>
                <NuxtProgress
                  class="mt-1"
                  :model-value="row.revenue_q"
                  :max="channelMax"
                  size="sm"
                  :aria-label="`${row.name}: ${row.share} do faturamento`"
                />
              </li>
            </ul>
            <p v-else class="op-body text-muted-foreground">Sem vendas no período.</p>
          </BiSection>
          <BiSection title="Top produtos" caption="Por faturamento no período">
            <template #aside>
              <BiChartMenu title="Top produtos" :header="['Produto', 'Quantidade', 'Faturamento', 'Parte']" :rows="topCsv" />
            </template>
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
            <p v-else class="op-body text-muted-foreground">Sem vendas no período.</p>
          </BiSection>
        </div>
      </template>
      <BiSwipeHint />
    </main>
  </div>
</template>
