<script setup lang="ts">
// Seleção binária do operador — a peça que faltava.
//
// Até aqui TODO checkbox das nove superfícies era o controle nativo do browser com
// uma tinta do Tailwind por cima (`size-4 rounded border-border`, às vezes um
// `accent-color`): desenho do sistema operacional, não da casa, diferente em cada
// dispositivo e sem estado INDETERMINADO — que é justamente o que falta para um
// "marcar todos" honesto (o do catálogo do Gestor de Pedidos mostra "vazio" quando
// metade das linhas está marcada, e mente).
//
// É um `<button role="checkbox">`, não um `<input>`: uma parada de tabulação só, o
// alvo de toque cobre a linha inteira (rótulo incluso) e o nome acessível sai do
// conteúdo. O desenho da marca é o mesmo que o `ColumnPicker` já usava — quadrado
// de borda que enche de `primary` com o check do lucide —, agora em um lugar só.
import { computed, useId, useTemplateRef } from "vue";

const props = withDefaults(
  defineProps<{
    /** Marcado (v-model). */
    modelValue?: boolean;
    /**
     * Terceiro estado: parcialmente marcado (`aria-checked="mixed"`). Quem manda
     * aqui é o pai — o "marcar todos" calcula `alguns && !todos`. Clicar num
     * indeterminado MARCA tudo, que é o que a mão espera.
     */
    indeterminate?: boolean;
    disabled?: boolean;
    /** Rótulo. Também aceita o slot default quando o texto tem marcação. */
    label?: string;
    /** Segunda linha, menor e apagada — a consequência da escolha. */
    description?: string;
  }>(),
  { modelValue: false },
);

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();

const slots = defineSlots<{
  default?: () => unknown;
  description?: () => unknown;
}>();

const control = useTemplateRef<HTMLButtonElement>("control");
const descriptionId = useId();

const hasLabel = computed(() => Boolean(props.label) || Boolean(slots.default));
const hasDescription = computed(() => Boolean(props.description) || Boolean(slots.description));
const marked = computed(() => props.indeterminate || props.modelValue);

function toggle() {
  if (props.disabled) return;
  // Indeterminado → marcado. Sair de "alguns" para "nenhum" seria desfazer o que o
  // operador já escolheu; ele clica o mestre para ALCANÇAR o todo.
  emit("update:modelValue", props.indeterminate ? true : !props.modelValue);
}

defineExpose({ focus: () => control.value?.focus() });
</script>

<template>
  <button
    ref="control"
    type="button"
    role="checkbox"
    :aria-checked="indeterminate ? 'mixed' : modelValue"
    :disabled="disabled"
    :aria-describedby="hasDescription ? descriptionId : undefined"
    data-slot="checkbox"
    class="group/checkbox inline-flex min-h-control gap-2.5 rounded-md text-left text-sm outline-offset-2 transition focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50"
    :class="[
      hasDescription ? 'items-start py-1.5' : 'items-center',
      hasLabel ? 'pr-1' : 'size-control justify-center',
    ]"
    @click="toggle"
  >
    <!-- `outline` de verdade, não `ring`: o anel de foco por box-shadow some no modo
         de alto contraste do sistema, e o operador que depende dele fica sem foco
         visível. Mesmo motivo no rádio e no select. -->
    <span
      class="grid size-5 shrink-0 place-items-center rounded border transition"
      :class="[
        hasDescription ? 'mt-0.5' : '',
        marked
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-background group-hover/checkbox:border-primary/60',
      ]"
    >
      <Icon v-if="indeterminate" name="lucide:minus" class="size-3.5" />
      <Icon v-else-if="modelValue" name="lucide:check" class="size-3.5" />
    </span>

    <span v-if="hasLabel" class="min-w-0">
      <span class="block">
        <slot>{{ label }}</slot>
      </span>
      <span v-if="hasDescription" :id="descriptionId" class="block text-xs font-normal text-muted-foreground">
        <slot name="description">{{ description }}</slot>
      </span>
    </span>
  </button>
</template>
