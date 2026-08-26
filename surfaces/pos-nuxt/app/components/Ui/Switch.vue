<template>
  <button
    type="button"
    role="switch"
    data-slot="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    :class="root({ class: normalizeClass(props.class) || undefined })"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span :class="thumb({ on: modelValue })" aria-hidden="true" />
  </button>
</template>

<script lang="ts">
  import { normalizeClass } from "vue";
  import type { HTMLAttributes } from "vue";

  export type SwitchProps = {
    /** Ligado? */
    modelValue?: boolean;
    disabled?: boolean;
    class?: HTMLAttributes["class"];
  };
</script>

<script lang="ts" setup>
  // Interruptor de verdade — a peça que faltava no balcão. Um botão-com-check
  // ("Emitir nota  ✓/–") diz "eu executo"; um switch diz "eu sou um estado", e
  // era estado o que essas perguntas sempre foram: liga/desliga que o cliente
  // escolhe e o operador transmite.
  //
  // Escrito à mão, sem lib nova: usa os tokens do PDV (neutro; `--primary` é o
  // escuro de destaque, não cor de marca) e a escala travada do design system —
  // trilho h-6/w-11 casa com a altura de campo h-11 sem puxar atenção.
  // Acessível pelo contrato do ARIA: `role="switch"` + `aria-checked`, foco
  // visível pelo mesmo anel dos demais controles, e o rótulo é dado por quem
  // usa (o `<label>` em volta), porque o rótulo é da PERGUNTA, não do widget.
  const props = withDefaults(defineProps<SwitchProps>(), { modelValue: false, disabled: false });
  const emit = defineEmits<{ "update:modelValue": [boolean] }>();

  const root = tv({
    base: [
      "peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-transparent",
      "transition-colors outline-none disabled:cursor-not-allowed disabled:opacity-50",
      "focus-visible:ring-ring/20 focus-visible:border-ring focus-visible:ring-2",
      "aria-checked:bg-primary bg-input",
    ],
  });
  // `translate-x` é o único movimento: sem escala nem sombra, para o trilho não
  // competir com o numpad ao lado.
  const thumb = tv({
    base: "pointer-events-none block size-5 rounded-full bg-background shadow-xs ring-0 transition-transform",
    variants: {
      on: {
        true: "translate-x-[1.375rem]",
        false: "translate-x-0.5",
      },
    },
  });
</script>
