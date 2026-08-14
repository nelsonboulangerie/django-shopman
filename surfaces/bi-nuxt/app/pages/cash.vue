<script setup lang="ts">
// Caixa — quebra por dia e por operador, sangrias/suprimentos e o mix de
// pagamento consolidado pelo fechamento. `closings_missing` fica à vista:
// buraco declarado, nunca silenciado.
import type { BICashReport } from "~/types/bi";
import {
  BUCKET_SPAN_LABELS,
  bucketLabel,
  bucketRows,
  delta,
  formatInt,
  formatMoney,
} from "~/presentation/bi";

const { report, pending, error, refresh } = useBiReport<BICashReport>("cash");

const differenceSeries = computed(() =>
  bucketRows(report.value?.days ?? []).map((bucket) => {
    const shifts = bucket.rows.reduce((sum, d) => sum + d.shifts, 0);
    const sangria = bucket.rows.reduce((sum, d) => sum + d.sangria_q, 0);
    const suprimento = bucket.rows.reduce((sum, d) => sum + d.suprimento_q, 0);
    return {
      label: bucketLabel(bucket.date, bucket.span),
      value: bucket.rows.reduce((sum, d) => sum + d.difference_q, 0),
      detail: [
        BUCKET_SPAN_LABELS[bucket.span],
        `${formatInt(shifts)} turno${shifts === 1 ? "" : "s"}`,
        `sangria ${formatMoney(sangria)}`,
        `suprimento ${formatMoney(suprimento)}`,
      ]
        .filter(Boolean)
        .join(" · "),
    };
  }),
);

const methodRows = computed(() =>
  (report.value?.payment_methods ?? []).map((row) => ({
    label: row.method,
    value: row.amount_q,
    display: formatMoney(row.amount_q),
  })),
);

const sangriaTotal = computed(() =>
  (report.value?.days ?? []).reduce((sum, day) => sum + day.sangria_q, 0),
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
        <StatTile
          label="Turnos fechados"
          :value="formatInt(report.shifts_total)"
          :delta="delta(report.shifts_total, report.previous.shifts_total)"
        />
        <StatTile
          label="Quebra acumulada"
          :value="formatMoney(report.difference_total_q)"
          :delta="{ text: `Anterior ${formatMoney(report.previous.difference_total_q)}`, tone: 'neutral' }"
          hint="Contado − esperado; negativo = faltou"
        />
        <StatTile
          label="Dias sem fechamento"
          :value="formatInt(report.closings_missing)"
          hint="Na janela; o mix de pagamento só cobre dias fechados"
        />
        <StatTile
          label="Sangrias"
          :value="formatMoney(sangriaTotal)"
          hint="Retiradas do caixa no período"
        />
      </div>

      <section class="rounded-md border border-border bg-card p-3">
        <h2 class="text-lg font-semibold text-foreground">Quebra de caixa por dia</h2>
        <p class="mb-3 text-xs text-muted-foreground">Acima do zero sobrou; abaixo faltou</p>
        <ChartDivergingBars :points="differenceSeries" :format="formatMoney" />
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Por operador</h2>
          <p class="mb-3 text-xs text-muted-foreground">Quebra acumulada no período</p>
          <table v-if="report.by_operator.length" class="w-full text-sm">
            <thead>
              <tr class="border-b border-border text-left text-xs font-medium text-muted-foreground">
                <th class="pb-2 font-medium">Operador</th>
                <th class="pb-2 text-right font-medium">Turnos</th>
                <th class="pb-2 text-right font-medium">Quebra</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in report.by_operator" :key="row.operator" class="border-b border-border last:border-0">
                <td class="py-2 pr-2 font-medium text-foreground">{{ row.operator }}</td>
                <td class="py-2 text-right tabular-nums text-foreground">{{ formatInt(row.shifts) }}</td>
                <td
                  class="py-2 text-right tabular-nums"
                  :class="row.difference_q < 0 ? 'font-semibold text-destructive' : 'text-foreground'"
                >
                  {{ formatMoney(row.difference_q) }}
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="text-sm text-muted-foreground">Nenhum turno fechado no período.</p>
        </section>
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Meios de pagamento</h2>
          <p class="mb-3 text-xs text-muted-foreground">Consolidado dos fechamentos do período</p>
          <ChartHBarList v-if="methodRows.length" :rows="methodRows" />
          <p v-else class="text-sm text-muted-foreground">Nenhum fechamento na janela ainda.</p>
        </section>
      </div>
    </template>
  </main>
</template>
