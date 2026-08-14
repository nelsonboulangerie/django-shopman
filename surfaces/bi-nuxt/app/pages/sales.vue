<script setup lang="ts">
// Vendas — faturamento, ticket e mix. Cancelado fica FORA do faturamento e é
// contado à parte (número escondido é número que mente).
import type { BISalesReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  WEEKDAY_LABELS,
  bucketLabel,
  bucketSalesDays,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatQty,
  hourLabel,
} from "~/presentation/bi";

const { report, pending, error, refresh } = useBiReport<BISalesReport>("sales");

const hasHistory = computed(() => (report.value?.historical_days ?? 0) > 0);

const revenueSeries = computed(() =>
  bucketSalesDays(report.value?.days ?? []).map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    value: bucket.revenue_q,
    muted: bucket.source === "yooga",
    detail: [
      BUCKET_SPAN_LABELS[bucket.span],
      `${formatInt(bucket.orders)} pedido${bucket.orders === 1 ? "" : "s"}`,
      bucket.source === "yooga" ? "histórico Yooga" : "",
    ]
      .filter(Boolean)
      .join(" · "),
  })),
);

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
  <main class="flex flex-1 flex-col gap-4 p-4">
    <p v-if="pending" class="text-sm text-muted-foreground">Carregando…</p>
    <div v-else-if="error" class="flex items-center gap-3">
      <p class="text-sm text-muted-foreground">Não deu para carregar os números.</p>
      <button type="button" class="h-9 rounded-md border border-border px-3 text-sm font-medium" @click="refresh()">
        Tentar de novo
      </button>
    </div>
    <template v-else-if="report">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Pedidos" :value="formatInt(report.orders_total)" />
        <StatTile label="Faturamento" :value="formatMoneyCompact(report.revenue_total_q)" />
        <StatTile label="Ticket médio" :value="formatMoney(report.average_ticket_q)" />
        <StatTile
          label="Cancelados"
          :value="formatInt(report.cancelled_total)"
          hint="fora do faturamento acima"
        />
      </div>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Faturamento por dia</h2>
        <p class="mb-3 text-xs text-muted-foreground">
          o tooltip traz os pedidos do ponto; janela longa agrega por semana ou mês
          <template v-if="hasHistory">
            · <span class="mx-0.5 inline-block h-2 w-2 rounded-sm bg-foreground/25 align-middle"></span>
            barras claras = histórico Yooga
          </template>
        </p>
        <ChartBarSeries :points="revenueSeries" :format="formatMoneyCompact" />
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Pedidos por hora</h2>
          <p class="mb-3 text-xs text-muted-foreground">soma do período, hora local</p>
          <ChartBarSeries :points="hourSeries" :format="(v) => formatInt(v)" :tick-every="4" />
        </section>
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Pedidos por dia da semana</h2>
          <p class="mb-3 text-xs text-muted-foreground">soma do período</p>
          <ChartBarSeries :points="weekdaySeries" :format="(v) => formatInt(v)" :tick-every="1" />
        </section>
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Por canal</h2>
          <p class="mb-3 text-xs text-muted-foreground">faturamento do período</p>
          <ChartHBarList v-if="channelRows.length" :rows="channelRows" />
          <p v-else class="text-sm text-muted-foreground">Sem vendas no período.</p>
        </section>
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Top produtos</h2>
          <p class="mb-3 text-xs text-muted-foreground">por faturamento no período</p>
          <table v-if="report.top_skus.length" class="w-full text-sm">
            <thead>
              <tr class="border-b border-border text-left text-xs font-medium text-muted-foreground">
                <th class="pb-2 font-medium">Produto</th>
                <th class="pb-2 text-right font-medium">Qtd</th>
                <th class="pb-2 text-right font-medium">Faturamento</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.top_skus" :key="row.sku" class="border-b border-border last:border-0">
                <td class="max-w-0 truncate py-2 pr-2 font-medium text-foreground">{{ row.name }}</td>
                <td class="py-2 text-right tabular-nums text-foreground">{{ formatQty(row.qty) }}</td>
                <td class="py-2 text-right tabular-nums text-foreground">{{ formatMoney(row.revenue_q) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-sm text-muted-foreground">Sem vendas no período.</p>
        </section>
      </div>
    </template>
  </main>
</template>
