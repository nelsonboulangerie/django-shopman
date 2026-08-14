<script setup lang="ts">
// Barras verticais de série temporal (uma série → sem legenda; o título nomeia).
// Marcas finas ancoradas na baseline, topo arredondado, vão entre barras;
// monocromático de propósito (cor só funcional no DS de operador). Hover por
// barra com tooltip; rótulos diretos só onde importam (máximo do período).
import { computed } from "vue";

const props = defineProps<{
  points: { label: string; value: number; detail?: string }[];
  /** Formata o valor no tooltip e no rótulo direto. */
  format?: (value: number) => string;
  /** Rótulos do eixo x mostrados a cada N pontos (default: ~6 rótulos). */
  tickEvery?: number;
}>();

const fmt = computed(() => props.format ?? ((v: number) => String(v)));
const max = computed(() => Math.max(...props.points.map((p) => p.value), 1));
const maxIndex = computed(() => {
  const values = props.points.map((p) => p.value);
  const top = Math.max(...values);
  return top > 0 ? values.indexOf(top) : -1;
});
const every = computed(
  () => props.tickEvery ?? Math.max(1, Math.ceil(props.points.length / 6)),
);
</script>

<template>
  <figure>
    <!-- max-w por barra: com poucos pontos a barra não vira um bloco gigante. -->
    <div class="flex h-36 items-end justify-center gap-px border-b border-border" role="img">
      <div
        v-for="(point, index) in points"
        :key="point.label"
        class="group relative flex h-full min-w-0 max-w-16 flex-1 items-end"
      >
        <div
          class="w-full rounded-t-sm bg-foreground/60 transition-colors group-hover:bg-foreground"
          :style="{ height: `${Math.max(point.value > 0 ? 3 : 0, (point.value / max) * 100)}%` }"
        ></div>
        <!-- Rótulo direto seletivo: só o pico do período. -->
        <span
          v-if="index === maxIndex"
          class="pointer-events-none absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs tabular-nums text-muted-foreground"
        >
          {{ fmt(point.value) }}
        </span>
        <div
          class="pointer-events-none absolute bottom-full left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-card px-2 py-1 text-xs text-foreground shadow-sm group-hover:block"
        >
          <span class="text-muted-foreground">{{ point.label }}</span>
          · <span class="font-medium tabular-nums">{{ fmt(point.value) }}</span>
          <span v-if="point.detail" class="text-muted-foreground"> · {{ point.detail }}</span>
        </div>
      </div>
    </div>
    <div class="mt-1 flex justify-center gap-px">
      <span
        v-for="(point, index) in points"
        :key="point.label"
        class="min-w-0 max-w-16 flex-1 truncate text-center text-xs text-muted-foreground"
      >
        {{ index % every === 0 ? point.label : "" }}
      </span>
    </div>
  </figure>
</template>
