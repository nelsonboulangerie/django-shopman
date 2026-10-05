<script setup lang="ts">
// Checkbox canônico do Nuxt UI, com o contrato operacional da suíte.
//
// A anatomia, o teclado, o estado misto e a integração com formulários pertencem
// ao `NuxtCheckbox` (Reka UI). Este wrapper conserva somente a API já usada pelos
// apps e amplia o alvo para o token de 44 px sem redesenhar o controle.
import { computed, useAttrs, useId, useTemplateRef } from "vue";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    indeterminate?: boolean;
    disabled?: boolean;
    label?: string;
    description?: string;
  }>(),
  { modelValue: false },
);

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();

const slots = defineSlots<{
  default?: () => unknown;
  description?: () => unknown;
}>();

const attrs = useAttrs();
const checkbox = useTemplateRef<{ $el?: HTMLElement }>("checkbox");
const descriptionId = useId();

const hasLabel = computed(() => Boolean(props.label) || Boolean(slots.default));
const hasDescription = computed(() => Boolean(props.description) || Boolean(slots.description));
const describedBy = computed(() =>
  hasDescription.value ? descriptionId : (attrs["aria-describedby"] as string | undefined),
);
const state = computed<boolean | "indeterminate">({
  get: () => (props.indeterminate ? "indeterminate" : props.modelValue),
  set: (value) => emit("update:modelValue", value === true),
});
const ui = computed(() => ({
  root: [
    "min-h-control rounded-md outline-offset-2",
    hasDescription.value ? "py-1.5" : "items-center",
    hasLabel.value ? "pr-1" : "size-control items-center justify-center",
  ].join(" "),
  // O pseudo-element amplia a área clicável até o root de 44 px sem transformar
  // o quadrado canônico de 20 px num bloco gigante.
  base: "size-5 after:absolute after:inset-0 after:content-['']",
  icon: "size-4",
  wrapper: "text-sm",
  description: "text-xs font-normal",
}));

defineExpose({
  focus: () => checkbox.value?.$el?.querySelector<HTMLElement>('[role="checkbox"]')?.focus(),
});
</script>

<template>
  <NuxtCheckbox
    ref="checkbox"
    v-model="state"
    v-bind="attrs"
    :disabled="disabled"
    :label="label"
    :description="description"
    :aria-describedby="describedBy"
    color="primary"
    size="md"
    data-slot="checkbox"
    :ui="ui"
  >
    <template v-if="hasLabel" #label>
      <slot>{{ label }}</slot>
    </template>
    <template v-if="hasDescription" #description>
      <span :id="descriptionId">
        <slot name="description">{{ description }}</slot>
      </span>
    </template>
  </NuxtCheckbox>
</template>
