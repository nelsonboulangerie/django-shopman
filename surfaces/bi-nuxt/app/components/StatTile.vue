<script setup lang="ts">
// Número-herói: quando o dado é UM valor, cartão, não gráfico (dataviz: a resposta às
// vezes não é um chart). Desenho dos cartões de número da prévia `bi-sobra4.html`
// (pino 5): rótulo, o número em `op-figure` (na cor do veredito quando há um), a
// unidade na mesma linha e, embaixo, a comparação ("sábado típico: 2 produtos").
// Com delta (prévia `depois-bi-vendas`, pino 7): a seta e a porcentagem numa pílula no
// tom do melhorou/piorou, e ao lado contra o quê e o valor de lá
// ("vs período anterior (3.384)").
import type { DeltaBadge } from "~/presentation/bi";

withDefaults(
  defineProps<{
    label: string;
    value: string;
    /** O que o número conta, na mesma linha ("produtos · 30 un."). */
    unit?: string;
    /** Tom do número quando ele É um veredito (faltou, sobrou, na medida). */
    tone?: "destructive" | "warning" | "success";
    hint?: string;
    /** Delta vs a base de comparação (F7): pílula + legenda prontas da presentation. */
    delta?: DeltaBadge;
    /** Ícone do rótulo (prévia: o cartão diz o que conta antes do número). */
    icon?: string;
    /** `hero`: o número sozinho e maior (o Faturamento no celular, v3 b). */
    size?: "default" | "hero";
  }>(),
  { size: "default", unit: "", tone: undefined, hint: "", delta: undefined, icon: "" },
);

// Tokens semânticos do tema (melhorou/piorou); neutro recua.
const PILL_CLASS = {
  positive: "bg-success/12 text-success",
  negative: "bg-destructive/12 text-destructive",
  neutral: "bg-muted text-muted-foreground",
} as const;
const ARROW = { up: "lucide:trending-up", down: "lucide:trending-down", flat: "lucide:minus", none: "" } as const;
const VALUE_TONE = {
  destructive: "text-destructive",
  warning: "text-warning",
  success: "text-success",
} as const;
</script>

<template>
  <div class="rounded-lg border border-border bg-card px-4 py-3" data-stat-tile>
    <p class="flex items-center gap-1.5 op-label text-muted-foreground">
      <Icon v-if="icon" :name="icon" class="size-4" aria-hidden="true" />{{ label }}
    </p>
    <p class="mt-0.5 text-foreground" :class="size === 'hero' ? 'text-[34px] leading-tight font-bold tracking-[-0.02em] tnum' : 'op-figure'">
      <span class="whitespace-nowrap" :class="tone ? VALUE_TONE[tone] : ''">{{ value }}</span>
      <span v-if="unit" class="ml-1.5 op-label font-normal text-muted-foreground">{{ unit }}</span>
    </p>
    <p v-if="delta" class="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 op-micro tnum" :aria-label="delta.text" data-stat-delta>
      <span
        v-if="delta.percent"
        class="inline-flex h-5 items-center gap-1 rounded-full px-1.5 font-semibold"
        :class="PILL_CLASS[delta.tone]"
        aria-hidden="true"
      >
        <Icon v-if="ARROW[delta.direction]" :name="ARROW[delta.direction]" class="size-3.5" />{{ delta.percent }}
      </span>
      <span class="text-muted-foreground" aria-hidden="true">{{ delta.caption }}</span>
    </p>
    <p v-if="hint" class="op-micro mt-0.5 text-muted-foreground">{{ hint }}</p>
  </div>
</template>
