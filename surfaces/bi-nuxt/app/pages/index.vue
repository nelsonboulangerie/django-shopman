<script setup lang="ts">
// Produção — a âncora do B.I.: série do que saiu do forno, rendimento e o
// tempo REAL de forno (só o par armar→Concluir mede; a cobertura declara o
// resto — ADR-021 §4).
import type { BIProductionReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  bucketLabel,
  bucketRows,
  coverageLabel,
  delta,
  formatInt,
  formatMinutes,
  formatQty,
} from "~/presentation/bi";

const { report, pending, error, refresh } = useBiReport<BIProductionReport>("production");

const sum = (values: (string | number)[]) => values.reduce((total: number, v) => total + Number(v), 0);

const finishedSeries = computed(() => {
  const previous = report.value?.previous.finished_by_day ?? [];
  const rows = (report.value?.days ?? []).map((day, index) => ({
    ...day,
    prev_finished: Number(previous[index] ?? 0),
  }));
  return bucketRows(rows).map((bucket) => ({
    label: bucketLabel(bucket.date, bucket.span),
    value: sum(bucket.rows.map((d) => d.finished)),
    previous: sum(bucket.rows.map((d) => d.prev_finished)),
    detail: [
      BUCKET_SPAN_LABELS[bucket.span],
      `previsto ${formatQty(String(sum(bucket.rows.map((d) => d.planned))))}`,
      `perda ${formatQty(String(sum(bucket.rows.map((d) => d.loss))))}`,
    ]
      .filter(Boolean)
      .join(" · "),
  }));
});

const yieldSeries = computed(() =>
  bucketRows(report.value?.days ?? []).map((bucket) => {
    const planned = sum(bucket.rows.map((d) => d.planned));
    const finished = sum(bucket.rows.map((d) => d.finished));
    return {
      label: bucketLabel(bucket.date, bucket.span),
      value: planned ? Math.round((finished * 100) / planned) : 0,
      detail: planned
        ? [
            BUCKET_SPAN_LABELS[bucket.span],
            `cheio ${formatQty(String(sum(bucket.rows.map((d) => d.full_price))))}`,
            `desconto ${formatQty(String(sum(bucket.rows.map((d) => d.discounted))))}`,
          ]
            .filter(Boolean)
            .join(" · ")
        : "sem produção",
    };
  }),
);

const lossTotal = computed(() =>
  (report.value?.days ?? []).reduce((sum, day) => sum + Number(day.loss), 0),
);

const finishedTotal = computed(() =>
  (report.value?.days ?? []).reduce((sum, day) => sum + Number(day.finished), 0),
);

// Rendimento do período inteiro: realizado ÷ previsto (previsto = realizado + perda).
const yieldPercent = (finished: number, loss: number) =>
  finished + loss ? Math.round((finished * 100) / (finished + loss)) : 0;

const yieldTotal = computed(() => yieldPercent(finishedTotal.value, lossTotal.value));
const yieldPrevious = computed(() => {
  const prev = report.value?.previous;
  if (!prev) return 0;
  return yieldPercent(Number(prev.finished_total), Number(prev.loss_total));
});

const ovenRows = (rows: BIProductionReport["oven_time_by_recipe"]) =>
  rows.map((row) => ({
    label: row.label,
    value: Number(row.avg_minutes),
    display: formatMinutes(row.avg_minutes),
    hint: `p90 ${formatMinutes(row.p90_minutes)} · armado ${formatMinutes(row.avg_planned_minutes)} · ${formatInt(row.runs)} ${row.runs === 1 ? "medição" : "medições"}`,
  }));
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
        <StatTile
          label="Fornadas fechadas"
          :value="formatInt(report.batches_finished)"
          :delta="delta(report.batches_finished, report.previous.batches_finished)"
        />
        <StatTile
          label="Tempo de forno medido"
          :value="`${report.oven_coverage_percent}%`"
          :hint="coverageLabel(report.batches_measured, report.batches_finished)"
        />
        <StatTile
          label="Perda no período"
          :value="formatInt(lossTotal)"
          :delta="delta(lossTotal, Number(report.previous.loss_total), { downIsGood: true })"
          hint="Unidades que não saíram do forno"
        />
        <StatTile
          label="Rendimento do período"
          :value="`${yieldTotal}%`"
          :delta="delta(yieldTotal, yieldPrevious)"
          hint="Realizado ÷ previsto"
        />
      </div>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Produção por dia</h2>
        <p class="mb-3 text-xs text-muted-foreground">
          Unidades que saíram do forno; traço = período anterior; o tooltip traz previsto e perda
        </p>
        <ChartBarSeries :points="finishedSeries" :format="(v) => formatInt(v)" />
      </section>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Rendimento por dia</h2>
        <p class="mb-3 text-xs text-muted-foreground">Realizado ÷ previsto, em %</p>
        <ChartBarSeries :points="yieldSeries" :format="(v) => `${v}%`" />
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Tempo de forno por receita</h2>
          <p class="mb-3 text-xs text-muted-foreground">
            Média medida (armar → Concluir) · {{ coverageLabel(report.batches_measured, report.batches_finished) }}
          </p>
          <ChartHBarList v-if="report.oven_time_by_recipe.length" :rows="ovenRows(report.oven_time_by_recipe)" />
          <p v-else class="text-sm text-muted-foreground">Nenhuma medição no período ainda. O timer do forno alimenta este quadro.</p>
        </section>
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Tempo de forno por forno</h2>
          <p class="mb-3 text-xs text-muted-foreground">Fornadas sem posição declarada ficam de fora deste corte</p>
          <ChartHBarList v-if="report.oven_time_by_oven.length" :rows="ovenRows(report.oven_time_by_oven)" />
          <p v-else class="text-sm text-muted-foreground">Nenhuma medição com forno atribuído no período.</p>
        </section>
      </div>
    </template>
  </main>
</template>
