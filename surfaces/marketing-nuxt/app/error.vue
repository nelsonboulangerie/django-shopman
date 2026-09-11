<script setup lang="ts">
import type { NuxtError } from "#app";

const props = defineProps<{ error: NuxtError }>();
const online = ref(true);

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
      icon: "lucide:wifi-off",
      title: "Você está sem conexão",
      detail:
        "O Marketing continua fechado para novas decisões. Reconecte e tente novamente; nada foi enviado.",
      retry: true,
    };
  if (status.value === 404)
    return {
      icon: "lucide:map-pin-off",
      title: "Esta página não existe",
      detail:
        "O endereço pode estar incompleto ou o item pode ter sido removido. Volte ao painel para continuar.",
      retry: false,
    };
  if (status.value === 426 || code.value === "unsupported_contract")
    return {
      icon: "lucide:refresh-cw",
      title: "Esta versão precisa ser atualizada",
      detail:
        "Recarregue a página para usar o contrato atual. Nenhuma decisão foi enviada por esta tela.",
      retry: true,
    };
  if (status.value === 503)
    return {
      icon: "lucide:construction",
      title: "Marketing temporariamente indisponível",
      detail:
        "A operação está em manutenção ou ainda não ficou pronta. Aguarde a liberação antes de tentar novamente.",
      retry: true,
    };
  return {
    icon: "lucide:triangle-alert",
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

useHead({ title: `${presentation.value.title} · Marketing` });
</script>

<template>
  <main class="grid min-h-screen place-items-center bg-background p-4 text-foreground">
    <section
      class="w-full max-w-md rounded-md border border-border bg-card p-6 text-center shadow-sm"
      aria-labelledby="marketing-error-title"
    >
      <div class="mx-auto grid size-12 place-items-center rounded-full bg-muted">
        <Icon :name="presentation.icon" class="size-6 text-muted-foreground" />
      </div>
      <p class="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Erro {{ status }}
      </p>
      <h1 id="marketing-error-title" class="mt-1 text-lg font-semibold">
        {{ presentation.title }}
      </h1>
      <p class="mt-2 text-sm text-muted-foreground">
        {{ presentation.detail }}
      </p>
      <p
        v-if="requestRef"
        class="mt-3 break-all rounded-md bg-muted px-3 py-2 text-left text-xs text-muted-foreground"
      >
        Referência para suporte:
        <strong class="font-mono text-foreground">{{ requestRef }}</strong>
      </p>
      <div class="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-center">
        <NuxtLink
          to="/"
          class="inline-flex min-h-11 items-center justify-center rounded-md border border-border px-4 text-sm font-semibold hover:bg-muted"
          @click="clearError({ redirect: '/' })"
        >
          Voltar ao painel
        </NuxtLink>
        <UiButton
          v-if="presentation.retry"
          type="button"
          @click="clearError({ redirect: $route.fullPath })"
        >
          Tentar novamente
        </UiButton>
      </div>
    </section>
  </main>
</template>
