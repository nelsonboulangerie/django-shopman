<script setup lang="ts">
// Tipo 2 dos controles de data da casa: "Período" (decisão do dono, 02/10/2026).
//
// O desenho é o do B.I., que o dono julgou o melhor da casa e que nasceu lá
// (`bi-nuxt/app/components/BiTopBar.vue`): UM botão que sempre DIZ a janela ativa
// ("28D · 05/09 a 02/10", "Hoje, qui 02/10"); os chips e o personalizado moram no
// popover dele, para a barra não disputar espaço nem rolar em tela estreita. O que
// se acrescentou: ‹ › dos lados, que andam um período IGUAL ao escolhido (dia → dia
// anterior, semana → semana anterior, mês → mês anterior, N dias → os N dias antes),
// e "Voltar para hoje" quando o período não é mais o de hoje.
//
// Cada consumidor declara as granularidades que aceita (`presets`): o KDS só dia, as
// Encomendas dia e semana, o B.I. todas mais o personalizado. Sem personalizado, o
// popover oferece "Ir para o dia" no lugar dele.
//
// O estado é do consumidor (`v-model`): quem guarda na URL guarda na URL.
import { onClickOutside } from "@vueuse/core";
import { computed, ref, useTemplateRef } from "vue";

import {
  CUSTOM_PERIOD,
  PERIOD_PRESETS,
  currentPeriod,
  customPeriod,
  goToDate,
  isCurrentPeriod,
  periodLabel,
  periodStepLabels,
  resolvePeriod,
  stepPeriod,
  todayIso,
  withPreset,
  type PeriodBounds,
  type PeriodSelection,
} from "../presentation/dates";

const props = withDefaults(
  defineProps<{
    modelValue: PeriodSelection;
    /** Granularidades aceitas, na ordem da tela (chaves de `PERIOD_PRESETS`). */
    presets?: readonly string[];
    /** Aceita intervalo personalizado (De/Até). */
    custom?: boolean;
    /** O hoje da loja; omitido, o do dispositivo. */
    today?: string;
    min?: string;
    max?: string;
    /** Onde "Máx" começa. */
    epoch?: string;
    /** Nome do controle para leitor de tela ("Período de análise"). */
    label?: string;
    /** Lado em que o popover se alinha ao botão. */
    align?: "start" | "end";
  }>(),
  {
    presets: () => ["day"],
    custom: false,
    today: undefined,
    min: undefined,
    max: undefined,
    epoch: undefined,
    label: "Período",
    align: "end",
  },
);

const emit = defineEmits<{ "update:modelValue": [PeriodSelection] }>();

const bounds = computed<PeriodBounds>(() => ({
  today: props.today || todayIso(),
  min: props.min,
  max: props.max,
  epoch: props.epoch,
}));
const range = computed(() => resolvePeriod(props.modelValue, bounds.value));
const buttonLabel = computed(() => periodLabel(props.modelValue, range.value, bounds.value.today));
const steps = computed(() => periodStepLabels(props.modelValue.preset));
const prev = computed(() => stepPeriod(props.modelValue, -1, bounds.value));
const next = computed(() => stepPeriod(props.modelValue, 1, bounds.value));
const current = computed(() => isCurrentPeriod(props.modelValue));

const allowed = computed(() => PERIOD_PRESETS.filter((preset) => props.presets.includes(preset.key)));
const calendarPresets = computed(() => allowed.value.filter((preset) => preset.kind === "calendar"));
const rollingPresets = computed(() => allowed.value.filter((preset) => preset.kind === "rolling"));
const columns = (count: number) => `grid-template-columns: repeat(${Math.min(Math.max(count, 1), 4)}, minmax(0, 1fr))`;

const open = ref(false);
const customFrom = ref("");
const customTo = ref("");
const jumpTo = ref("");
const root = useTemplateRef<HTMLElement>("root");
onClickOutside(root, () => {
  open.value = false;
});

function set(selection: PeriodSelection | null) {
  if (selection) emit("update:modelValue", selection);
}

function toggle() {
  if (!open.value) {
    customFrom.value = range.value.date_from;
    customTo.value = range.value.date_to;
    jumpTo.value = range.value.date_from;
  }
  open.value = !open.value;
}

function pick(key: string) {
  set(withPreset(props.modelValue, key, bounds.value));
  open.value = false;
}

function submitCustom() {
  if (!customFrom.value || !customTo.value) return;
  set(customPeriod(customFrom.value, customTo.value));
  open.value = false;
}

function submitJump() {
  if (!jumpTo.value) return;
  set(goToDate(props.modelValue, jumpTo.value, bounds.value));
  open.value = false;
}

function backToToday() {
  // Do personalizado, "hoje" é a primeira granularidade que o consumidor aceita.
  if (props.modelValue.preset === CUSTOM_PERIOD) {
    set({ preset: allowed.value[0]?.key ?? "day", from: "", to: "" });
    return;
  }
  set(currentPeriod(props.modelValue));
}

const chipClass = (active: boolean) =>
  active
    ? "bg-card font-semibold text-foreground shadow-sm"
    : "text-muted-foreground hover:bg-card/60 hover:text-foreground";
const arrowClass =
  "grid size-control shrink-0 place-items-center rounded-md border border-border bg-background text-foreground transition hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-40";
</script>

<template>
  <div ref="root" class="flex flex-wrap items-center gap-2" role="group" :aria-label="label" data-period-picker>
    <div class="relative flex items-center gap-1">
      <button
        type="button"
        :class="arrowClass"
        :aria-label="steps.prev"
        :title="steps.prev"
        :disabled="!prev"
        data-period-prev
        @click="set(prev)"
      >
        <Icon name="lucide:chevron-left" class="size-5" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="inline-flex min-h-control items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground"
        :aria-expanded="open"
        :aria-label="`${label}: ${buttonLabel}`"
        data-period-button
        @click="toggle"
      >
        <Icon name="lucide:calendar-range" class="size-4 text-muted-foreground" aria-hidden="true" />
        <span class="tabular-nums" data-period-label>{{ buttonLabel }}</span>
        <Icon name="lucide:chevron-down" class="size-4 text-muted-foreground" aria-hidden="true" />
      </button>
      <button
        type="button"
        :class="arrowClass"
        :aria-label="steps.next"
        :title="steps.next"
        :disabled="!next"
        data-period-next
        @click="set(next)"
      >
        <Icon name="lucide:chevron-right" class="size-5" aria-hidden="true" />
      </button>

      <div
        v-if="open"
        class="absolute top-full z-20 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-md border border-border bg-card p-3 shadow-md"
        :class="align === 'end' ? 'right-0' : 'left-0'"
        data-period-popover
      >
        <template v-if="calendarPresets.length > 1 || (calendarPresets.length && rollingPresets.length)">
          <p class="mb-2 text-xs font-medium text-muted-foreground">Período</p>
          <div class="grid gap-1.5 rounded-md bg-muted p-1" :style="columns(calendarPresets.length)" role="group" aria-label="Período do calendário">
            <button
              v-for="preset in calendarPresets"
              :key="preset.key"
              type="button"
              class="inline-flex min-h-control items-center justify-center rounded-md px-1 text-sm whitespace-nowrap transition-all"
              :class="chipClass(modelValue.preset === preset.key)"
              :data-period-preset="preset.key"
              @click="pick(preset.key)"
            >
              {{ preset.label }}
            </button>
          </div>
        </template>
        <template v-if="rollingPresets.length">
          <p class="mt-3 mb-2 text-xs font-medium text-muted-foreground">Últimos</p>
          <div class="grid gap-1.5 rounded-md bg-muted p-1" :style="columns(rollingPresets.length)" role="group" aria-label="Janelas móveis">
            <button
              v-for="preset in rollingPresets"
              :key="preset.key"
              type="button"
              class="inline-flex min-h-control items-center justify-center rounded-md px-1 text-sm whitespace-nowrap transition-all"
              :class="chipClass(modelValue.preset === preset.key)"
              :data-period-preset="preset.key"
              @click="pick(preset.key)"
            >
              {{ preset.label }}
            </button>
          </div>
        </template>

        <template v-if="custom">
          <div v-if="allowed.length" class="my-3 border-t border-border"></div>
          <p class="mb-2 text-xs font-medium text-muted-foreground">Personalizado</p>
          <div class="grid grid-cols-2 gap-2">
            <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              De
              <input
                v-model="customFrom"
                type="date"
                :min="min"
                :max="max"
                class="min-h-control w-full rounded-md border border-border bg-background px-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
                data-period-custom-from
              />
            </label>
            <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
              Até
              <input
                v-model="customTo"
                type="date"
                :min="min"
                :max="max"
                class="min-h-control w-full rounded-md border border-border bg-background px-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
                data-period-custom-to
              />
            </label>
          </div>
          <button
            type="button"
            class="mt-2 inline-flex min-h-control w-full items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
            :disabled="!customFrom || !customTo"
            data-period-custom-apply
            @click="submitCustom"
          >
            Aplicar período
          </button>
        </template>
        <template v-else>
          <div v-if="calendarPresets.length > 1 || rollingPresets.length" class="my-3 border-t border-border"></div>
          <label class="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
            Ir para o dia
            <input
              v-model="jumpTo"
              type="date"
              :min="min"
              :max="max"
              class="min-h-control w-full rounded-md border border-border bg-background px-2 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring"
              data-period-jump
            />
          </label>
          <button
            type="button"
            class="mt-2 inline-flex min-h-control w-full items-center justify-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
            :disabled="!jumpTo"
            data-period-jump-apply
            @click="submitJump"
          >
            Mostrar esta data
          </button>
        </template>
      </div>
    </div>

    <button
      v-if="!current"
      type="button"
      class="inline-flex min-h-control items-center rounded-md px-3 text-sm font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
      data-period-today
      @click="backToToday"
    >
      Voltar para hoje
    </button>
  </div>
</template>
