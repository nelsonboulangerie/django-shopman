<script setup lang="ts">
// "Exibir" no estreito (dono, 07/11/2026): os controles de VISUALIZAÇÃO de uma lista
// (Grade ou Lista, densidade, ocultar indisponíveis) num botão só, com menu. O ícone é
// o estado atual da vista; o menu traz cada opção marcada; o nome do botão diz o estado
// inteiro. Uma preferência ligada deixa o botão marcado (`soft`).
//
// A tela decide QUANDO usar: no estreito (celular), no lugar dos segmentados e do olho;
// na mesa, os segmentados à vista continuam. Contrato e regra no README ("Exibir no
// estreito"). Desenho em `presentation/viewMenu.ts`.
import type { ButtonProps } from "@nuxt/ui";
import { computed } from "vue";

import {
  viewMenuHasToggleOn,
  viewMenuIcon,
  viewMenuItems,
  viewMenuLabel,
  type OperatorViewGroup,
} from "../presentation/viewMenu";

// `class` e `data-*` da tela vão no botão (a raiz do menu não desenha nada).
defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    groups: OperatorViewGroup[];
    size?: ButtonProps["size"];
  }>(),
  { size: "md" },
);

const items = computed(() => viewMenuItems(props.groups));
const icon = computed(() => viewMenuIcon(props.groups));
const label = computed(() => viewMenuLabel(props.groups));
const marked = computed(() => viewMenuHasToggleOn(props.groups));
</script>

<template>
  <NuxtDropdownMenu :items="items" :content="{ align: 'end' }">
    <NuxtButton
      :icon="icon"
      :size="size"
      color="neutral"
      :variant="marked ? 'soft' : 'outline'"
      square
      :aria-label="label"
      :title="label"
      v-bind="$attrs"
      data-operator-view-menu
    />
  </NuxtDropdownMenu>
</template>
