<script setup lang="ts">
// Busca em níveis montada no canônico (dono, 09/10): `NuxtDashboardSearchButton` +
// `NuxtDashboardSearch`, sem Tabs nem Modal próprios. Os níveis são os GRUPOS da paleta,
// numa ordem fixa (`preserve-group-order`), do mais perto ao mais longe:
//   Nesta tela  ("Filtrar a fila por …" vira um recorte da tela, e os itens dela)
//   Neste app   (Histórico, Clientes…)
//   Na suíte    (produtos, telas de outros apps)
// O nível não se escolhe antes de buscar: ele aparece no resultado. Tecla "/" abre.
// Celular: o botão vira só a lupa (`collapsed`, o oficial). A troca é por CSS.
import { computed, onMounted, ref } from "vue";

import type { Fase2SearchItem } from "../types/fase2";

const props = defineProps<{
  /** "a fila", "o histórico": o que a tela mostra. */
  screen: string;
  screenItems: readonly Fase2SearchItem[];
  app: string;
  appItems: readonly Fase2SearchItem[];
  suiteItems: readonly Fase2SearchItem[];
  /** Abre ao montar, com um termo (retratos da proposta). */
  openOnMount?: boolean;
}>();
const emit = defineEmits<{ filter: [term: string] }>();

const open = ref(false);
const term = ref("");
onMounted(() => {
  if (!props.openOnMount) return;
  term.value = "ana";
  open.value = true;
});

const groups = computed(() => {
  const typed = term.value.trim();
  return [
    {
      id: "screen",
      label: `Nesta tela`,
      items: [
        ...(typed
          ? [
              {
                label: `Filtrar ${props.screen} por “${typed}”`,
                icon: "i-lucide-list-filter",
                suffix: "vira um recorte",
                onSelect: () => emit("filter", typed),
              },
            ]
          : []),
        ...props.screenItems,
      ],
    },
    { id: "app", label: `No ${props.app}`, items: [...props.appItems] },
    { id: "suite", label: "Na suíte", items: [...props.suiteItems] },
  ];
});
</script>

<template>
  <div class="flex shrink-0 items-center" data-fase2-search>
    <NuxtDashboardSearchButton
      collapsed
      :kbds="[]"
      aria-label="Buscar"
      class="sm:hidden"
      data-fase2-search-phone
      @click="open = true"
    />
    <NuxtDashboardSearchButton
      label="Buscar"
      :kbds="['/']"
      class="w-56 max-sm:hidden"
      data-fase2-search-desk
      @click="open = true"
    />
    <NuxtDashboardSearch
      v-model:open="open"
      v-model:search-term="term"
      :groups="groups"
      :color-mode="false"
      shortcut="/"
      preserve-group-order
      title="Buscar"
      description="Nesta tela, neste app e em toda a suíte."
      placeholder="Pedido, cliente, produto ou tela"
    />
  </div>
</template>
