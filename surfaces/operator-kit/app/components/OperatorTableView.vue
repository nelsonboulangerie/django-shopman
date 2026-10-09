<script setup lang="ts">
// "Exibir" (WP-FASE2-UX-OPERADOR, K1): a forma da tabela num botão só, só o ícone, na
// toolbar da tela. Linhas (Compacta, o padrão, ou Confortável) e as colunas visíveis,
// guardadas neste dispositivo. Muda COMO a tabela aparece, nunca O QUE aparece: por isso
// mora fora do painel de filtros.
//
// Só na mesa (do `sm` para cima, por CSS): no celular as colunas já são as que cabem.
// A lista de colunas vem da própria `OperatorTable` com a mesma chave.
import { computed } from "vue";

import { useOperatorTableView } from "../composables/useOperatorTableView";

const props = defineProps<{
  /** A mesma `view-key` da `OperatorTable`. */
  tableKey: string;
}>();

const { density, view, columns, setDensity, setVisible, showAll } = useOperatorTableView(props.tableKey);

const keepOpen = (event: Event) => event.preventDefault();

const hiddenCount = computed(
  () => view.value.hidden.filter((id) => columns.value.some((column) => column.id === id)).length,
);

const items = computed(() => [
  [
    { type: "label" as const, label: "Linhas" },
    ...(["compact", "comfortable"] as const).map((value) => ({
      label: value === "compact" ? "Compacta" : "Confortável",
      type: "checkbox" as const,
      checked: density.value === value,
      onUpdateChecked: () => setDensity(value),
      onSelect: keepOpen,
    })),
  ],
  ...(columns.value.length
    ? [
        [
          { type: "label" as const, label: "Colunas" },
          ...columns.value.map((column) => ({
            label: column.label,
            type: "checkbox" as const,
            checked: !view.value.hidden.includes(column.id),
            onUpdateChecked: (checked: boolean) => setVisible(column.id, checked),
            onSelect: keepOpen,
          })),
        ],
      ]
    : []),
  ...(hiddenCount.value
    ? [[{ label: "Mostrar todas as colunas", icon: "i-lucide-eye", onSelect: () => showAll() }]]
    : []),
]);

const ariaLabel = computed(() =>
  hiddenCount.value
    ? `Exibir: linhas e colunas (${hiddenCount.value} ${hiddenCount.value === 1 ? "coluna oculta" : "colunas ocultas"})`
    : "Exibir: linhas e colunas",
);
</script>

<template>
  <NuxtDropdownMenu :items="items" :content="{ align: 'end' }">
    <NuxtButton
      icon="i-lucide-columns-3"
      color="neutral"
      :variant="hiddenCount ? 'soft' : 'outline'"
      square
      :aria-label="ariaLabel"
      :title="ariaLabel"
      class="max-sm:hidden"
      data-operator-table-view
    />
  </NuxtDropdownMenu>
</template>
