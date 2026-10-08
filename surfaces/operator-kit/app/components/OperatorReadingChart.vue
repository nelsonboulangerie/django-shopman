<script setup lang="ts">
// Gráfico de leitura (PR-K1 do WP-BI-CANON-LAUDO, item C1). Uma peça para as quatro
// formas que os quadros da suíte usam: barras, barras com o traço tracejado da
// comparação, divergente (sobrou ou faltou) e linha com área.
//
// - O desenho é Unovis (`OperatorReadingChartPlot.client.vue`) dentro de `<ClientOnly>`,
//   com `NuxtSkeleton` da mesma altura no SSR: nada pula quando o gráfico chega.
// - O ponto em leitura é UM só, venha do mouse, do toque ou do teclado: a frase dele
//   aparece acima do gráfico e o traço vertical marca onde ele está. No teclado, a área
//   do gráfico é uma parada de tabulação; setas andam, Home e End vão às pontas,
//   Escape solta. O leitor de tela ouve a frase a cada seta.
// - A tabela equivalente (`NuxtTable`) sai no SSR com os mesmos números, já formatados.
//   É o que o leitor de tela lê; `table-visible` a mostra também a quem enxerga.
// Contrato no README do kit, seção "Gráfico e quadro de leitura".
import type { TableColumn } from "@nuxt/ui";
import { computed, ref, useId } from "vue";

import {
  READING_TONE_COLOR,
  defaultReadingFormat,
  drawnSeries,
  nextReadingIndex,
  readingLegend,
  readingPointSummary,
  readingTableRows,
  type ReadingChartKind,
  type ReadingChartPoint,
  type ReadingChartSeries,
  type ReadingDivergingLabels,
  type ReadingFormat,
  type ReadingTableRow,
} from "../presentation/readingChart";

const props = withDefaults(
  defineProps<{
    /** O nome do gráfico, dito pelo leitor de tela ao chegar nele. */
    title: string;
    kind?: ReadingChartKind;
    /** O nome do eixo horizontal ("Hora", "Dia", "Produto"): primeira coluna da tabela. */
    axisLabel: string;
    series: ReadingChartSeries[];
    points: ReadingChartPoint[];
    /** Como cada valor é escrito (moeda, unidade). Default: número em pt-BR. */
    format?: ReadingFormat;
    /** Obrigatório no divergente: o nome de cada lado. */
    diverging?: ReadingDivergingLabels;
    height?: number;
    /** Quantos rótulos o eixo horizontal mostra, no máximo. */
    maxTicks?: number;
    /** Mostra a tabela equivalente também a quem enxerga (sempre existe para o leitor de tela). */
    tableVisible?: boolean;
    tableCaption?: string;
    emptyTitle?: string;
    emptyDescription?: string;
  }>(),
  {
    kind: "bars",
    format: defaultReadingFormat,
    diverging: undefined,
    height: 208,
    maxTicks: 6,
    tableVisible: false,
    tableCaption: undefined,
    emptyTitle: "Sem dados para esta leitura",
    emptyDescription: undefined,
  },
);

const readoutId = useId();
const active = ref<number | null>(null);
// De onde veio o ponto: o ponteiro solta ao sair; o teclado só ao Escape ou ao perder o foco.
const source = ref<"pointer" | "keyboard" | null>(null);
// O que o leitor de tela anuncia: só o que as setas mudam, nunca o passar do mouse.
const announcement = ref("");

const isEmpty = computed(() => props.points.length === 0);
const activePoint = computed(() => (active.value === null ? undefined : props.points[active.value]));
const readout = computed(() =>
  activePoint.value
    ? readingPointSummary(activePoint.value, props.kind, props.series, props.format, props.diverging)
    : "",
);
const legend = computed(() => readingLegend(props.kind, props.series, props.diverging));
const tableRows = computed(() =>
  readingTableRows(props.kind, props.series, props.points, props.format, props.diverging),
);
const columns = computed<TableColumn<ReadingTableRow>[]>(() => [
  { accessorKey: "label", header: props.axisLabel },
  ...drawnSeries(props.kind, props.series).map((item) => ({ accessorKey: item.key, header: item.label })),
]);
const caption = computed(() => props.tableCaption ?? `${props.title}, em tabela`);

function select(index: number | null, from: "pointer" | "keyboard") {
  active.value = index;
  source.value = index === null ? null : from;
  if (from === "keyboard") announcement.value = readout.value;
}

function onKeydown(event: KeyboardEvent) {
  const next = nextReadingIndex(active.value, event.key, props.points.length);
  if (next === undefined) return;
  event.preventDefault();
  select(next, "keyboard");
}

function onPointer(index: number) {
  if (index >= 0 && index < props.points.length) select(index, "pointer");
}

function onLeave() {
  if (source.value === "pointer") select(null, "pointer");
}

function onBlur() {
  if (source.value === "keyboard") {
    active.value = null;
    source.value = null;
  }
}
</script>

<template>
  <div class="min-w-0 space-y-2" data-operator-reading-chart :data-kind="kind">
    <NuxtEmpty
      v-if="isEmpty"
      icon="i-lucide-chart-no-axes-column"
      :title="emptyTitle"
      :description="emptyDescription"
      variant="naked"
    />
    <template v-else>
      <p :id="readoutId" class="op-body min-h-6" data-operator-reading-readout>
        <span v-if="readout">{{ readout }}</span>
        <span v-else class="text-muted">Toque no gráfico, passe o mouse ou use as setas para ler cada ponto.</span>
      </p>
      <div
        tabindex="0"
        role="group"
        :aria-label="title"
        :aria-describedby="readoutId"
        class="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        data-operator-reading-area
        @keydown="onKeydown"
        @blur="onBlur"
      >
        <ClientOnly>
          <OperatorReadingChartPlot
            :kind="kind"
            :series="series"
            :points="points"
            :format="format"
            :diverging="diverging"
            :height="height"
            :forced-index="source === 'keyboard' ? active : null"
            :max-ticks="maxTicks"
            @point="onPointer"
            @leave="onLeave"
          />
          <template #fallback>
            <NuxtSkeleton class="w-full" :style="{ height: `${height}px` }" />
          </template>
        </ClientOnly>
      </div>
      <ul
        v-if="legend.length > 1"
        class="op-micro flex flex-wrap gap-x-4 gap-y-1"
        aria-hidden="true"
        data-operator-reading-legend
      >
        <li v-for="item in legend" :key="item.label" class="flex items-center gap-1.5">
          <span
            v-if="item.dashed"
            class="inline-block w-4 border-t-2 border-dashed"
            :style="{ borderColor: READING_TONE_COLOR[item.tone] }"
          />
          <span
            v-else
            class="inline-block size-3 rounded-sm"
            :style="{ background: READING_TONE_COLOR[item.tone] }"
          />
          {{ item.label }}
        </li>
      </ul>
      <p class="sr-only" role="status" data-operator-reading-announcement>{{ announcement }}</p>
      <div :class="tableVisible ? undefined : 'sr-only'" data-operator-reading-table>
        <!-- Só para o leitor de tela, a tabela não rola: dentro do recorte de 1px do
             sr-only o contêiner `overflow-auto` do NuxtTable vira região rolável sem
             parada de teclado (axe: scrollable-region-focusable). -->
        <NuxtTable
          :data="tableRows"
          :columns="columns"
          :caption="caption"
          :class="tableVisible ? undefined : 'overflow-visible'"
        />
      </div>
    </template>
  </div>
</template>
