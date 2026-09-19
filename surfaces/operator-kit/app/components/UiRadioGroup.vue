<script setup lang="ts" generic="T extends ChoiceValue">
// Escolha exclusiva do operador. Dono da seleção, do foco e do teclado; cada opção
// é um `UiRadio` filho (ou sai da prop `options`, para o caso trivial).
//
// Antes disto cada tela montava `<input type="radio">` nativo dentro de um `<label>`
// com borda — desenho do sistema no meio do desenho da casa — e a navegação por
// seta só funcionava porque o browser dava de graça. Aqui a seta é nossa: anda
// pulando opção desabilitada, dá a volta, e o Tab entra e sai do grupo por UMA
// parada, como manda o padrão de grupo de rádio.
import { computed, provide, reactive, shallowRef } from "vue";

import { firstEnabledIndex, lastEnabledIndex, stepIndex } from "../presentation/choice";
import { radioGroupKey, type RadioGroupContext, type RadioItem } from "../presentation/radioGroup";
import type { ChoiceOption, ChoiceValue } from "../types/choice";

const props = withDefaults(
  defineProps<{
    /** Valor escolhido (v-model). */
    modelValue?: T;
    /** Nome acessível do grupo, quando não há `<legend>` por perto. */
    label?: string;
    disabled?: boolean;
    orientation?: "vertical" | "horizontal";
    /** Atalho: renderiza as opções sem o app escrever um `UiRadio` por item. */
    options?: ChoiceOption<T>[];
  }>(),
  { orientation: "vertical" },
);

const emit = defineEmits<{ "update:modelValue": [value: T] }>();

const items = shallowRef<RadioItem[]>([]);

function select(value: ChoiceValue) {
  if (props.disabled) return;
  // O contexto é erased (`ChoiceValue`): quem sabe o tipo do grupo é a prop, e é
  // ela que o `v-model` do app enxerga.
  emit("update:modelValue", value as T);
}

function focusAt(index: number) {
  const item = items.value[index];
  if (!item) return;
  select(item.value);
  item.focus();
}

const context = reactive({
  selected: computed(() => props.modelValue),
  disabled: computed(() => Boolean(props.disabled)),
  select,
  register(item: RadioItem) {
    items.value = [...items.value, item];
  },
  unregister(item: RadioItem) {
    items.value = items.value.filter((registered) => registered !== item);
  },
  move(item: RadioItem, delta: number) {
    const from = items.value.indexOf(item);
    focusAt(stepIndex(items.value, from, delta));
  },
  moveToEdge(edge: "first" | "last") {
    focusAt(edge === "first" ? firstEnabledIndex(items.value) : lastEnabledIndex(items.value));
  },
  isTabStop(item: RadioItem) {
    const chosen = items.value.findIndex((registered) => registered.value === props.modelValue);
    const stop = chosen >= 0 ? chosen : firstEnabledIndex(items.value);
    return items.value[stop] === item;
  },
}) as RadioGroupContext;

provide(radioGroupKey, context);
</script>

<template>
  <div
    role="radiogroup"
    :aria-label="label"
    :aria-orientation="orientation"
    data-slot="radio-group"
    class="grid gap-2"
    :class="orientation === 'horizontal' ? 'grid-flow-col auto-cols-fr' : ''"
  >
    <slot>
      <UiRadio
        v-for="option in options ?? []"
        :key="String(option.value)"
        :value="option.value"
        :label="option.label"
        :description="option.hint"
        :disabled="option.disabled"
      />
    </slot>
  </div>
</template>
