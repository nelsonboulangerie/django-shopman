<script setup lang="ts">
// Campo de período canônico: um único controle visual para dois limites opcionais.
// O contrato externo segue strings ISO (`YYYY-MM-DD`) para preservar as APIs.
import { parseDate, type CalendarDate, type DateValue } from "@internationalized/date";
import type { DateRange } from "reka-ui";
import { computed, ref, useAttrs } from "vue";
import { vLocalizedSegments } from "../utils/localizedSegments";

defineOptions({ inheritAttrs: false });

export interface UiDateRangeValue {
  start?: string;
  end?: string;
}

const props = withDefaults(
  defineProps<{
    modelValue?: UiDateRangeValue;
    min?: string;
    max?: string;
    disabled?: boolean;
    readonly?: boolean;
    required?: boolean;
    id?: string;
    label?: string;
  }>(),
  { modelValue: () => ({ start: "", end: "" }), label: "Período" },
);

const emit = defineEmits<{ "update:modelValue": [value: { start: string; end: string }] }>();

const open = ref(false);
const attrs = useAttrs();
const fieldAttrs = computed(() => {
  const rest = { ...attrs };
  delete rest.class;
  return rest;
});

function asDate(value?: string): CalendarDate | undefined {
  if (!value) return undefined;
  try {
    return parseDate(value.slice(0, 10));
  } catch {
    return undefined;
  }
}

function asString(value?: DateValue): string {
  return value?.toString() ?? "";
}

function emitRange(next: DateRange | null | undefined) {
  emit("update:modelValue", {
    start: asString(next?.start),
    end: asString(next?.end),
  });
}

const value = computed<DateRange | null>({
  get: () => ({
    start: asDate(props.modelValue?.start),
    end: asDate(props.modelValue?.end),
  }),
  set: emitRange,
});
const minValue = computed(() => asDate(props.min));
const maxValue = computed(() => asDate(props.max));

function clearStart() {
  emit("update:modelValue", { start: "", end: props.modelValue?.end ?? "" });
}

function clearEnd() {
  emit("update:modelValue", { start: props.modelValue?.start ?? "", end: "" });
}

function clearAll() {
  emit("update:modelValue", { start: "", end: "" });
}

function shortDate(value?: string): string {
  if (!value) return "";
  const [year, month, day] = value.slice(0, 10).split("-");
  if (!year || !month || !day) return value;
  return `${day}/${month}/${year}`;
}

const rangeLabel = computed(() => {
  const start = shortDate(props.modelValue?.start);
  const end = shortDate(props.modelValue?.end);
  if (start && end && start === end) return start;
  if (start && end) return `${start} a ${end}`;
  if (start) return `A partir de ${start}`;
  if (end) return `Até ${end}`;
  return "Sem período definido";
});

function closeWhenComplete(next: DateRange) {
  emitRange(next);
  open.value = false;
}

const fieldUi = {
  base: "flex min-h-control min-w-0 flex-1 items-center gap-0.5 rounded-l-md border border-r-0 border-input bg-background px-3 text-sm tabular-nums text-foreground shadow-xs outline-none focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
  segment: "rounded px-0.5 outline-none data-[placeholder]:text-muted-foreground focus:bg-accent focus:text-accent-foreground",
  separatorIcon: "mx-1 size-3.5 shrink-0 text-muted-foreground",
};
const calendarUi = {
  root: "w-full",
  header: "mb-2 flex items-center justify-between gap-1",
  heading: "min-w-0 flex-1",
  headingLabel: "block w-full text-center text-sm font-semibold capitalize",
  body: "w-full",
  grid: "w-full border-collapse",
  gridRow: "grid grid-cols-7",
  gridWeekDaysRow: "mb-1 grid grid-cols-7",
  headCell: "grid size-control place-items-center text-xs font-medium text-muted-foreground capitalize",
  cell: "grid size-control place-items-center",
  cellTrigger:
    "grid size-control place-items-center rounded-md text-sm tabular-nums outline-none transition hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring data-[selected]:bg-primary data-[selected]:font-semibold data-[selected]:text-primary-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-35 data-[outside-view]:text-muted-foreground/50 data-[highlighted]:bg-primary/10 data-[highlighted]:text-foreground data-[selection-start]:bg-primary data-[selection-start]:text-primary-foreground data-[selection-end]:bg-primary data-[selection-end]:text-primary-foreground",
};
const navButton = {
  color: "neutral" as const,
  variant: "ghost" as const,
  class: "grid size-control place-items-center rounded-md text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring",
};
const previousYear = { ...navButton, "aria-label": "Ano anterior" };
const previousMonth = { ...navButton, "aria-label": "Mês anterior" };
const nextMonth = { ...navButton, "aria-label": "Próximo mês" };
const nextYear = { ...navButton, "aria-label": "Próximo ano" };
</script>

<template>
  <UiPopover v-model:open="open">
    <div :class="['min-w-0', attrs.class]" data-slot="date-range-field">
      <UiPopoverTrigger as-child>
        <button
          :id="id"
          type="button"
          class="flex min-h-control w-full min-w-0 items-center gap-2 rounded-md border border-input bg-background px-3 text-left text-sm text-foreground shadow-xs outline-none transition hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 sm:hidden"
          :aria-label="`${label}: ${rangeLabel}`"
          :disabled="disabled || readonly"
          data-slot="date-range-mobile-trigger"
        >
          <Icon name="lucide:calendar-range" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate">{{ rangeLabel }}</span>
        </button>
      </UiPopoverTrigger>
      <div v-localized-segments class="hidden min-w-0 sm:flex">
        <NuxtInputDate
          :id="id"
          v-model="value"
          v-bind="fieldAttrs"
          range
          locale="pt-BR"
          granularity="day"
          separator-icon="lucide:arrow-right"
          :aria-label="label"
          :min-value="minValue"
          :max-value="maxValue"
          :disabled="disabled"
          :readonly="readonly"
          :required="required"
          :ui="fieldUi"
        />
        <UiPopoverTrigger as-child>
          <button
            type="button"
            class="grid size-control shrink-0 place-items-center rounded-r-md border border-input bg-background text-muted-foreground shadow-xs outline-none transition hover:bg-accent hover:text-foreground focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50"
            :aria-label="`Abrir calendário de ${label.toLocaleLowerCase('pt-BR')}`"
            :disabled="disabled || readonly"
            data-slot="date-range-calendar-trigger"
          >
            <Icon name="lucide:calendar-range" class="size-4" aria-hidden="true" />
          </button>
        </UiPopoverTrigger>
      </div>
    </div>
    <UiPopoverContent
      align="start"
      :collision-padding="0"
      sticky="always"
      class="w-screen max-w-[20.5rem] p-1.5 min-[360px]:p-2"
      data-slot="date-range-calendar-popover"
    >
      <NuxtCalendar
        v-model="value"
        range
        locale="pt-BR"
        :aria-label="`Calendário de ${label.toLocaleLowerCase('pt-BR')}`"
        :min-value="minValue"
        :max-value="maxValue"
        :prev-month="previousMonth"
        :next-month="nextMonth"
        :prev-year="previousYear"
        :next-year="nextYear"
        :ui="calendarUi"
        @update:valid-model-value="closeWhenComplete"
      />
      <div class="mt-2 grid grid-cols-3 gap-1.5">
        <button
          type="button"
          class="min-h-control rounded-md px-2 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          :disabled="disabled || readonly || !modelValue?.start"
          data-date-range-clear-start
          @click="clearStart"
        >
          Sem início
        </button>
        <button
          type="button"
          class="min-h-control rounded-md px-2 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          :disabled="disabled || readonly || !modelValue?.end"
          data-date-range-clear-end
          @click="clearEnd"
        >
          Sem fim
        </button>
        <button
          type="button"
          class="min-h-control rounded-md px-2 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
          :disabled="disabled || readonly || (!modelValue?.start && !modelValue?.end)"
          data-date-range-clear-all
          @click="clearAll"
        >
          Limpar
        </button>
      </div>
    </UiPopoverContent>
  </UiPopover>
</template>

<style>
@media (max-height: 640px) {
  [data-reka-popper-content-wrapper]:has(> [data-slot="date-range-calendar-popover"]) {
    top: 0 !important;
    transform: none !important;
  }
}

[data-slot="date-range-calendar-popover"] [role="heading"][aria-level="2"] {
  display: none;
}
</style>
