<script setup lang="ts">
// Clientes — a distribuição RFM que o guestman JÁ mantém (CustomerInsight;
// o B.I. só lê) e a chegada de clientes novos por semana.
//
// Peças do kit (PR-B5 do WP-BI-CANON-LAUDO): período compacto e ⋯ da página no
// cabeçalho, frescor da leitura no lugar do selo "On", números em `OperatorMetric`,
// gráficos em `OperatorReadingChart` dentro do `OperatorReadingCard` (com CSV).
import type { BICustomersReport } from "~/types/bi";
import {
  readingChartCsv,
  type ReadingChartPoint,
  type ReadingChartSeries,
} from "../../../operator-kit/app/presentation/readingChart";
import { customersAnswer, formatInt, formatMoney, shortDate } from "~/presentation/bi";

const { report, freshness, pending, error, refresh } = useBiReport<BICustomersReport>("customers");
const { selection, bounds, presets } = useBiWindow();
const shareItems = useBiShareMenuItems();

const errorActions = computed(() => [
  { label: "Tentar de novo", icon: "i-lucide-refresh-cw", color: "error" as const, variant: "outline" as const, onClick: () => refresh() },
]);

// Rótulos pt-BR dos segmentos (espelham guestman RFM_SEGMENTS).
const SEGMENT_LABELS: Record<string, string> = {
  champion: "Campeões",
  loyal_customer: "Clientes fiéis",
  recent_customer: "Clientes recentes",
  regular: "Regulares",
  at_risk: "Em risco",
  lost: "Perdidos",
};

const segmentSeries: ReadingChartSeries[] = [{ key: "customers", label: "Clientes", tone: "primary" }];
const segmentPoints = computed<ReadingChartPoint[]>(() =>
  (report.value?.segments ?? []).map((row) => ({
    label: SEGMENT_LABELS[row.segment] ?? row.segment,
    values: { customers: row.customers },
  })),
);

const weeklySeries: ReadingChartSeries[] = [{ key: "new_customers", label: "Clientes novos", tone: "primary" }];
const weeklyPoints = computed<ReadingChartPoint[]>(() =>
  (report.value?.new_by_week ?? []).map((row) => ({
    label: shortDate(row.week_start),
    values: { new_customers: row.new_customers },
  })),
);

const formatCount = (value: number) => formatInt(value);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader title="Os clientes estão voltando?">
      <template #actions>
        <OperatorReadingPageMenu :items="shareItems" />
      </template>
      <template #filters>
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
        <ClientOnly>
          <ReadFreshness inline class="ms-auto" :metadata="freshness" :failed="Boolean(error)" />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <NuxtEmpty
        v-if="pending && !report"
        loading
        variant="naked"
        title="Lendo os clientes"
        description="Segmentos e clientes novos do período escolhido."
        data-bi-loading
      />
      <NuxtAlert
        v-if="error"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="Não deu para carregar os clientes."
        :description="report ? 'Os números na tela são os da leitura anterior.' : undefined"
        :actions="errorActions"
        orientation="horizontal"
        role="alert"
        data-bi-error
      />
      <template v-if="report">
        <!-- `xl:grid-cols-[1.4fr_1fr...]`: a resposta (uma frase) pede mais largura que cada número. -->
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]">
          <OperatorMetric
            title="A resposta"
            :value="customersAnswer(report)"
            size="statement"
            class="col-span-2 xl:col-span-1"
          />
          <OperatorMetric title="Clientes" :value="formatInt(report.customers_total)" />
          <OperatorMetric
            title="Com histórico analisado"
            :value="formatInt(report.with_insight)"
            hint="Clientes com recência, frequência e valor já calculados"
          />
          <OperatorMetric
            title="Em risco de sumir"
            :value="formatInt(report.at_risk)"
            :tone="report.at_risk ? 'warning' : undefined"
          />
          <OperatorMetric title="Ticket médio por cliente" :value="formatMoney(report.average_ticket_q)" />
        </div>

        <div class="grid items-start gap-3 lg:grid-cols-2">
          <OperatorReadingCard
            title="Segmentos de cliente"
            description="Recência, frequência e valor, calculados pelo CRM"
            :csv="readingChartCsv('Segmento', segmentSeries, segmentPoints)"
          >
            <OperatorReadingChart
              title="Clientes por segmento"
              axis-label="Segmento"
              :series="segmentSeries"
              :points="segmentPoints"
              :format="formatCount"
              empty-title="Nenhum cliente com perfil calculado ainda"
              empty-description="O CRM calcula o perfil depois das primeiras compras."
            />
          </OperatorReadingCard>
          <OperatorReadingCard
            title="Clientes novos por semana"
            description="Primeiro cadastro dentro do período; a semana começa na segunda"
            :csv="readingChartCsv('Semana começando em', weeklySeries, weeklyPoints)"
          >
            <OperatorReadingChart
              title="Clientes novos por semana"
              axis-label="Semana começando em"
              :series="weeklySeries"
              :points="weeklyPoints"
              :format="formatCount"
              empty-title="Nenhum cliente novo no período"
            />
          </OperatorReadingCard>
        </div>
      </template>
    </main>
  </div>
</template>
