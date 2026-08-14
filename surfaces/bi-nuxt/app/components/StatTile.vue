<script setup lang="ts">
// Número-herói: quando o dado é UM valor, tile — não gráfico (dataviz: a
// resposta às vezes não é um chart). Papéis do DS: label + figure + micro.
import type { DeltaBadge } from "~/presentation/bi";

defineProps<{
  label: string;
  value: string;
  hint?: string;
  /** Delta vs período anterior (F7) — texto + tom prontos da presentation. */
  delta?: DeltaBadge;
}>();

// Tokens semânticos dessaturados do tema (melhorou/piorou); neutro recua.
const TONE_CLASS = {
  positive: "text-success",
  negative: "text-destructive",
  neutral: "text-muted-foreground",
} as const;
</script>

<template>
  <div class="rounded-md border border-border bg-card p-3">
    <p class="text-xs font-medium text-muted-foreground">{{ label }}</p>
    <p class="mt-1 text-3xl font-bold tabular-nums text-foreground">{{ value }}</p>
    <p v-if="delta" class="mt-1 text-xs tabular-nums" :class="TONE_CLASS[delta.tone]">
      {{ delta.text }}
    </p>
    <p v-if="hint" class="mt-1 text-xs text-muted-foreground">{{ hint }}</p>
  </div>
</template>
