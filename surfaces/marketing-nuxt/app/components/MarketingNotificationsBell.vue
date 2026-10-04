<script setup lang="ts">
// O sino abre a fila de decisões. Ele não tem lista própria.
//
// Decisão do dono (03/10/2026): quase todo aviso do Marketing era "anúncio para
// revisar", que é a mesma coisa que a fila da casa mostra, e o painel do sino
// repetia essa lista com outra forma, outro prazo e outro botão. Agora o sino diz se
// há decisão esperando, e tocar nele leva à fila.
//
// Camada visual da suíte (V4-MKT, prévia `marketing-decisoes4.html`): o sino mora na
// barra de 56px do celular, com o ponto âmbar quando algo espera (o número fica no
// selo de Decisões, na barra do polegar, e por extenso no nome acessível). A caixa
// pessoal (SSE, poll e o "visto") é do `MarketingInboxLive`, montado no shell.
const route = useRoute();
const { decisionCount } = useMarketingDecisions();

const onQueue = computed(() => route.path === "/");
const label = computed(() =>
  decisionCount.value === 0
    ? "Decisões: nada esperando você"
    : decisionCount.value === 1
      ? "Decisões: 1 esperando você"
      : `Decisões: ${decisionCount.value} esperando você`,
);
</script>

<template>
  <NuxtLink
    to="/"
    class="relative grid size-12 shrink-0 place-items-center rounded-md text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    :aria-label="label"
    :aria-current="onQueue ? 'page' : undefined"
    title="Decisões que esperam você"
    data-marketing-bell
  >
    <Icon name="lucide:bell" class="size-6" />
    <span
      v-if="decisionCount"
      class="absolute top-2.5 right-2.5 size-2.5 rounded-full bg-suite-badge ring-2 ring-card"
      aria-hidden="true"
      data-marketing-bell-dot
    />
  </NuxtLink>
</template>
