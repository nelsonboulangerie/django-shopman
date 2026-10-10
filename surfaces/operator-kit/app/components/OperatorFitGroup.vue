<script setup lang="ts">
// Um grupo de ações que divide o mesmo espaço (dono, 10/10/2026, "Rótulo que cabe" no
// README). O grupo É o contêiner (`container-type: inline-size`): a largura dele decide
// o degrau de todas as ações de uma vez (completo, curto, só ícone), e a barra nunca
// mistura "Enviar à cozinha" com um ícone solto ao lado.
//
// A tela declara as ações como dados (`actions`, só o que pesa na conta: rótulo, curto e
// ícone) e desenha os `OperatorButton` no slot, na mesma ordem. Como o contêiner não
// tem largura própria, o grupo ocupa a largura que o pai dá (`w-full` ou `flex-1`).
import { computed, provide } from "vue";

import {
  actionFitVars,
  type OperatorAdaptiveLabel,
  type OperatorFitSize,
} from "../presentation/actionLabel";
import { OPERATOR_FIT_GROUP } from "../presentation/fitGroup";

const props = withDefaults(
  defineProps<{
    actions: readonly OperatorAdaptiveLabel[];
    size?: OperatorFitSize;
    /** Espaço entre as ações, em rem (o `gap-2` da casa). */
    gap?: number;
    /** O que o grupo gasta com o que não é ação (frase, ×), em rem. */
    reserve?: number;
  }>(),
  { size: "md", gap: 0.5, reserve: 0 },
);

provide(OPERATOR_FIT_GROUP, true);

const style = computed(() =>
  actionFitVars(props.actions, { size: props.size, gap: props.gap, reserve: props.reserve }),
);
</script>

<template>
  <div class="op-fit-scope min-w-0" :style="style" data-operator-fit-group>
    <slot />
  </div>
</template>
