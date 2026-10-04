<script setup lang="ts">
// Carregando e erro de leitura, iguais em todas as telas do B.I.: frase inteira e
// "Tentar de novo" a um toque (nunca um clique inerte).
defineProps<{ pending?: boolean; error?: unknown; what?: string }>();
const emit = defineEmits<{ retry: [] }>();
</script>

<template>
  <div v-if="pending" class="flex items-center gap-2 op-body text-muted-foreground" role="status">
    <Icon name="lucide:loader-circle" class="size-4 motion-safe:animate-spin" aria-hidden="true" />
    Carregando…
  </div>
  <div v-else-if="error" class="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card px-4 py-3" role="alert">
    <p class="op-body text-foreground">Não deu para carregar {{ what || "os números" }}.</p>
    <button
      type="button"
      class="inline-flex min-h-control items-center gap-2 rounded-md border border-border bg-card px-3 op-label font-semibold transition hover:bg-accent"
      @click="emit('retry')"
    >
      <Icon name="lucide:refresh-cw" class="size-4" aria-hidden="true" />
      Tentar de novo
    </button>
  </div>
</template>
