<script setup lang="ts">
// O desenho do gráfico de leitura, em Unovis (o template oficial de dashboard do Nuxt
// UI usa Unovis; o Nuxt UI não tem Chart). Só desenha: o ponto em leitura, a frase, a
// legenda e a tabela equivalente moram no `OperatorReadingChart`, que monta este
// arquivo dentro de `<ClientOnly>`. O SVG é `aria-hidden`: quem lê por voz lê a tabela.
import {
  VisArea,
  VisAxis,
  VisCrosshair,
  VisGroupedBar,
  VisLine,
  VisXYContainer,
} from "@unovis/vue";
import { computed } from "vue";

import {
  READING_TONE_COLOR,
  drawnSeries,
  pointValue,
  readingRunIndex,
  readingRuns,
  readingTickIndices,
  readingYDomain,
  seriesTone,
  type ReadingChartKind,
  type ReadingChartPoint,
  type ReadingChartSeries,
  type ReadingDivergingLabels,
  type ReadingFormat,
  type ReadingRun,
} from "../presentation/readingChart";

const props = defineProps<{
  kind: ReadingChartKind;
  series: ReadingChartSeries[];
  points: ReadingChartPoint[];
  /** O formato do eixo vertical (compacto no dinheiro); a frase do ponto usa o cheio. */
  axisFormat: ReadingFormat;
  diverging?: ReadingDivergingLabels;
  height: number;
  /** O ponto que o teclado escolheu. O do ponteiro o Crosshair já segue sozinho; forçá-lo
   * travaria o traço no primeiro ponto tocado. `null` devolve o traço ao ponteiro. */
  forcedIndex: number | null;
  maxTicks: number;
}>();

const emit = defineEmits<{
  /** O ponteiro (mouse, ou toque pelo evento de compatibilidade) chegou num ponto. */
  point: [index: number];
  /** O ponteiro saiu do gráfico. */
  leave: [];
}>();

interface Row {
  index: number;
  point: ReadingChartPoint;
}

const rows = computed<Row[]>(() => props.points.map((point, index) => ({ index, point })));
const drawn = computed(() => drawnSeries(props.kind, props.series));
const yDomain = computed(() => readingYDomain(props.kind, props.series, props.points));
const ticks = computed(() => readingTickIndices(props.points.length, props.maxTicks));

const x = (row: Row) => row.index;
const accessor = (key: string) => (row: Row) => pointValue(row.point, key) ?? undefined;
const tickLabel = (tick: number | Date) => props.points[Number(tick)]?.label ?? "";
const yTick = (tick: number | Date) => props.axisFormat(Number(tick));
// O eixo vertical ganha largura para o rótulo caber numa linha ("R$ 15 mil"); o
// Unovis reserva só um quinto do gráfico e quebrava o rótulo no celular.
const Y_TICK_WIDTH = 96;

// Barras: as séries lado a lado (bars) ou só a primeira (comparison, diverging).
const barSeries = computed(() =>
  props.kind === "bars" ? drawn.value : props.kind === "line" ? [] : drawn.value.slice(0, 1),
);
const barY = computed(() => barSeries.value.map((item) => accessor(item.key)));
const barColor = (row: Row, index: number) => {
  if (props.kind === "diverging") {
    const value = pointValue(row.point, drawn.value[0]?.key ?? "") ?? 0;
    return READING_TONE_COLOR[
      value < 0 ? (props.diverging?.negativeTone ?? "error") : (props.diverging?.positiveTone ?? "primary")
    ];
  }
  const item = barSeries.value[index];
  return READING_TONE_COLOR[item ? seriesTone(item, index) : "primary"];
};

// Linhas: todas no `line`; no `comparison`, o traço da segunda série.
const lineSeries = computed(() => {
  if (props.kind === "line") return drawn.value.map((item, index) => ({ item, index }));
  if (props.kind === "comparison" && drawn.value[1]) return [{ item: drawn.value[1], index: 1 }];
  return [];
});
const areaSeries = computed(() => (props.kind === "line" ? drawn.value[0] : undefined));
// A área sai trecho a trecho: num buraco da série, a linha quebra e a área também.
const areaRuns = computed(() => (areaSeries.value ? readingRuns(props.points, areaSeries.value.key) : []));
const runX = (run: ReadingRun) => (row: Row) => readingRunIndex(run, row.index);
const runY = (run: ReadingRun, key: string) => (row: Row) =>
  pointValue(props.points[readingRunIndex(run, row.index)]!, key) ?? undefined;
const DASH = [6, 4];

// O traço vertical do ponto em leitura. Círculos só onde há linha; nas barras o
// Crosshair recebe os acessores delas (o Unovis os exige) e não desenha círculo.
const crosshairY = computed(() =>
  lineSeries.value.length ? lineSeries.value.map(({ item }) => accessor(item.key)) : barY.value,
);
const crosshairColor = (_row: Row, index: number) => {
  const entry = lineSeries.value[index];
  return READING_TONE_COLOR[entry ? seriesTone(entry.item, entry.index) : "primary"];
};
const noCircles = () => [];

function onCrosshairMove(_x?: number | Date, _datum?: Row, datumIndex?: number) {
  if (typeof datumIndex === "number") emit("point", datumIndex);
  else emit("leave");
}
</script>

<template>
  <div aria-hidden="true" data-operator-reading-plot class="min-w-0">
    <VisXYContainer :data="rows" :height="height" :y-domain="yDomain">
      <VisGroupedBar v-if="barSeries.length" :x="x" :y="barY" :color="barColor" />
      <template v-if="areaSeries">
        <VisArea
          v-for="run in areaRuns"
          :key="`${run.start}-${run.end}`"
          :x="runX(run)"
          :y="runY(run, areaSeries.key)"
          :color="READING_TONE_COLOR[seriesTone(areaSeries, 0)]"
          :opacity="0.1"
          exclude-from-domain-calculation
        />
      </template>
      <VisLine
        v-for="entry in lineSeries"
        :key="entry.item.key"
        :x="x"
        :y="accessor(entry.item.key)"
        :color="READING_TONE_COLOR[seriesTone(entry.item, entry.index)]"
        :line-dash-array="kind === 'comparison' ? DASH : undefined"
        :line-width="2"
      />
      <VisAxis
        type="x"
        :x="x"
        :tick-values="ticks"
        :tick-format="tickLabel"
        :grid-line="false"
      />
      <VisAxis type="y" :num-ticks="3" :tick-format="yTick" :tick-text-width="Y_TICK_WIDTH" />
      <!-- O VisCrosshair do @unovis/vue 1.7 não declara props: repassa os atributos
           como vieram, e atributo hifenizado não vira config. Por isso o camelCase. -->
      <!-- eslint-disable vue/attribute-hyphenation -->
      <VisCrosshair
        :x="x"
        :y="crosshairY"
        :color="crosshairColor"
        :getCircles="lineSeries.length ? undefined : noCircles"
        :forceShowAt="forcedIndex ?? undefined"
        :hideWhenFarFromPointer="false"
        :onCrosshairMove="onCrosshairMove"
      />
      <!-- eslint-enable vue/attribute-hyphenation -->
    </VisXYContainer>
  </div>
</template>

<style scoped>
[data-operator-reading-plot] :deep(text) {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  fill: var(--ui-text);
}
[data-operator-reading-plot] :deep(line),
[data-operator-reading-plot] :deep(path.domain) {
  stroke: var(--ui-border);
}
</style>
