<script setup lang="ts">
import { getCurrentInstance, normalizeClass } from "vue";
import type { HTMLAttributes } from "vue";
import { twMerge } from "tailwind-merge";

defineOptions({ inheritAttrs: false });

const props = defineProps<{
  modelValue?: unknown;
  class?: HTMLAttributes["class"];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: unknown];
  change: [event: Event];
}>();

const select = useTemplateRef<HTMLSelectElement>("select");

// `modelValue` e `value` são contratos distintos aqui: alguns call sites usam
// v-model, enquanto outros deliberadamente leem o Event nativo em @change.
// Quando não há a prop modelValue, não ligamos :value e deixamos o attr value
// intacto. Testar presença (em vez do valor) preserva também um v-model que
// comece legitimamente como undefined.
const hasModelValue = Object.prototype.hasOwnProperty.call(
  getCurrentInstance()?.vnode.props ?? {},
  "modelValue",
);
const modelBinding = computed(() => hasModelValue ? { value: props.modelValue } : {});

const baseClass = [
  "h-11 rounded-md border border-border bg-background px-3 py-1 text-sm text-foreground shadow-xs outline-none transition-[color,box-shadow]",
  "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
  "focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
  "aria-invalid:border-destructive aria-invalid:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40",
].join(" ");

function optionValue(option: HTMLOptionElement): unknown {
  return Object.prototype.hasOwnProperty.call(option, "_value")
    ? (option as HTMLOptionElement & { _value: unknown })._value
    : option.value;
}

function onChange(event: Event) {
  const target = event.target as HTMLSelectElement;
  const selected = target.selectedOptions[0];
  const value = target.multiple
    ? Array.from(target.selectedOptions, optionValue)
    : selected ? optionValue(selected) : target.value;

  emit("update:modelValue", value);
  emit("change", event);
}

defineExpose({ select });
</script>

<template>
  <select
    v-bind="{ ...$attrs, ...modelBinding }"
    ref="select"
    data-slot="native-select"
    :class="twMerge(baseClass, normalizeClass(props.class))"
    @change="onChange"
  >
    <slot />
  </select>
</template>
