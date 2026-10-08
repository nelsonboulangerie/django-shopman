<script setup lang="ts">
// O ⋯ de cada gráfico (prévia `depois-bi-vendas`, pino 7): os números daquele quadro
// num CSV, sem sair da leitura. O CSV sai dos mesmos pontos que o gráfico desenha.
// NuxtDropdownMenu canônico, com o ⋯ horizontal da suíte.
import type { BiMenuItem } from "~/presentation/bi";

const props = defineProps<{
  title: string;
  /** Cabeçalho e linhas do CSV (o que o quadro mostra). */
  header: string[];
  rows: (string | number)[][];
}>();

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

const items = computed<BiMenuItem[]>(() => [
  { label: "Exportar CSV deste quadro", icon: "i-lucide-download", onSelect: exportCsv },
]);
</script>

<template>
  <NuxtDropdownMenu :items="items" :content="{ align: 'end' }">
    <NuxtButton
      icon="i-lucide-ellipsis"
      color="neutral"
      variant="ghost"
      square
      :aria-label="`Mais sobre ${title}`"
      data-bi-chart-menu
    />
  </NuxtDropdownMenu>
</template>
