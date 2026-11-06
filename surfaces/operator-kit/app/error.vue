<script setup lang="ts">
// A página de erro de TODO app de operador que estende o kit. Sem ela, o Nuxt
// desenhava a dele, em inglês, num Gestor que
// fala português (beta 06/11, F11). O app que precisa de copy própria (o
// Marketing) mantém o seu `app/error.vue`, que tem prioridade sobre o da layer.
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
const presentation = computed(() => {
  if (!online.value)
    return {
      icon: "i-lucide-wifi-off",
      title: "Você está sem conexão",
      detail: "Reconecte e tente de novo. Nada foi enviado por esta tela.",
      retry: true,
    };
  if (status.value === 404)
    return {
      icon: "i-lucide-map-pin-off",
      title: "Esta página não existe",
      detail:
        "O endereço pode estar incompleto ou o item pode ter sido removido. Volte ao início para continuar.",
      retry: false,
    };
  if (status.value === 503)
    return {
      icon: "i-lucide-construction",
      title: "Temporariamente indisponível",
      detail: "O sistema está em manutenção ou ainda não ficou pronto. Aguarde um pouco e tente de novo.",
      retry: true,
    };
  return {
    icon: "i-lucide-triangle-alert",
    title: "Não foi possível abrir esta tela",
    detail: "Tente de novo. Se continuar, informe a referência abaixo.",
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
const { label: appLabel } = useOperatorWindowTitle();
useHead({ title: () => presentation.value.title });

// As saídas da tela de erro: voltar ao início (secundária) e tentar de novo (a
// principal, quando faz sentido).
const errorActions = computed(() => [
  {
    label: "Voltar ao início",
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
    <!-- O `NuxtEmpty` só desenha `h2`: o `h1` da página é o nome do app (para o leitor
         de tela, que navega por título), e o erro fica abaixo dele. -->
    <h1 v-if="appLabel" class="sr-only">{{ appLabel }}</h1>
    <NuxtEmpty
      class="w-full max-w-md"
      :icon="presentation.icon"
      :title="presentation.title"
      :actions="errorActions"
      data-operator-error
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
