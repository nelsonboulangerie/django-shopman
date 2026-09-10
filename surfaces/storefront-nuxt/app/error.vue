<script setup lang="ts">
import type { NuxtError } from '#app'
import type { HomeResponse } from '~/types/shopman'

const props = defineProps<{ error: NuxtError }>()

const apiPath = useShopmanApiPath()
const session = useShopSession()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

// Numa 404/5xx de SSR o app.vue não roda, então a sessão (marca + WhatsApp) viria vazia
// e o tema cairia no neutro cinza — fora da paleta da Nelson. Buscamos o mesmo shell do
// app (mesma `key` ⇒ reaproveita o cache quando o erro é lançado depois do app já ter
// carregado). Se a própria API caiu, o fetch falha em silêncio e degradamos para
// neutro/sem CTA — aceitável só no pior caso.
const { data: shellHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-shell-home'
})
watch(() => shellHome.value, value => session.setFromHome(value?.home), { immediate: true })

useShopTheme(session.shop)

const is404 = computed(() => props.error?.statusCode === 404)
const whatsappUrl = computed(() => session.publicConfig.value?.whatsapp_url || '')

const kicker = computed(() => (is404.value ? 'Erro 404' : ''))
const title = computed(() =>
  is404.value ? 'Não encontramos esta página' : 'Tivemos um problema por aqui'
)
const message = computed(() =>
  is404.value
    ? 'O item pode ter saído do cardápio ou o endereço está incorreto. Vamos levar você de volta ao cardápio.'
    : 'Tente de novo em alguns segundos. Se precisar fechar um pedido agora, fale conosco no WhatsApp.'
)

// Páginas de erro nunca devem ser indexadas (o status 404/5xx já sinaliza, isto é
// reforço). `follow` para o crawler ainda seguir os links de volta.
useSeoMeta({ robots: 'noindex, follow', title: () => title.value })

function goMenu () {
  clearError({ redirect: '/menu' })
}

function goHome () {
  clearError({ redirect: '/' })
}

// "Tente de novo" é a promessa da mensagem do 5xx — o botão a cumpre no lugar,
// sem obrigar a pessoa a conhecer o gesto de recarregar.
function retry () {
  if (import.meta.client) window.location.reload()
}
</script>

<template>
  <div class="error-screen flex min-h-svh flex-col items-center justify-center gap-6 px-6 py-16 text-center">
    <div class="error-screen-copy shop-stack-block max-w-md">
      <p v-if="kicker" class="shop-kicker">{{ kicker }}</p>
      <h1 class="shop-display">{{ title }}</h1>
      <p class="shop-muted">{{ message }}</p>
    </div>
    <div class="error-screen-actions flex flex-col gap-3 sm:flex-row">
      <template v-if="is404">
        <UiButton icon="lucide:utensils" @click="goMenu">Voltar ao cardápio</UiButton>
        <UiButton variant="outline" icon="lucide:house" @click="goHome">Página inicial</UiButton>
      </template>
      <template v-else>
        <UiButton icon="lucide:rotate-cw" @click="retry">Tentar de novo</UiButton>
        <UiButton variant="outline" icon="lucide:house" @click="goHome">Página inicial</UiButton>
        <UiButton
          v-if="whatsappUrl"
          variant="outline"
          :href="whatsappUrl"
          target="_blank"
          rel="noreferrer noopener"
        >
          Falar no WhatsApp
        </UiButton>
      </template>
    </div>

    <UiButton
      v-if="is404 && whatsappUrl"
      variant="link"
      size="sm"
      :href="whatsappUrl"
      target="_blank"
      rel="noreferrer noopener"
      class="text-muted-foreground"
    >
      Prefere falar conosco? WhatsApp
    </UiButton>
  </div>
</template>

<style>
/* Esqueleto autossuficiente da tela de erro. A folha global (utilities com
   hash) pode ter morrido junto com o erro — é exatamente o cenário pós-deploy
   em que esta tela aparece — e o Nuxt inline os estilos de componente no HTML
   do SSR, então ESTE bloco chega mesmo quando o resto do CSS não chega.
   Duplicar o layout das utilities aqui é o custo de a tela nunca abrir crua. */
.error-screen {
  box-sizing: border-box;
  min-height: 100vh;
  min-height: 100svh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1.5rem;
  padding: 4rem 1.5rem;
  text-align: center;
}
.error-screen-copy {
  max-width: 28rem;
}
.error-screen-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
}
</style>
