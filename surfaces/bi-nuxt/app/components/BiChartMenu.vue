<script setup lang="ts">
// O ⋯ de cada gráfico (prévia `depois-bi-vendas`, pino 7): os números daquele quadro
// num CSV, sem sair da leitura. O CSV sai dos mesmos pontos que o gráfico desenha.
import { PopoverContent, PopoverPortal, PopoverRoot, PopoverTrigger } from "reka-ui";

const props = defineProps<{
  title: string;
  /** Cabeçalho e linhas do CSV (o que o quadro mostra). */
  header: string[];
  rows: (string | number)[][];
}>();

const open = ref(false);
const ITEM = "flex min-h-control w-full items-center gap-2.5 rounded-md px-2.5 text-left op-body transition hover:bg-accent";

function csvCell(value: string | number): string {
  const text = String(value);
  return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function fileName(title: string): string {
  return title
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function exportCsv() {
  open.value = false;
  const lines = [props.header, ...props.rows].map((row) => row.map(csvCell).join(";"));
  // A marca de ordem de bytes faz a planilha abrir o UTF-8 com acento certo.
  const blob = new Blob(["﻿", lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${fileName(props.title)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <PopoverRoot v-model:open="open">
    <PopoverTrigger as-child>
      <UiIconButton icon="lucide:ellipsis-vertical" :label="`Mais sobre ${title}`" :active="open" class="-mt-1 -mr-2" data-bi-chart-menu />
    </PopoverTrigger>
    <PopoverPortal>
      <PopoverContent
        side="bottom"
        align="end"
        :side-offset="6"
        :collision-padding="8"
        class="z-50 w-64 rounded-lg border bg-popover p-1.5 text-popover-foreground shadow-lg outline-hidden"
      >
        <div role="menu" class="flex flex-col">
          <button type="button" role="menuitem" :class="ITEM" @click="exportCsv">
            <Icon name="lucide:download" class="size-4 text-muted-foreground" aria-hidden="true" />
            Exportar CSV deste quadro
          </button>
        </div>
      </PopoverContent>
    </PopoverPortal>
  </PopoverRoot>
</template>
