<script setup lang="ts">
import type { CartProjection } from '~/types/shopman'

// A ponta do anúncio: quem tocou no link do WhatsApp cai aqui e a sacola se monta.
//
// Não exige login DE PROPÓSITO. O link dorme horas numa conversa, então não pode ser
// magic link (5 min, uso único); e esticar esse prazo espalharia links de sessão em
// históricos que são encaminhados e printados. O link carrega a oferta; identificar-se
// acontece no checkout, onde já acontecia.
//
// A resolução é toda no CLIQUE: preço de agora, estoque de agora. O que o servidor não
// conseguir montar volta em `skipped`, e a tela conta — nunca finge que entrou.
const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { setFromServer } = useCartState()

const offerRef = computed(() => String(route.params.ref || ''))

/** Item que a oferta não conseguiu montar — nomeado, e com saída quando houver. */
type SkippedOfferItem = {
  sku: string
  name: string
  is_notifiable: boolean
  is_notify_subscribed: boolean
}

type ClaimResponse = {
  ok: boolean
  offer: { ref: string; name: string }
  added: string[]
  skipped: SkippedOfferItem[]
  cart: CartProjection
}

const pending = ref(true)
const offerName = ref('')
const skipped = ref<SkippedOfferItem[]>([])
const problem = ref('')
/** Sacola já tinha itens: quem decide somar ou trocar é o cliente, não nós. */
const conflict = ref(false)

async function claim (mode?: 'append' | 'replace') {
  pending.value = true
  problem.value = ''
  conflict.value = false
  try {
    const response = await $fetch<ClaimResponse>(
      apiPath(`/api/v1/offers/${encodeURIComponent(offerRef.value)}/claim/`),
      {
        method: 'POST',
        headers: await csrfHeaders(),
        body: mode ? { mode } : {},
        credentials: 'include'
      }
    )
    offerName.value = response.offer?.name || ''
    skipped.value = response.skipped || []
    setFromServer(response.cart)
    if (response.ok) {
      await navigateTo('/sacola')
      return
    }
    // Nada entrou: a oferta existe, mas nenhum item dela está vendável agora.
    problem.value = 'Os itens desta oferta não estão disponíveis neste momento.'
  } catch (error: unknown) {
    const status = (error as { statusCode?: number; status?: number })?.statusCode
      ?? (error as { status?: number })?.status
    const detail = (error as { data?: { detail?: string; error_code?: string } })?.data
    if (status === 409 && detail?.error_code === 'cart_not_empty') {
      conflict.value = true
    } else {
      problem.value = detail?.detail || 'Não foi possível abrir esta oferta.'
    }
  } finally {
    pending.value = false
  }
}

onMounted(() => { claim() })

// Oferta é conteúdo efêmero e personalizado: não interessa ao índice, e indexar um
// link que monta sacola convidaria o Google a montar sacolas.
useSeoMeta({ title: 'Sua oferta', robots: 'noindex, nofollow' })
</script>

<template>
  <main class="shop-section">
    <div class="shop-container">
      <div class="mx-auto max-w-md shop-stack-block">
        <div v-if="pending" class="py-10 text-center" aria-busy="true">
          <Icon name="lucide:loader-circle" class="mx-auto size-8 animate-spin text-muted-foreground" />
          <p class="mt-4 shop-muted">Separando sua oferta…</p>
        </div>

        <!-- Sacola com itens: perguntamos. Trocar sem perguntar apagaria uma sacola que
             o cliente montou, e isso não se desfaz. -->
        <section v-else-if="conflict" class="shop-stack-block text-center">
          <header>
            <h1 class="shop-title">Você já tem itens na sacola</h1>
            <p class="mt-2 shop-muted">
              Podemos somar a oferta ao que já está lá, ou começar uma sacola nova conosco.
            </p>
          </header>
          <div class="shop-stack-tight">
            <UiButton size="lg" class="w-full justify-center" @click="claim('append')">
              Somar à minha sacola
            </UiButton>
            <UiButton size="lg" variant="outline" class="w-full justify-center" @click="claim('replace')">
              Começar uma sacola nova
            </UiButton>
            <UiButton variant="ghost" size="sm" class="w-full justify-center" to="/sacola">
              Ver minha sacola
            </UiButton>
          </div>
        </section>

        <section v-else-if="problem" class="text-center">
          <Icon name="lucide:circle-slash" class="mx-auto size-8 text-muted-foreground" />
          <h1 class="mt-4 shop-title">{{ problem }}</h1>
          <p class="mt-2 shop-muted">
            O cardápio de hoje segue no ar, e tem coisa boa saindo do forno.
          </p>
          <UiButton size="lg" class="mt-4 w-full justify-center" to="/menu">
            Ver o cardápio
          </UiButton>
        </section>

        <!-- Entrou parcial: nomeamos o que ficou de fora, em vez de deixar o cliente
             descobrir na sacola — e quem pode ser avisado é avisado daqui mesmo. -->
        <section v-else-if="skipped.length">
          <div class="text-center">
            <h1 class="shop-title">{{ offerName || 'Oferta' }} na sua sacola</h1>
            <p class="mt-2 shop-muted">
              {{ skipped.length === 1 ? 'Um item não estava disponível agora e ficou de fora:' : 'Alguns itens não estavam disponíveis agora e ficaram de fora:' }}
            </p>
          </div>
          <ul class="mt-4 divide-y rounded-lg border">
            <li
              v-for="item in skipped"
              :key="item.sku"
              class="flex items-center justify-between gap-3 px-4 py-3"
            >
              <span class="min-w-0 flex-1 truncate shop-item-title">{{ item.name }}</span>
              <StockNotifyButton
                v-if="item.is_notifiable"
                :sku="item.sku"
                :name="item.name"
                :subscribed="item.is_notify_subscribed"
                compact
              />
              <span v-else class="shrink-0 shop-meta">Indisponível</span>
            </li>
          </ul>
          <UiButton size="lg" class="mt-4 w-full justify-center" to="/sacola">
            Ver minha sacola
          </UiButton>
        </section>
      </div>
    </div>
  </main>
</template>
