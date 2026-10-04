<script setup lang="ts">
// Clientes — a distribuição RFM que o guestman JÁ mantém (CustomerInsight;
// o B.I. só lê) e a chegada de clientes novos por semana.
import type { BICustomersReport } from "~/types/bi";
import { customersAnswer, formatInt, formatMoney, shortDate } from "~/presentation/bi";

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
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Os clientes estão voltando?">
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
          <BiAnswer :text="customersAnswer(report)" class="col-span-2 xl:col-span-1" />
          <StatTile label="Clientes" :value="formatInt(report.customers_total)" />
          <StatTile
            label="Com histórico analisado"
            :value="formatInt(report.with_insight)"
            hint="Clientes com recência, frequência e valor já calculados"
          />
          <StatTile label="Em risco de sumir" :value="formatInt(report.at_risk)" :tone="report.at_risk ? 'warning' : undefined" />
          <StatTile label="Ticket médio por cliente" :value="formatMoney(report.average_ticket_q)" />
        </div>

        <div class="grid gap-3 lg:grid-cols-2">
          <BiSection title="Segmentos de cliente" caption="Recência, frequência e valor, calculados pelo CRM">
            <ChartHBarList v-if="segmentRows.length" :rows="segmentRows" />
            <p v-else class="op-body text-muted-foreground">Nenhum cliente com perfil calculado ainda.</p>
          </BiSection>
          <BiSection title="Clientes novos por semana" caption="Primeiro cadastro dentro do período">
            <ChartBarSeries v-if="weeklySeries.length" :points="weeklySeries" :format="(v) => formatInt(v)" :tick-every="1" />
            <p v-else class="op-body text-muted-foreground">Nenhum cliente novo no período.</p>
          </BiSection>
        </div>
      </template>
    </main>
  </div>
</template>
