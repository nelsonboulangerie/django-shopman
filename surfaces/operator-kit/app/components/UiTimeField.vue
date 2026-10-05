<script setup lang="ts">
// Campo de hora canônico: segmentos com teclado, setas e ciclo de 24 horas.
// O valor externo continua `HH:mm`, portanto nenhuma API ou projection muda.
import { parseTime, type Time } from "@internationalized/date";
import { computed } from "vue";
import { vLocalizedSegments } from "../utils/localizedSegments";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    disabled?: boolean;
    readonly?: boolean;
    required?: boolean;
    label?: string;
    /** Incremento dos minutos ao usar as setas. */
    minuteStep?: number;
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

const value = computed({
  get: () => asTime(props.modelValue),
  set: (next: Time | undefined) => emit("update:modelValue", next ? next.toString().slice(0, 5) : ""),
});

const fieldUi = {
  base: "flex min-h-control min-w-0 items-center gap-0.5 rounded-md border border-input bg-background px-3 text-sm tabular-nums text-foreground shadow-xs outline-none focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
  segment: "rounded px-0.5 outline-none data-[placeholder]:text-muted-foreground focus:bg-accent focus:text-accent-foreground",
};
</script>

<template>
  <div v-localized-segments>
    <NuxtInputTime
      v-model="value"
      v-bind="$attrs"
      locale="pt-BR"
      :hour-cycle="24"
      granularity="minute"
      :step="{ minute: minuteStep }"
      step-snapping
      :aria-label="label"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
      :ui="fieldUi"
      data-slot="time-field"
    >
      <Icon name="lucide:clock-3" class="ml-auto size-4 text-muted-foreground" aria-hidden="true" />
    </NuxtInputTime>
  </div>
</template>
