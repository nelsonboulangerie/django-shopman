<script setup lang="ts">
// O formato do esqueleto pertence à tela; animação, semântica e tema pertencem
// ao USkeleton. O rótulo em português evita deixar o fallback inglês escapar.
withDefaults(
  defineProps<{
    label?: string;
  }>(),
  { label: "Carregando" },
);
</script>

<template>
  <NuxtSkeleton :aria-label="label">
    <span class="sr-only">{{ label }}</span>
  </NuxtSkeleton>
</template>
