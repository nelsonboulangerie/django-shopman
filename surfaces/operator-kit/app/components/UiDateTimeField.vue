<script setup lang="ts">
// Data e hora são dois gestos no dispositivo, mas um único valor no contrato.
// Separá-los evita o campo `datetime-local` estreito e variável entre sistemas.
import { ref, watch } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    id?: string;
    min?: string;
    max?: string;
    disabled?: boolean;
    readonly?: boolean;
    required?: boolean;
    label?: string;
    minuteStep?: number;
  }>(),
  { modelValue: "", label: "Data e hora", minuteStep: 1 },
);

const emit = defineEmits<{ "update:modelValue": [value: string] }>();

const date = ref(props.modelValue.slice(0, 10));
const time = ref(props.modelValue.slice(11, 16));

watch(
  () => props.modelValue,
  (next) => {
    const nextDate = next.slice(0, 10);
    const nextTime = next.slice(11, 16);
    if (nextDate !== date.value) date.value = nextDate;
    if (nextTime !== time.value) time.value = nextTime;
  },
);

watch([date, time], ([nextDate, nextTime]) => {
  if (nextDate && nextTime) {
    emit("update:modelValue", `${nextDate}T${nextTime}`);
  } else if (props.modelValue) {
    // Um valor parcial não atravessa o contrato da API. Os segmentos continuam
    // na tela até o operador completar ambos; ao apagar, o valor externo zera.
    emit("update:modelValue", "");
  }
});
</script>

<template>
  <div
    class="grid min-w-0 grid-cols-[minmax(0,1fr)_minmax(7rem,0.55fr)] gap-2 max-[380px]:grid-cols-1"
    role="group"
    :aria-label="label"
    data-slot="date-time-field"
  >
    <UiDateField
      :id="id ? `${id}-date` : undefined"
      v-model="date"
      :label="`${label}, data`"
      :min="min?.slice(0, 10)"
      :max="max?.slice(0, 10)"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
    />
    <UiTimeField
      :id="id ? `${id}-time` : undefined"
      v-model="time"
      :label="`${label}, hora`"
      :minute-step="minuteStep"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
    />
  </div>
</template>
