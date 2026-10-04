<script setup lang="ts">
// A janela de análise no cabeçalho da tela (prévia `bi-sobra4.html`: o período mora na
// linha do título). É o `OperatorPeriodPicker` do kit (Tipo 2 dos controles de data da
// casa): UM botão que DIZ a janela, os chips e o personalizado no popover, e ‹ › que
// andam um período igual. A janela vive na URL (`useBiWindow`).
withDefaults(defineProps<{ align?: "start" | "end" }>(), { align: "end" });
const { selection, bounds, presets } = useBiWindow();
</script>

<template>
  <OperatorPeriodPicker
    v-model="selection"
    :presets="presets"
    custom
    :today="bounds.today"
    :max="bounds.max"
    :epoch="bounds.epoch"
    :align="align"
    label="Período de análise"
  />
</template>
