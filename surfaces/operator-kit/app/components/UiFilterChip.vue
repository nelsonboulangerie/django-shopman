<script setup lang="ts">
// Compatibilidade temporária para apps ainda não migrados. O Gestor usa NuxtTabs
// diretamente. Não há receita visual local: só props públicas do Nuxt UI.
defineProps<{
  active?: boolean;
  count?: number | null;
}>();
</script>

<template>
  <NuxtButton
    type="button"
    :color="active ? 'primary' : 'neutral'"
    :variant="active ? 'soft' : 'outline'"
  >
    <slot name="icon" />
    <slot />
    <NuxtBadge
      v-if="count != null"
      color="neutral"
      variant="outline"
      size="sm"
      :label="String(count)"
    />
  </NuxtButton>
</template>
