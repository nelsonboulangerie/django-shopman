<script setup lang="ts">
// Produção, segunda leitura: os lotes no período (a janela de análise). Antes morava
// embaixo do "Sobrou ou faltou", com um segundo controle de tempo no meio da página
// (laudo F08); agora é a segunda aba da tela (`?view=lots`), e o cabeçalho da aba
// tem UM tempo, o período, no lugar de sempre (a página monta o cabeçalho; este
// componente é o corpo). A série do que saiu do forno, o aproveitamento e o tempo REAL de
// forno (só o par armar→Concluir mede; a cobertura declara o resto, ADR-021 §4).
//
// Gráficos e quadros são as peças de leitura do kit: o ponto em leitura serve mouse,
// toque e teclado, e o "Dia a dia" mostra o previsto e a perda que antes só existiam
// no `:hover` da barra (laudo F01).
import type { TableColumn } from "#ui/types";
import type { BIProductionReport } from "~/types/bi";
import { coverageLabel, delta, formatInt, startedAssumedHint } from "~/presentation/bi";
import {
  FINISHED_SERIES,
  OVEN_FOCUS_ROWS,
  YIELD_SERIES,
  bucketAxisLabel,
  finishedPoints,
  formatPercentValue,
  ovenCsv,
  ovenRows,
  ovenScale,
  productionBuckets,
  productionDayRows,
  productionDaysCsv,
  showAllLabel,
  yieldPercent,
  yieldPoints,
  type OvenRow,
  type ProductionDayRow,
} from "~/presentation/production";
import { readingChartCsv } from "../../../operator-kit/app/presentation/readingChart";

const { report, pending, error, refresh } = useBiReport<BIProductionReport>("production");


// No celular o eixo comporta quatro rótulos de data sem que se encostem.
const isPhone = useMediaQuery("(max-width: 639.98px)", { ssrWidth: 1280 });
const maxTicks = computed(() => (isPhone.value ? 4 : 6));

const buckets = computed(() => (report.value ? productionBuckets(report.value) : []));
const axisLabel = computed(() => bucketAxisLabel(buckets.value));
const finished = computed(() => finishedPoints(buckets.value));
const yields = computed(() => yieldPoints(buckets.value));
const dayRows = computed(() => productionDayRows(buckets.value));

const lossTotal = computed(() => (report.value?.days ?? []).reduce((total, d) => total + Number(d.loss), 0));
const finishedTotal = computed(() => (report.value?.days ?? []).reduce((total, d) => total + Number(d.finished), 0));
const startedTotal = computed(() => (report.value?.days ?? []).reduce((total, d) => total + Number(d.started), 0));
// Aproveitamento do período inteiro: realizado ÷ previsto (UX-PROD-AF).
const yieldTotal = computed(() => yieldPercent(finishedTotal.value, startedTotal.value) ?? 0);
const yieldPrevious = computed(() => {
  const prev = report.value?.previous;
  if (!prev) return 0;
  return yieldPercent(Number(prev.finished_total), Number(prev.started_total)) ?? 0;
});

const dayColumns = computed<TableColumn<ProductionDayRow>[]>(() => [
  { accessorKey: "label", header: axisLabel.value },
  { accessorKey: "started", header: "Previsto", meta: { class: { th: "text-end", td: "text-end tnum" } } },
  // No celular o realizado sai da tabela (o gráfico "Produção por dia" já o lê ponto a ponto).
  { accessorKey: "finished", header: "Realizado", meta: { class: { th: "text-end max-sm:hidden", td: "text-end tnum max-sm:hidden" } } },
  { accessorKey: "loss", header: "Perda", meta: { class: { th: "text-end", td: "text-end tnum" } } },
  { accessorKey: "yield", header: "Aproveitamento", meta: { class: { th: "text-end max-sm:hidden", td: "text-end tnum max-sm:hidden" } } },
  { accessorKey: "fullPrice", header: "A preço cheio", meta: { class: { th: "text-end max-md:hidden", td: "text-end tnum max-md:hidden" } } },
  { accessorKey: "discounted", header: "Com desconto", meta: { class: { th: "text-end max-md:hidden", td: "text-end tnum max-md:hidden" } } },
]);

// Tempo de forno: tabela com a média em barra (NuxtProgress) e o "Ver todas" (laudo F20).
const ovenColumns = (first: string): TableColumn<OvenRow>[] => [
  { accessorKey: "label", header: first },
  { id: "average", header: "Média" },
  { accessorKey: "p90", header: "p90", meta: { class: { th: "text-end max-sm:hidden", td: "text-end tnum max-sm:hidden" } } },
  { accessorKey: "planned", header: "Armado", meta: { class: { th: "text-end max-sm:hidden", td: "text-end tnum max-sm:hidden" } } },
  { accessorKey: "runs", header: "Medições", meta: { class: { th: "text-end", td: "text-end tnum" } } },
];
const recipeColumns = ovenColumns("Receita");
const ovenColumnsByOven = ovenColumns("Forno");
const allRecipes = ref(false);
const recipes = computed(() => ovenRows(report.value?.oven_time_by_recipe ?? []));
const recipesShown = computed(() => (allRecipes.value ? recipes.value : recipes.value.slice(0, OVEN_FOCUS_ROWS)));
const recipeScale = computed(() => ovenScale(recipes.value));
const ovens = computed(() => ovenRows(report.value?.oven_time_by_oven ?? []));
const ovenScaleByOven = computed(() => ovenScale(ovens.value));

</script>

<template>
  <div class="flex flex-col gap-3 [&>*]:shrink-0" data-bi-lots>
    <BiPageState :error="error" what="os lotes do período" @retry="refresh()" />
    <NuxtEmpty v-if="pending && !report" loading title="Carregando os lotes do período" data-bi-loading />

    <template v-if="report">
      <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <OperatorMetric
          title="Lotes fechados"
          :value="formatInt(report.batches_finished)"
          :delta="delta(report.batches_finished, report.previous.batches_finished)"
        />
        <OperatorMetric
          title="Tempo de forno medido"
          :value="`${report.oven_coverage_percent}%`"
          :hint="coverageLabel(report.batches_measured, report.batches_finished)"
        />
        <OperatorMetric
          title="Perda no período"
          :value="formatInt(lossTotal)"
          :delta="delta(lossTotal, Number(report.previous.loss_total), { downIsGood: true })"
          hint="Unidades que não saíram do forno"
        />
        <OperatorMetric
          title="Aproveitamento do período"
          :value="`${yieldTotal}%`"
          :delta="delta(yieldTotal, yieldPrevious)"
          :hint="startedAssumedHint(report.batches_started_assumed, report.batches_finished)"
        />
      </div>

      <OperatorReadingCard
        title="Produção por dia"
        description="Unidades que saíram do forno; tracejado = período anterior"
        :csv="readingChartCsv(axisLabel, FINISHED_SERIES, finished)"
      >
        <OperatorReadingChart
          title="Produção por dia"
          kind="comparison"
          :axis-label="axisLabel"
          :series="FINISHED_SERIES"
          :points="finished"
          :format="formatInt"
              :max-ticks="maxTicks"
          empty-title="Nenhum lote fechado no período"
        />
      </OperatorReadingCard>

      <OperatorReadingCard
        title="Aproveitamento por dia"
        description="Realizado ÷ previsto, em %"
        :csv="readingChartCsv(axisLabel, YIELD_SERIES, yields)"
      >
        <OperatorReadingChart
          title="Aproveitamento por dia"
          :axis-label="axisLabel"
          :series="YIELD_SERIES"
          :points="yields"
          :format="formatPercentValue"
              :max-ticks="maxTicks"
          empty-title="Nenhum lote fechado no período"
        />
      </OperatorReadingCard>

      <OperatorReadingCard
        title="Dia a dia"
        description="Previsto, realizado, perda e o mix de preço de cada dia do período"
        :csv="productionDaysCsv(buckets)"
        data-bi-production-days
      >
        <NuxtTable :data="dayRows" :columns="dayColumns" sticky="header" class="max-h-96" caption="Produção dia a dia">
          <template #empty>
            <NuxtEmpty variant="naked" icon="i-lucide-chef-hat" title="Nenhum lote fechado no período" />
          </template>
        </NuxtTable>
      </OperatorReadingCard>

      <!-- Lado a lado só a partir de 2xl: abaixo disso, cinco colunas não cabem em meia largura. -->
      <div class="grid items-start gap-3 2xl:grid-cols-2">
        <OperatorReadingCard
          title="Tempo de forno por receita"
          :description="`Média medida (armar → Concluir) · ${coverageLabel(report.batches_measured, report.batches_finished)}`"
          :csv="ovenCsv('Receita', report.oven_time_by_recipe)"
        >
          <NuxtTable :data="recipesShown" :columns="recipeColumns" caption="Tempo de forno por receita">
            <template #average-cell="{ row }">
              <div class="flex min-w-32 items-center gap-2">
                <NuxtProgress :model-value="row.original.minutes" :max="recipeScale" size="sm" class="flex-1" aria-hidden="true" />
                <span class="tnum font-medium">{{ row.original.average }}</span>
              </div>
            </template>
            <template #empty>
              <NuxtEmpty variant="naked" icon="i-lucide-timer" title="Nenhuma medição no período ainda" description="O timer do forno alimenta este quadro." />
            </template>
          </NuxtTable>
          <template v-if="recipes.length > OVEN_FOCUS_ROWS" #footer>
            <NuxtButton
              color="neutral"
              variant="outline"
              :icon="allRecipes ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'"
              :label="allRecipes ? 'Mostrar só as primeiras' : showAllLabel(recipes.length, { one: 'receita', many: 'receitas' })"
              data-bi-oven-all
              @click="allRecipes = !allRecipes"
            />
          </template>
        </OperatorReadingCard>
        <OperatorReadingCard
          title="Tempo de forno por forno"
          description="Lotes sem posição declarada ficam de fora deste corte"
          :csv="ovenCsv('Forno', report.oven_time_by_oven)"
        >
          <NuxtTable :data="ovens" :columns="ovenColumnsByOven" caption="Tempo de forno por forno">
            <template #average-cell="{ row }">
              <div class="flex min-w-32 items-center gap-2">
                <NuxtProgress :model-value="row.original.minutes" :max="ovenScaleByOven" size="sm" class="flex-1" aria-hidden="true" />
                <span class="tnum font-medium">{{ row.original.average }}</span>
              </div>
            </template>
            <template #empty>
              <NuxtEmpty variant="naked" icon="i-lucide-timer" title="Nenhuma medição com forno atribuído no período" />
            </template>
          </NuxtTable>
        </OperatorReadingCard>
      </div>
    </template>
  </div>
</template>
