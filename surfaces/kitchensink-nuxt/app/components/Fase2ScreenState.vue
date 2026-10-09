<script setup lang="ts">
// Protótipo do `OperatorScreenState` (K7), rodada 2, com a voz que o dono escolheu
// (09/10): frase inteira, sujeito claro, sem gíria. "Nenhum pedido precisa de você
// agora." e "Não foi possível carregar a fila" são as dele; os outros estados seguem o
// mesmo tom. Sem cartão em volta: o estado ocupa o lugar do conteúdo.
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    kind: "loading" | "empty" | "error" | "offline" | "no-results";
    /** "a fila", "o histórico", "os insumos". */
    noun: string;
    /** No vazio: o que a tela mostraria ("pedido"). */
    item?: string;
    at?: string;
  }>(),
  { item: "pedido", at: "10:42" },
);
defineEmits<{ retry: []; clear: [] }>();

const copy = computed(() => {
  const item = props.item;
  return {
    loading: { icon: "i-lucide-loader", title: `Carregando ${props.noun}.`, description: "" },
    empty: { icon: "i-lucide-circle-check", title: `Nenhum ${item} precisa de você agora.`, description: "" },
    error: {
      icon: "i-lucide-circle-x",
      title: `Não foi possível carregar ${props.noun}`,
      description: "O servidor não respondeu. Os dados da tela podem estar desatualizados.",
    },
    offline: {
      icon: "i-lucide-wifi-off",
      title: "Sem conexão",
      description: `O que está na tela é de ${props.at}. A tela se atualiza quando a conexão voltar.`,
    },
    "no-results": {
      icon: "i-lucide-search-x",
      title: `Nenhum ${item} neste recorte.`,
      description: "Tire um dos recortes ou limpe os filtros.",
    },
  }[props.kind];
});
</script>

<template>
  <div v-if="kind === 'loading'" class="space-y-2" role="status" aria-busy="true" data-fase2-state="loading">
    <NuxtSkeleton class="h-20" />
    <NuxtSkeleton class="h-20" />
    <p class="text-sm text-muted">{{ copy.title }}</p>
  </div>
  <NuxtEmpty
    v-else
    :icon="copy.icon"
    :title="copy.title"
    :description="copy.description || undefined"
    :actions="
      kind === 'error'
        ? [{ label: 'Tentar de novo', icon: 'i-lucide-refresh-cw', color: 'neutral', variant: 'outline', onClick: () => $emit('retry') }]
        : kind === 'no-results'
          ? [{ label: 'Limpar os filtros', color: 'neutral', variant: 'outline', onClick: () => $emit('clear') }]
          : undefined
    "
    :data-fase2-state="kind"
  />
</template>
