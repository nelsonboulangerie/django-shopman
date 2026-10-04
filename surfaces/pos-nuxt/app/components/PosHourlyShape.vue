<script setup lang="ts">
// "Explicar o dia estranho" (v4 `fim-do-dia.jpg` b, pino 8): o gráfico por hora
// "Hoje × sábado típico". Só a FORMA: barras relativas de 0 a 1, sem eixo de
// valor, sem reais e sem contagem; o fim do dia é cego para dinheiro. Hoje é a
// barra cheia; o típico é o contorno tracejado atrás dela.
import type { ClosingHourlyShape } from "~/types/closing";

const props = defineProps<{ shape: ClosingHourlyShape }>();

const bars = computed(() => props.shape.hours.map((hour, index) => ({
  hour,
  today: props.shape.today[index] ?? null,
  typical: props.shape.typical[index] ?? 0,
})));
function pct(value: number | null): string {
  return `${Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100)}%`;
}
</script>

<template>
  <figure class="grid gap-2 rounded-lg bg-secondary/60 p-3" data-closing-hourly>
    <figcaption class="flex flex-wrap items-center gap-x-4 gap-y-1 op-micro text-muted-foreground">
      <span class="inline-flex items-center gap-1.5"><span class="size-2.5 rounded-full bg-primary" aria-hidden="true" />Hoje, por hora</span>
      <span class="inline-flex items-center gap-1.5"><span class="size-2.5 rounded-full border border-dashed border-muted-foreground" aria-hidden="true" />{{ shape.typical_label[0]?.toUpperCase() }}{{ shape.typical_label.slice(1) }}</span>
      <span class="ml-auto">só a forma, sem valores</span>
    </figcaption>
    <div class="flex h-28 items-end gap-1.5" role="img" :aria-label="`Movimento por hora, hoje comparado a ${shape.typical_label}${shape.drop_after ? `; caiu depois das ${shape.drop_after}` : ''}`">
      <div v-for="bar in bars" :key="bar.hour" class="flex h-full min-w-0 flex-1 flex-col items-center gap-1">
        <div class="relative w-full flex-1">
          <span class="absolute inset-x-0 bottom-0 rounded-t-sm border border-dashed border-muted-foreground/60" :style="{ height: pct(bar.typical) }" aria-hidden="true" />
          <span v-if="bar.today !== null" class="absolute inset-x-[18%] bottom-0 rounded-t-sm bg-primary" :style="{ height: pct(bar.today) }" aria-hidden="true" />
        </div>
        <span class="op-micro text-muted-foreground tnum">{{ bar.hour }}</span>
      </div>
    </div>
  </figure>
</template>
