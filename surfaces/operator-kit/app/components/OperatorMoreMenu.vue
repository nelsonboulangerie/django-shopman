<script setup lang="ts">
// O ⋯ "Mais ações", um só na suíte (WP-FASE2-UX-OPERADOR, peça "⋯ único").
//
// A tela declara as ações como dados (`items`, o formato do `NuxtDropdownMenu`, com
// grupos e o `reason` de uma ação que não pode) e a peça desenha o MESMO ⋯ no cabeçalho,
// no cartão, na linha da tabela e no quadro de leitura, no celular e na mesa:
//
// - o botão é um só: reticências deitadas (nunca de pé), `ghost`, `neutral`,
//   quadrado; o nome (`label`) diz o que ele guarda ("Mais ações do pedido 1048") e
//   vira `aria-label` e `title`;
// - o menu é o `NuxtDropdownMenu` oficial, alinhado ao fim do botão (o Reka vira o lado
//   sozinho quando não cabe);
// - texto da casa não se corta: o rótulo e a descrição do item quebram linha, e o menu
//   nunca passa da largura que sobra na tela. O `:ui` mora aqui, uma vez;
// - o motivo de uma ação desabilitada aparece escrito sob o rótulo
//   (`presentation/moreMenu.ts`).
//
// Atributos (`class`, `data-*`) chegam ao botão. Slots de item do `NuxtDropdownMenu`
// (`slot: "freshness"` num item → `#freshness`) passam direto.
//
// O que NÃO é este ⋯: o "Mais" da barra inferior e o menu do operador (navegação, não
// ação), e o ⋯ que abre um PAINEL (o pedido do Gestor, o cenário do B.I. com campo de
// nome). Esses levam outro desenho e estão listados com motivo na trava
// `tests/guardrails.moreMenu.test.ts`.
import { computed } from "vue";

import { moreMenuGroups, type OperatorMoreMenuItems } from "../presentation/moreMenu";

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    items: OperatorMoreMenuItems;
    /** O nome do ⋯: o que ele guarda. Vira `aria-label` e `title` do botão. */
    label?: string;
  }>(),
  { label: "Mais ações" },
);

const open = defineModel<boolean>("open", { default: false });

const groups = computed(() => moreMenuGroups(props.items));

// A pele do menu: largura limitada ao que sobra na tela e texto que quebra em vez de
// cortar. Uma vez aqui, nunca na tela que usa o ⋯.
const MENU_UI = {
  content: "max-w-(--reka-dropdown-menu-content-available-width)",
  itemLabel: "text-clip whitespace-normal",
  itemDescription: "text-clip whitespace-normal",
};
</script>

<template>
  <NuxtDropdownMenu
    v-model:open="open"
    :items="groups"
    :content="{ align: 'end', collisionPadding: 8 }"
    :ui="MENU_UI"
  >
    <NuxtButton
      v-bind="$attrs"
      icon="i-lucide-ellipsis"
      color="neutral"
      variant="ghost"
      square
      :aria-label="label"
      :title="label"
      data-operator-more-menu
    />
    <template
      v-for="name in Object.keys($slots).filter((slot) => slot !== 'default')"
      :key="name"
      #[name]="scope"
    >
      <slot :name="name" v-bind="scope ?? {}" />
    </template>
  </NuxtDropdownMenu>
</template>
