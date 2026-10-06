<script setup lang="ts">
import {
  VisXYContainer,
  VisLine,
  VisArea,
  VisAxis,
  VisGroupedBar,
} from "@unovis/vue";
import { dashboardTrend } from "../fixtures/operatorDashboard";

defineProps<{ bars?: boolean }>();
const x = (point: (typeof dashboardTrend)[number]) => point.index;
const y = (point: (typeof dashboardTrend)[number]) => point.orders;
const tick = (index: number) => dashboardTrend[index]?.label ?? "";
</script>

<template>
  <!-- O dado equivalente fica na tabela SSR da receita; SVG não duplica anúncios. -->
  <div aria-hidden="true" data-operator-trend-chart class="min-w-0">
    <VisXYContainer :data="dashboardTrend" :height="192" :y-domain="[0, 40]">
      <VisGroupedBar v-if="bars" :x="x" :y="y" color="var(--ui-primary)" />
      <template v-else>
        <VisArea :x="x" :y="y" color="var(--ui-primary)" :opacity="0.1" />
        <VisLine :x="x" :y="y" color="var(--ui-primary)" />
      </template>
      <VisAxis
        type="x"
        :x="x"
        :tick-format="tick"
        :num-ticks="6"
        :grid-line="false"
      />
      <VisAxis type="y" :y="y" :num-ticks="3" />
    </VisXYContainer>
  </div>
</template>

<style scoped>
[data-operator-trend-chart] :deep(text) {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  fill: var(--ui-text);
}
[data-operator-trend-chart] :deep(line),
[data-operator-trend-chart] :deep(path.domain) {
  stroke: var(--ui-border);
}
</style>
