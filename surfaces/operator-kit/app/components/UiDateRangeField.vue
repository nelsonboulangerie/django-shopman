<script setup lang="ts">
// Composição oficial do Nuxt UI para intervalo: UInputDate(range) + UPopover +
// UCalendar(range). O contrato externo continua em ISO (`YYYY-MM-DD`) para não
// contaminar APIs e projections com os objetos de @internationalized/date.
import { parseDate, type CalendarDate, type DateValue } from "@internationalized/date";
import { useScreen } from "../composables/useScreen";
import type { DateRange } from "reka-ui";
import { computed, ref, useAttrs } from "vue";
import { vLocalizedSegments } from "../utils/localizedSegments";

defineOptions({ inheritAttrs: false });

export interface UiDateRangeValue {
  start?: string;
  end?: string;
}

type InputDateRef = {
  inputsRef?: Array<{ $el?: HTMLElement }>;
};

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
    clearable?: boolean;
    allowOpenEnded?: boolean;
    isDateDisabled?: (date: DateValue) => boolean;
    isDateUnavailable?: (date: DateValue) => boolean;
  }>(),
  {
    modelValue: () => ({ start: "", end: "" }),
    label: "Período",
    clearable: true,
    allowOpenEnded: true,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: { start: string; end: string }];
}>();

const attrs = useAttrs();
const inputDate = ref<InputDateRef | null>(null);
const screen = useScreen();
const desktop = computed(() => !screen.belowSm.value);

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

const value = computed<DateRange>({
  get: () => ({
    start: asDate(props.modelValue?.start),
    end: asDate(props.modelValue?.end),
  }),
  set: emitRange,
});
const minValue = computed(() => asDate(props.min));
const maxValue = computed(() => asDate(props.max));

function clearStart() {
  emit("update:modelValue", {
    start: "",
    end: props.modelValue?.end ?? "",
  });
}

function clearEnd() {
  emit("update:modelValue", {
    start: props.modelValue?.start ?? "",
    end: "",
  });
}

function clearAll() {
  emit("update:modelValue", { start: "", end: "" });
}
</script>

<template>
  <div
    v-localized-segments
    :class="['min-w-0', attrs.class]"
    data-slot="date-range-field"
  >
    <NuxtInputDate
      :id="id"
      ref="inputDate"
      v-model="value"
      v-bind="fieldAttrs"
      range
      fixed
      locale="pt-BR"
      granularity="day"
      :size="desktop ? 'xl' : 'xs'"
      separator-icon="lucide:arrow-right"
      :aria-label="label"
      :min-value="minValue"
      :max-value="maxValue"
      :is-date-unavailable="isDateUnavailable"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      class="min-h-control w-full min-w-0"
    >
      <template #trailing>
        <!-- Sem `:ui` por instância: o calendário nasce no portal DEPOIS do popover ou
             do modal que contém o campo, e com o mesmo z do tema fica por cima dele. Os
             segmentos no celular usam a largura oficial (o `w-6` local quebrava o "mm" em
             duas linhas a 390 px, no diálogo de canais do Gestor). -->
        <NuxtPopover :reference="inputDate?.inputsRef?.[0]?.$el">
          <NuxtButton
            color="neutral"
            variant="link"
            size="sm"
            icon="lucide:calendar-range"
            :aria-label="`Abrir calendário de ${label.toLocaleLowerCase('pt-BR')}`"
            class="px-0"
            data-slot="date-range-calendar-trigger"
            :disabled="disabled || readonly"
          />

          <template #content>
            <div data-slot="date-range-calendar-popover">
              <NuxtCalendar
                v-model="value"
                range
                locale="pt-BR"
                :number-of-months="desktop ? 2 : 1"
                :aria-label="`Calendário de ${label.toLocaleLowerCase('pt-BR')}`"
                :min-value="minValue"
                :max-value="maxValue"
                :is-date-disabled="isDateDisabled"
                :is-date-unavailable="isDateUnavailable"
                class="p-2"
              />

              <div
                v-if="clearable"
                class="flex flex-wrap items-center justify-end gap-1 border-t border-default px-2 py-1.5"
              >
                <NuxtButton
                  v-if="allowOpenEnded"
                  type="button"
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  label="Sem início"
                  :disabled="disabled || readonly || !modelValue?.start"
                  data-date-range-clear-start
                  @click="clearStart"
                />
                <NuxtButton
                  v-if="allowOpenEnded"
                  type="button"
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  label="Sem fim"
                  :disabled="disabled || readonly || !modelValue?.end"
                  data-date-range-clear-end
                  @click="clearEnd"
                />
                <NuxtButton
                  type="button"
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  label="Limpar"
                  :disabled="disabled || readonly || (!modelValue?.start && !modelValue?.end)"
                  data-date-range-clear-all
                  @click="clearAll"
                />
              </div>
            </div>
          </template>
        </NuxtPopover>
      </template>
    </NuxtInputDate>
  </div>
</template>
