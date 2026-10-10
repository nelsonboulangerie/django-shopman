<script setup lang="ts">
// UInputTime canônico com valor externo `HH:mm`, o contrato das APIs da suíte.
import { parseTime, type Time } from "@internationalized/date";
import type { TimeRangeFieldRootProps } from "reka-ui";
import { computed } from "vue";
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
    id?: string;
    label?: string;
    minuteStep?: number;
    isTimeUnavailable?: TimeRangeFieldRootProps["isTimeUnavailable"];
  }>(),
  { modelValue: "", label: "Hora", minuteStep: 1 },
);

const emit = defineEmits<{ "update:modelValue": [value: string] }>();

function asTime(value?: string): Time | undefined {
  if (!value) return undefined;
  try {
    return parseTime(value.slice(0, 5));
  } catch {
    return undefined;
  }
}

const value = computed<Time | undefined>({
  get: () => asTime(props.modelValue),
  set: (next) =>
    emit("update:modelValue", next ? next.toString().slice(0, 5) : ""),
});
const minValue = computed(() => asTime(props.min));
const maxValue = computed(() => asTime(props.max));
</script>

<template>
  <div v-localized-segments class="min-w-0">
    <NuxtInputTime
      :id="id"
      v-model="value"
      v-bind="$attrs"
      fixed
      locale="pt-BR"
      :hour-cycle="24"
      granularity="minute"
      size="xl"
      icon="lucide:clock-3"
      :step="{ minute: minuteStep }"
      step-snapping
      :aria-label="label"
      :min-value="minValue"
      :max-value="maxValue"
      :is-time-unavailable="isTimeUnavailable"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      class="min-h-control w-full"
      data-slot="time-field"
    />
  </div>
</template>
