<script setup lang="ts">
// Entregas — quanto a casa paga à TaOn e quanto o frete dos clientes cobre.
// A corrida é custo da casa (o frete não muda com ela); a projection conta cada
// corrida uma vez, mesmo quando ela leva vários pedidos.
import type { BIDeliveryCostReport } from "~/types/bi";
import {
  readingChartCsv,
  type ReadingChartPoint,
  type ReadingChartSeries,
} from "../../../operator-kit/app/presentation/readingChart";
import { formatMoney, shortDate } from "~/presentation/bi";
import {
  deliveryAnswer,
  estimatedRidesHint,
  ridesHint,
} from "~/presentation/delivery";

const { report, freshness, pending, error, refresh } =
  useBiReport<BIDeliveryCostReport>("delivery-cost");
const { selection, bounds, presets } = useBiWindow();
const shareItems = useBiShareMenuItems();
const { actions: readingActions, label: readingLabel } =
  useReadingPageActions(shareItems);

const dailySeries: ReadingChartSeries[] = [
  { key: "cost", label: "Custo da TaOn", tone: "primary" },
  { key: "fee", label: "Frete cobrado", tone: "neutral" },
];
const dailyPoints = computed<ReadingChartPoint[]>(() =>
  (report.value?.days ?? []).map((row) => ({
    label: shortDate(row.date),
    values: { cost: row.cost_q, fee: row.fee_q },
  })),
);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <OperatorPageHeader
      title="Quanto a entrega custa à casa?"
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
          <ReadFreshness
            inline
            class="ms-auto"
            :metadata="freshness"
            :failed="Boolean(error)"
          />
        </ClientOnly>
      </template>
    </OperatorPageHeader>

    <main class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 pt-3 pb-4">
      <NuxtEmpty
        v-if="pending && !report"
        loading
        variant="naked"
        title="Lendo as entregas"
        description="Custo das corridas da TaOn e frete cobrado no período escolhido."
        data-bi-loading
      />
      <OperatorScreenState
        v-if="error"
        state="error"
        what="as entregas"
        :description="
          report ? 'Os números na tela são os da leitura anterior.' : undefined
        "
        @retry="refresh()"
      />
      <template v-if="report">
        <div
          class="grid grid-cols-2 gap-3 xl:grid-cols-[1.4fr_1fr_1fr_1fr_1fr]"
          data-bi-delivery-tiles
        >
          <OperatorMetric
            title="A resposta"
            :value="deliveryAnswer(report)"
            size="statement"
            class="col-span-2 xl:col-span-1"
          />
          <OperatorMetric
            title="Custo da TaOn"
            :value="formatMoney(report.cost_q)"
            :hint="estimatedRidesHint(report.estimated_rides) || undefined"
          />
          <OperatorMetric
            title="Frete cobrado"
            :value="formatMoney(report.fee_q)"
            hint="O que os clientes pagaram nos pedidos levados"
          />
          <OperatorMetric
            title="Frete menos custo"
            :value="formatMoney(report.balance_q)"
            :tone="report.balance_q < 0 ? 'warning' : undefined"
          />
          <OperatorMetric
            title="Custo por entrega"
            :value="formatMoney(report.cost_per_delivery_q)"
            :hint="ridesHint(report)"
          />
        </div>

        <OperatorReadingCard
          title="Custo e frete por dia"
          description="Dia da chamada do entregador. Uma corrida com várias entregas conta uma vez."
          :csv="
            readingChartCsv('Dia', dailySeries, dailyPoints, { money: true })
          "
        >
          <OperatorReadingChart
            title="Custo da TaOn e frete cobrado por dia"
            axis-label="Dia"
            :series="dailySeries"
            :points="dailyPoints"
            :format="formatMoney"
            empty-title="Nenhuma corrida da TaOn no período"
            empty-description="As corridas aparecem aqui quando a TaOn fecha o valor."
          />
        </OperatorReadingCard>
      </template>
    </main>
  </div>
</template>
