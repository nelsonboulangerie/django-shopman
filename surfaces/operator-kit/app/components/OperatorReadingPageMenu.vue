<script setup lang="ts">
// O ⋯ do cabeçalho de uma página de leitura (PR-K1 do WP-BI-CANON-LAUDO, item C2).
// Promovido do `BiPageMenu` do B.I. "Copiar link desta leitura" é de toda página
// de leitura: o período, o dia e os recortes vivem na URL, então o endereço É a
// leitura. Ações próprias da página entram por `items`, no mesmo menu.
//
// Dentro do `OperatorPageHeader`, prefira `useReadingPageActions` com `:actions`: as
// mesmas ações em dados, e o kit decide o que cabe na barra do celular.
import type { DropdownMenuItem } from "@nuxt/ui";
import { computed } from "vue";

import { useReadingPageActions } from "../composables/useReadingPageActions";
import type { OperatorHeaderAction } from "../presentation/pageHeader";

const props = withDefaults(defineProps<{ items?: DropdownMenuItem[] }>(), { items: () => [] });

const { actions, label: triggerLabel } = useReadingPageActions(
  () => props.items as OperatorHeaderAction[],
);
const menuItems = computed<DropdownMenuItem[]>(() => actions.value as DropdownMenuItem[]);
</script>

<template>
  <NuxtDropdownMenu :items="menuItems" :content="{ align: 'end' }">
    <NuxtButton
      icon="i-lucide-ellipsis"
      color="neutral"
      variant="ghost"
      square
      :aria-label="triggerLabel"
      data-operator-reading-page-menu
    />
  </NuxtDropdownMenu>
</template>
