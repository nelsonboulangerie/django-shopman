<script setup lang="ts">
// Barras verticais de série (uma série por gráfico; a legenda mora no quadro).
// Marcas finas ancoradas na baseline, topo arredondado, vão entre barras. A cor diz o
// que a série é (prévia `depois-bi-vendas`, pino 7): latão para dinheiro e produção
// (`primary`), azul de informação para a hora do dia (`info`), verde para o dia da
// semana (`success`). O traço é a comparação, na cor do texto. Contraste de marca
// ≥ 3:1 sobre o cartão nos dois temas. Hover por barra com tooltip; rótulo direto só
// no pico, numa pílula escura. Ponto `closed` (a casa não abre) mostra "fechado" no
// lugar da barra.
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    // `muted` marca a barra de outra classe visual (ex.: trecho histórico);
    // `previous` desenha um traço na altura da comparação (bullet-style, F7). A página
    // que usar qualquer um mostra a legenda correspondente.
    points: { label: string; value: number; detail?: string; muted?: boolean; previous?: number; closed?: boolean }[];
    /** Formata o valor no tooltip e no rótulo direto. */
    format?: (value: number) => string;
    /** Rótulos do eixo x mostrados a cada N pontos (default: ~6 rótulos). */
    tickEvery?: number;
    tone?: "primary" | "info" | "success";
    /** Altura da área das barras (o gráfico compacto do celular usa menos). */
    height?: "default" | "compact";
  }>(),
  { format: undefined, tickEvery: undefined, tone: "primary", height: "default" },
);

const fmt = computed(() => props.format ?? ((v: number) => String(v)));
// O máximo considera o traço da comparação, senão ele estoura o quadro.
const max = computed(() =>
  Math.max(...props.points.flatMap((p) => [p.value, p.previous ?? 0]), 1),
);
const maxIndex = computed(() => {
  const values = props.points.map((p) => p.value);
  const top = Math.max(...values);
  return top > 0 ? values.indexOf(top) : -1;
});
const every = computed(
  () => props.tickEvery ?? Math.max(1, Math.ceil(props.points.length / 6)),
);
const BAR = {
  primary: { solid: "bg-primary group-hover:bg-primary/80", muted: "bg-primary/35 group-hover:bg-primary/55" },
  info: { solid: "bg-info group-hover:bg-info/80", muted: "bg-info/35 group-hover:bg-info/55" },
  success: { solid: "bg-success/70 group-hover:bg-success/60", muted: "bg-success/35 group-hover:bg-success/55" },
} as const;
const PEAK = { primary: "bg-primary", info: "bg-info", success: "bg-success" } as const;
// A pílula do pico não pode vazar do quadro: nas pontas ela se alinha pela borda.
function peakAlign(index: number): string {
  const count = props.points.length;
  if (count > 2 && index >= count - Math.max(1, Math.round(count / 6))) return "right-0";
  if (count > 2 && index < Math.max(1, Math.round(count / 6))) return "left-0";
  return "left-1/2 -translate-x-1/2";
}
</script>

<template>
  <figure class="pt-7">
    <!-- max-w por barra: com poucos pontos a barra não vira um bloco gigante. -->
    <div class="flex items-end justify-center gap-px border-b border-border" :class="height === 'compact' ? 'h-24' : 'h-36'" role="img">
      <div
        v-for="(point, index) in points"
        :key="point.label"
        class="group relative flex h-full min-w-0 max-w-16 flex-1 items-end"
      >
        <span
          v-if="point.closed && !point.value"
          class="pointer-events-none absolute bottom-1 left-1/2 -translate-x-1/2 whitespace-nowrap op-micro text-muted-foreground"
          data-chart-closed
        >fechado</span>
        <div
          class="w-full rounded-t-sm transition-colors"
          :class="point.muted ? BAR[tone].muted : index === maxIndex ? PEAK[tone] : BAR[tone].solid"
          :style="{ height: `${Math.max(point.value > 0 ? 3 : 0, (point.value / max) * 100)}%` }"
        ></div>
        <!-- Traço da comparação (bullet-style): posição, não preenchimento. -->
        <div
          v-if="point.previous"
          class="pointer-events-none absolute left-0 right-0 h-0.5 bg-foreground/70"
          :style="{ bottom: `${(point.previous / max) * 100}%` }"
        ></div>
        <!-- Rótulo direto seletivo: só o pico, numa pílula. -->
        <span
          v-if="index === maxIndex"
          class="pointer-events-none absolute -translate-y-full whitespace-nowrap rounded bg-foreground px-1.5 py-px op-micro font-semibold tnum text-background"
          :class="peakAlign(index)"
          :style="{ bottom: `calc(${(point.value / max) * 100}% + 4px)` }"
          data-chart-peak
        >
          {{ fmt(point.value) }}
        </span>
        <div
          class="pointer-events-none absolute bottom-full left-1/2 z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-popover px-2 py-1 op-micro text-popover-foreground shadow-sm group-hover:block"
        >
          <span class="text-muted-foreground">{{ point.label }}</span>
          · <span class="font-semibold tnum">{{ fmt(point.value) }}</span>
          <span v-if="point.previous" class="text-muted-foreground">
            · comparação {{ fmt(point.previous) }}</span>
          <span v-if="point.detail" class="text-muted-foreground"> · {{ point.detail }}</span>
        </div>
      </div>
    </div>
    <!-- Célula de tick pode vazar sobre as vizinhas (vazias por construção):
         com muitas barras a célula fica mais estreita que o rótulo. -->
    <div class="mt-1 flex justify-center gap-px">
      <span
        v-for="(point, index) in points"
        :key="point.label"
        class="relative min-w-0 max-w-16 flex-1 text-center op-micro tnum text-muted-foreground"
      >
        <span
          v-if="index % every === 0"
          class="absolute left-1/2 -translate-x-1/2 whitespace-nowrap"
        >{{ point.label }}</span>
        <span v-else>&nbsp;</span>
      </span>
    </div>
  </figure>
</template>
