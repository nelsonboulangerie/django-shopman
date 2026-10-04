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

function scrollToChannels() {
  document.querySelector("[data-bi-by-channel]")?.scrollIntoView({ behavior: "smooth", block: "start" });
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
        <label
          class="relative inline-flex min-h-control items-center gap-2 rounded-md border border-border bg-card px-3 op-label transition focus-within:ring-2 focus-within:ring-ring/40 hover:bg-accent"
          data-bi-sales-compare
        >
          <Icon name="lucide:git-compare-arrows" class="size-4 text-muted-foreground" aria-hidden="true" />
          <span class="font-normal text-muted-foreground">Comparar com:</span>
          <span class="font-semibold">{{ against }}</span>
          <span class="hidden tnum font-normal text-muted-foreground sm:inline">({{ compareCaption }})</span>
          <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
          <select
            :value="compare"
            class="absolute inset-0 cursor-pointer opacity-0"
            aria-label="Comparar com"
            @change="setQuery('compare', ($event.target as HTMLSelectElement).value, 'previous')"
          >
            <option value="previous">período anterior</option>
            <option value="year">mesmo período do ano passado</option>
          </select>
        </label>
        <span class="mx-1 h-6 w-px bg-border" aria-hidden="true" />
        <UiFilterChip :active="!report.channel" :aria-pressed="!report.channel" data-bi-channel-chip="" @click="setQuery('channel', '', '')">
          <template #icon><Icon v-if="!report.channel" name="lucide:check" class="size-4 text-primary" aria-hidden="true" /></template>
          Todos os canais
        </UiFilterChip>
        <UiFilterChip
          v-for="option in report.channels"
          :key="option.ref"
          :active="report.channel === option.ref"
          :aria-pressed="report.channel === option.ref"
          :data-bi-channel-chip="option.ref"
          @click="setQuery('channel', report.channel === option.ref ? '' : option.ref, '')"
        >
          <template #icon><Icon :name="channelIcon(option.kind)" class="size-4" aria-hidden="true" /></template>
          {{ option.name }}
        </UiFilterChip>
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
          <button
            v-if="topChannel"
            type="button"
            class="flex min-h-12 items-center gap-2 rounded-lg border border-border bg-card px-4 text-left op-label"
            data-bi-top-channel
            @click="scrollToChannels"
          >
            <span class="min-w-0 flex-1">Maior canal: <b>{{ topChannel.name }}</b>, {{ topChannel.share }} do faturamento</span>
            <Icon name="lucide:chevron-right" class="size-5 text-muted-foreground" aria-hidden="true" />
          </button>
        </div>

        <!-- Tablet e desktop (v3): a resposta e os quatro números, cada um com a pílula. -->
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

        <div class="grid gap-3 lg:grid-cols-2">
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

        <div class="grid gap-3 lg:grid-cols-2">
          <BiSection title="Por canal" caption="Faturamento do período" data-bi-by-channel>
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
                <div class="mt-1 h-2 rounded-full bg-muted">
                  <div class="h-2 rounded-full bg-primary" :style="{ width: `${(row.revenue_q / channelMax) * 100}%` }" />
                </div>
              </li>
            </ul>
            <p v-else class="op-body text-muted-foreground">Sem vendas no período.</p>
          </BiSection>
          <BiSection title="Top produtos" caption="Por faturamento no período">
            <template #aside>
              <BiChartMenu title="Top produtos" :header="['Produto', 'Quantidade', 'Faturamento', 'Parte']" :rows="topCsv" />
            </template>
            <table v-if="report.top_skus.length" class="w-full op-label">
              <thead>
                <tr class="border-b border-border text-left op-eyebrow text-muted-foreground">
                  <th class="pb-2 font-semibold">Produto</th>
                  <th class="pb-2 text-right font-semibold">Qtd</th>
                  <th class="pb-2 text-right font-semibold">Faturamento</th>
                  <th class="w-24 pb-2 pl-3 font-semibold">Parte</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in report.top_skus" :key="row.sku" class="border-b border-border last:border-0">
                  <td class="py-2 pr-2 font-medium text-foreground">{{ row.name }}</td>
                  <td class="py-2 text-right tnum text-foreground">{{ formatQty(row.qty) }}</td>
                  <td class="py-2 text-right tnum text-foreground">{{ formatMoney(row.revenue_q) }}</td>
                  <td class="py-2 pl-3">
                    <div class="h-1.5 rounded-full bg-muted" role="img" :aria-label="`${sharePercent(row.revenue_q, topTotal)} do faturamento`">
                      <div class="h-1.5 rounded-full bg-primary" :style="{ width: `${(row.revenue_q / topMax) * 100}%` }" />
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-else class="op-body text-muted-foreground">Sem vendas no período.</p>
          </BiSection>
        </div>
      </template>
      <BiSwipeHint />
    </main>
  </div>
</template>
