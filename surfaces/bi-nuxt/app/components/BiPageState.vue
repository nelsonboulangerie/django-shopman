<script setup lang="ts">
// Carregando e erro de leitura, iguais em todas as telas do B.I.: frase inteira e
// "Tentar de novo" a um toque (nunca um clique inerte). Carregando é o NuxtSkeleton
// canônico com o nome da espera; erro é o NuxtAlert com a ação no próprio aviso.
const props = defineProps<{ pending?: boolean; error?: unknown; what?: string }>();
const emit = defineEmits<{ retry: [] }>();

const actions = computed(() => [
  {
    label: "Tentar de novo",
    icon: "i-lucide-refresh-cw",
    color: "neutral" as const,
    variant: "outline" as const,
    onClick: () => emit("retry"),
  },
]);
</script>

<template>
  <div v-if="pending" class="grid gap-3" role="status" :aria-label="`Carregando ${props.what || 'os números'}`" data-bi-loading>
    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <NuxtSkeleton v-for="i in 4" :key="i" class="h-20" />
    </div>
    <NuxtSkeleton class="h-40" />
  </div>
  <NuxtAlert
    v-else-if="error"
    color="error"
    variant="subtle"
    icon="i-lucide-circle-alert"
    :title="`Não deu para carregar ${props.what || 'os números'}.`"
    :actions="actions"
    orientation="horizontal"
    role="alert"
    data-bi-error
  />
</template>
