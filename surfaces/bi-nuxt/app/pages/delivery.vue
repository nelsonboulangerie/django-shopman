<script setup lang="ts">
// Entregas — quanto a casa paga pelas entregas, por serviço, e quanto o frete dos
// clientes cobre. A corrida é custo da casa (o frete não muda com ela); a projection
// conta cada corrida uma vez, mesmo quando ela leva vários pedidos. Uma linha por
// serviço (o nome do cadastro) e o total embaixo: comparar os serviços (#3144).
import type { BIDeliveryCostReport, BIDeliveryTimingReport } from "~/types/bi";
import {
  readingChartCsv,
  type ReadingChartPoint,
  type ReadingChartSeries,
} from "../../../operator-kit/app/presentation/readingChart";
import { formatInt, formatMoney, shortDate } from "~/presentation/bi";
import {
  DELIVERY_TOTAL_KEY,
  deliveryAnswer,
  deliveryServiceCsv,
  deliveryServiceRows,
  estimatedRidesHint,
  ridesHint,
  rideAcceptLabel,
  rideMinutes,
  rideTimingCsv,
  rideTimingRows,
  type DeliveryServiceRow,
  type RideTimingRow,
} from "~/presentation/delivery";

const { report, freshness, pending, error, refresh } =
  useBiReport<BIDeliveryCostReport>("delivery-cost");
const { selection, bounds, presets } = useBiWindow();
const shareItems = useBiShareMenuItems();
const { actions: readingActions, label: readingLabel } =
  useReadingPageActions(shareItems);

const dailySeries: ReadingChartSeries[] = [
  { key: "cost", label: "Custo das entregas", tone: "primary" },
  { key: "fee", label: "Frete cobrado", tone: "neutral" },
];
// A tabela por serviço: a coluna numérica alinha à direita; o total fica embaixo,
// então a tabela não reordena pelo cabeçalho (o total subiria).
const NUM = { th: "text-right", td: "text-right tnum" } as const;
const NAME = { td: "font-medium text-highlighted" } as const;
const serviceColumns = [
  { accessorKey: "name", header: "Serviço", meta: { class: NAME } },
  { accessorKey: "rides", header: "Corridas", meta: { class: NUM } },
  { accessorKey: "deliveries", header: "Entregas", meta: { class: NUM } },
  { accessorKey: "cost_q", header: "Custo", meta: { class: NUM } },
  { accessorKey: "fee_q", header: "Frete cobrado", meta: { class: NUM } },
  { accessorKey: "balance_q", header: "Frete menos custo", meta: { class: NUM } },
  { accessorKey: "cost_per_delivery_q", header: "Custo por entrega", meta: { class: NUM } },
];
const serviceRows = computed<DeliveryServiceRow[]>(() => (report.value ? deliveryServiceRows(report.value) : []));
const isTotal = (row: { service: string }) => row.service === DELIVERY_TOTAL_KEY;

// Tempo das corridas (#2467): a mesma janela, outra leitura. Cada corrida uma vez, por
// serviço, em medianas; sem esta leitura, a página de custo segue inteira.
const { report: timing } = useBiReport<BIDeliveryTimingReport>("delivery-timing");
// Minutos numa linha só ("3,5 min", nunca "3,5" em cima de "min"): no celular a tabela rola.
const TIME = { th: "text-right", td: "text-right tnum whitespace-nowrap" } as const;
const timingColumns = [
  { accessorKey: "name", header: "Serviço", meta: { class: NAME } },
  { accessorKey: "rides", header: "Corridas", meta: { class: NUM } },
  { accessorKey: "accept_minutes", header: "Até aceitar", meta: { class: TIME } },
  { accessorKey: "pickup_minutes", header: "Até a coleta", meta: { class: TIME } },
  { accessorKey: "street_minutes", header: "Na rua", meta: { class: TIME } },
  { accessorKey: "total_minutes", header: "Total", meta: { class: TIME } },
];
const timingRows = computed<RideTimingRow[]>(() =>
  timing.value ? rideTimingRows(timing.value, report.value?.services.map((row) => row.service) ?? []) : [],
);

const dailyPoints = computed<ReadingChartPoint[]>(() =>
  (report.value?.days ?? []).map((row) => ({
    label: shortDate(row.date),
    values: { cost: row.cost_q, fee: row.fee_q },
  })),
);
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col" data-compact-page>
    <!-- `data-compact-page`: no celular, a linha do chão (`BiCompactBar`) toma o lugar da
         barra de cima e da linha de recortes; o tempo da leitura fica na faixa logo abaixo. -->
    <BiCompactBar title="Entregas" :options="readingActions">
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
        description="Custo das corridas e frete cobrado no período escolhido."
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
            title="Custo das entregas"
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
          title="Por serviço de entrega"
          description="Um serviço por linha, com o nome do cadastro, e o total embaixo. O pedido levado por dois serviços conta a entrega e o frete no que entregou."
          :csv="serviceRows.length ? deliveryServiceCsv(serviceRows) : undefined"
        >
          <OperatorTable
            in-card
            :data="serviceRows"
            :columns="serviceColumns"
            :row-key="(row) => row.service"
            caption="Custo das entregas por serviço"
            empty-icon="i-lucide-bike"
            empty-title="Nenhuma corrida no período"
            data-bi-delivery-services
          >
            <template #name-cell="{ row }">
              <span :class="isTotal(row.original) ? 'font-semibold text-highlighted' : undefined">{{ row.original.name }}</span>
            </template>
            <template #rides-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ formatInt(row.original.rides) }}</span>
            </template>
            <template #deliveries-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ formatInt(row.original.deliveries) }}</span>
            </template>
            <template #cost_q-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ formatMoney(row.original.cost_q) }}</span>
            </template>
            <template #fee_q-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ formatMoney(row.original.fee_q) }}</span>
            </template>
            <template #balance_q-cell="{ row }">
              <span :class="[row.original.balance_q < 0 ? 'text-warning' : undefined, { 'font-semibold': isTotal(row.original) }]">{{ formatMoney(row.original.balance_q) }}</span>
            </template>
            <template #cost_per_delivery_q-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ formatMoney(row.original.cost_per_delivery_q) }}</span>
            </template>
          </OperatorTable>
        </OperatorReadingCard>

        <OperatorReadingCard
          title="Tempo das corridas"
          description="Mediana, em minutos, contada da chamada. Até aceitar e até a coleta: quanto o entregador leva para aceitar e para pegar as sacolas. Na rua: da coleta à última entrega. Total: da chamada à última entrega. Na chamada: o entregador da casa aceita quando é chamado, sem espera. Uma corrida com várias entregas conta uma vez."
          :csv="timingRows.length ? rideTimingCsv(timingRows) : undefined"
        >
          <OperatorTable
            in-card
            :data="timingRows"
            :columns="timingColumns"
            :row-key="(row) => row.service"
            caption="Tempo das corridas por serviço"
            empty-icon="i-lucide-timer"
            empty-title="Nenhuma corrida no período"
            data-bi-delivery-timing
          >
            <template #name-cell="{ row }">
              <span :class="isTotal(row.original) ? 'font-semibold text-highlighted' : undefined">{{ row.original.name }}</span>
            </template>
            <template #rides-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ formatInt(row.original.rides) }}</span>
            </template>
            <template #accept_minutes-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ rideAcceptLabel(row.original.accept_minutes) }}</span>
            </template>
            <template #pickup_minutes-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ rideMinutes(row.original.pickup_minutes) }}</span>
            </template>
            <template #street_minutes-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ rideMinutes(row.original.street_minutes) }}</span>
            </template>
            <template #total_minutes-cell="{ row }">
              <span :class="{ 'font-semibold': isTotal(row.original) }">{{ rideMinutes(row.original.total_minutes) }}</span>
            </template>
          </OperatorTable>
        </OperatorReadingCard>

        <OperatorReadingCard
          title="Custo e frete por dia"
          description="Dia da chamada do entregador. Uma corrida com várias entregas conta uma vez."
          :csv="
            readingChartCsv('Dia', dailySeries, dailyPoints, { money: true })
          "
        >
          <OperatorReadingChart
            title="Custo das entregas e frete cobrado por dia"
            axis-label="Dia"
            :series="dailySeries"
            :points="dailyPoints"
            :format="formatMoney"
            empty-title="Nenhuma corrida no período"
            empty-description="As corridas aparecem aqui quando o serviço fecha o valor."
          />
        </OperatorReadingCard>
      </template>
    </main>
  </div>
</template>
