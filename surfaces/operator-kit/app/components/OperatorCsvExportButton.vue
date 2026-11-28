<script setup lang="ts">
import { downloadCsv, type CsvTable } from "../presentation/csv";

withDefaults(
  defineProps<{
    table: CsvTable;
    fileName: string;
    label?: string;
    color?: "primary" | "neutral";
    variant?: "solid" | "outline" | "ghost";
  }>(),
  { label: "Exportar CSV", color: "neutral", variant: "outline" },
);
</script>

<template>
  <NuxtButton
    :label="label"
    icon="i-lucide-download"
    :color="color"
    :variant="variant"
    @click="downloadCsv(table, fileName)"
  />
</template>
