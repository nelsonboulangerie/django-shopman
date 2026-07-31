<script setup lang="ts">
import type { PaymentResponse, PaymentStatusResponse, Action } from '~/types/shopman'
import { paymentAlertFilled, paymentAlertIcon, paymentAlertVariant, paymentMethodLabel, shouldPollPayment } from '~/presentation/payment'
import { countdownPct, deadlineCountdown, isCountdownUrgent, serverClockOffsetMs } from '~/presentation/deadline'
import { orderAccessErrorView } from '~/presentation/orderAccess'

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const actionPending = ref<Record<string, boolean>>({})
// Forward the session cookie on SSR so order access resolves on first paint
// (same pattern as the account pages) — otherwise the server fetch lands
// unauthenticated and the page renders the "not found" fallback for a customer
// who can actually see this payment.
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data, pending, error, refresh } = await useFetch<PaymentResponse>(
  () => apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include', headers: requestHeaders }
)

const payment = computed(() => data.value?.payment || null)
// As CTAs reais (retry_payment, authorize_card, pay_card) vivem em
// `promise.actions`; `payment.actions` só carrega o botão mock de DEBUG. A tela
// iterava apenas o segundo, então estados como `intent_error` e
// `card_checkout_pending` mostravam o erro e NENHUM botão para sair dele.
// `mock_confirm_payment` tem caixa própria (ambiente de teste) e `track_order`
// já é o botão fixo do topo do aside — iterar os dois aqui rendia o MESMO botão
// duas vezes, com rótulos diferentes e um deles sem caber na coluna.
const ACOES_COM_LUGAR_PROPRIO = new Set(['mock_confirm_payment', 'track_order'])
// `copy`/`instruction` não são ações de servidor: são orientação sobre o que já
// está na tela. Renderizadas nesta lista viravam botão-frase que não faz nada
// ("Use o QR Code ou copia e cola abaixo"), ao lado do "Copiar código" real.
const KINDS_QUE_NAO_SAO_ACAO = new Set(['copy', 'instruction'])
// Pix ainda sem código (a loja confere antes, com `timing=post_commit`). Sem
// isso o card ficava oco: cabeçalho com o total e um vazio embaixo, com cara de
// conteúdo que falhou ao carregar.
const esperandoCodigoPix = computed(() => Boolean(
  payment.value?.method === 'pix' &&
  !payment.value?.pix_qr_code &&
  !payment.value?.pix_copy_paste &&
  !payment.value?.error_message
))
const paymentActions = computed<Action[]>(() => {
  const vistas = new Set<string>()
  return [...(payment.value?.promise?.actions || []), ...(payment.value?.actions || [])]
    .filter((a) => {
      if (!a?.ref || vistas.has(a.ref) || ACOES_COM_LUGAR_PROPRIO.has(a.ref)) return false
      if (KINDS_QUE_NAO_SAO_ACAO.has(a.kind)) return false
      vistas.add(a.ref)
      return true
    })
})
// Copy estática da tela vem do registro omotenashi (configurável no Admin); o
// fallback cobre só o intervalo de carregamento. O painel de status é o promise.
const copy = computed(() => data.value?.copy ?? {
  order_ref_label: 'Pedido',
  total_label: 'Total',
  meta_description: 'Pague seu pedido para seguirmos com o preparo',
  card_intro: 'Conclua o pagamento no nosso ambiente seguro. A confirmação é automática. Volte aqui se quiser acompanhar seu pedido.',
  card_security_note: 'Pagamento processado por provedor seguro. Nós não recebemos os dados do seu cartão.',
  pix_instruction: 'Escaneie o QR Code ou copie o código Pix abaixo.',
  pix_copy_label: 'Pix Copia e Cola',
  pix_copy_btn: 'Copiar código',
  pix_copied: 'Código Pix copiado.',
  pix_expires_label: 'Tempo para pagar'
})
const errorView = computed(() => orderAccessErrorView((error.value as { statusCode?: number } | null)?.statusCode, 'payment'))
const loginHref = computed(() => `/entrar?next=${encodeURIComponent(`/pedido/${orderRef.value}/pagamento`)}`)

watchEffect(() => {
  if (data.value?.redirect_url && !payment.value && import.meta.client) {
    void navigateTo(localRouteFromBackend(data.value.redirect_url))
  }
})

// Relógio vivo alinhado ao servidor (timeouts transparentes). `nowMs` corrige o
// relógio do dispositivo pelo offset de server_now_iso.
const clientNow = ref(Date.now())
const serverOffset = computed(() => serverClockOffsetMs(payment.value?.server_now_iso, Date.now()))
const nowMs = computed(() => clientNow.value + serverOffset.value)

// Janela do PIX ancorada no primeiro tempo restante visto, para a barra drenar
// de cheia a vazia sem o início real do intent.
const pixWindowSeconds = ref(0)
const pixCountdown = computed(() => deadlineCountdown(payment.value?.pix_expires_at, nowMs.value))
watch(pixCountdown, countdown => {
  if (countdown && countdown.totalSeconds > 0 && pixWindowSeconds.value === 0) {
    pixWindowSeconds.value = countdown.totalSeconds
  }
}, { immediate: true })
const pixPct = computed(() => pixCountdown.value ? countdownPct(pixCountdown.value.totalSeconds, pixWindowSeconds.value) : 0)
const pixUrgent = computed(() => isCountdownUrgent(pixPct.value))

let tick: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null
let expiryHandled = false
// Sinal de offline: 3 polls seguidos falhando (~24s) = o countdown do PIX
// está rodando às cegas — o cliente precisa saber que estamos sem conexão.
const failedPolls = ref(0)
const connectionLost = computed(() => failedPolls.value >= 3)
onMounted(() => {
  tick = setInterval(() => { clientNow.value = Date.now() }, 1000)
  poll = setInterval(async () => {
    if (!shouldPollPayment(payment.value)) return
    const status = await $fetch<PaymentStatusResponse>(apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/status/`), {
      credentials: 'include',
      timeout: 7000
    }).catch(() => null)
    if (status === null) {
      failedPolls.value += 1
      return
    }
    failedPolls.value = 0
    if (status.should_redirect) {
      await navigateTo(localRouteFromBackend(status.redirect_url))
    } else {
      await refresh()
    }
  }, 8000)
})
onBeforeUnmount(() => {
  if (tick) clearInterval(tick)
  if (poll) clearInterval(poll)
})

// Quando o PIX zera, o backend decide (deadline_action): a UI só sincroniza uma
// vez para refletir o estado terminal (expirado/cancelado) que a projeção trouxer.
watch(() => pixCountdown.value?.isExpired, async expired => {
  if (expired && !expiryHandled && shouldPollPayment(payment.value)) {
    expiryHandled = true
    await refresh()
  }
})

async function copyPix () {
  if (!payment.value?.pix_copy_paste || !import.meta.client) return
  await navigator.clipboard.writeText(payment.value.pix_copy_paste)
  useSonner.success(copy.value.pix_copied)
}

// PIX expirado: re-consulta o servidor para descobrir o estado real. NÃO existe
// reemissão de intent — `customer_orders.ensure_payment_intent` retorna cedo
// quando já há `intent_ref`, e `payment_service.initiate` é idempotente. O
// comentário anterior afirmava o contrário e o botão prometia um código novo que
// nunca vinha. Quando o prazo vence, o pedido segue para cancelamento por
// timeout; o caminho honesto é ver o estado no acompanhamento.
const regenerating = ref(false)
async function recheckPayment () {
  if (regenerating.value) return
  regenerating.value = true
  expiryHandled = false
  pixWindowSeconds.value = 0
  failedPolls.value = 0
  try {
    await refresh()
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível verificar o pagamento agora.'))
  } finally {
    regenerating.value = false
  }
}

async function postAction (action: Action) {
  actionPending.value = { ...actionPending.value, [action.ref]: true }
  try {
    const headers = await csrfHeaders()
    if (action.idempotency === 'required' || action.idempotency === 'recommended') {
      headers['x-idempotency-key'] = newRemoteMutationKey(action.ref)
    }
    const result = await $fetch<{ redirect_url?: string }>(apiPath(action.href), {
      method: remoteMethod(action.method),
      headers,
      credentials: 'include'
    })
    if (result.redirect_url) await navigateTo(localRouteFromBackend(result.redirect_url))
    else await refresh()
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível atualizar o pagamento.'))
  } finally {
    actionPending.value = omitKey(actionPending.value, action.ref)
  }
}

// "Simular pagamento" (staging/DEBUG): captura o pagamento por um gateway mock,
// para testar o fluxo PIX/cartão de ponta a ponta sem gateway real. Só aparece
// quando o backend marca payment.mock_enabled.
const simulating = ref(false)
async function simulatePayment () {
  if (simulating.value) return
  simulating.value = true
  try {
    const headers = await csrfHeaders()
    headers['x-idempotency-key'] = newRemoteMutationKey(`mock-confirm:${orderRef.value}`)
    const result = await $fetch<{ redirect_url?: string }>(
      apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/mock-confirm/`),
      { method: 'POST', headers, credentials: 'include' }
    )
    if (result.redirect_url) await navigateTo(localRouteFromBackend(result.redirect_url))
    else await refresh()
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível simular o pagamento.'))
  } finally {
    simulating.value = false
  }
}

useSeoMeta({
  title: () => `Pagamento ${orderRef.value}`,
  description: () => copy.value.meta_description
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container max-w-4xl py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Pedido', link: orderTrackingRoute(orderRef) },
            { label: 'Pagamento' }
          ]"
        />
      </div>
    </div>
    <div class="shop-container max-w-4xl shop-stack-block">
      <div>
        <p class="shop-kicker">Pagamento</p>
        <h1 class="mt-1 shop-title">{{ copy.order_ref_label }} {{ orderRef }}</h1>
      </div>

      <!-- Skeleton que espelha o layout real (painel + cartão de pagamento). -->
      <div v-if="pending" class="shop-stack-block">
        <UiSkeleton class="h-20 rounded-lg" />
        <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <UiSkeleton class="h-72 rounded-lg" />
          <UiSkeleton class="h-40 rounded-lg" />
        </div>
      </div>

      <UiAlert v-else-if="error" variant="warning" :icon="errorView.icon">
        <UiAlertTitle>{{ errorView.title }}</UiAlertTitle>
        <UiAlertDescription>
          <div class="shop-stack-block">
            <p>{{ errorView.message }}</p>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton v-if="errorView.showLogin" :to="loginHref" icon="lucide:log-in">Entrar</UiButton>
              <UiButton v-if="errorView.canRetry" variant="outline" icon="lucide:rotate-cw" @click="refresh">Tentar de novo</UiButton>
              <UiButton to="/menu" variant="ghost" icon="lucide:utensils">Ver cardápio</UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="payment">
        <UiAlert
          :variant="paymentAlertVariant(payment.promise.tone)"
          :filled="paymentAlertFilled(payment.promise.tone)"
          :icon="paymentAlertIcon(payment.promise.tone)"
        >
          <UiAlertTitle>{{ payment.promise.title }}</UiAlertTitle>
          <UiAlertDescription>
            {{ payment.promise.message }}
            <!-- Nota de rodapé: complemento opcional, sem rótulo, em tom secundário. -->
            <span v-if="payment.promise.footnote" class="mt-2 block shop-body">{{ payment.promise.footnote }}</span>
          </UiAlertDescription>
        </UiAlert>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <UiCard>
            <UiCardHeader>
              <p class="shop-muted text-sm">{{ copy.total_label }}</p>
              <UiCardTitle>{{ payment.total_display }}</UiCardTitle>
              <UiCardDescription>{{ paymentMethodLabel(payment.method) }}</UiCardDescription>
            </UiCardHeader>
            <UiCardContent class="space-y-4">
              <!-- Erro primeiro: escondido no rodapé do card, o cliente tentava
                   pagar de novo sem saber por que a primeira vez falhou. -->
              <UiAlert v-if="payment.error_message" variant="destructive">
                <UiAlertTitle>Não foi possível concluir o pagamento</UiAlertTitle>
                <UiAlertDescription>{{ payment.error_message }}</UiAlertDescription>
              </UiAlert>

              <div v-if="payment.method === 'card' && payment.checkout_url" class="shop-stack-block rounded-lg border p-4">
                <div class="flex items-start gap-3">
                  <Icon name="lucide:shield-check" :size="22" class="mt-0.5 shrink-0 text-emerald-600" />
                  <div class="space-y-1">
                    <p class="shop-item-title font-semibold text-foreground">Pagamento seguro</p>
                    <p class="shop-muted">{{ copy.card_intro }}</p>
                    <p class="shop-meta">{{ copy.card_security_note }}</p>
                  </div>
                </div>
                <UiButton :href="payment.checkout_url" target="_blank" rel="noopener noreferrer" class="w-full" :class="simulating ? 'pointer-events-none opacity-50' : ''" size="lg" icon="lucide:credit-card">
                  Pagar com cartão
                </UiButton>
                <!-- No celular o popup pode ser bloqueado: deixamos claro que dá
                     para tocar de novo, sem o cliente achar que travou. -->
                <p class="shop-meta text-center">Não abriu? Toque no botão novamente.</p>
              </div>

              <div v-else-if="payment.method === 'card'" class="flex items-center gap-3 rounded-lg border p-4">
                <Icon name="lucide:loader-circle" :size="20" class="shrink-0 animate-spin text-muted-foreground" />
                <p class="shop-muted">Preparando o pagamento seguro com cartão…</p>
              </div>

              <!-- Lugar reservado para o código: diz "vai aparecer aqui" sem
                   afirmar que já está sendo gerado (com post_commit o intent só
                   nasce quando a loja confirma). `motion-safe` respeita quem
                   pediu menos movimento. -->
              <div v-if="esperandoCodigoPix" class="flex flex-col items-center gap-3 py-2">
                <div class="flex size-48 max-w-full items-center justify-center rounded-lg border border-dashed text-muted-foreground">
                  <Icon name="lucide:qr-code" class="size-12 motion-safe:animate-pulse" />
                </div>
                <p class="shop-meta text-center">{{ copy.pix_expires_label }} começa quando o código aparecer.</p>
              </div>

              <!-- Pix: a ordem segue o que o cliente faz — quanto tempo tem,
                   como pagar (QR), e o copia-e-cola para quem paga no mesmo
                   aparelho. O código não é para ler: é para copiar, então fica
                   numa linha com o botão ao lado, não num bloco rolável. -->
              <div v-if="payment.pix_qr_code || payment.pix_copy_paste" class="shop-stack-block">
                <div v-if="pixCountdown && !pixCountdown.isExpired" class="space-y-2" role="timer">
                  <div class="flex items-center justify-between shop-body">
                    <span class="text-muted-foreground">{{ copy.pix_expires_label }}</span>
                    <span class="shop-price-strong" :class="pixUrgent ? 'text-destructive' : 'text-foreground'">{{ pixCountdown.mmss }}</span>
                  </div>
                  <UiProgress :model-value="pixPct" :class="pixUrgent ? '[&>div]:bg-destructive' : ''" />
                </div>

                <div v-if="payment.pix_qr_code" class="flex flex-col items-center gap-3">
                  <div class="rounded-lg border bg-white p-4">
                    <img :src="payment.pix_qr_code" alt="QR Code Pix" class="size-48 max-w-full" />
                  </div>
                  <p class="shop-muted text-center">{{ copy.pix_instruction }}</p>
                </div>

                <div v-if="payment.pix_copy_paste" class="shop-stack-tight">
                  <p class="shop-meta">{{ copy.pix_copy_label }}</p>
                  <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <!-- Tocar o código copia também: no celular, selecionar 100+
                         chars à mão é penoso. -->
                    <p
                      class="min-w-0 flex-1 cursor-pointer truncate rounded-lg border bg-muted px-3 py-2 font-mono text-xs"
                      role="button"
                      tabindex="0"
                      aria-label="Copiar código Pix"
                      :title="payment.pix_copy_paste"
                      @click="copyPix"
                      @keydown.enter.prevent="copyPix"
                      @keydown.space.prevent="copyPix"
                    >{{ payment.pix_copy_paste }}</p>
                    <UiButton variant="outline" icon="lucide:copy" class="shrink-0" @click="copyPix">{{ copy.pix_copy_btn }}</UiButton>
                  </div>
                </div>

                <p v-if="pixCountdown && !pixCountdown.isExpired" class="shop-meta">
                  Assim que o pagamento cair, atualizamos esta tela automaticamente.
                </p>

                <p v-if="connectionLost" class="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-800 dark:text-amber-300" role="status">
                  Sem conexão no momento. Se você já pagou, a confirmação chega assim que a internet voltar.
                </p>

                <!-- Pix expirado: dizer a verdade. Não há reemissão de código; o
                     pedido segue para cancelamento por timeout. Oferecemos
                     reconferir (o pagamento pode ter caído no limite) e o
                     acompanhamento, que mostra o estado real. -->
                <div v-if="pixCountdown?.isExpired" class="shop-stack-tight rounded-lg border border-destructive/30 bg-destructive/5 p-3">
                  <p class="shop-body font-semibold text-destructive">O prazo do Pix expirou.</p>
                  <p class="shop-muted">Se você pagou nos últimos instantes, confira de novo — a confirmação pode estar a caminho. Senão, o pedido será liberado e você pode refazê-lo.</p>
                  <div class="flex flex-col gap-2 sm:flex-row">
                    <UiButton icon="lucide:refresh-cw" :loading="regenerating" class="w-full justify-center sm:w-auto" @click="recheckPayment">
                      Conferir de novo
                    </UiButton>
                    <UiButton :to="localRouteFromBackend(payment.tracking_url)" variant="outline" icon="lucide:route" class="w-full justify-center sm:w-auto">
                      Acompanhar pedido
                    </UiButton>
                  </div>
                </div>
              </div>

              <!-- Ambiente de teste: único lugar do "simular". A ação equivalente
                   vinda da projeção é filtrada do aside, senão o mesmo botão
                   aparecia duas vezes, com rótulos diferentes. -->
              <div v-if="payment.mock_enabled" class="shop-stack-tight rounded-lg border border-dashed bg-muted/40 p-4">
                <p class="shop-meta">Ambiente de teste · captura por gateway simulado</p>
                <UiButton
                  variant="outline"
                  class="w-full"
                  icon="lucide:flask-conical"
                  :loading="simulating"
                  @click="simulatePayment"
                >
                  Simular pagamento
                </UiButton>
              </div>

            </UiCardContent>
          </UiCard>

          <!-- Sem card em volta: na maioria dos estados sobra um único botão, e
               a moldura virava uma caixa vazia grande ao lado do conteúdo. -->
          <aside class="space-y-2 lg:pt-0">
            <UiButton :to="localRouteFromBackend(payment.tracking_url)" variant="outline" class="w-full" icon="lucide:route">
              Acompanhar pedido
            </UiButton>
            <UiButton
              v-for="action in paymentActions"
              :key="action.ref"
              :variant="actionVariant(action)"
              class="w-full"
              :disabled="!action.enabled"
              :loading="!!actionPending[action.ref]"
              @click="postAction(action)"
            >
              {{ action.label }}
            </UiButton>
          </aside>
        </div>
      </template>
    </div>
  </main>
</template>
