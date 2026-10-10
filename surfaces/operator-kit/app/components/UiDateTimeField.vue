<script setup lang="ts">
// Data e hora são dois gestos no dispositivo, mas um único valor no contrato.
// Separá-los evita o campo `datetime-local` estreito e variável entre sistemas.
import { computed, ref, watch } from "vue";

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

// O limite é um instante (`YYYY-MM-DDTHH:mm`). A data recebe só o dia; a hora
// recebe o limite apenas no dia-limite, porque nos outros dias toda hora vale.
// Sem isso, no dia de `min` a hora ficava livre e o campo aceitava um instante
// anterior ao limite.
const timeMin = computed(() =>
  props.min && date.value && date.value === props.min.slice(0, 10)
    ? props.min.slice(11, 16) || undefined
    : undefined,
);
const timeMax = computed(() =>
  props.max && date.value && date.value === props.max.slice(0, 10)
    ? props.max.slice(11, 16) || undefined
    : undefined,
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
      :min="timeMin"
      :max="timeMax"
      :disabled="disabled"
      :readonly="readonly"
      :required="required"
    />
  </div>
</template>
