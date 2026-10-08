<script setup lang="ts">
// Número-herói: quando o dado é UM valor, cartão, não gráfico. NuxtCard canônico:
// rótulo (com ícone), o número em `op-figure` (na cor do veredito quando há um), a
// unidade na mesma linha e, embaixo, a comparação. Com delta (prévia
// `depois-bi-vendas`, pino 7): a seta e a porcentagem num NuxtBadge no tom do
// melhorou/piorou e, ao lado, contra o quê ("vs período anterior (3.384)").
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
    /** Delta vs a base de comparação (F7): o badge e a legenda prontos da presentation. */
    delta?: DeltaBadge;
    /** Ícone do rótulo (prévia: o cartão diz o que conta antes do número). */
    icon?: string;
    /** `hero`: o número sozinho e maior (o Faturamento no celular, v3 b). */
    size?: "default" | "hero";
  }>(),
  { size: "default", unit: "", tone: undefined, hint: "", delta: undefined, icon: "" },
);

const DELTA_COLOR = { positive: "success", negative: "error", neutral: "neutral" } as const;
const ARROW = { up: "i-lucide-trending-up", down: "i-lucide-trending-down", flat: "i-lucide-minus", none: undefined } as const;
const VALUE_TONE = {
  destructive: "text-destructive",
  warning: "text-warning",
  success: "text-success",
} as const;
</script>

<template>
  <NuxtCard data-stat-tile>
    <p class="flex items-center gap-1.5 op-label text-muted-foreground">
      <NuxtIcon v-if="icon" :name="icon" class="size-4" aria-hidden="true" />{{ label }}
    </p>
    <p class="mt-0.5 text-foreground" :class="size === 'hero' ? 'op-display font-bold tnum' : 'op-figure'">
      <span class="whitespace-nowrap" :class="tone ? VALUE_TONE[tone] : ''">{{ value }}</span>
      <span v-if="unit" class="ml-1.5 op-label font-normal text-muted-foreground">{{ unit }}</span>
    </p>
    <p v-if="delta" class="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 op-micro tnum" :aria-label="delta.text" data-stat-delta>
      <NuxtBadge
        v-if="delta.percent"
        :color="DELTA_COLOR[delta.tone]"
        variant="soft"
        :icon="ARROW[delta.direction]"
        :label="delta.percent"
        aria-hidden="true"
      />
      <span class="text-muted-foreground" aria-hidden="true">{{ delta.caption }}</span>
    </p>
    <p v-if="hint" class="op-micro mt-0.5 text-muted-foreground">{{ hint }}</p>
  </NuxtCard>
</template>
