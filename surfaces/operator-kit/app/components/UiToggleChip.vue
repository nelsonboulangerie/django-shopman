<script setup lang="ts">
// Escolha múltipla desenhada como CHIP — a peça que faltava ao lado do `UiCheckbox`.
//
// ⚠️ Não é o mesmo controle. O `UiCheckbox` desenha um quadrado com o rótulo ao lado; o
// chip é uma pílula cuja CAIXA INTEIRA acende. Onde a escolha é curta e cabem várias na
// mesma linha — plataformas de disparo, etiquetas, segmentos, dias da semana — o chip é
// o desenho certo, e trocá-lo pelo quadrado seria pôr a peça parecida no lugar da peça
// certa. Foi por isso que a conversão dos primitivos de escolha deixou essas telas de
// fora, com o vazio registrado em comentário: elas pediam ISTO.
//
// Antes deste arquivo havia 50 ocorrências de `aria-pressed` escritas à mão nas
// superfícies de operador, mais as pílulas de plataforma do Marketing, que embrulhavam
// um `<input type="checkbox" class="sr-only">` num `<label>` pintado. Três desenhos
// para o mesmo gesto, e o alvo de toque saindo de literal em vez de token em quase
// todos.
//
// SEMÂNTICA: `role="checkbox"`, como o `UiCheckbox`, e não `aria-pressed`. Escolher
// plataformas é marcar itens de uma lista, não apertar botões que ficam apertados —
// o leitor de tela diz "marcada", que é o que a pessoa está fazendo. Um grupo de chips
// deve morar dentro de um `<fieldset>` com `<legend>` ou de um `role="group"` com nome.
//
// ⚠️ NÃO confundir com o `UiFilterChip`, que tem a mesma silhueta e outro ofício. Ele é
// CHROME: filtra uma lista, não carrega valor de formulário, não tem ARIA de escolha, e
// acende em `bg-primary` sólido. Este é CONTROLE: contribui para o que vai ser enviado,
// tem `aria-checked`, e acende em contorno + tint levíssimo, que é o padrão único de
// seleção da escala de design. Mesma forma, trabalhos diferentes — como `UiButton` e
// `UiIconButton`. Se você está filtrando uma lista, o outro é o certo.
import { computed, useTemplateRef } from "vue";

const props = withDefaults(
  defineProps<{
    /** Marcado (v-model). */
    modelValue?: boolean;
    disabled?: boolean;
    /** Rótulo. Também aceita o slot default quando há ícone ou marcação junto. */
    label?: string;
  }>(),
  { modelValue: false },
);

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();

const slots = defineSlots<{ default?: () => unknown }>();

const control = useTemplateRef<HTMLButtonElement>("control");
const hasLabel = computed(() => Boolean(props.label) || Boolean(slots.default));

function toggle() {
  if (props.disabled) return;
  emit("update:modelValue", !props.modelValue);
}

defineExpose({ focus: () => control.value?.focus() });
</script>

<template>
  <button
    ref="control"
    type="button"
    role="checkbox"
    :aria-checked="modelValue"
    :disabled="disabled"
    data-slot="toggle-chip"
    class="inline-flex min-h-control items-center justify-center gap-1.5 rounded-full border px-3 text-sm transition-colors outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50"
    :class="
      // ⚠️ Seleção é contorno + tint levíssimo, o padrão ÚNICO da escala de design
      // (ver `operator-base.css`). Nada de preencher sólido nem de `ring`: `ring` é
      // reservado a foco de teclado, e preenchimento sólido é do botão primário — é o
      // que separa este chip do `UiFilterChip`.
      modelValue
        ? 'border-primary bg-primary/10 text-foreground'
        : 'border-border text-muted-foreground hover:bg-muted'
    "
    @click="toggle"
  >
    <slot v-if="hasLabel">{{ label }}</slot>
  </button>
</template>
