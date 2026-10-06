<script setup lang="ts">
// Composição oficial do Nuxt UI para uma data: UInputDate + UPopover +
// UCalendar. Só traduzimos o valor ISO usado pelas APIs da suíte.
import { parseDate, type CalendarDate, type DateValue } from "@internationalized/date";
import { computed, ref, useAttrs } from "vue";
import { vLocalizedSegments } from "../utils/localizedSegments";

defineOptions({ inheritAttrs: false });

type InputDateRef = {
  inputsRef?: Array<{ $el?: HTMLElement }>;
};

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    min?: string;
    max?: string;
    disabled?: boolean;
    readonly?: boolean;
    required?: boolean;
    id?: string;
    label?: string;
    isDateDisabled?: (date: DateValue) => boolean;
    isDateUnavailable?: (date: DateValue) => boolean;
  }>(),
  { modelValue: "", label: "Data" },
);

const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const attrs = useAttrs();
const inputDate = ref<InputDateRef | null>(null);

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

const value = computed<DateValue | undefined>({
  get: () => asDate(props.modelValue),
  set: (next) => emit("update:modelValue", next?.toString() ?? ""),
});
const minValue = computed(() => asDate(props.min));
const maxValue = computed(() => asDate(props.max));

function pick(next: unknown) {
  if (!next || Array.isArray(next) || typeof next !== "object" || "start" in next) return;
  value.value = next as DateValue;
}
</script>

<template>
  <div
    v-localized-segments
    :class="['min-w-0', attrs.class]"
    data-slot="date-field"
  >
    <NuxtInputDate
      :id="id"
      ref="inputDate"
      v-model="value"
      v-bind="fieldAttrs"
      fixed
      locale="pt-BR"
      granularity="day"
      size="xl"
      :aria-label="label"
      :min-value="minValue"
      :max-value="maxValue"
      :is-date-unavailable="isDateUnavailable"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      class="min-h-control w-full"
    >
      <template #trailing>
        <NuxtPopover
          :reference="inputDate?.inputsRef?.[3]?.$el"
          :ui="{ content: 'z-[60]' }"
        >
          <NuxtButton
            color="neutral"
            variant="link"
            size="sm"
            icon="lucide:calendar-days"
            :aria-label="`Abrir calendário de ${label.toLocaleLowerCase('pt-BR')}`"
            class="px-0"
            data-slot="date-calendar-trigger"
            :disabled="disabled || readonly"
          />

          <template #content>
            <NuxtCalendar
              :model-value="value"
              locale="pt-BR"
              :aria-label="`Calendário de ${label.toLocaleLowerCase('pt-BR')}`"
              :min-value="minValue"
              :max-value="maxValue"
              :is-date-disabled="isDateDisabled"
              :is-date-unavailable="isDateUnavailable"
              class="p-2"
              data-slot="date-calendar-popover"
              @update:model-value="pick"
            />
          </template>
        </NuxtPopover>
      </template>
    </NuxtInputDate>
  </div>
</template>
