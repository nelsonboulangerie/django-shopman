<script setup lang="ts">
// Seção da proposta da fase 2 (material de decisão, não peça do kit): título, a
// atividade que a peça serve e os apps onde ela aparece, numa linha só.
defineProps<{
  id: string;
  title: string;
  /** "A7 ler uma lista em tabela" */
  serves: string;
  apps: readonly string[];
}>();
</script>

<template>
  <section :id="id" :aria-labelledby="`${id}-title`" class="space-y-4" :data-fase2-section="id">
    <div class="space-y-2">
      <h2 :id="`${id}-title`" class="text-xl font-semibold">{{ title }}</h2>
      <p class="text-sm text-muted">
        Serve <span class="font-medium text-default">{{ serves }}</span> em
        {{ apps.join(", ") }}.
      </p>
    </div>
    <slot />
  </section>
</template>
