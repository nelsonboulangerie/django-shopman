<script setup lang="ts">
// Grupo de múltipla escolha canônico do Nuxt UI.
//
// A raiz, o fieldset, a legenda, o teclado e a integração de formulário pertencem
// ao `NuxtCheckboxGroup` (Reka UI). Este wrapper só traduz o contrato de opções já
// compartilhado pela suíte e aplica os tokens operacionais de toque. `table`,
// `card` e `list` continuam sendo as variantes oficiais, sem anatomia paralela.
import { computed, useAttrs } from "vue";

import type { ChoiceOption } from "../types/choice";

defineOptions({ inheritAttrs: false });

type CheckboxGroupVariant = "list" | "card" | "table";
type CheckboxGroupOrientation = "vertical" | "horizontal";
type CheckboxGroupIndicator = "start" | "end" | "hidden";
type CheckboxGroupUi = Partial<
  Record<
    | "root"
    | "fieldset"
    | "legend"
    | "item"
    | "container"
    | "base"
    | "indicator"
    | "icon"
    | "wrapper"
    | "label"
    | "description",
    string
  >
>;

const props = withDefaults(
  defineProps<{
    modelValue?: string[];
    items: ChoiceOption<string>[];
    legend?: string;
    disabled?: boolean;
    required?: boolean;
    name?: string;
    variant?: CheckboxGroupVariant;
    orientation?: CheckboxGroupOrientation;
    indicator?: CheckboxGroupIndicator;
    ui?: CheckboxGroupUi;
  }>(),
  {
    modelValue: () => [],
    variant: "list",
    orientation: "vertical",
    indicator: "start",
  },
);

const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();
const slots = defineSlots<{
  legend?: () => unknown;
  label?: (props: { item: ChoiceOption<string> & { id: string } }) => unknown;
  description?: (props: { item: ChoiceOption<string> & { id: string } }) => unknown;
}>();

const attrs = useAttrs();
function choiceItem(item: unknown): ChoiceOption<string> & { id: string } {
  return item as ChoiceOption<string> & { id: string };
}
const ui = computed<CheckboxGroupUi>(() => ({
  root: ["w-full", props.ui?.root].filter(Boolean).join(" "),
  fieldset: [props.variant === "table" ? "w-full" : "", props.ui?.fieldset]
    .filter(Boolean)
    .join(" "),
  // 44 px pertence ao alvo inteiro. O quadrado visual continua com a dimensão
  // canônica de 20 px, igual ao `UiCheckbox` individual.
  item: ["min-h-control", props.variant === "list" ? "py-1 pr-1" : "", props.ui?.item]
    .filter(Boolean)
    .join(" "),
  base: ["size-5", props.ui?.base].filter(Boolean).join(" "),
  icon: ["size-4", props.ui?.icon].filter(Boolean).join(" "),
  description: ["text-xs font-normal", props.ui?.description].filter(Boolean).join(" "),
  ...(props.ui?.legend ? { legend: props.ui.legend } : {}),
  ...(props.ui?.container ? { container: props.ui.container } : {}),
  ...(props.ui?.indicator ? { indicator: props.ui.indicator } : {}),
  ...(props.ui?.wrapper ? { wrapper: props.ui.wrapper } : {}),
  ...(props.ui?.label ? { label: props.ui.label } : {}),
}));
</script>

<template>
  <NuxtCheckboxGroup
    v-bind="attrs"
    :model-value="modelValue"
    :items="items"
    :legend="legend"
    :disabled="disabled"
    :required="required"
    :name="name"
    :variant="variant"
    :orientation="orientation"
    :indicator="indicator"
    value-key="value"
    label-key="label"
    description-key="hint"
    color="primary"
    size="md"
    data-slot="checkbox-group"
    :ui="ui"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="slots.legend" #legend>
      <slot name="legend" />
    </template>
    <template v-if="slots.label" #label="{ item }">
      <slot name="label" :item="choiceItem(item)" />
    </template>
    <template v-if="slots.description" #description="{ item }">
      <slot name="description" :item="choiceItem(item)" />
    </template>
  </NuxtCheckboxGroup>
</template>
