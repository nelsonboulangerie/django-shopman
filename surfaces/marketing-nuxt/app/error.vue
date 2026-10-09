<script setup lang="ts">
import { clearError, useRoute, type NuxtError } from "#app";

const props = defineProps<{ error: NuxtError }>();
const online = ref(true);
const route = useRoute();

function safeRequestRef(): string {
  const data =
    props.error.data && typeof props.error.data === "object"
      ? (props.error.data as Record<string, unknown>)
      : null;
  const value = data?.request_id ?? data?.receipt_ref;
  const text = typeof value === "string" ? value : "";
  return /^[A-Za-z0-9._:-]{1,100}$/.test(text) ? text : "";
}

const status = computed(() => Number(props.error.statusCode || 500));
const requestRef = computed(safeRequestRef);
const code = computed(() => {
  const data =
    props.error.data && typeof props.error.data === "object"
      ? (props.error.data as Record<string, unknown>)
      : null;
  return typeof data?.code === "string" ? data.code : "";
});
const presentation = computed(() => {
  if (!online.value)
    return {
      icon: "i-lucide-wifi-off",
      title: "Você está sem conexão",
      detail:
        "O Marketing continua fechado para novas decisões. Reconecte e tente novamente; nada foi enviado.",
      retry: true,
    };
  if (status.value === 404)
    return {
      icon: "i-lucide-map-pin-off",
      title: "Esta página não existe",
      detail:
        "O endereço pode estar incompleto ou o item pode ter sido removido. Volte às decisões para continuar.",
      retry: false,
    };
  if (status.value === 426 || code.value === "unsupported_contract")
    return {
      icon: "i-lucide-refresh-cw",
      title: "Esta versão precisa ser atualizada",
      detail:
        "Recarregue a página para carregar a versão nova do Marketing. Nada foi enviado por esta tela.",
      retry: true,
    };
  if (status.value === 503)
    return {
      icon: "i-lucide-construction",
      title: "Marketing temporariamente indisponível",
      detail:
        "A operação está em manutenção ou ainda não ficou pronta. Aguarde a liberação antes de tentar novamente.",
      retry: true,
    };
  return {
    icon: "i-lucide-triangle-alert",
    title: "Não foi possível abrir o Marketing",
    detail:
      "O problema foi mantido separado de uma decisão de campanha. Tente novamente; se persistir, informe a referência abaixo.",
    retry: true,
  };
});

function updateConnection() {
  online.value = navigator.onLine;
}

onMounted(() => {
  updateConnection();
  window.addEventListener("online", updateConnection);
  window.addEventListener("offline", updateConnection);
});
onBeforeUnmount(() => {
  window.removeEventListener("online", updateConnection);
  window.removeEventListener("offline", updateConnection);
});

// O Nuxt renderiza o error.vue NO LUGAR do app.vue: o template do título tem
// que ser instalado aqui também, senão a janela perde o nome do app.
useOperatorWindowTitle();
useHead({ title: presentation.value.title });

// As saídas da tela de erro, no conjunto mínimo: voltar à casa (secundária) e tentar de
// novo (a principal, quando faz sentido).
const errorActions = computed(() => [
  {
    label: "Voltar às decisões",
    icon: "i-lucide-arrow-left",
    color: "neutral" as const,
    variant: "outline" as const,
    onClick: () => clearError({ redirect: "/" }),
  },
  ...(presentation.value.retry
    ? [
        {
          label: "Tentar de novo",
          icon: "i-lucide-refresh-cw",
          onClick: () => clearError({ redirect: route.fullPath }),
        },
      ]
    : []),
]);
</script>

<template>
  <!-- Sem o shell da suíte: o Nuxt desenha esta página NO LUGAR do app.vue. -->
  <main class="grid min-h-screen place-items-center bg-background p-4 text-foreground">
    <NuxtEmpty
      class="w-full max-w-md"
      :icon="presentation.icon"
      :title="presentation.title"
      :actions="errorActions"
      data-marketing-error
    >
      <template #description>
        <span class="block text-xs font-semibold uppercase tracking-wide">Erro {{ status }}</span>
        <span class="mt-2 block">{{ presentation.detail }}</span>
        <span v-if="requestRef" class="mt-3 block break-all text-xs">
          Referência para suporte:
          <strong class="font-mono text-foreground">{{ requestRef }}</strong>
        </span>
      </template>
    </NuxtEmpty>
  </main>
</template>
