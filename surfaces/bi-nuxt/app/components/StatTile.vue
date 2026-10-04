<script setup lang="ts">
// Número-herói: quando o dado é UM valor, cartão, não gráfico (dataviz: a resposta às
// vezes não é um chart). Desenho dos cartões de número da prévia `bi-sobra4.html`
// (pino 5): rótulo, o número em `op-figure` (na cor do veredito quando há um), a
// unidade na mesma linha e, embaixo, a comparação ("sábado típico: 2 produtos").
import type { DeltaBadge } from "~/presentation/bi";

defineProps<{
  label: string;
  value: string;
  /** O que o número conta, na mesma linha ("produtos · 30 un."). */
  unit?: string;
  /** Tom do número quando ele É um veredito (faltou, sobrou, na medida). */
  tone?: "destructive" | "warning" | "success";
  hint?: string;
  /** Delta vs período anterior (F7): texto + tom prontos da presentation. */
  delta?: DeltaBadge;
}>();

// Tokens semânticos do tema (melhorou/piorou); neutro recua.
const TONE_CLASS = {
  positive: "text-success",
  negative: "text-destructive",
  neutral: "text-muted-foreground",
} as const;
const VALUE_TONE = {
  destructive: "text-destructive",
  warning: "text-warning",
  success: "text-success",
} as const;
</script>

<template>
  <div class="rounded-lg border border-border bg-card px-4 py-3" data-stat-tile>
    <p class="op-label text-muted-foreground">{{ label }}</p>
    <p class="op-figure mt-0.5 text-foreground">
      <span :class="tone ? VALUE_TONE[tone] : ''">{{ value }}</span>
      <span v-if="unit" class="ml-1.5 op-label font-normal text-muted-foreground">{{ unit }}</span>
    </p>
    <p v-if="delta" class="op-micro mt-0.5 tnum" :class="TONE_CLASS[delta.tone]">
      {{ delta.text }}
    </p>
    <p v-if="hint" class="op-micro mt-0.5 text-muted-foreground">{{ hint }}</p>
  </div>
</template>
