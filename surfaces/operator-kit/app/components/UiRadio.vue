<script setup lang="ts">
// Uma opção de `UiRadioGroup`. Só existe dentro de um — sozinha ela não teria como
// saber quem mais disputa a escolha.
//
// Variante `card` é o padrão porque é o que as três telas que existiam já faziam à
// mão (Disparo, Modelo de anúncio, Início do dispositivo): caixa com borda que
// acende em `primary` quando escolhida. `inline` é a mesma opção sem a caixa, para
// quando o grupo já mora dentro de um cartão.
import { computed, inject, onBeforeUnmount, useId, useTemplateRef } from "vue";

import { radioGroupKey, type RadioItem } from "../presentation/radioGroup";
import type { ChoiceValue } from "../types/choice";

const props = withDefaults(
  defineProps<{
    value: ChoiceValue;
    label?: string;
    description?: string;
    disabled?: boolean;
    variant?: "card" | "inline";
  }>(),
  { variant: "card" },
);

const slots = defineSlots<{
  default?: () => unknown;
  description?: () => unknown;
}>();

const injected = inject(radioGroupKey, null);
if (!injected) {
  // Falhar gritando, não em silêncio: um rádio fora do grupo parece funcionar
  // (ele desenha), mas nunca desmarca o irmão — o pior tipo de defeito.
  throw new Error("UiRadio precisa estar dentro de um UiRadioGroup.");
}
// O `throw` acima narrowa o `injected`, mas o template é compilado à parte e não
// herda esse estreitamento; ele lê esta const, que já nasce não-nula.
const group = injected;

const control = useTemplateRef<HTMLButtonElement>("control");
const descriptionId = useId();

const item: RadioItem = {
  get value() {
    return props.value;
  },
  get disabled() {
    return Boolean(props.disabled) || group.disabled;
  },
  focus: () => control.value?.focus(),
};

group.register(item);
onBeforeUnmount(() => group.unregister(item));

const checked = computed(() => group.selected === props.value);
const isDisabled = computed(() => Boolean(props.disabled) || group.disabled);
const hasLabel = computed(() => Boolean(props.label) || Boolean(slots.default));
const hasDescription = computed(() => Boolean(props.description) || Boolean(slots.description));

function onKeydown(event: KeyboardEvent) {
  const forward = event.key === "ArrowDown" || event.key === "ArrowRight";
  const backward = event.key === "ArrowUp" || event.key === "ArrowLeft";

  if (forward || backward) {
    event.preventDefault();
    group.move(item, forward ? 1 : -1);
    return;
  }
  if (event.key === "Home" || event.key === "End") {
    event.preventDefault();
    group.moveToEdge(event.key === "Home" ? "first" : "last");
  }
}
</script>

<template>
  <button
    ref="control"
    type="button"
    role="radio"
    :aria-checked="checked"
    :aria-describedby="hasDescription ? descriptionId : undefined"
    :disabled="isDisabled"
    :tabindex="group.isTabStop(item) ? 0 : -1"
    data-slot="radio"
    class="group/radio flex min-h-control w-full gap-2.5 text-left text-sm outline-offset-2 transition focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50"
    :class="[
      hasDescription ? 'items-start' : 'items-center',
      variant === 'card'
        ? ['rounded-lg border p-3', checked ? 'border-primary bg-primary/5' : 'border-border hover:bg-accent/40']
        : 'rounded-md py-1.5 pr-1',
    ]"
    @click="group.select(value)"
    @keydown="onKeydown"
  >
    <span
      class="grid size-5 shrink-0 place-items-center rounded-full border transition"
      :class="[
        hasDescription ? 'mt-0.5' : '',
        checked ? 'border-primary' : 'border-border bg-background group-hover/radio:border-primary/60',
      ]"
    >
      <span v-if="checked" class="size-2.5 rounded-full bg-primary"></span>
    </span>

    <span v-if="hasLabel" class="min-w-0">
      <span class="block font-medium">
        <slot>{{ label }}</slot>
      </span>
      <span v-if="hasDescription" :id="descriptionId" class="block text-xs font-normal text-muted-foreground">
        <slot name="description">{{ description }}</slot>
      </span>
    </span>
  </button>
</template>
