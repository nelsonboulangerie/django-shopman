<script setup lang="ts">
// "Exibir": densidade e colunas num botão só (rodada 2). Antes eram três controles
// (Confortável, Compacta, Colunas) disputando a toolbar; a densidade é escolha de
// dispositivo, feita uma vez, e não merece lugar fixo na linha: na toolbar ela é só o
// ícone. Só aparece na mesa: no celular as colunas já são as que cabem.
import { computed } from "vue";

const props = defineProps<{ columns: { id: string; label: string }[] }>();
const density = defineModel<"compact" | "comfortable">("density", { required: true });
const visibility = defineModel<Record<string, boolean>>("visibility", { required: true });

const items = computed(() => [
  [
    { type: "label" as const, label: "Linhas" },
    ...(["compact", "comfortable"] as const).map((value) => ({
      label: value === "compact" ? "Compacta" : "Confortável",
      type: "checkbox" as const,
      checked: density.value === value,
      onUpdateChecked: () => {
        density.value = value;
      },
      onSelect: (event: Event) => event.preventDefault(),
    })),
  ],
  [
    { type: "label" as const, label: "Colunas" },
    ...props.columns.map((column) => ({
      label: column.label,
      type: "checkbox" as const,
      checked: visibility.value[column.id] !== false,
      onUpdateChecked: (checked: boolean) => {
        visibility.value = { ...visibility.value, [column.id]: checked };
      },
      onSelect: (event: Event) => event.preventDefault(),
    })),
  ],
]);
</script>

<template>
  <NuxtDropdownMenu :items="items" :content="{ align: 'end' }">
    <NuxtButton
      icon="i-lucide-columns-3"
      color="neutral"
      variant="outline"
      square
      aria-label="Exibir: linhas e colunas"
      class="max-sm:hidden"
      data-fase2-table-view
    />
  </NuxtDropdownMenu>
</template>
