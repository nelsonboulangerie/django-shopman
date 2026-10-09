<script setup lang="ts">
// O erro de leitura, igual em todas as telas do B.I.: frase inteira e "Tentar de novo"
// a um toque, na cor do aviso (decisão do #1545). Carregando é o `NuxtEmpty loading` de
// cada tela, com o nome da espera.
const props = defineProps<{ error?: unknown; what?: string }>();
const emit = defineEmits<{ retry: [] }>();

const actions = computed(() => [
  {
    label: "Tentar de novo",
    icon: "i-lucide-refresh-cw",
    color: "error" as const,
    variant: "outline" as const,
    onClick: () => emit("retry"),
  },
]);
</script>

<template>
  <NuxtAlert
    v-if="error"
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
