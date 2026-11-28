<script setup lang="ts">
// "Liberar o Chrome no Windows": o botão da resposta do WhatsApp quando o login
// começou num computador (escada sem fricção, decisão do dono de 23/10).
//
// A mensagem chega no celular e a aba que pediu a entrada está do outro lado da mesa.
// O botão nomeia o que libera, e abrir esta página É o toque de liberar: a pessoa já
// escolheu ao tocar no botão, então não pedimos um segundo toque. A prévia do link no
// WhatsApp não roda script e não vê o fragmento (#…), então ela não libera ninguém. A
// referência sai da barra de endereço assim que é lida.

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const state = ref<'working' | 'done' | 'gone'>('working')
const releaseTarget = ref('')

useSeoMeta({
  title: 'Liberar acesso',
  robots: 'noindex, nofollow',
})
useHead({ meta: [{ name: 'referrer', content: 'no-referrer' }] })

onMounted(async () => {
  const releaseRef = window.location.hash.replace(/^#/, '').trim()
  window.history.replaceState(window.history.state, '', window.location.pathname)
  if (!releaseRef) {
    state.value = 'gone'
    return
  }
  try {
    const response = await $fetch<{ released: boolean, release_target?: string }>(
      apiPath('/api/v1/auth/whatsapp/release/'),
      {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: { ref: releaseRef },
      },
    )
    releaseTarget.value = response.release_target || ''
    state.value = 'done'
  } catch {
    state.value = 'gone'
  }
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container max-w-md shop-stack-block" data-login-release>
      <template v-if="state === 'done'">
        <h1 class="shop-title">Pronto, pode voltar ao computador</h1>
        <p class="shop-muted">
          {{ releaseTarget ? `Liberamos ${releaseTarget}.` : 'Liberamos o navegador do computador.' }}
          A loja entra sozinha por lá, em instantes. Nada mais precisa ser feito aqui.
        </p>
      </template>

      <template v-else-if="state === 'gone'">
        <h1 class="shop-title">Este pedido de entrada já não vale</h1>
        <p class="shop-muted">
          Ele passou de 10 minutos ou foi encerrado. No computador, toque em “Abrir o WhatsApp”
          de novo e envie a nova mensagem.
        </p>
      </template>

      <div v-else class="flex items-center gap-3" aria-live="polite">
        <Icon name="lucide:loader-circle" class="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <p class="shop-muted">Liberando o computador…</p>
      </div>
    </div>
  </main>
</template>
