<script setup lang="ts">
// Raiz do PDV: UMA decisão, por rota, entre dois shells que não se conhecem.
//
// - Rotas de operador (venda, antesala, fechamento…) sobem no
//   `<PosOperatorShell>`: Projection do terminal, identificação (PIN/crachá),
//   tela de senha, setup de estação, auto-lock de kiosk, SSE.
// - A tela do cliente (`/display`) sobe no `<PosCustomerDisplayShell>`: kiosk
//   "como o feed da TV" — nunca identifica, nunca trava, nunca pede senha; só
//   escuta o BroadcastChannel da estação.
//
// A escolha acontece AQUI, antes de qualquer fetch, e não dentro de um shell
// cheio de `v-if`: o display já foi uma tela de operador com N condicionais para
// não se comportar como tal, e bastou um deles falhar para a janela que ninguém
// toca derrubar a sessão da estação no meio da venda. As duas janelas nunca
// trocam de rota entre si (a estação ABRE o display em outra janela), mas a
// decisão segue a rota mesmo assim — é o que a torna verificável.
const route = useRoute();
const isCustomerDisplay = computed(() => route.path === "/display");
</script>

<template>
  <PosCustomerDisplayShell v-if="isCustomerDisplay" />
  <PosOperatorShell v-else />
</template>
