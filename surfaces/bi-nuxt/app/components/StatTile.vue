<script setup lang="ts">
// Número-herói: quando o dado é UM valor, tile — não gráfico (dataviz: a
// resposta às vezes não é um chart). Papéis do DS: label + figure + micro.
defineProps<{
  label: string;
  value: string;
  hint?: string;
  /** Delta vs período anterior (F7) — texto pronto da presentation. */
  delta?: string;
}>();
</script>

<template>
  <div class="rounded-md border border-border bg-card p-3">
    <p class="text-xs font-medium text-muted-foreground">{{ label }}</p>
    <p class="mt-1 text-3xl font-bold tabular-nums text-foreground">{{ value }}</p>
    <p v-if="delta" class="mt-1 text-xs tabular-nums text-muted-foreground">{{ delta }}</p>
    <p v-if="hint" class="mt-1 text-xs text-muted-foreground">{{ hint }}</p>
  </div>
</template>
