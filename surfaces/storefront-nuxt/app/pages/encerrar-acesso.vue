<script setup lang="ts">
// "Não foi você? Encerre este acesso" — o link da mensagem de login pelo WhatsApp.
//
// O login que começa no site entra sozinho quando a mensagem chega. A defesa contra
// quem pede a alguém que envie a mensagem com o código DELE é esta: a mensagem avisa
// onde a entrada aconteceu e dá um toque para desfazer. A referência vem no fragmento
// (#…) e nunca chega a log de HTTP; sai da barra de endereço assim que é lida.
//
// Um toque para encerrar, e não ao abrir: o WhatsApp pode abrir o link sozinho para
// montar a prévia, e a prévia não pode derrubar o acesso de ninguém.

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const revokeRef = ref('')
const state = ref<'ready' | 'working' | 'done' | 'gone'>('ready')

useSeoMeta({
  title: 'Encerrar acesso',
  robots: 'noindex, nofollow',
})
useHead({ meta: [{ name: 'referrer', content: 'no-referrer' }] })

onMounted(() => {
  revokeRef.value = window.location.hash.replace(/^#/, '').trim()
  window.history.replaceState(window.history.state, '', window.location.pathname)
  if (!revokeRef.value) state.value = 'gone'
})

async function revoke () {
  if (!revokeRef.value || state.value === 'working') return
  state.value = 'working'
  try {
    await $fetch(apiPath('/api/v1/auth/whatsapp/revoke/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { ref: revokeRef.value },
    })
    state.value = 'done'
  } catch {
    state.value = 'gone'
  }
}
</script>

<template>
  <main class="shop-section">
    <div class="shop-container max-w-md shop-stack-block" data-login-revoke>
      <template v-if="state === 'done'">
        <h1 class="shop-title">Acesso encerrado</h1>
        <p class="shop-muted">Quem entrou com a sua mensagem já está fora da sua conta. Nada mais precisa ser feito.</p>
        <UiButton to="/menu" variant="outline" icon="lucide:utensils">Ver cardápio</UiButton>
      </template>

      <template v-else-if="state === 'gone'">
        <h1 class="shop-title">Este aviso já não vale</h1>
        <p class="shop-muted">
          O acesso já foi encerrado, ou este aviso passou de 24 horas. Para conferir os dispositivos
          que entram na sua conta, abra Segurança na sua conta.
        </p>
        <UiButton to="/conta/seguranca" variant="outline" icon="lucide:shield">Abrir Segurança</UiButton>
      </template>

      <template v-else>
        <h1 class="shop-title">Não foi você que entrou?</h1>
        <p class="shop-muted">
          Alguém entrou na sua conta usando a mensagem que saiu do seu WhatsApp. Se não foi você,
          encerre esse acesso agora: a outra pessoa sai da sua conta e o dispositivo dela é esquecido.
        </p>
        <UiButton
          size="lg"
          variant="destructive"
          icon="lucide:log-out"
          class="w-full justify-center"
          :loading="state === 'working'"
          @click="revoke"
        >
          Encerrar esse acesso
        </UiButton>
        <p class="shop-meta">Foi você? Então está tudo certo, pode fechar esta página.</p>
      </template>
    </div>
  </main>
</template>
