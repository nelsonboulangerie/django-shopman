<script setup lang="ts">
// O dia da leitura no cabeçalho (prévia `bi-sobra4.html`, pino 2): ‹ · "Ontem sáb 03/10" · ›
// num controle só. As setas andam para o dia aberto anterior/seguinte que o servidor
// informa (dia fechado não existe na leitura); a seta para frente some no último dia
// que já terminou, porque o dia em curso ainda não tem resposta. O meio abre o
// calendário canônico da suíte, igual no desktop, tablet e celular.
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

const SEG = "grid size-control shrink-0 place-items-center transition hover:bg-accent focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:text-muted-foreground/40";
</script>

<template>
  <div class="flex items-center gap-2" data-bi-day-stepper>
    <div class="flex h-control shrink-0 items-center overflow-hidden rounded-md border border-border bg-card" role="group" aria-label="Dia da leitura">
      <button
        type="button"
        :class="[SEG, 'border-r border-border']"
        :disabled="!previous"
        :aria-label="previous ? `Dia anterior: ${dayCaption(previous)}` : 'Sem dia anterior com loja aberta'"
        :title="previous ? `Dia anterior: ${dayCaption(previous)}` : 'Sem dia anterior com loja aberta'"
        data-day-prev
        @click="emit('change', previous)"
      >
        <Icon name="lucide:chevron-left" class="size-4" aria-hidden="true" />
      </button>
      <UiDateField :model-value="day" :max="max" label="Dia da leitura" @update:model-value="onPick">
        <template #trigger>
          <button
            type="button"
            class="inline-flex h-full items-center gap-2 px-3 op-label transition hover:bg-accent"
            :aria-label="`Dia da leitura: ${dayName(day, today)}, ${dayCaption(day)}. Escolher outro dia`"
            data-day-open
          >
            <Icon name="lucide:calendar" class="size-4 text-muted-foreground" aria-hidden="true" />
            <span class="font-semibold">{{ dayName(day, today) }}</span>
            <span class="tnum text-muted-foreground">{{ dayCaption(day) }}</span>
            <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
          </button>
        </template>
      </UiDateField>
      <button
        type="button"
        :class="[SEG, 'border-l border-border']"
        :disabled="!next"
        :aria-label="next ? `Dia seguinte: ${dayCaption(next)}` : 'O dia seguinte ainda não terminou'"
        :title="next ? `Dia seguinte: ${dayCaption(next)}` : 'O dia seguinte ainda não terminou'"
        data-day-next
        @click="emit('change', next)"
      >
        <Icon name="lucide:chevron-right" class="size-4" aria-hidden="true" />
      </button>
    </div>
  </div>
</template>
