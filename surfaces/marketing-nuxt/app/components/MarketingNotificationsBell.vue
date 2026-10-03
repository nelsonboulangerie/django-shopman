<script setup lang="ts">
// O sino abre a fila de decisões. Ele não tem lista própria.
//
// Decisão do dono (03/10/2026): quase todo aviso do Marketing era "anúncio para
// revisar", que é a mesma coisa que a fila da casa mostra, e o painel do sino
// repetia essa lista com outra forma, outro prazo e outro botão. Agora o número
// do sino é o número de decisões, e tocar nele leva à fila.
//
// O que a caixa pessoal continua fazendo daqui, porque o sino está montado em
// todas as telas: a conexão SSE e o poll de segurança (que publicam a revisão que
// faz a fila buscar a verdade de novo) e o registro de "visto" quando a fila está
// na tela, para o aviso não continuar "novo" depois de lido.
const route = useRoute();
const { notifications, markVisible } = useMarketingNotificationInbox();
const { decisionCount } = useMarketingDecisions({ live: true });

const onQueue = computed(() => route.path === "/");
const label = computed(() =>
  decisionCount.value === 0
    ? "Decisões: nada esperando você"
    : decisionCount.value === 1
      ? "Decisões: 1 esperando você"
      : `Decisões: ${decisionCount.value} esperando você`,
);

// Só no navegador (o `onMounted` não roda no SSR): registrar "visto" é um POST.
function markSeenWhileOnQueue() {
  if (onQueue.value) void markVisible();
}
onMounted(markSeenWhileOnQueue);
watch([onQueue, notifications], markSeenWhileOnQueue);
</script>

<template>
  <NuxtLink
    to="/"
    class="relative grid size-11 shrink-0 place-items-center rounded-md border border-border text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    :aria-label="label"
    :aria-current="onQueue ? 'page' : undefined"
    title="Decisões que esperam você"
    data-marketing-bell
  >
    <Icon name="lucide:bell" class="size-5" />
    <span
      v-if="decisionCount"
      class="absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-destructive px-1 text-xs font-bold tabular-nums text-white"
      aria-hidden="true"
      >{{ decisionCount > 99 ? "99+" : decisionCount }}</span
    >
  </NuxtLink>
</template>
