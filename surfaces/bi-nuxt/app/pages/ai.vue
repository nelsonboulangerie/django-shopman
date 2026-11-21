<script setup lang="ts">
// IA: quanto a casa gasta com IA (por papel e por modelo), a pauta da conferência antes do
// envio e as respostas que caíram na alternativa segura. Só do Dono, só leitura: o que se
// faz a respeito (responder a pergunta que falta, ajustar a resposta) mora no Admin.
import type {
  ReadingChartPoint,
  ReadingChartSeries,
} from "../../../operator-kit/app/presentation/readingChart";
import { formatInt, shortDate } from "~/presentation/bi";
import {
  aiAnswer,
  conferenceHint,
  csvBrl,
  csvRate,
  csvUsd,
  fallbacksTitle,
  formatPerCall,
  formatSpend,
  perCallSort,
  quoteHint,
  whenLabel,
} from "~/presentation/ai";
import type { BIAiFallback, BIAiGap, BIAiReason, BIAiReport, BIAiSpendRow } from "~/types/bi";

const { report, freshness, pending, error, refresh } = useBiReport<BIAiReport>("ai");
const { selection, bounds, presets } = useBiWindow();
const shareItems = useBiShareMenuItems();
const { actions: readingActions, label: readingLabel } = useReadingPageActions(shareItems);

const spendSeries: ReadingChartSeries[] = [{ key: "cost", label: "Gasto com IA", tone: "primary" }];
const spendPoints = computed<ReadingChartPoint[]>(() =>
  (report.value?.days ?? []).map((row) => ({
    label: shortDate(row.date),
    values: { cost: row.cost_brl_micros ?? 0 },
  })),
);
const formatChartValue = (micros: number) => formatSpend(micros, 0);
const daysCsv = computed(() => ({
  header: ["Dia", "Gasto (US$)", "Gasto (R$)", "PTAX de venda (R$ por US$)", "Dia da PTAX", "Provisória"],
  rows: (report.value?.days ?? []).map((day) => [
    day.date, csvUsd(day.cost_usd_micros), csvBrl(day.cost_brl_micros), day.rate ?? "", day.quoted_on ?? "", day.provisional ? "sim" : "não",
  ]),
}));

const spendColumns = [
  { accessorKey: "purpose_label", header: "Papel", enableSorting: true, meta: { class: { td: "whitespace-normal font-medium text-highlighted" } } },
  { accessorKey: "model", header: "Modelo", enableSorting: true, meta: { class: { th: "max-sm:hidden", td: "max-sm:hidden" } } },
  { accessorKey: "calls", header: "Chamadas", enableSorting: true, meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "per_call", accessorFn: (row: BIAiSpendRow) => perCallSort(row), header: "Por chamada", enableSorting: true, meta: { class: { th: "text-right max-sm:hidden", td: "text-right tnum max-sm:hidden" } } },
  { id: "cost", accessorFn: (row: BIAiSpendRow) => row.cost_usd_micros, header: "Gasto", enableSorting: true, meta: { class: { th: "text-right", td: "text-right tnum" } } },
];
const spendCsv = computed(() => ({
  header: ["Papel", "Modelo", "Chamadas", "Erros", "Recusadas pelo teto", "Gasto (US$)", "Gasto (R$)", "Cotação média (R$ por US$)", "Preço estimado"],
  rows: (report.value?.rows ?? []).map((row) => [
    row.purpose_label, row.model, row.calls, row.errors, row.denied,
    csvUsd(row.cost_usd_micros), csvBrl(row.cost_brl_micros), csvRate(row.cost_brl_micros, row.cost_usd_micros),
    row.estimated ? "sim" : "não",
  ]),
}));

const reasonMax = computed(() => Math.max(1, ...(report.value?.reasons ?? []).map((row) => row.count)));
const reasonColumns = [
  { accessorKey: "label", header: "Motivo", meta: { class: { td: "whitespace-normal font-medium text-highlighted" } } },
  { accessorKey: "count", header: "Respostas", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { id: "share", header: "Parte", meta: { class: { th: "w-28 max-sm:hidden", td: "w-28 max-sm:hidden" } } },
];

const gapColumns = [
  { accessorKey: "question", header: "O cliente perguntou", meta: { class: { td: "whitespace-normal text-highlighted" } } },
  { accessorKey: "count", header: "Vezes", meta: { class: { th: "text-right", td: "text-right tnum" } } },
  { accessorKey: "last_at", header: "Última", meta: { class: { th: "text-right max-sm:hidden", td: "text-right tnum max-sm:hidden" } } },
];

const fallbackColumns = [
  { accessorKey: "at", header: "Quando", meta: { class: { td: "tnum whitespace-nowrap" } } },
  { accessorKey: "customer_text", header: "O cliente disse", meta: { class: { td: "whitespace-normal text-highlighted" } } },
  { accessorKey: "reply_text", header: "A Concierge respondeu", meta: { class: { th: "max-md:hidden", td: "whitespace-normal max-md:hidden" } } },
  { accessorKey: "reasons", header: "Por que reprovou", meta: { class: { td: "whitespace-normal" } } },
];

</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col" data-compact-page>
    <BiCompactBar title="IA" :options="readingActions">
      <template #primary>
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
      </template>
    </BiCompactBar>
    <OperatorPageHeader
      title="Quanto a IA custa e como ela está respondendo?"
      :actions="readingActions"
      :actions-label="readingLabel"
    >
      <template #filters-primary>
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
      </template>
      <template #filters-end>
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
        title="Lendo o uso de IA"
        description="Gasto por papel e modelo, conferência e alternativa segura no período escolhido."
        data-bi-loading
      />
      <OperatorScreenState
        v-if="error"
        state="error"
        what="o uso de IA"
        :description="report ? 'Os números na tela são os da leitura anterior.' : undefined"
        @retry="refresh()"
      />
      <template v-if="report">
        <div class="grid grid-cols-2 gap-3 xl:grid-cols-[1.6fr_1fr_1fr_1fr]" data-bi-ai-tiles>
          <OperatorMetric title="A resposta" :value="aiAnswer(report)" size="statement" class="col-span-2 xl:col-span-1" />
          <OperatorMetric
            title="Gasto com IA"
            :value="formatSpend(report.cost_brl_micros, report.cost_usd_micros)"
            :hint="quoteHint(report)"
          />
          <OperatorMetric
            title="Chamadas"
            :value="formatInt(report.calls)"
            :hint="`${formatInt(report.errors)} com erro, ${formatInt(report.denied)} recusadas pelo teto`"
          />
          <OperatorMetric
            title="Reprovadas na conferência"
            :value="`${formatInt(report.would_fall)} de ${formatInt(report.conferred)}`"
            :hint="conferenceHint(report)"
            :tone="report.would_fall ? 'warning' : undefined"
          />
        </div>

        <OperatorReadingCard
          title="Gasto por papel e modelo"
          description="Cada chamada a um modelo de IA, pelo medidor da casa. Papel é para que a casa usou a IA. Em reais pela PTAX de venda de cada dia."
          :csv="spendCsv"
        >
          <OperatorTable
            in-card
            :data="report.rows"
            :columns="spendColumns"
            :row-key="(row) => `${row.purpose}-${row.model}`"
            caption="Gasto com IA por papel e modelo"
            empty-icon="i-lucide-sparkles"
            empty-title="Nenhuma chamada de IA no período"
            data-bi-ai-spend
          >
            <template #purpose_label-cell="{ row }">
              {{ row.original.purpose_label }}
              <span class="block text-xs font-normal text-muted sm:hidden">{{ row.original.model }}</span>
            </template>
            <template #per_call-cell="{ row }">{{ formatPerCall(row.original.cost_brl_micros, row.original.cost_usd_micros, row.original.calls) }}</template>
            <template #cost-cell="{ row }">
              {{ formatSpend(row.original.cost_brl_micros, row.original.cost_usd_micros) }}
              <span v-if="row.original.estimated" class="block text-xs font-normal text-muted">preço estimado</span>
            </template>
          </OperatorTable>
        </OperatorReadingCard>

        <OperatorReadingCard
          title="Gasto por dia"
          :description="`Dia da chamada. ${quoteHint(report)}.`"
          :csv="daysCsv"
        >
          <OperatorReadingChart
            title="Gasto com IA por dia"
            axis-label="Dia"
            :series="spendSeries"
            :points="spendPoints"
            :format="formatChartValue"
            empty-title="Nenhuma chamada de IA no período"
            empty-description="O gasto aparece aqui a cada chamada que passa pelo medidor."
          />
        </OperatorReadingCard>

        <div class="grid gap-3 xl:grid-cols-2">
          <OperatorReadingCard
            title="A pauta da conferência"
            :description="`Por que as respostas reprovaram, somado. ${conferenceHint(report)}.`"
          >
            <OperatorTable
              in-card
              :data="report.reasons"
              :columns="reasonColumns"
              :row-key="(row: BIAiReason) => row.reason"
              caption="Motivos de reprovação na conferência"
              empty-icon="i-lucide-check-check"
              empty-title="Nenhuma resposta reprovada no período"
              data-bi-ai-reasons
            >
              <template #share-cell="{ row }">
                <NuxtProgress :model-value="row.original.count" :max="reasonMax" size="sm" />
              </template>
            </OperatorTable>
          </OperatorReadingCard>

          <OperatorReadingCard
            title="O que falta à casa"
            description="Perguntas que a Concierge não soube responder e passou para a equipe. Responder uma delas no Admin ensina a Concierge."
          >
            <OperatorTable
              in-card
              :data="report.gaps"
              :columns="gapColumns"
              :row-key="(row: BIAiGap) => row.question"
              caption="Perguntas sem resposta da casa"
              empty-icon="i-lucide-book-check"
              empty-title="A Concierge soube responder tudo no período"
              data-bi-ai-gaps
            >
              <template #question-cell="{ row }">
                <a :href="row.original.admin_url" class="underline decoration-dotted underline-offset-4 hover:text-primary">{{ row.original.question }}</a>
              </template>
              <template #last_at-cell="{ row }">{{ whenLabel(row.original.last_at) }}</template>
            </OperatorTable>
          </OperatorReadingCard>
        </div>

        <OperatorReadingCard
          :title="fallbacksTitle(report)"
          :description="`${formatInt(report.fallbacks.length)} respostas no período, a mais recente primeiro. Texto do cliente redigido.`"
        >
          <OperatorTable
            in-card
            :data="report.fallbacks"
            :columns="fallbackColumns"
            :row-key="(row: BIAiFallback) => `${row.conversation_id}-${row.at}`"
            caption="Respostas reprovadas pela conferência"
            empty-icon="i-lucide-shield-check"
            empty-title="Nenhuma resposta caiu na alternativa segura"
            data-bi-ai-fallbacks
          >
            <template #at-cell="{ row }">
              <a :href="row.original.admin_url" class="underline decoration-dotted underline-offset-4 hover:text-primary">{{ whenLabel(row.original.at) }}</a>
            </template>
            <template #reasons-cell="{ row }">
              <span class="flex flex-wrap gap-1">
                <NuxtBadge v-for="reason in row.original.reasons" :key="reason" color="warning" size="sm">{{ reason }}</NuxtBadge>
              </span>
            </template>
          </OperatorTable>
        </OperatorReadingCard>
      </template>
    </main>
  </div>
</template>
