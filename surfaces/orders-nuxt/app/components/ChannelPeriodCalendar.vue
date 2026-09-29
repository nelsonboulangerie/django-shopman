<script setup lang="ts">
// "Escolher período…" do modal do toggle de canal: um calendário de mês com o
// intervalo marcado (primeiro toque = começa, segundo = termina) e a hora de cada
// ponta. Feito aqui, e não com o seletor nativo, porque o seletor nativo não mostra
// o INTERVALO — e férias de duas semanas se conferem de olho, não de cabeça.
import type { ChannelSwitchDraft } from "~/presentation/channelSwitch";
import { isoDay, monthLabel, monthWeeks, pickDay, rangeLine } from "~/presentation/channelSwitch";

const draft = defineModel<ChannelSwitchDraft>({ required: true });
const props = defineProps<{ today?: Date }>();

const today = computed(() => props.today ?? new Date());
const cursor = ref(new Date(today.value.getFullYear(), today.value.getMonth(), 1));
const weeks = computed(() => monthWeeks(cursor.value.getFullYear(), cursor.value.getMonth(), today.value));
const title = computed(() => monthLabel(cursor.value.getFullYear(), cursor.value.getMonth()));
const canGoBack = computed(() => isoDay(cursor.value) > isoDay(new Date(today.value.getFullYear(), today.value.getMonth(), 1)));
const line = computed(() => rangeLine(draft.value));

function shift(months: number) {
  cursor.value = new Date(cursor.value.getFullYear(), cursor.value.getMonth() + months, 1);
}

function pick(iso: string) {
  draft.value = { ...draft.value, ...pickDay(draft.value, iso) };
}

function inRange(iso: string) {
  const { startDate, endDate } = draft.value;
  return Boolean(startDate && endDate && iso > startDate && iso < endDate);
}
</script>

<template>
  <div class="rounded-md border p-3" data-period-calendar>
    <div class="mb-2 flex items-center justify-between">
      <button
        type="button" class="grid min-h-control min-w-control place-items-center rounded-md transition hover:bg-accent disabled:opacity-30"
        :disabled="!canGoBack" aria-label="Mês anterior" @click="shift(-1)"
      >
        <Icon name="lucide:chevron-left" class="size-4" />
      </button>
      <p class="text-sm font-medium first-letter:uppercase">{{ title }}</p>
      <button
        type="button" class="grid min-h-control min-w-control place-items-center rounded-md transition hover:bg-accent"
        aria-label="Próximo mês" @click="shift(1)"
      >
        <Icon name="lucide:chevron-right" class="size-4" />
      </button>
    </div>
    <div class="grid grid-cols-7 text-center text-xs text-muted-foreground" aria-hidden="true">
      <span v-for="(weekday, index) in ['D', 'S', 'T', 'Q', 'Q', 'S', 'S']" :key="index" class="py-1">{{ weekday }}</span>
    </div>
    <div v-for="(week, index) in weeks" :key="index" class="grid grid-cols-7">
      <button
        v-for="day in week" :key="day.iso"
        type="button"
        class="m-0.5 grid h-9 place-items-center rounded-md text-sm tabular-nums transition disabled:opacity-25"
        :class="[
          day.iso === draft.startDate || day.iso === draft.endDate ? 'bg-primary font-semibold text-primary-foreground' :
          inRange(day.iso) ? 'bg-primary/15' : 'hover:bg-accent',
          day.inMonth ? '' : 'text-muted-foreground/60',
        ]"
        :disabled="day.past"
        :aria-pressed="day.iso === draft.startDate || day.iso === draft.endDate"
        :data-day="day.iso"
        @click="pick(day.iso)"
      >
        {{ day.day }}
      </button>
    </div>
    <div class="mt-3 grid grid-cols-2 gap-2">
      <label class="flex flex-col gap-1 text-xs font-medium">
        Começa às
        <input
          v-model="draft.startTime" type="time" step="900"
          class="min-h-control rounded-md border bg-background px-2 text-sm tabular-nums"
        >
      </label>
      <label class="flex flex-col gap-1 text-xs font-medium">
        Termina às
        <input
          v-model="draft.endTime" type="time" step="900"
          class="min-h-control rounded-md border bg-background px-2 text-sm tabular-nums"
        >
      </label>
    </div>
    <p v-if="line" class="mt-2 text-sm" data-period-range>{{ line }}</p>
  </div>
</template>
