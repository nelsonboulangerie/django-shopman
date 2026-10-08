<script setup lang="ts">
// O dia da leitura no cabeçalho (prévia `bi-sobra4.html`, pino 2): ‹ · "Ontem sáb 03/10" · ›
// num controle só (NuxtFieldGroup). As setas andam para o dia aberto anterior/seguinte
// que o servidor informa (dia fechado não existe na leitura); a seta para frente fica
// desligada no último dia que já terminou, porque o dia em curso ainda não tem
// resposta. O meio é o campo de data canônico da suíte (UiDateField: segmentos e
// calendário), igual no desktop, no tablet e no celular.
import { dayCaption, dayName } from "~/presentation/overShort";

const props = defineProps<{
  day: string;
  today: string;
  previous: string;
  next: string;
  /** O último dia que se pode ler (ontem). */
  max: string;
}>();
const emit = defineEmits<{ change: [day: string] }>();

function onPick(value: string) {
  if (value && value !== props.day) emit("change", value);
}

const previousLabel = computed(() =>
  props.previous ? `Dia anterior: ${dayCaption(props.previous)}` : "Sem dia anterior com loja aberta",
);
const nextLabel = computed(() =>
  props.next ? `Dia seguinte: ${dayCaption(props.next)}` : "O dia seguinte ainda não terminou",
);
</script>

<template>
  <NuxtFieldGroup aria-label="Dia da leitura" data-bi-day-stepper>
    <NuxtButton
      icon="i-lucide-chevron-left"
      color="neutral"
      variant="outline"
      square
      :disabled="!previous"
      :aria-label="previousLabel"
      :title="previousLabel"
      data-day-prev
      @click="emit('change', previous)"
    />
    <!-- O UiDateField do kit NÃO tem slot #trigger: o botão "Ontem sáb 03/10" que
         este componente passava era descartado em silêncio desde aaed185cf (a mesma
         classe do #below). O campo canônico fica como é, com o nome do dia no rótulo. -->
    <UiDateField
      :model-value="day"
      :max="max"
      :label="`Dia da leitura: ${dayName(day, today)}`"
      data-day-open
      @update:model-value="onPick"
    />
    <NuxtButton
      icon="i-lucide-chevron-right"
      color="neutral"
      variant="outline"
      square
      :disabled="!next"
      :aria-label="nextLabel"
      :title="nextLabel"
      data-day-next
      @click="emit('change', next)"
    />
  </NuxtFieldGroup>
</template>
