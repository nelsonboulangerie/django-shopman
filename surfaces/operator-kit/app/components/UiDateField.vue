<script setup lang="ts">
// Campo de data canônico da suíte. Mantém o contrato simples das APIs
// (`YYYY-MM-DD`), mas troca o desenho dependente do sistema operacional pela
// anatomia acessível de DateField + Calendar do Nuxt UI/Reka.
import { parseDate, type CalendarDate, type DateValue } from "@internationalized/date";
import { computed, ref } from "vue";
import { vLocalizedSegments } from "../utils/localizedSegments";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    min?: string;
    max?: string;
    disabled?: boolean;
    readonly?: boolean;
    required?: boolean;
    label?: string;
  }>(),
  { modelValue: "", label: "Data" },
);

const emit = defineEmits<{ "update:modelValue": [value: string] }>();
defineSlots<{ trigger?: () => unknown }>();
const open = ref(false);

function asDate(value?: string): CalendarDate | undefined {
  if (!value) return undefined;
  try {
    return parseDate(value.slice(0, 10));
  } catch {
    return undefined;
  }
}

const value = computed<DateValue | undefined>({
  get: () => asDate(props.modelValue),
  set: (next) => emit("update:modelValue", next?.toString() ?? ""),
});
const minValue = computed(() => asDate(props.min));
const maxValue = computed(() => asDate(props.max));

function pick(next: unknown) {
  // O componente Nuxt também aceita range/múltiplo; este wrapper deliberadamente
  // expõe só a variante de uma data.
  if (!next || Array.isArray(next) || typeof next !== "object" || "start" in next) return;
  value.value = next as DateValue;
  open.value = false;
}

const fieldUi = {
  base: "flex min-h-control min-w-0 flex-1 items-center gap-0.5 rounded-l-md border border-r-0 border-input bg-background px-3 text-sm tabular-nums text-foreground shadow-xs outline-none focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
  segment: "rounded px-0.5 outline-none data-[placeholder]:text-muted-foreground focus:bg-accent focus:text-accent-foreground",
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
  cellTrigger: "grid size-control place-items-center rounded-md text-sm tabular-nums outline-none transition hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring data-[selected]:bg-primary data-[selected]:font-semibold data-[selected]:text-primary-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-35 data-[outside-view]:text-muted-foreground/50",
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
    <UiPopoverTrigger v-if="$slots.trigger" as-child>
      <slot name="trigger" />
    </UiPopoverTrigger>
    <div v-else v-localized-segments class="flex min-w-0" data-slot="date-field">
      <NuxtInputDate
        v-model="value"
        v-bind="$attrs"
        locale="pt-BR"
        granularity="day"
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
          data-slot="date-calendar-trigger"
        >
          <Icon name="lucide:calendar-days" class="size-4" aria-hidden="true" />
        </button>
      </UiPopoverTrigger>
    </div>
    <UiPopoverContent
      align="start"
      :collision-padding="0"
      sticky="always"
      class="w-screen max-w-[20.5rem] p-1.5 min-[360px]:p-2"
      data-slot="date-calendar-popover"
    >
      <NuxtCalendar
        :model-value="value"
        locale="pt-BR"
        :aria-label="`Calendário de ${label.toLocaleLowerCase('pt-BR')}`"
        :min-value="minValue"
        :max-value="maxValue"
        :prev-month="previousMonth"
        :next-month="nextMonth"
        :prev-year="previousYear"
        :next-year="nextYear"
        :ui="calendarUi"
        @update:model-value="pick"
      />
    </UiPopoverContent>
  </UiPopover>
</template>

<style>
/* Em uma janela curta, o calendário é maior que o espaço acima e abaixo do
   gatilho. Reka o posiciona com topo negativo; nesse perfil ele vira um painel
   preso ao topo visível, mantendo a navegação do mês alcançável por toque. */
@media (max-height: 640px) {
  [data-reka-popper-content-wrapper]:has(> [data-slot="date-calendar-popover"]) {
    top: 0 !important;
    transform: none !important;
  }
}

[data-slot="date-calendar-popover"] [role="heading"][aria-level="2"] {
  display: none;
}
</style>
