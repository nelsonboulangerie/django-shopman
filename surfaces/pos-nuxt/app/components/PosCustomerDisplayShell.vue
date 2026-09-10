<script setup lang="ts">
// SHELL KIOSK da tela do cliente (`/display`) — "como o feed da TV".
//
// A tela do cliente é uma janela virada para a parede, aberta pela estação com
// `window.open("/display")`. Ela não é uma tela de operador e não obedece à
// regra das telas de operador ("precisa saber quem está operando"). A regra dela:
//   - NUNCA identifica: não busca sessão, não lê a Projection do terminal.
//   - NUNCA trava: sem auto-lock, sem overlay de PIN/crachá — travar é logout no
//     servidor, e a janela que ninguém toca derrubava o operador no meio da venda.
//   - NUNCA pede senha: formulário de login na parede não identifica ninguém.
//   - NUNCA abre SSE nem poll: não há leitor para o refetch.
// O ÚNICO sinal que ela obedece é o BroadcastChannel da estação
// (`useCustomerDisplayConsumer`), inclusive o nome da loja, que viaja no snapshot.
//
// Por isso este shell é só a moldura e a saída da página — nenhum composable de
// operador entra aqui, e `app.vue` escolhe este shell ANTES de qualquer fetch.
// Sem <OfflineBanner>: o display não depende da rede (o canal é local ao
// navegador), e "tentando reconectar" na parede seria um aviso ao cliente sobre
// nada. Sem <UiSonner>: toast é feedback de gesto, e aqui ninguém gesticula.
</script>

<template>
  <div class="min-h-dvh bg-background text-foreground" data-pos-shell="customer-display">
    <NuxtRouteAnnouncer />
    <NuxtPage />
  </div>
</template>
