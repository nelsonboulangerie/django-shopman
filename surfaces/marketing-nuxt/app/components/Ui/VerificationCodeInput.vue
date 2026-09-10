<script setup lang="ts">
import { PinInputInput, PinInputRoot } from "reka-ui";
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    id: string;
    name?: string;
    length?: number;
    disabled?: boolean;
    autofocus?: boolean;
    label?: string;
    help?: string;
  }>(),
  {
    modelValue: "",
    name: "one-time-code",
    length: 6,
    disabled: false,
    autofocus: false,
    label: "",
    help: "Abra o autenticador cadastrado para sua conta e copie o código atual.",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  complete: [value: string];
}>();

const positions = computed(() =>
  Array.from({ length: props.length }, (_, index) => index),
);
const labelId = computed(() => `${props.id}-label`);
const helpId = computed(() => `${props.id}-help`);
const visibleLabel = computed(
  () =>
    props.label ||
    `Código de ${props.length} ${props.length === 1 ? "dígito" : "dígitos"} do autenticador`,
);
const digits = computed<number[]>({
  get: () =>
    Array.from(
      props.modelValue.replace(/\D/g, "").slice(0, props.length),
      Number,
    ),
  set: (value) => {
    emit(
      "update:modelValue",
      value.join("").replace(/\D/g, "").slice(0, props.length),
    );
  },
});

function complete(value: number[]) {
  emit("complete", value.join("").slice(0, props.length));
}
</script>

<template>
  <div>
    <label :id="labelId" :for="id" class="text-sm font-medium">
      {{ visibleLabel }}
    </label>
    <PinInputRoot
      :id="id"
      v-model="digits"
      :name="name"
      type="number"
      otp
      :disabled="disabled"
      class="mt-2 flex max-w-full gap-1.5 sm:gap-2"
      role="group"
      :aria-labelledby="labelId"
      :aria-describedby="helpId"
      @complete="complete"
    >
      <PinInputInput
        v-for="position in positions"
        :key="position"
        :index="position"
        :autofocus="autofocus && position === 0"
        :aria-label="`Dígito ${position + 1} de ${length}`"
        class="border-input bg-card focus-visible:border-ring focus-visible:ring-ring/20 h-12 w-10 rounded-md border text-center text-lg font-semibold tabular-nums shadow-xs outline-none transition-[color,box-shadow] focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 sm:w-11"
      />
    </PinInputRoot>
    <p :id="helpId" class="mt-2 text-xs text-muted-foreground">
      {{ help }}
    </p>
  </div>
</template>
