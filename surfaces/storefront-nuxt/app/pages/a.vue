<script setup lang="ts">
// Magic-link bridge: the customer arrives from a notification at `/a?t=<token>`.
// We exchange the token through the BFF (`/api/auth/access/`), so the session
// cookie is set on the store host, then navigate to the backend-derived
// destination. The token (not a `next` param) decides where they land — no
// open-redirect surface.
interface AccessResponse {
  ok?: boolean
  redirect?: string
  is_authenticated?: boolean
  customer_name?: string
  customer_phone?: string
  requires_welcome?: boolean
  welcome_suggested_name?: string
  // Handoff do site expirou: entrou logado, mas a sacola não veio (link vencido).
  handoff_expired?: boolean
  notice?: string
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()

const token = computed(() => String(route.query.t || '').trim())
const failed = ref(false)
const exchanging = ref(false)
const browserHandoff = ref(false)
const browserHandoffManual = ref(false)
const browserHandoffFailed = ref(false)
let browserHandoffTimer: ReturnType<typeof setTimeout> | null = null

async function exchangeToken () {
  if (!token.value) {
    failed.value = true
    return
  }
  browserHandoff.value = false
  exchanging.value = true

  // ⚠️ Tira o token da barra de endereço antes de qualquer coisa. Ele é um crachá: deixá-lo
  // ali o deixa no histórico do navegador, na barra do navegador embutido do WhatsApp e em
  // qualquer print tirado depois. A troca já foi lida da rota; a URL não precisa mais dele.
  const clean = window.location.pathname
  window.history.replaceState(window.history.state, '', clean)

  try {
    const response = await $fetch<AccessResponse>(apiPath('/api/auth/access/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { token: token.value }
    })
    session.setFromAuthSession(response)
    // Sacola não veio (handoff expirou): aviso gentil que sobrevive à navegação (Sonner
    // vive no layout). O login segue normal; só comunicamos a sacola ausente.
    if (response.handoff_expired && response.notice) useSonner(response.notice)
    await navigateTo(response.redirect || '/conta')
  } catch {
    // O reclique é respondido pelo SERVIDOR (200 com `already_authenticated`), porque só
    // ele sabe se existe sessão no cookie — numa carga nova o estado daqui nasce vazio.
    // Cair aqui é falha de verdade: token inválido e ninguém identificado.
    failed.value = true
  } finally {
    exchanging.value = false
  }
}

function tryOpenSystemBrowser () {
  browserHandoff.value = true
  browserHandoffManual.value = false
  browserHandoffFailed.value = false
  try {
    window.location.href = systemBrowserUrl(window.location.href)
    browserHandoffTimer = setTimeout(() => { browserHandoffManual.value = true }, 1200)
  } catch {
    browserHandoffFailed.value = true
  }
}

onMounted(async () => {
  if (!token.value) {
    failed.value = true
    return
  }

  // Link vindo do ManyChat costuma abrir no navegador embutido do WhatsApp. O melhor lugar
  // para tentar atravessar é ANTES de consumir o token, porque o navegador externo precisa
  // abrir esta mesma URL e fazer o exchange no pote de cookie dele.
  if (isInAppBrowser()) {
    tryOpenSystemBrowser()
    return
  }

  await exchangeToken()
})

onBeforeUnmount(() => {
  if (browserHandoffTimer) clearTimeout(browserHandoffTimer)
})

useSeoMeta({
  title: 'Entrando…',
  robots: 'noindex'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container max-w-md shop-stack-block">
      <template v-if="browserHandoff">
        <div class="flex flex-col items-center gap-4 py-12 text-center" data-access-browser-handoff>
          <Icon name="lucide:external-link" :size="32" class="text-muted-foreground" />
          <div class="shop-stack-micro">
            <h1 class="shop-heading">Abrindo no seu navegador</h1>
            <p class="shop-body text-muted-foreground">
              Assim sua entrada fica salva no navegador que você usa todo dia.
            </p>
          </div>

          <div class="grid w-full gap-2">
            <UiButton type="button" icon="lucide:external-link" class="w-full justify-center" @click="tryOpenSystemBrowser">
              Abrir no meu navegador
            </UiButton>
            <UiButton
              type="button"
              variant="ghost"
              icon="lucide:message-circle"
              class="w-full justify-center"
              :loading="exchanging"
              @click="exchangeToken"
            >
              Continuar por aqui
            </UiButton>
          </div>

          <p v-if="browserHandoffManual" class="shop-caption text-muted-foreground">
            Não abriu? Toque nos três pontinhos aqui em cima e escolha
            <strong>Abrir no navegador</strong>.
          </p>
          <p v-if="browserHandoffFailed" class="shop-caption text-muted-foreground">
            Não conseguimos abrir automaticamente. Você pode continuar por aqui.
          </p>
        </div>
      </template>

      <template v-else-if="!failed">
        <div class="flex flex-col items-center gap-4 py-12 text-center">
          <Icon name="lucide:loader-circle" :size="32" class="animate-spin text-muted-foreground" />
          <p class="shop-body text-muted-foreground">Entrando na sua conta…</p>
        </div>
      </template>

      <UiAlert v-else variant="warning" icon="lucide:link-2-off">
        <UiAlertTitle>Não conseguimos abrir este link</UiAlertTitle>
        <UiAlertDescription>
          <div class="shop-stack-block">
            <p>O link pode ter expirado ou já ter sido usado. Entre para acompanhar seu pedido.</p>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton to="/entrar" icon="lucide:log-in">Entrar</UiButton>
              <UiButton to="/menu" variant="ghost" icon="lucide:utensils">Ver cardápio</UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>
    </div>
  </main>
</template>
