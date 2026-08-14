<script setup lang="ts">
// Lista com barra horizontal — identidade + magnitude num relance (canais,
// segmentos, tempo por receita). O texto veste tokens de texto; a barra é
// tinta neutra. Valor sempre visível à direita (a barra sozinha não basta).
import { computed } from "vue";

const props = defineProps<{
  rows: { label: string; value: number; display: string; hint?: string }[];
}>();

const max = computed(() => Math.max(...props.rows.map((r) => r.value), 1));
</script>

<template>
  <ul class="flex flex-col gap-2">
    <li v-for="row in rows" :key="row.label" class="min-w-0">
      <div class="flex items-baseline justify-between gap-2">
        <span class="truncate text-sm font-medium text-foreground">{{ row.label }}</span>
        <span class="shrink-0 text-sm tabular-nums text-foreground">{{ row.display }}</span>
      </div>
      <div class="mt-1 h-2 rounded-full bg-muted">
        <div
          class="h-2 rounded-full bg-foreground/60"
          :style="{ width: `${(row.value / max) * 100}%` }"
        ></div>
      </div>
      <p v-if="row.hint" class="mt-0.5 text-xs text-muted-foreground">{{ row.hint }}</p>
    </li>
  </ul>
</template>
