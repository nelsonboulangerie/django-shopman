<script setup lang="ts">
// O pé das tabelas de relatório: "Exibindo 1–50 de 132 resultados" e Anterior/Próxima.
// A paginação é por cursor no servidor (a página da vez não se ordena sozinha).
import type { ProductionReportsResponse } from "~/types/production";

defineProps<{
  pagination: ProductionReportsResponse["pagination"];
  pending?: boolean;
}>();
const emit = defineEmits<{ open: [cursor: string] }>();
</script>

<template>
  <nav class="flex flex-wrap items-center justify-between gap-3 text-sm" aria-label="Paginação do relatório">
    <span class="text-muted-foreground tabular-nums" role="status" aria-live="polite">
      Exibindo {{ pagination.from }}–{{ pagination.to }} de {{ pagination.total }}
      {{ pagination.total === 1 ? "resultado" : "resultados" }}
    </span>
    <div class="flex gap-2">
      <NuxtButton
        label="Anterior"
        icon="i-lucide-chevron-left"
        color="neutral"
        variant="outline"
        :disabled="!pagination.previous_cursor || pending"
        @click="emit('open', pagination.previous_cursor)"
      />
      <NuxtButton
        label="Próxima"
        trailing-icon="i-lucide-chevron-right"
        color="neutral"
        variant="outline"
        :disabled="!pagination.next_cursor || pending"
        @click="emit('open', pagination.next_cursor)"
      />
    </div>
  </nav>
</template>
