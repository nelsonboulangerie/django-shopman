<script setup lang="ts">
// Dono da caixa pessoal do Marketing, montado UMA vez no shell (`app.vue`).
//
// Até a camada visual da suíte (V4-MKT) quem fazia isto era o sino, porque o sino
// estava em todas as telas. Agora o sino só existe no celular (do tablet para cima o
// selo de Decisões no rail é o sino), e o que a caixa faz não pode depender de qual
// largura de tela está aberta:
//
// - a conexão SSE e o poll de segurança (60 s), que publicam a revisão que faz a fila
//   buscar a verdade de novo (ADR-016: o SSE só invalida);
// - a ÚNICA instância de `useMarketingDecisions` que escuta essa revisão (`live`), para
//   cada aviso custar um refetch, não um por leitor;
// - o registro de "visto" quando a fila está na tela, para o aviso não continuar
//   "novo" depois de lido.
const route = useRoute();
const { notifications, markVisible } = useMarketingNotificationInbox();
useMarketingDecisions({ live: true });

const onQueue = computed(() => route.path === "/");

// Só no navegador (o `onMounted` não roda no SSR): registrar "visto" é um POST.
function markSeenWhileOnQueue() {
  if (onQueue.value) void markVisible();
}
onMounted(markSeenWhileOnQueue);
watch([onQueue, notifications], markSeenWhileOnQueue);
</script>

<template>
  <span hidden data-marketing-inbox-live />
</template>
