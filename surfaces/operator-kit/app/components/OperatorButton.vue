<script setup lang="ts">
// O botão de ação da suíte com o rótulo que cabe (dono, 10/10/2026). É o `NuxtButton`
// canônico (cor, variante e tamanho do conjunto mínimo passam direto) com UMA coisa a
// mais: o rótulo se adapta ao espaço do contêiner, nesta ordem:
//
//   1. o completo (`label`, "Enviar à cozinha");
//   2. o curto que a ação escreveu (`short-label`, "Cozinha"). Nunca abreviação
//      inventada: sem `short-label`, o botão pula do completo para o ícone;
//   3. só o ícone (`icon`), com o completo como nome acessível e como dica.
//
// Sem ícone não há o degrau 3: o último texto fica e quebra linha (nunca vaza, nunca
// corta). Por isso toda ação que pode ficar apertada declara um ícone.
//
// A troca é CSS puro (`operator-fit.css`): o contêiner mais próximo declara
// `container-type: inline-size` (`class="op-fit-scope"` ou `@container`) e o botão
// compara a largura dele com a que precisa (`presentation/actionLabel.ts`, calculada a
// partir do texto, igual no servidor e no cliente: sem flash, sem medir em JS).
//
// Sozinho no contêiner, o botão calcula a própria necessidade. Dentro de um
// `OperatorFitGroup` (ou de uma barra do kit) ele usa a do grupo, e todas as ações da
// barra trocam juntas.
import { computed, inject, useAttrs } from "vue";

import OperatorFitLabel from "./OperatorFitLabel.vue";

import { actionFitAttrs, type OperatorFitSize } from "../presentation/actionLabel";
import { OPERATOR_FIT_GROUP } from "../presentation/fitGroup";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    /** O rótulo completo, com verbo e alvo. É sempre o nome acessível. */
    label: string;
    /** O curto, escrito por quem conhece a ação ("Cozinha"). */
    shortLabel?: string;
    icon?: string;
    trailingIcon?: string;
    /** Nome acessível mais longo que o rótulo ("Desfazer o Pronto do 0131"). */
    ariaLabel?: string;
    size?: OperatorFitSize;
    color?: "primary" | "success" | "info" | "warning" | "error" | "neutral";
    variant?: "solid" | "outline" | "soft" | "subtle" | "ghost" | "link";
    block?: boolean;
    loading?: boolean;
    disabled?: boolean;
    to?: string | Record<string, unknown>;
    href?: string;
    target?: string;
    type?: "button" | "submit" | "reset";
  }>(),
  {
    shortLabel: undefined,
    icon: undefined,
    trailingIcon: undefined,
    ariaLabel: undefined,
    size: "md",
    color: "primary",
    variant: "solid",
    block: false,
    loading: false,
    disabled: false,
    to: undefined,
    href: undefined,
    target: undefined,
    type: "button",
  },
);

const grouped = inject(OPERATOR_FIT_GROUP, false);

const attrs = useAttrs();
const fit = computed(() => actionFitAttrs(props, { size: props.size, grouped }));
// O que quem chama passa (`title` com o motivo, `class`, `data-*`) vence; o `style`
// soma (as variáveis do encaixe e o estilo de quem chama).
const bound = computed(() => ({
  ...fit.value,
  ...attrs,
  style: [fit.value.style, attrs.style],
}));
</script>

<template>
  <NuxtButton
    v-bind="bound"
    :to="to"
    :href="href"
    :target="target"
    :type="type"
    :size="size"
    :color="color"
    :variant="variant"
    :block="block"
    :loading="loading"
    :disabled="disabled"
    :icon="icon"
    :trailing-icon="trailingIcon"
  >
    <OperatorFitLabel :label="label" :short-label="shortLabel" :icon="icon" />
    <template v-if="$slots.trailing" #trailing>
      <slot name="trailing" />
    </template>
  </NuxtButton>
</template>
