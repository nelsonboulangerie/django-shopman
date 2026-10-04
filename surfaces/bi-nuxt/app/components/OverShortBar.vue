<script setup lang="ts">
// A barra compacta de cada produto (prévia `bi-sobra4.html`, pino 6): o trilho é o que
// a casa FEZ, o cheio é o que VENDEU (latão), o tracejado são as vendas perdidas
// estimadas (tijolo), e o traço vertical é o que se vende num dia típico. A legenda
// fica na cabeça da coluna; o número exato, na linha de baixo.
import type { BIOverShortRow } from "~/types/bi";
import { barGeometry } from "~/presentation/overShort";

const props = defineProps<{ row: BIOverShortRow; scale: number }>();
const geometry = computed(() => barGeometry(props.row, props.scale));
</script>

<template>
  <div class="relative h-3.5 w-full max-w-[200px]" aria-hidden="true" data-over-short-bar>
    <div class="absolute inset-y-0 left-0 rounded-sm border border-border bg-muted" :style="{ width: `${geometry.made}%` }" />
    <div class="absolute inset-y-0 left-0 rounded-sm bg-primary" :style="{ width: `${geometry.sold}%` }" />
    <div
      v-if="geometry.lost > 0"
      class="absolute inset-y-0 rounded-r-sm border border-dashed border-destructive/70 bg-destructive/10"
      :style="{ left: `${geometry.lostFrom}%`, width: `${geometry.lost}%` }"
    />
    <div
      v-if="geometry.typical !== null"
      class="absolute -top-1 -bottom-1 w-0.5 bg-foreground"
      :style="{ left: `${geometry.typical}%` }"
    />
  </div>
</template>
