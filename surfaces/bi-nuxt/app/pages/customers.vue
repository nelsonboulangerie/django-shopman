<script setup lang="ts">
// Clientes — a distribuição RFM que o guestman JÁ mantém (CustomerInsight;
// o B.I. só lê) e a chegada de clientes novos por semana.
import type { BICustomersReport } from "~/types/bi";
import { formatInt, formatMoney, shortDate } from "~/presentation/bi";

const { report, pending, error, refresh } = useBiReport<BICustomersReport>("customers");

// Rótulos pt-BR dos segmentos (espelham guestman RFM_SEGMENTS).
const SEGMENT_LABELS: Record<string, string> = {
  champion: "Campeões",
  loyal_customer: "Clientes fiéis",
  recent_customer: "Clientes recentes",
  regular: "Regulares",
  at_risk: "Em risco",
  lost: "Perdidos",
};

const segmentRows = computed(() =>
  (report.value?.segments ?? []).map((row) => ({
    label: SEGMENT_LABELS[row.segment] ?? row.segment,
    value: row.customers,
    display: formatInt(row.customers),
  })),
);

const weeklySeries = computed(() =>
  (report.value?.new_by_week ?? []).map((row) => ({
    label: shortDate(row.week_start),
    value: row.new_customers,
    detail: "semana começando na segunda",
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
        <StatTile label="Clientes" :value="formatInt(report.customers_total)" />
        <StatTile
          label="Com histórico analisado"
          :value="formatInt(report.with_insight)"
          hint="Perfil RFM calculado pelo CRM"
        />
        <StatTile label="Em risco de sumir" :value="formatInt(report.at_risk)" />
        <StatTile label="Ticket médio por cliente" :value="formatMoney(report.average_ticket_q)" />
      </div>

      <div class="grid gap-4 lg:grid-cols-2">
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Segmentos RFM</h2>
          <p class="mb-3 text-xs text-muted-foreground">Recência, frequência e valor, calculados pelo CRM</p>
          <ChartHBarList v-if="segmentRows.length" :rows="segmentRows" />
          <p v-else class="text-sm text-muted-foreground">Nenhum cliente com perfil calculado ainda.</p>
        </section>
        <section class="rounded-md border border-border bg-card p-3">
          <h2 class="text-lg font-semibold text-foreground">Clientes novos por semana</h2>
          <p class="mb-3 text-xs text-muted-foreground">Primeiro cadastro dentro do período</p>
          <ChartBarSeries v-if="weeklySeries.length" :points="weeklySeries" :format="(v) => formatInt(v)" :tick-every="1" />
          <p v-else class="text-sm text-muted-foreground">Nenhum cliente novo no período.</p>
        </section>
      </div>
    </template>
  </main>
</template>
