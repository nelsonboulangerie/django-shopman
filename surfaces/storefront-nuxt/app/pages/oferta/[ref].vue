<script setup lang="ts">
import { retainedRemoteMutationKey, forgetRemoteMutationKey } from '~/utils/remoteMutations'
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
  /** A sacola já tinha itens e eles ficaram: a oferta foi somada a eles. */
  kept_existing_items: boolean
  cart: CartProjection
}

type ClaimMode = 'merge' | 'replace'

const pending = ref(true)
const offerName = ref('')
const addedNames = ref<string[]>([])
const skipped = ref<SkippedOfferItem[]>([])
const problem = ref('')
const assembled = ref(false)
const intention = ref('')
/**
 * A oferta entrou numa sacola que já tinha itens, e o cliente ainda não disse se fica
 * com tudo. O aviso está na tela e não sai sem escolha — ver `onBeforeRouteLeave`.
 */
const decisionOpen = ref(false)
const deciding = ref(false)

function claimResource (mode: ClaimMode) {
  return `offer:${offerRef.value}:${mode}`
}

async function claim (mode: ClaimMode = 'merge') {
  const resource = claimResource(mode)
  intention.value = retainedRemoteMutationKey(resource, 'offer')
  pending.value = true
  problem.value = ''
  try {
    const response = await $fetch<ClaimResponse>(
      apiPath(`/api/v1/offers/${encodeURIComponent(offerRef.value)}/claim/`),
      {
        method: 'POST',
        headers: { ...(await csrfHeaders()), 'Idempotency-Key': intention.value },
        body: mode === 'replace' ? { mode } : {},
        credentials: 'include'
      }
    )
    offerName.value = response.offer?.name || ''
    skipped.value = response.skipped || []
    addedNames.value = response.cart.items.filter(item => response.added.includes(item.sku)).map(item => item.name)
    setFromServer(response.cart)
    assembled.value = response.ok
    // A oferta SEMPRE soma: quem decide é o servidor, e ele nunca troca sem pedido. A
    // pergunta que sobra é sobre o que já estava na sacola, e só existe se havia algo lá
    // e a oferta de fato entrou — sem item novo, não há nada a manter nem a dispensar.
    if (response.kept_existing_items && response.added.length) {
      decisionOpen.value = true
      return
    }
    if (response.ok && !skipped.value.length) {
      await navigateTo('/sacola')
      forgetRemoteMutationKey(resource)
      return
    }
    // Nada entrou: a oferta existe, mas nenhum item dela está vendável agora.
    if (!skipped.value.length) problem.value = 'Nenhum item foi adicionado à sacola.'
  } catch (error: unknown) {
    const detail = (error as { data?: { detail?: string } })?.data
    problem.value = detail?.detail || 'Não foi possível abrir esta oferta.'
  } finally {
    pending.value = false
  }
}

async function keepEverything () {
  deciding.value = true
  decisionOpen.value = false
  forgetRemoteMutationKey(claimResource('merge'))
  if (!skipped.value.length) await navigateTo('/sacola')
  deciding.value = false
}

async function keepOnlyTheOffer () {
  deciding.value = true
  decisionOpen.value = false
  forgetRemoteMutationKey(claimResource('merge'))
  // `replace` esvazia a sacola e remonta a oferta: sobra a oferta sozinha, que é o que
  // o cliente escolheu. Preço e estoque se resolvem de novo, no mesmo caminho.
  await claim('replace')
  deciding.value = false
}

/**
 * Intransigente, por decisão do dono: enquanto a escolha não acontece, não há saída —
 * nem clique fora, nem ESC, nem navegar. Um aviso ignorável deixaria a sacola num
 * estado que o cliente não escolheu, e ele só descobriria no checkout.
 */
onBeforeRouteLeave(() => !decisionOpen.value)

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

        <!-- A oferta entrou e a sacola já tinha itens: o fato fica na tela atrás do
             aviso, para que a página nunca fique em branco. -->
        <section v-else-if="decisionOpen" class="text-center">
          <h1 class="shop-title">{{ offerName || 'Oferta' }} na sua sacola</h1>
          <p v-if="addedNames.length" class="mt-4" role="status">Adicionados: {{ addedNames.join(', ') }}.</p>
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
            <h1 class="shop-title">{{ assembled ? `${offerName || 'Oferta'} parcialmente na sua sacola` : 'Nenhum item foi adicionado' }}</h1>
            <p class="mt-2 shop-muted">
              {{ skipped.length === 1 ? 'Um item não estava disponível agora e ficou de fora:' : 'Alguns itens não estavam disponíveis agora e ficaram de fora:' }}
            </p>
          </div>
          <p v-if="addedNames.length" class="mt-4" role="status">Adicionados: {{ addedNames.join(', ') }}.</p>
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

    <!-- ⚠️ Intransigente: não fecha por clique fora (o AlertDialog não fecha), nem por
         ESC, não tem Cancelar e não deixa a rota sair. As duas saídas são as duas
         escolhas. A copy é a do dono, palavra por palavra. -->
    <UiAlertDialog :open="decisionOpen">
      <UiAlertDialogContent @escape-key-down.prevent>
        <UiAlertDialogHeader>
          <UiAlertDialogTitle>Você já tinha itens na sacola e a oferta foi adicionada.</UiAlertDialogTitle>
          <UiAlertDialogDescription>Deseja manter tudo na sacola?</UiAlertDialogDescription>
        </UiAlertDialogHeader>
        <UiAlertDialogFooter>
          <UiAlertDialogAction :disabled="deciding" @click="keepEverything">
            Sim, manter tudo
          </UiAlertDialogAction>
          <UiAlertDialogAction variant="outline" :disabled="deciding" @click="keepOnlyTheOffer">
            Não, só a oferta
          </UiAlertDialogAction>
        </UiAlertDialogFooter>
      </UiAlertDialogContent>
    </UiAlertDialog>
  </main>
</template>
