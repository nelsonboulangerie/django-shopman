<script setup lang="ts">
// Linhas de esqueleto do cardápio: a mesma grade e o mesmo ritmo dos itens de verdade
// (texto à esquerda, foto de 7rem à direita), para a troca não mexer na página.
withDefaults(defineProps<{ count?: number }>(), { count: 6 })
</script>

<template>
  <div class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
    <div v-for="n in count" :key="n" class="flex gap-3 border-b py-3">
      <div class="min-w-0 flex-1 space-y-2 self-center">
        <UiSkeleton class="h-4 w-3/4" />
        <UiSkeleton class="h-3 w-full" />
        <UiSkeleton class="h-4 w-1/4" />
      </div>
      <UiSkeleton class="size-28 shrink-0 rounded-lg" />
    </div>
  </div>
</template>
