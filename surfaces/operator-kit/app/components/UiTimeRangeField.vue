<script setup lang="ts">
// A variante `range` oficial do UInputTime, mantendo strings `HH:mm` na borda.
import { parseTime, type Time } from "@internationalized/date";
import { useMediaQuery } from "@vueuse/core";
import type { TimeRangeFieldRootProps } from "reka-ui";
import { computed } from "vue";
import { vLocalizedSegments } from "../utils/localizedSegments";

defineOptions({ inheritAttrs: false });

export interface UiTimeRangeValue {
  start?: string;
  end?: string;
}

type TimeRange = NonNullable<TimeRangeFieldRootProps["modelValue"]>;

const props = withDefaults(
  defineProps<{
    modelValue?: UiTimeRangeValue;
    min?: string;
    max?: string;
    disabled?: boolean;
    readonly?: boolean;
    required?: boolean;
    id?: string;
    label?: string;
    minuteStep?: number;
    isTimeUnavailable?: TimeRangeFieldRootProps["isTimeUnavailable"];
  }>(),
  {
    modelValue: () => ({ start: "", end: "" }),
    label: "Horário",
    minuteStep: 1,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: { start: string; end: string }];
}>();
const desktop = useMediaQuery("(min-width: 640px)");

function asTime(value?: string): Time | undefined {
  if (!value) return undefined;
  try {
    return parseTime(value.slice(0, 5));
  } catch {
    return undefined;
  }
}

function asString(value?: TimeRange["start"]): string {
  return value?.toString().slice(0, 5) ?? "";
}

const value = computed<TimeRange>({
  get: () => ({
    start: asTime(props.modelValue?.start),
    end: asTime(props.modelValue?.end),
  }),
  set: (next) =>
    emit("update:modelValue", {
      start: asString(next?.start),
      end: asString(next?.end),
    }),
});
const minValue = computed(() => asTime(props.min));
const maxValue = computed(() => asTime(props.max));
</script>

<template>
  <div v-localized-segments class="min-w-0" data-slot="time-range-field">
    <NuxtInputTime
      :id="id"
      v-model="value"
      v-bind="$attrs"
      range
      fixed
      locale="pt-BR"
      :hour-cycle="24"
      granularity="minute"
      :size="desktop ? 'xl' : 'xs'"
      icon="lucide:clock-3"
      separator-icon="lucide:arrow-right"
      :step="{ minute: minuteStep }"
      step-snapping
      :aria-label="label"
      :min-value="minValue"
      :max-value="maxValue"
      :is-time-unavailable="isTimeUnavailable"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      class="min-h-control w-full min-w-0"
    />
  </div>
</template>
