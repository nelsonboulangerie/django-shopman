<script setup lang="ts">
// Barras divergentes em torno do zero — polaridade é FUNCIONAL: falta de caixa
// (negativo) veste destructive, sobra veste o latão da suíte (`primary`). Nunca reusar essas
// cores como "série 4" (dataviz: status é reservado).
import { computed } from "vue";

const props = defineProps<{
  points: { label: string; value: number; detail?: string }[];
  format?: (value: number) => string;
  tickEvery?: number;
}>();

const fmt = computed(() => props.format ?? ((v: number) => String(v)));
const maxAbs = computed(() => Math.max(...props.points.map((p) => Math.abs(p.value)), 1));
const every = computed(
  () => props.tickEvery ?? Math.max(1, Math.ceil(props.points.length / 6)),
);
const half = (value: number) => `${(Math.abs(value) / maxAbs.value) * 100}%`;
</script>

<template>
  <figure>
    <div class="flex h-36 flex-col" role="img">
      <div class="flex flex-1 items-end gap-px">
        <div v-for="point in points" :key="`up-${point.label}`" class="group relative flex h-full min-w-0 flex-1 items-end">
          <div
            v-if="point.value > 0"
            class="w-full rounded-t-sm bg-primary transition-colors group-hover:bg-primary/80"
            :style="{ height: half(point.value) }"
          ></div>
          <div
            class="pointer-events-none absolute bottom-full left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 op-micro text-popover-foreground shadow-sm group-hover:block"
          >
            <span class="text-muted-foreground">{{ point.label }}</span>
            · <span class="font-semibold tnum">{{ fmt(point.value) }}</span>
            <span v-if="point.detail" class="text-muted-foreground"> · {{ point.detail }}</span>
          </div>
        </div>
      </div>
      <div class="border-t border-border"></div>
      <div class="flex flex-1 items-start gap-px">
        <div v-for="point in points" :key="`down-${point.label}`" class="group relative flex h-full min-w-0 flex-1 items-start">
          <div
            v-if="point.value < 0"
            class="w-full rounded-b-sm bg-destructive transition-colors group-hover:bg-destructive/80"
            :style="{ height: half(point.value) }"
          ></div>
          <div
            class="pointer-events-none absolute top-full left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 op-micro text-popover-foreground shadow-sm group-hover:block"
          >
            <span class="text-muted-foreground">{{ point.label }}</span>
            · <span class="font-semibold tnum">{{ fmt(point.value) }}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="mt-1 flex gap-px">
      <span
        v-for="(point, index) in points"
        :key="point.label"
        class="min-w-0 flex-1 truncate text-center op-micro tnum text-muted-foreground"
      >
        {{ index % every === 0 ? point.label : "" }}
      </span>
    </div>
  </figure>
</template>
