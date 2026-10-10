<script setup lang="ts">
// O miolo do rótulo que cabe (`operator-fit.css`), um só para o `OperatorButton` e
// para os botões das barras do kit que levam conteúdo próprio (`OperatorTimedButton`).
// Vai dentro do `NuxtButton` que recebeu `actionFitAttrs(...)`, e o CSS mostra um texto
// de cada vez.
//
// O nome acessível é o `aria-label` do botão (o completo, de `actionFitAttrs`). O
// curto é conteúdo GERADO (`::before` com `attr(data-op-fit-short)`): o `textContent`
// do botão continua sendo só o rótulo completo, para quem procura o botão pelo texto.
import { computed } from "vue";

import { isAdaptive, shortOf } from "../presentation/actionLabel";

const props = withDefaults(
  defineProps<{
    label: string;
    shortLabel?: string;
    /** O botão tem ícone (degrau 3). */
    icon?: string;
  }>(),
  { shortLabel: undefined, icon: undefined },
);

const short = computed(() => shortOf(props));
const adaptive = computed(() => isAdaptive(props));
</script>

<template>
  <span v-if="adaptive" class="op-fit-label" data-op-fit-label>
    <template v-if="short">
      <span class="op-fit-text" data-op-fit-variant="full">{{ label }}</span>
      <span
        class="op-fit-text"
        aria-hidden="true"
        data-op-fit-variant="short"
        :data-op-fit-short="short"
        :data-op-fit-last="icon ? undefined : ''"
      />
    </template>
    <span
      v-else
      class="op-fit-text"
      data-op-fit-variant="only"
      :data-op-fit-last="icon ? undefined : ''"
    >{{ label }}</span>
  </span>
  <span v-else class="op-fit-text" data-op-fit-variant="only" data-op-fit-last>{{ label }}</span>
</template>
