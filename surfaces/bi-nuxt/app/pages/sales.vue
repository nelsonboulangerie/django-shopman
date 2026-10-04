<script setup lang="ts">
// Vendas — faturamento, ticket e mix. Cancelado fica FORA do faturamento e é
// contado à parte (número escondido é número que mente).
import type { BISalesReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  WEEKDAY_LABELS,
  bucketLabel,
  bucketSalesDays,
  delta,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
  sourceConflictLabel,
  salesAnswer,
  sourcesCaption,
} from "~/presentation/bi";

const { report, pending, error, refresh } = useBiReport<BISalesReport>("sales");

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

const weekdaySeries = computed(() =>
  (report.value?.orders_by_weekday ?? []).map((count, index) => ({
    label: WEEKDAY_LABELS[index] ?? String(index),
    value: count,
  })),
);

const channelRows = computed(() =>
  (report.value?.by_channel ?? []).map((row) => ({
    label: row.channel_ref,
    value: row.revenue_q,
    display: formatMoney(row.revenue_q),
    hint: `${formatInt(row.orders)} pedido${row.orders === 1 ? "" : "s"}`,
  })),
);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Quanto vendemos?">
      <template #actions>
        <BiWindowPicker />
        <BiPageMenu />
      </template>
      <template #phone-actions>
        <BiPhoneBell />
      </template>
    </OperatorPageHeader>

    <main class="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
      <BiPageState :pending="pending && !report" :error="error" @retry="refresh()" />
      <template v-if="report">
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
          <BiAnswer :text="salesAnswer(report)" class="col-span-2 xl:col-span-1" />
          <StatTile
            label="Faturamento"
            :value="formatMoneyCompact(report.revenue_total_q)"
            :delta="delta(report.revenue_total_q, report.previous.revenue_total_q)"
          />
          <StatTile
            label="Pedidos"
            :value="formatInt(report.orders_total)"
            :delta="delta(report.orders_total, report.previous.orders_total)"
          />
          <StatTile
            label="Ticket médio"
            :value="formatMoney(report.average_ticket_q)"
            :delta="delta(report.average_ticket_q, report.previous.average_ticket_q)"
          />
          <StatTile label="Cancelados" :value="formatInt(report.cancelled_total)" hint="Fora do faturamento ao lado" />
        </div>

        <BiSection title="Faturamento por dia">
          <template #caption>
            Traço = período anterior; janela longa agrega por semana ou mês
            <template v-if="hasHistory">
              · <span class="mx-0.5 inline-block size-2 rounded-sm bg-primary/35 align-middle"></span>
              barras claras = histórico Yooga
            </template>
          </template>
          <ChartBarSeries :points="revenueSeries" :format="formatMoneyCompact" />
          <p v-if="conflicts.length" class="mt-3 op-micro text-muted-foreground">
            Dia com pedido no Shopman lê só o Shopman, e o histórico daquele dia sai da conta.
            <span v-for="line in conflicts" :key="line" class="block">{{ line }}.</span>
          </p>
        </BiSection>

        <div class="grid gap-3 lg:grid-cols-2">
          <BiSection title="Pedidos por hora" :caption="`Soma do período, hora local${sourcesNote}`">
            <ChartBarSeries :points="hourSeries" :format="(v) => formatInt(v)" :tick-every="4" />
          </BiSection>
          <BiSection title="Pedidos por dia da semana" :caption="`Soma do período${sourcesNote}`">
            <ChartBarSeries :points="weekdaySeries" :format="(v) => formatInt(v)" :tick-every="1" />
          </BiSection>
        </div>

        <div class="grid gap-3 lg:grid-cols-2">
          <BiSection title="Por canal" caption="Faturamento do período">
            <ChartHBarList v-if="channelRows.length" :rows="channelRows" />
            <p v-else class="op-body text-muted-foreground">Sem vendas no período.</p>
          </BiSection>
          <BiSection title="Top produtos" caption="Por faturamento no período">
            <table v-if="report.top_skus.length" class="w-full op-label">
              <thead>
                <tr class="border-b border-border text-left op-eyebrow text-muted-foreground">
                  <th class="pb-2 font-semibold">Produto</th>
                  <th class="pb-2 text-right font-semibold">Qtd</th>
                  <th class="pb-2 text-right font-semibold">Faturamento</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in report.top_skus" :key="row.sku" class="border-b border-border last:border-0">
                  <td class="py-2 pr-2 font-medium text-foreground">{{ row.name }}</td>
                  <td class="py-2 text-right tnum text-foreground">{{ formatQty(row.qty) }}</td>
                  <td class="py-2 text-right tnum text-foreground">{{ formatMoney(row.revenue_q) }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="op-body text-muted-foreground">Sem vendas no período.</p>
          </BiSection>
        </div>
      </template>
    </main>
  </div>
</template>
