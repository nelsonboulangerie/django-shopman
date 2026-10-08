<script setup lang="ts">
// Quadro de leitura (PR-K1 do WP-BI-CANON-LAUDO, item C2): o `NuxtCard` com `title` e
// `description` (Nuxt UI 4.7+) e o ⋯ das ações do quadro. Promovido do `BiChartMenu`
// do B.I.; serve B.I., Gestor (histórico, catálogo), Compras e Marketing.
//
// - O título vira cabeçalho de verdade (`h2` por padrão, `heading-level` muda) e dá
//   nome à região: quem navega por cabeçalho ou por região chega ao quadro pelo nome.
// - Com `csv`, o ⋯ oferece "Exportar CSV deste quadro": os números que o quadro mostra,
//   num arquivo. Para um gráfico, `readingChartCsv(...)` monta o `csv` dos mesmos pontos.
// - `items` acrescenta ações próprias do quadro ao mesmo ⋯ (nunca um segundo menu).
// - A pele (fundo, padding, borda) é a do tema (`app.config.ts`, `card`).
import type { DropdownMenuItem } from "@nuxt/ui";
import { computed, useId } from "vue";

import {
  readingCsvFileName,
  readingCsvText,
  type ReadingCsv,
} from "../presentation/readingChart";

const props = withDefaults(
  defineProps<{
    title: string;
    description?: string;
    csv?: ReadingCsv;
    items?: DropdownMenuItem[];
    headingLevel?: 2 | 3 | 4;
  }>(),
  { description: undefined, csv: undefined, items: () => [], headingLevel: 2 },
);

const headingId = useId();
const heading = computed(() => `h${props.headingLevel}`);

function exportCsv() {
  if (!props.csv) return;
  const blob = new Blob([readingCsvText(props.csv)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = readingCsvFileName(props.title);
  link.click();
  URL.revokeObjectURL(url);
}

const menuItems = computed<DropdownMenuItem[]>(() => [
  ...(props.csv
    ? [{ label: "Exportar CSV deste quadro", icon: "i-lucide-download", onSelect: exportCsv }]
    : []),
  ...props.items,
]);
</script>

<template>
  <NuxtCard
    as="section"
    :title="title"
    :description="description"
    :aria-labelledby="headingId"
    data-operator-reading-card
  >
    <template #title>
      <div class="flex items-start justify-between gap-2">
        <component :is="heading" :id="headingId">{{ title }}</component>
        <NuxtDropdownMenu v-if="menuItems.length" :items="menuItems" :content="{ align: 'end' }">
          <NuxtButton
            icon="i-lucide-ellipsis"
            color="neutral"
            variant="ghost"
            square
            class="-my-1"
            :aria-label="`Mais sobre ${title}`"
            data-operator-reading-card-menu
          />
        </NuxtDropdownMenu>
      </div>
    </template>
    <slot />
    <template v-if="$slots.footer" #footer><slot name="footer" /></template>
  </NuxtCard>
</template>
