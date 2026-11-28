<script setup lang="ts">
import { navigateTo } from '#app'
import type { CartProjection, CartResponse, CheckoutMutationResponse, CheckoutResponse } from '~/types/shopman'
import type { AddressSelection } from '~/presentation/address'
import { cartBatchFloor, cartBatchFloorReason, discountDisplay, linePrice, promoSavingsNote, reviewWaitlist } from '~/presentation/cart'
import { cartLinePromise, orderReadyLine } from '~/presentation/promise'
import { exceedsPaymentConstraint, pixProviderTestConstraint } from '~/presentation/paymentConstraints'
import { PICKUP_TAX_ID_WHY, TAX_ID_WHY, taxIdError, formatTaxId, isValidTaxId, taxIdDigits, taxIdLooksComplete } from '~/presentation/taxId'
import { displayBrazilianPhone, normalizeAuthPhone } from '~/utils/authPhone'
import { checkoutBagRefusal, ORDER_ALREADY_SENT_MESSAGE } from '~/utils/checkoutBagRefusal'
import { CHECKOUT_DRAFT_KEY, parseCheckoutDraft, removeCheckoutDraft } from '~/utils/checkoutDraft'
import { CHECKOUT_RECOVERY_DELAYS_MS, startCheckoutRecovery, type CheckoutRecoveryLoop, type CheckoutRecoveryOutcome } from '~/utils/checkoutRecovery'
import { buildCheckoutPayload, checkoutBaseline, createCheckoutAttemptKey, noteTaxId, type CheckoutFormState } from '~/utils/checkoutPayload'
import { formatCount } from '~/utils/display'
import { isHostedCheckout } from '~/presentation/payment'
import { markCardHandoff } from '~/utils/cardHandoff'
import { markJustPlaced } from '~/utils/justPlaced'
import {
  addressSummary as buildAddressSummary,
  availableFulfillmentOptions,
  canContinueCheckoutWhen,
  checkoutDateBounds,
  checkoutDateChoices,
  checkoutStepForField,
  checkoutStepHeaderSummary,
  checkoutStepIcons,
  checkoutStepLabels,
  checkoutStepState,
  checkoutSteps,
  confirmSheetDescription as buildConfirmSheetDescription,
  contactComplete as buildContactComplete,
  contactSummary as buildContactSummary,
  datepickerDisabledDates as buildDatepickerDisabledDates,
  displayCheckoutDate,
  orderDateMovedNotice,
  firstCheckoutError,
  fulfillmentIcon as resolveFulfillmentIcon,
  fulfillmentLabel as resolveFulfillmentLabel,
  fulfillmentSummary as buildFulfillmentSummary,
  initialCheckoutDate,
  isCheckoutDateUnavailable,
  localDateValue,
  isCustomCheckoutDate,
  notesToggleState,
  parseClosedDateEntries,
  parseLocalDate,
  paymentIcon as resolvePaymentIcon,
  paymentMethodHint,
  weekdayDateLabel,
  paymentMethodLabel as resolvePaymentMethodLabel,
  quickCheckoutDateOptions,
  checkoutWindows,
  earliestCheckoutWindowRef,
  reconciledWindowRef,
  selectedPickupSlot,
  shouldOfferPickupSwap,
  checkoutWindowsReason,
  noWindowsMessage,
  todayOverMessage,
  usesWindowGrid,
  checkoutNotesCopy,
  couponCardState,
  deliveryZoneRefused,
  DELIVERY_ZONE_REFUSAL_FOCUS,
  rememberChoicesDescription,
  whenSummary as buildWhenSummary,
  checkoutNow,
  checkoutTodayValue,
  type CheckoutSectionState,
  type CheckoutStep
} from '~/utils/checkoutFlow'

type Step = CheckoutStep

// Checkout exige cliente autenticado (canal padrão). O guard de auth resolve a sessão
// no SSR e redireciona pro /entrar antes de renderizar — sem flash da tela gated.
definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
// `liveCart` é a sacola de toda a loja; `cart` (abaixo) é a que veio com o checkout.
const { setFromServer, clearCart, applyCoupon, removeCoupon, cartIssue, raiseStockIssue, cart: liveCart } = useCartState()
const route = useRoute()
const { notice: pageNotice, show: showPageNotice } = usePageNotice()
const session = useShopSession()
const telemetry = useStorefrontTelemetry()
const checkoutRoot = ref<HTMLElement | null>(null)
const {
  keyboardActive,
  onFocusIn: onCheckoutFocusIn,
  onFocusOut: onCheckoutFocusOut
} = useMobileFormViewport(checkoutRoot)
// O card da ação só flutua enquanto deixa a página à vista (#3573): com a fonte do
// sistema a 200 % ele desce para o fim do formulário, depois da dica "tem mais abaixo".
const actionDock = ref<HTMLElement | null>(null)
const actionDockFloats = useActionDockFit(actionDock)
// DDD padrão da loja (config admin) — assumido quando o cliente digita telefone
// sem DDD, para o número nunca virar "(55) …" nem falhar a validação por isso.
// O checkout carrega o DDD padrão direto (crítico p/ normalizar telefone mesmo
// em acesso direto/SSR sem passar pelo home); public_config é só fallback.
const defaultDdd = computed(() => checkout.value?.default_ddd || session.publicConfig.value?.default_ddd || '')
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const state = reactive<CheckoutFormState>({
  name: '',
  phone: '',
  fulfillment_type: 'pickup',
  saved_address_id: null,
  delivery_address: '',
  delivery_address_structured: {},
  delivery_complement: '',
  delivery_instructions: '',
  delivery_date: '',
  delivery_time_slot: '',
  payment_method: '',
  change_for: '',
  notes: '',
  is_gift: false,
  recipient_name: '',
  recipient_phone: '',
  gift_message: '',
  gift_hide_values: false,
  save_as_default: true,
  fiscal_tax_id: '',
  fiscal_tax_id_on_pickup: false,
  save_fiscal_tax_id: false
})

const chosenDate = ref<Date | null>(null)
const activeStep = ref<Step>('fulfillment')
const contactEditing = ref(false)
const nameEditing = ref(false)
const nameInput = ref<{ $el?: HTMLElement } | null>(null)
const useLoyalty = ref(false)
const loyaltySyncing = ref(false)
// Liga/desliga o resgate de pontos NA SESSÃO (fonte única). Carrinho e checkout
// passam a refletir o mesmo desconto, em vez de um flag de UI divergente.
watch(useLoyalty, async (enabled) => {
  if (loyaltySyncing.value) return
  try {
    await $fetch(apiPath('/api/v1/checkout/loyalty/'), {
      method: 'PATCH',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { enabled }
    })
    await refresh()
  } catch {
    // Falha não bloqueia; o commit ainda respeita o estado da sessão.
  }
})
const submitting = ref(false)
const confirmedTrackingUrl = ref('')
const confirmationUnknown = ref(false)
// "Não sabemos se o pedido entrou": enquanto a tela confere sozinha (U6), o envio
// fica travado; no teto da conferência, ele volta, e a copy diz isso.
const checkingOrder = ref(false)
let recoveryLoop: CheckoutRecoveryLoop | null = null
const UNCERTAIN_CHECKING = 'Estamos conferindo com o sistema se o pedido entrou. Não envie de novo: assim que soubermos, esta tela abre o acompanhamento.'
const UNCERTAIN_NOT_FOUND = 'Conferimos e o pedido não apareceu. Pode confirmar de novo: o mesmo pedido não entra duas vezes.'
const uncertainTitle = computed(() => checkingOrder.value ? 'Não sabemos ainda se o pedido entrou' : 'O pedido não apareceu')
const serverError = ref('')
const fieldErrors = ref<Record<string, string>>({})

function clearFieldError (key: string) {
  if (!fieldErrors.value[key]) return
  const { [key]: _removed, ...rest } = fieldErrors.value
  fieldErrors.value = rest
}

function clearFieldErrors (keys: string[]) {
  let next = fieldErrors.value
  let changed = false
  for (const key of keys) {
    if (!next[key]) continue
    const { [key]: _removed, ...rest } = next
    next = rest
    changed = true
  }
  if (changed) fieldErrors.value = next
}

// Dica de encomenda quando o dia escolhido está fechado (backend: preorder_hint).
// Aditivo: acompanha o erro do campo de data, não muda o roteamento do fieldError.
const deliveryDateHint = ref('')
// A data que a sacola moveu (#2411): o aviso do passo "Quando". A recusa "Sua sacola
// mudou" do envio relê o checkout, e a releitura pode mover a data: quando move, o
// aviso do dia novo já disse tudo, e o genérico não repete.
const dateMovedNotice = ref('')
let dateMovedNoticeShown = false
// O X fecha o aviso, e ele volta na próxima releitura do checkout enquanto a causa
// durar, isto é, enquanto ela não escolher uma data (regra do aviso de tela, #2095).
const dateMovedDismissed = ref(false)
const attemptKey = ref(createCheckoutAttemptKey())
const addressSelection = ref<AddressSelection | null>(null)
// Formulário do picker aberto com edição que o checkout ainda não recebeu
// (beta SMS-15): o "Continuar" espera a confirmação, em vez de seguir com o
// endereço antigo e perder a edição.
const addressDraftPending = ref(false)
const pickupSwapOffer = ref(false)
// Fora da área numa loja SEM retirada: `pickupSwapOffer` fica falso, o `v-else-if` da
// cobertura também, e nenhuma linha era renderizada — o cliente atravessava o resto do
// checkout e tomava o erro no commit. A recusa precisa de ramo próprio.
const deliveryUncovered = ref(false)
const zoneRefused = computed(() => deliveryZoneRefused({
  fulfillmentType: state.fulfillment_type,
  pickupSwapOffer: pickupSwapOffer.value,
  deliveryUncovered: deliveryUncovered.value,
  zoneError: cart.value?.delivery_zone_error
}))
// ⚠️ Aparece numa combinação só: pontos + entrega em endereço NOVO, em sessão que conhece o
// número e não as mãos (chegou por link de campanha). É a única rota que converteria o saldo
// de alguém em pão entregue em outro lugar. Endereço salvo e balcão nunca passam por aqui.
const identityConfirmOffer = ref(false)
const { confirm: confirmByWhatsApp, starting: confirming } = useWhatsAppConfirm(() => refresh())
const quotingZone = ref(false)
const draftSyncing = ref(false)
const deliveryDraftFailed = ref(false)
const checkoutTotalDisplay = computed(() => draftSyncing.value
  ? 'Atualizando total…'
  : deliveryDraftFailed.value ? 'Total a confirmar' : cart.value?.grand_total_display || 'R$ 0,00')
const changePhoneOpen = ref(false)
const confirmOpen = ref(false)
const receiptOpen = ref(false)
const datePopoverOpen = ref(false)
const notesOpen = ref(false)
// Desligar o toggle é o dismiss VISUAL, não a destruição do texto: a observação
// digitada vai para o rascunho interno e volta ao reabrir. Com o toggle fechado,
// `state.notes` fica vazio — observação dispensada nunca viaja oculta no payload.
const stashedNotes = ref('')
watch(notesOpen, (open) => {
  const next = notesToggleState(open, state.notes, stashedNotes.value)
  state.notes = next.notes
  stashedNotes.value = next.stashed
})
watch(() => state.name, value => {
  if (value.trim()) clearFieldError('name')
})
watch(() => state.phone, value => {
  if (value.trim()) clearFieldError('phone')
})
watch(() => state.payment_method, value => {
  if (value) clearFieldError('payment_method')
})

// CPF/CNPJ NA NOTA (decisão do dono, 13/10/2026, que substitui a de 24/09).
// Na ENTREGA o campo aparece no MESMO passo do endereço, opcional: sem
// documento a nota sai presencial, consumidor não identificado (a praxe do
// delivery). Na RETIRADA é o "CPF na nota?" do balcão: opcional, no passo do
// pagamento. O campo é um só (`fiscal_tax_id`) e
// já vem com o documento que a casa conhece (cadastro ou última entrega). A
// tela confere o que foi digitado, cedo e no campo; a trava do servidor
// continua sendo a da emissão.
const showTaxIdField = computed(() => state.fulfillment_type === 'delivery')
const showPickupTaxIdField = computed(() => state.fulfillment_type === 'pickup' && state.fiscal_tax_id_on_pickup)
const taxIdPrefillNote = computed(() => {
  const prefill = taxIdDigits(checkout.value?.prefill_tax_id)
  const typed = taxIdDigits(state.fiscal_tax_id)
  if (!prefill) return ''
  if (prefill === typed) {
    return checkout.value?.prefill_tax_id_source === 'last_delivery'
      ? 'O mesmo da sua última entrega. Se a nota for para outra pessoa, troque aqui.'
      : 'Do seu cadastro. Se a nota for para outra pessoa, troque aqui.'
  }
  // Diferente do cadastro: CPF não muda, então é a nota de outra pessoa. Vale
  // só aqui, e a tela diz que o cadastro não muda (no PDV a troca existe, com
  // atrito, porque há operador; aqui não é gesto de checkout).
  if (checkout.value?.prefill_tax_id_source === 'document' && isValidTaxId(typed)) {
    return 'Vale só para esta nota. O documento do seu cadastro continua o mesmo.'
  }
  return ''
})
// Guardar no cadastro é PERGUNTA, desmarcada, e só existe quando a pessoa é
// conhecida, o cadastro dela ainda não tem documento e há um documento certo
// indo para a nota.
const offerSaveTaxId = computed(() => !!checkout.value?.offer_save_tax_id && isValidTaxId(noteTaxId(state)))
const taxIdIssue = computed(() => taxIdError(state.fiscal_tax_id))
function onTaxIdInput (value: string | number) {
  state.fiscal_tax_id = formatTaxId(String(value ?? ''))
}
watch(() => state.fiscal_tax_id, value => {
  // O erro some quando o documento fecha certo; enquanto se digita, não se
  // acusa um CPF pela metade (ele só é "errado" quando o tamanho fecha).
  if (!fieldErrors.value.fiscal_tax_id) {
    if (taxIdLooksComplete(value) && taxIdIssue.value) {
      fieldErrors.value = { ...fieldErrors.value, fiscal_tax_id: taxIdIssue.value }
    }
    return
  }
  if (!taxIdIssue.value) clearFieldError('fiscal_tax_id')
  else if (taxIdLooksComplete(value)) fieldErrors.value = { ...fieldErrors.value, fiscal_tax_id: taxIdIssue.value }
})
watch(() => state.fulfillment_type, value => {
  if (value !== 'delivery' && !state.fiscal_tax_id_on_pickup) clearFieldError('fiscal_tax_id')
})
watch(() => state.fiscal_tax_id_on_pickup, on => {
  if (!on && state.fulfillment_type === 'pickup') clearFieldError('fiscal_tax_id')
})

// Presente (GIFT-UX). Em ENTREGA: destinatário + mensagem + sem preços no papel.
// Em RETIRADA: "embalar para presente" — só mensagem + sem preços no papel (o
// comprador leva; sem destinatário). Desligar descarta os dados do presente.
const isPickup = computed(() => state.fulfillment_type === 'pickup')
// Retirada: quando o pedido fica pronto, pela promessa das linhas (WP-L02, #2652).
const orderReadyNotice = computed(() => isPickup.value ? orderReadyLine(cart.value?.items) : '')
const giftTitle = computed(() => (isPickup.value ? 'Embalar para presente' : 'É para presente?'))
const notesCopy = computed(() => checkoutNotesCopy(isPickup.value))
const rememberDescription = computed(() => rememberChoicesDescription(isPickup.value))
const couponCard = computed(() => couponCardState(cart.value))
const giftDescription = computed(() => (isPickup.value
  ? 'Embalagem especial e um cartão com sua mensagem.'
  : 'Entregamos para outra pessoa, com um cartão com sua mensagem.'))
// "Sem preços no papel" esconde preço só nos papéis da casa (etiqueta, via e
// cartão; `backstage.services.order_documents._values_are_hidden`). A NFC-e
// sai sempre com os valores: na retirada ela fica com quem compra; na entrega
// a DANFE vai dentro da sacola. Com cobrança na porta, o valor a cobrar e o
// troco saem no papel do entregador. A cópia diz isso, e nada além disso.
const giftHideValuesDescription = computed(() => {
  if (isPickup.value) return 'A etiqueta e o cartão saem sem preços. A nota fiscal sai com os valores e fica com você.'
  const base = 'A etiqueta e o cartão saem sem preços. A nota fiscal vai junto com o pedido e mostra os valores.'
  return state.payment_method === 'cash' ? `${base} Pagando na entrega, o valor a cobrar aparece no papel.` : base
})
watch(() => state.is_gift, (on) => {
  if (on) state.gift_hide_values = true
  if (!on) {
    state.recipient_name = ''
    state.recipient_phone = ''
    state.gift_message = ''
    state.gift_hide_values = false
    clearFieldErrors(['recipient_name', 'recipient_phone'])
  }
// Na restauração, os campos do rascunho vêm depois do toggle. A escolha salva
// prevalece sobre o padrão aplicado ao gesto de ativar presente.
}, { flush: 'sync' })
watch(() => state.recipient_name, value => {
  if (value.trim()) clearFieldError('recipient_name')
})
watch(() => state.recipient_phone, value => {
  const local = normalizeAuthPhone(value, 'BR', defaultDdd.value).replace(/^\+55/, '')
  if (local.length >= 10) clearFieldError('recipient_phone')
})
// Resumo do presente para o passo de confirmação.
const giftSummary = computed(() => {
  if (!state.is_gift) return ''
  const parts: string[] = []
  if (isPickup.value) {
    parts.push('Embalar para presente')
  } else {
    parts.push(`Para ${state.recipient_name.trim() || 'quem recebe'}`)
    if (state.recipient_phone.trim()) parts.push(displayBrazilianPhone(state.recipient_phone, defaultDdd.value))
  }
  if (state.gift_hide_values) parts.push('valores ocultos')
  return parts.join(' · ')
})

// Subtítulo da opção de data = SEMPRE o dia da semana + data ("Segunda-feira, 15/06").
// A palavra relativa (Hoje/Amanhã/Próxima fornada) vive no TÍTULO — mesmo padrão p/ todas.
function dateOptionDescription (value: string): string {
  return weekdayDateLabel(value)
}

// Título da próxima data disponível: "Amanhã" quando ela for de fato o dia seguinte;
// senão "Próxima fornada" (ex.: sáb→seg pulando domingo, véspera de feriado/férias).
function nextDateTitle (value: string): string {
  return displayCheckoutDate(value, shopNow.value) === 'Amanhã' ? 'Amanhã' : 'Próxima fornada'
}

const checkoutQuery = computed(() => state.delivery_date ? { delivery_date: state.delivery_date } : {})

const { data, pending, error, refresh } = await useFetch<CheckoutResponse>(apiPath('/api/v1/storefront/checkout/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: checkoutQuery,
  lazy: true
})
usePageContentPending(pending)

// Uma leitura iniciada antes de uma mutação do rascunho pode terminar depois
// dela. Os demais campos da projection (datas/slots/copy) continuam úteis, mas
// a revisão da sacola nunca pode andar para trás: ela é a trava otimista usada
// no commit. Sem esta barreira, a resposta atrasada fazia o servidor recusar
// corretamente o pedido e obrigava o cliente a confirmar tudo outra vez.
const freshestCheckout = shallowRef<CheckoutResponse['checkout'] | null>(data.value?.checkout || null)
function cartRevision (value: CartProjection | null | undefined): number {
  return typeof value?.revision === 'number' ? value.revision : -1
}
watch(() => data.value?.checkout, (incoming) => {
  if (!incoming) return
  const current = freshestCheckout.value
  freshestCheckout.value = current && cartRevision(incoming.cart) < cartRevision(current.cart)
    ? { ...incoming, cart: current.cart }
    : incoming
}, { immediate: true })
function acceptCartProjection (incoming: CartProjection) {
  const current = freshestCheckout.value
  if (!current || cartRevision(incoming) < cartRevision(current.cart)) return
  freshestCheckout.value = { ...current, cart: incoming }
}

const checkout = computed(() => freshestCheckout.value)
// A sacola sumiu no servidor (#3267): a barreira acima, que só deixa a revisão andar para
// a frente, seguraria o item que saiu no resumo e no contador. Aqui a leitura nova é a
// verdade, vazia.
function acceptEmptiedCheckout () {
  if (data.value?.checkout) freshestCheckout.value = data.value.checkout
}

// O relógio do checkout é o da LOJA (`checkout.today`, escrito pelo servidor no fuso
// dela): "Hoje", "Amanhã", o piso da fornada e os limites do calendário saem daqui, e
// não do relógio do aparelho (plano EXCELENCIA-STOREFRONT, P2-08).
const shopNow = computed(() => checkoutNow(checkout.value))
const shopToday = computed(() => checkoutTodayValue(checkout.value))

// O checkout não envelhece: ao voltar para a aba, quando a rede volta, e numa cadência
// calma com a aba à vista, a tela refaz a consulta. O corte do dia, o fechamento da
// casa e o prazo da frase do dinheiro aparecem sem a cliente tocar em nada, em vez de
// só no envio. Não refaz no meio de um envio nem enquanto ela digita num campo.
const CHECKOUT_CALM_REFRESH_MS = 120_000
function isTyping (): boolean {
  const active = import.meta.client ? document.activeElement : null
  return !!active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')
}
async function refreshIfIdle () {
  if (submitting.value || isTyping()) return
  await refresh().catch(() => null)
  // O aviso da data que a sacola moveu, fechado com a causa de pé (ela ainda não
  // escolheu a data), volta nesta releitura (#2411; regra do aviso de tela, #2095).
  if (dateMovedNotice.value) dateMovedDismissed.value = false
}
useConnectivity().watchConnectivity(refreshIfIdle)
let calmRefreshTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  calmRefreshTimer = setInterval(() => {
    if (document.visibilityState === 'visible') void refreshIfIdle()
  }, CHECKOUT_CALM_REFRESH_MS)
})
onBeforeUnmount(() => {
  if (calmRefreshTimer) clearInterval(calmRefreshTimer)
})
const cart = computed(() => checkout.value?.cart)

// Cupom: aplica/remove via cart state (servidor) e re-busca o checkout p/ refletir
// o desconto no resumo (o `cart` daqui vem do payload do checkout, não do cart state).
const coupon = ref('')
const couponPending = ref(false)
const couponIssue = ref('')
// Cupom: mesmo toggle-card dos demais campos. Desligar limpa o código digitado.
const couponOpen = ref(false)
watch(couponOpen, (open) => {
  if (!open) {
    coupon.value = ''
    couponIssue.value = ''
    return
  }
  // Ao abrir o toggle, foca o campo do cupom (pós-render).
  void nextTick(() => { (document.getElementById('checkout-coupon-input') as HTMLInputElement | null)?.focus() })
})
watch(coupon, () => {
  if (couponIssue.value) couponIssue.value = ''
})
async function submitCoupon () {
  if (!coupon.value.trim() || couponPending.value) return
  couponPending.value = true
  couponIssue.value = ''
  try {
    await applyCoupon(coupon.value.trim())
    coupon.value = ''
    await refresh()
  } catch (e) {
    // Um aviso só: o erro mora embaixo do campo (aria-describedby). O toast
    // repetia a mesma frase em outro canto da tela (beta 06/11).
    couponIssue.value = errorDetail(e, 'Cupom inválido ou indisponível.')
  } finally {
    couponPending.value = false
  }
}
async function dropCoupon () {
  couponPending.value = true
  couponIssue.value = ''
  try {
    await removeCoupon()
    await refresh()
  } finally {
    couponPending.value = false
  }
}
// Toggle único do cupom: ON quando o campo está aberto OU já há cupom aplicado.
// Desligar = remover o cupom (se aplicado) ou só fechar o campo.
const couponSwitchOn = computed(() => couponOpen.value || !!cart.value?.coupon_code)
function onCouponToggle (on: boolean) {
  if (on) { couponOpen.value = true; return }
  if (cart.value?.coupon_code) void dropCoupon()
  else couponOpen.value = false
}
const action = computed(() => checkout.value?.actions.find(candidate => candidate.ref === 'checkout') || null)
const checkoutActionLabel = computed(() => action.value?.label || 'Confirmar pedido')
// Sacola vazia é um beco sem saída se o CTA só fica desabilitado — omotenashi
// pede um caminho de volta. Neste estado o botão vira "Adicionar itens" (ativo,
// leva ao cardápio) em vez de "Revisar pedido" morto + "Sacola vazia.".
const bagIsEmpty = computed(() => !!cart.value?.is_empty)
// A recusa "sua sacola ficou vazia" (#3267) diz a frase e dá a saída no aviso de página.
// Enquanto ele está à vista, a etapa e a barra do total não repetem a frase nem oferecem
// uma segunda saída igual; fechado o aviso, a sacola vazia volta ao de sempre.
const bagGoneNoticeShowing = computed(() =>
  bagIsEmpty.value
  && pageNotice.value?.path === route.path
  && pageNotice.value?.tone === 'attention'
  && pageNotice.value?.action?.to === '/menu'
)
const authAction = computed(() => checkout.value?.auth_action || null)
const authRoute = computed(() => authAction.value?.href || '/entrar?next=/finalizar')
const availableFulfillment = computed(() => availableFulfillmentOptions(checkout.value))
// Upsell de frete grátis: só faz sentido em entrega e enquanto a taxa não zerou.
const freeDeliveryUpsell = computed(() =>
  state.fulfillment_type === 'delivery' && !cart.value?.delivery_is_free
    ? cart.value?.free_delivery_progress || null
    : null
)
// Mínimo de entrega é FLAT por canal e o Core já preenche `delivery_minimum_progress`
// no cart assim que o subtotal está abaixo dele — independente de endereço. Então a loja
// barra a entrega CEDO (no passo de recebimento, quando "Entrega" é escolhida), em vez de
// deixar o cliente atravessar o checkout e só tomar o erro no commit.
const deliveryBelowMinimum = computed(() =>
  state.fulfillment_type === 'delivery' && !!cart.value?.delivery_minimum_progress
)
const savedAddresses = computed(() => checkout.value?.saved_addresses || [])
const paymentMethods = computed(() => checkout.value?.payment_methods || [])
const pixProviderTest = computed(() => pixProviderTestConstraint(checkout.value?.payment_constraints))
// Recusa `pix_test_amount_limit` do servidor: ele mede o total AUTORITATIVO, que
// pode ter mudado desde que a tela carregou. Vale enquanto o total da tela for o
// que o servidor recusou; a sacola mudou, quem decide volta a ser a conta local.
const pixLimitRefusal = ref<{ message: string, totalQ: number } | null>(null)
// Faltou estoque no envio (`insufficient_supply`): o servidor diz qual item, e a tela
// guarda isso para o aviso com saída (plano EXCELENCIA-STOREFRONT, P1-11). Com a folha
// de alternativas pronta (`stock_issue`, #2687), a saída abre na própria tela: o que
// ainda dá para levar, o que serve no lugar, o aviso de volta. `lineId` e `qty` dizem
// qual linha passou do teto e quanto ela pedia: quando a linha muda, o aviso some.
interface StockRefusal {
  sku: string
  name: string
  message: string
  issue: Record<string, unknown> | null
  lineId: string | null
  qty: number | null
}
const stockRefusal = ref<StockRefusal | null>(null)
function openStockAlternatives () {
  const issue = stockRefusal.value?.issue
  if (!issue) return
  // A folha devolve o foco a quem o tinha quando ela abriu. Aberta sozinha (a revisão
  // acabou de fechar), o foco ainda não estava em lugar nenhum: o "Agora não" mandava a
  // cliente para o começo da página. O foco vai ao botão do aviso ANTES de a folha abrir,
  // e é para ele que ela volta, sempre.
  document.querySelector<HTMLElement>('[data-checkout-stock-alternatives]')?.focus({ preventScroll: true })
  raiseStockIssue(issue)
}
// A folha mexeu na sacola (levou o que dá, trocou, tirou): o checkout relê a sacola
// dele, e o aviso sai quando a linha recusada já não pede o que pedia.
watch(() => cart.value?.items, (items) => {
  const refusal = stockRefusal.value
  if (!refusal?.lineId || !items) return
  const line = items.find(item => item.line_id === refusal.lineId)
  if (!line || line.qty !== refusal.qty) stockRefusal.value = null
})
watch(() => liveCart.value.revision, (next, prev) => {
  if (!stockRefusal.value?.lineId || next == null || next === prev) return
  if (next !== cart.value?.revision) void refresh()
})
function revealStockRefusal () {
  // O alvo é a moldura (régua canônica + respiro), não o aviso: o aviso sozinho
  // não tem margem de rolagem e pararia debaixo do cabeçalho. Com a folha de
  // alternativas a caminho, a tela só rola: o foco já foi para o botão do aviso
  // (`openStockAlternatives`), e mexer nele com a folha aberta disputaria o foco dela.
  reveal(() => document.querySelector('[data-focus-target="stock-refusal"]'), { align: 'start', focus: !stockRefusal.value?.issue })
}
// A folha de revisão, ao terminar de fechar, devolve o foco ao botão que a abriu
// ("Revisar pedido"), e o navegador rola até ele. Quando ela fecha por causa de uma
// recusa com aviso, o foco é do aviso: a devolução é cancelada e a tela vai até ele.
// O fim do fechamento pode chegar antes ou depois de a consulta refeita terminar; a
// marca vale para as duas ordens e cai quando a revisão abre de novo.
let reviewClosesIntoStockRefusal = false
// A revisão abre do começo. Sem isto o foco inicial ia para o primeiro elemento
// focável do corpo, o link dos Termos, que agora fica no fim do card "Antes de
// enviar": a folha abria já rolada e escondia o primeiro item. O foco vai para a
// própria folha (o leitor de tela começa pelo título), sem rolar nada.
function onReviewOpened (event: Event) {
  event.preventDefault()
  ;(event.target as HTMLElement | null)?.focus?.({ preventScroll: true })
}
function onReviewClosed (event: Event) {
  if (!reviewClosesIntoStockRefusal) return
  reviewClosesIntoStockRefusal = false
  event.preventDefault()
  revealStockRefusal()
  // A folha de alternativas sobe depois que a revisão fechou: duas folhas ao mesmo
  // tempo disputariam o foco. Ao fechar, ela devolve o foco ao botão do aviso.
  openStockAlternatives()
}
const pixLimitRefusalActive = computed(() =>
  !!pixLimitRefusal.value && state.payment_method === 'pix' &&
  (cart.value?.grand_total_q == null || cart.value.grand_total_q === pixLimitRefusal.value.totalQ)
)
const pixProviderTestSelected = computed(() =>
  state.payment_method === 'pix' && (!!pixProviderTest.value || pixLimitRefusalActive.value)
)
const pixProviderTestExceeded = computed(() =>
  pixProviderTestSelected.value &&
  (pixLimitRefusalActive.value || exceedsPaymentConstraint(cart.value?.grand_total_q, pixProviderTest.value))
)
const pixProviderTestLimitDisplay = computed(() => pixProviderTest.value?.max_amount_display || 'R$ 10,00')
const pixProviderTestMessage = computed(() => {
  if (pixLimitRefusalActive.value && pixLimitRefusal.value?.message) return pixLimitRefusal.value.message
  // Dentro do limite a frase não pode mandar trocar nada: seria instrução que o
  // pedido não precisa seguir, ao lado de "está dentro do limite".
  if (!pixProviderTestExceeded.value) {
    return `Ambiente de testes: a Efí simula a confirmação de Pix de até ${pixProviderTestLimitDisplay.value}.`
  }
  return pixProviderTest.value?.message || (
    `Ambiente de testes: a Efí simula a confirmação de Pix de até ${pixProviderTestLimitDisplay.value}. ` +
    'Para continuar, troque a forma de pagamento ou ajuste os itens do pedido.'
  )
})
const submitDisabled = computed(() =>
  !action.value?.enabled || !!cart.value?.is_empty || submitting.value || checkingOrder.value || pixProviderTestExceeded.value || draftSyncing.value || deliveryDraftFailed.value
)
// Retirada e entrega leem a grade da casa (a mesma da concierge e do PDV): meia
// hora hoje, turno na encomenda. O resto da tela trata as duas do mesmo jeito.
const slots = computed(() => checkoutWindows(checkout.value, state.fulfillment_type))
const isDeliveryWindows = computed(() => state.fulfillment_type === 'delivery')
// Meias horas viram uma grade compacta de células iguais; turnos, uma lista.
const isWindowGrid = computed(() => usesWindowGrid(checkout.value, state.fulfillment_type))
// O motivo da janela apagada é um só (o item que segura o pedido): sai uma vez
// acima dos horários, não repetido em cada um.
const windowsReason = computed(() => checkoutWindowsReason(slots.value))
const selectedSlot = computed(() => selectedPickupSlot(slots.value, state.delivery_time_slot))
const paymentMethodLabel = computed(() => resolvePaymentMethodLabel(checkout.value, state.payment_method))
const selectedSlotLabel = computed(() => selectedSlot.value?.label || state.delivery_time_slot || '')
const fulfillmentLabel = computed(() => resolveFulfillmentLabel(state.fulfillment_type))
const fulfillmentIcon = computed(() => resolveFulfillmentIcon(state.fulfillment_type))
const selectedDateLabel = computed(() => displayCheckoutDate(state.delivery_date, shopNow.value, true))
// A frase do dinheiro da forma de pagamento escolhida ('' quando o servidor não tem
// prazo a prometer).
const moneyNotice = computed(() =>
  checkout.value?.money_notices?.find(notice => notice.method === state.payment_method)?.text || ''
)
const whenSummary = computed(() => buildWhenSummary(state.delivery_date, selectedSlotLabel.value, shopNow.value))
const fulfillmentSummary = computed(() => buildFulfillmentSummary(fulfillmentLabel.value, whenSummary.value))
// Lista de espera na revisão: só quando alguma linha realmente disputa a
// fornada do dia ESCOLHIDO (pedido agendado para outra data não tem fila).
// "Itens em lista de espera: avisamos quando ficarem prontos." só quando alguma linha em
// espera NÃO tem a promessa com dia e hora. Com a promessa ("Fica pronto amanhã, sexta, a
// partir das 15h"), a linha já diz quando: as duas juntas eram duas promessas para o
// mesmo item.
const hasReviewWaitlist = computed(() =>
  (cart.value?.items || []).some(line =>
    reviewWaitlist(line, state.delivery_date, shopToday.value) && !cartLinePromise(line.promise)
  )
)
const phoneDisplay = computed(() => displayBrazilianPhone(state.phone || checkout.value?.customer_phone || '', defaultDdd.value))
const contactComplete = computed(() => buildContactComplete(state, phoneDisplay.value))
// O campo Nome aparece por ESTADO explícito, nunca por conteúdo.
//
// A forma antiga era `nameEditing.value || !state.name.trim()`: para quem chega
// sem nome, o input abria porque o campo estava vazio, e na PRIMEIRA tecla o
// `v-model` gravava "T", o `!state.name.trim()` virava false e o `v-if`
// desmontava o input no meio da digitação. O cartão colapsava para a linha de
// leitura mostrando só "T", marcado "Feito", sem erro e sem requisição — e no
// banco `first_name`/`last_name` ficavam vazios. Não era corrida (reproduzido
// com 40 ms, 150 ms e 400 ms entre teclas): era o próprio desenho, a condição de
// exibição lendo o conteúdo do campo que ela exibe.
//
// Agora `nameEditing` é a única fonte: entra em edição por ação deliberada
// (`startEditName`) ou pela abertura automática na hidratação quando ainda não
// há nome, e só SAI em `saveContact()`, que valida antes. Digitar não pode mais
// fechar o campo, porque digitar não mexe em `nameEditing`.
const showNameInput = computed(() => nameEditing.value)
const nameBeforeEdit = ref('')
// Cancelar só faz sentido quando há um nome anterior para restaurar. Para quem
// nunca teve nome, "cancelar" fecharia o campo deixando o cadastro vazio, que é
// exatamente o estado que este conserto existe para impedir.
const canCancelNameEdit = computed(() => !!nameBeforeEdit.value.trim())
async function startEditName () {
  nameBeforeEdit.value = state.name
  nameEditing.value = true
  await nextTick()
  const el = nameInput.value?.$el
  if (el?.tagName === 'INPUT') el.focus()
  else el?.querySelector?.('input')?.focus?.()
}
function cancelEditName () {
  if (!canCancelNameEdit.value) return
  state.name = nameBeforeEdit.value
  nameEditing.value = false
}
const contactSummary = computed(() => buildContactSummary(state, phoneDisplay.value))
// No card colapsado, nome e telefone em linhas próprias (telefone na 3ª linha
// por padrão) — fica legível sem depender de caber tudo numa linha só.
const contactCardSummary = computed(() => [state.name, phoneDisplay.value].filter(Boolean).join('\n'))
const addressSummary = computed(() => buildAddressSummary(state))
// Endereço quebrado em linhas (mesmo padrão do rodapé) — leitura bonita na revisão.
const deliveryAddressLines = computed(() => addressLines(state.delivery_address))
const confirmSheetDescription = computed(() => buildConfirmSheetDescription(checkout.value))
// Um pedido, uma data: a sacola que espera uma fornada de outro dia não vira
// pedido de antes dela. O piso entra nos limites (calendário, caixas, "Continuar").
const batchFloor = computed(() => cartBatchFloor(checkout.value?.cart?.items || [], shopToday.value))
const dateBounds = computed(() => checkoutDateBounds(checkout.value, shopNow.value, batchFloor.value?.date || ''))
const batchFloorNotice = computed(() => cartBatchFloorReason(batchFloor.value, state.fulfillment_type, shopToday.value))
const checkoutMinDate = computed(() => dateBounds.value.minDate)
const checkoutMaxDate = computed(() => dateBounds.value.maxDate)
const closedDateEntries = computed(() => parseClosedDateEntries(checkout.value?.closed_dates_json))
const closedWeekdays = computed(() => checkout.value?.closed_weekdays || [])
const datepickerDisabledDates = computed(() => buildDatepickerDisabledDates(
  closedDateEntries.value, closedWeekdays.value,
  checkout.value?.today_over ? dateBounds.value.todayValue : ''
))
// Opções de data: "Hoje" (se aberto) + "Próxima fornada" (a próxima data em
// que a loja opera) + "Outra data" (calendário). Vêm do backend, que nunca
// devolve dia fechado. Fallback local só se a projection não trouxer nada.
const quickDateOptions = computed(() => {
  const available = checkout.value?.available_dates || []
  if (!available.length) {
    return quickCheckoutDateOptions(dateBounds.value, closedDateEntries.value, closedWeekdays.value)
      .map(option => ({ value: option.value, title: option.label, disabled: option.disabled }))
  }
  return checkoutDateChoices(available, dateBounds.value, nextDateTitle)
})
const isCustomDate = computed(() => isCustomCheckoutDate(state.delivery_date, quickDateOptions.value))
// "Hoje" fora das opções porque o dia já encerrou: a tela diz, em vez de sumir calado.
const todayOverNotice = computed(() => (checkout.value?.today_over ? todayOverMessage(state.fulfillment_type) : ''))
const isTodaySelected = computed(() => state.delivery_date === dateBounds.value.todayValue)
// Toda retirada paga (na loja online, toda retirada: o canal só aceita Pix e cartão,
// pagos no envio): a revisão diz a regra do pedido não retirado antes de a cliente
// enviar. Vale para hoje também, porque o corte do pedido pago é o fim do expediente
// do dia combinado, seja ele qual for (#2613; coordenação, 22/11/2026).
const showUnclaimedOrderRule = computed(() => isPickup.value && Boolean(state.delivery_date))
const contactState = computed<CheckoutSectionState>(() => {
  if (fieldErrors.value.name || fieldErrors.value.phone) return 'error'
  // `nameEditing` entra aqui junto com `contactEditing`, e esta é a METADE
  // decisiva do conserto do campo Nome. A seção só fica expandida em 'current';
  // com o telefone já preenchido pelo servidor, a PRIMEIRA letra do nome fazia
  // `contactComplete` virar true, a etapa virava 'done' e a seção inteira
  // colapsava — levando o input embora no meio da digitação, com o cartão
  // exibindo "T" e o selo "Feito". Enquanto alguém está digitando o nome, a
  // etapa é a etapa ATUAL; quem a declara terminada é o `saveContact()`.
  if (contactEditing.value || nameEditing.value || !contactComplete.value) return 'current'
  return 'done'
})
const canContinueWhen = computed(() => {
  return canContinueCheckoutWhen(state, slots.value, selectedSlot.value, dateBounds.value, closedDateEntries.value, closedWeekdays.value)
})

const steps = computed<Step[]>(() => checkoutSteps(state.fulfillment_type))
const stepLabels = checkoutStepLabels
const stepIcons = checkoutStepIcons

// Foco da página: a seção em que o cliente trabalha AGORA. Cada seção se marca
// com `data-focus-target`; quando o foco muda (etapa concluída, "Editar",
// erro), o mecanismo leva a página até ela — sempre na mesma linha, sob a
// navbar.
//
// `nameEditing` entra aqui, e não é detalhe: com o campo de nome aberto, a
// próxima ação é salvá-lo. Sem ele na conta, o card oferecia "Continuar" para
// quem ainda não tinha nome preenchido, e o cadastro só reclamava lá na
// revisão. As duas portas que abrem o campo são deliberadas — a hidratação de
// quem chega sem nome, e o "Editar" —, então o foco ir para lá não atropela
// ninguém no meio do caminho.
const focusKey = computed<string>(() => (
  contactEditing.value || nameEditing.value || contactState.value === 'error' ? 'contact' : activeStep.value
))
// Checkout é um fluxo guiado: na chegada, a tarefa atual ocupa a régua mesmo
// que já caiba parcialmente na tela. Para o cliente identificado isso leva
// "Como receber" ao fio dourado e deixa o cabeçalho, já lido, rolar para cima.
const { reveal } = useNextFocus(focusKey, { initialReveal: 'always' })

// A AÇÃO SEGUE O FOCO. A etapa em que o cliente trabalha decide qual é o único
// botão que avança, e ele mora no card suspenso, nunca no fim da seção.
//
// Medido num iPhone SE (375x667) na etapa de pagamento: o "Revisar pedido"
// ficava a 883px do topo, 216px ABAIXO da dobra. O botão que conclui o pedido
// só existia para quem rolava atrás dele.
//
// UM botão, UM lugar: duplicar o CTA no fluxo e no card criaria dois estados
// para a mesma intenção, e eles divergem no primeiro estado de carregamento.
// Por isso os rodapés das seções deixaram de ter botão.
//
// `reason` nunca é decorativo: botão desabilitado no lugar mais nobre da tela
// tem que dizer o que falta (a sacola vazia já fazia isso, virando "Adicionar
// itens" em vez de um "Revisar pedido" morto).
// Navegação também pende: em rede lenta o pedaço da rota demora, e o toque precisa
// de resposta enquanto isso (clique nunca inerte).
const { run: goToMenu, pending: goingToMenu } = usePendingAction(async () => { await navigateTo('/menu') })
const { run: adjustCartForPix, pending: adjustingCartForPix } = usePendingAction(async () => { await navigateTo('/sacola') })

interface CheckoutPrimaryAction {
  label: string
  icon: string
  loading: boolean
  disabled: boolean
  reason: string
  run: () => void
}

const primaryAction = computed<CheckoutPrimaryAction>(() => {
  if (focusKey.value === 'contact') {
    return { label: 'Salvar contato', icon: 'lucide:check', loading: false, disabled: false, reason: '', run: saveContact }
  }
  if (focusKey.value === 'fulfillment') {
    return {
      label: 'Continuar',
      icon: 'lucide:arrow-right',
      loading: draftSyncing.value,
      disabled: deliveryBelowMinimum.value || draftSyncing.value,
      reason: deliveryBelowMinimum.value && cart.value?.delivery_minimum_progress
        ? `Faltam ${cart.value.delivery_minimum_progress.remaining_display} para o mínimo de entrega`
        : deliveryDraftFailed.value ? 'Toque em Continuar para atualizar o total.' : '',
      run: continueFromFulfillment
    }
  }
  if (focusKey.value === 'address') {
    return {
      label: 'Continuar',
      icon: 'lucide:arrow-right',
      loading: draftSyncing.value,
      disabled: draftSyncing.value || !addressSelection.value || zoneRefused.value || addressDraftPending.value,
      reason: !addressSelection.value
        ? 'Escolha ou informe o endereço de entrega.'
        : addressDraftPending.value
          ? 'Confirme o endereço que você está editando.'
          : zoneRefused.value
          ? 'Ainda não entregamos nesse endereço.'
          : '',
      run: continueFromAddress
    }
  }
  if (focusKey.value === 'when') {
    return {
      label: 'Continuar',
      icon: 'lucide:arrow-right',
      loading: false,
      disabled: !canContinueWhen.value,
      reason: canContinueWhen.value ? '' : 'Escolha a data e o horário.',
      run: continueFromWhen
    }
  }
  // Sacola vazia é beco sem saída se o botão só ficar apagado: vira o caminho
  // de volta ao cardápio, ativo.
  if (bagIsEmpty.value) {
    return { label: 'Adicionar itens', icon: 'lucide:utensils', loading: goingToMenu.value, disabled: false, reason: 'Sacola vazia.', run: goToMenu }
  }
  return {
    label: 'Revisar pedido',
    icon: 'lucide:clipboard-check',
    loading: submitting.value,
    disabled: submitDisabled.value,
    reason: pixProviderTestExceeded.value
      ? `Pix vai até ${pixProviderTestLimitDisplay.value} no período de testes. Troque a forma de pagamento ou ajuste os itens.`
      : submitDisabled.value ? (action.value?.reason || '') : '',
    run: continueFromPayment
  }
})

// Rascunho do checkout: sair do navegador e voltar (ou o iOS recarregar a aba por
// memória) NÃO pode perder o que já foi preenchido. Usa localStorage (sobrevive à aba
// ser morta/recarregada — sessionStorage é apagado nesses casos). O parse/validação
// vive em utils/checkoutDraft (puro, testado); o save só liga após restaurar, pra não
// sobrescrever o rascunho antigo com os defaults desta carga. Validade 6h.
let draftRestored = false
let hasRestoredCheckoutDraft = false
function clearCheckoutDraft () {
  if (import.meta.client) removeCheckoutDraft()
}
// O rascunho mora no localStorage, que o servidor não vê. Aplicá-lo durante a
// hidratação fazia o primeiro render do cliente divergir do HTML do servidor
// ("Hydration completed but contains mismatches", beta SMS-22). Na carga direta
// ele entra depois de montar; em navegação cliente a projeção é lazy e esperamos
// o draft_context verdadeiro antes de validar o rascunho.
// O AddressPicker lê a seleção só ao montar: a chave o remonta com a seleção
// restaurada, em vez de deixar o rádio no endereço pré-selecionado.
const addressPickerKey = ref(0)
function restoreCheckoutDraft () {
  if (!import.meta.client || draftRestored) return
  if (!checkout.value) return
  const draftContext = cart.value?.draft_context || ''
  try {
    const { draft, stale } = parseCheckoutDraft(localStorage.getItem(CHECKOUT_DRAFT_KEY), Date.now(), draftContext)
    if (draft) {
      hasRestoredCheckoutDraft = true
      Object.assign(state, draft.state)
      if (draft.attemptKey) attemptKey.value = draft.attemptKey
      if (draft.activeStep) activeStep.value = draft.activeStep
      // A seleção de endereço restaurada alimenta o AddressPicker (prop
      // `selection`): salvo re-marca o rádio; novo reabre o form preenchido.
      // Sem ela, o preselect do picker SOBRESCREVIA o endereço do rascunho.
      if (draft.addressSelection) {
        addressSelection.value = draft.addressSelection
        addressPickerKey.value += 1
      }
      // Observação restaurada reabre o toggle — texto nunca viaja escondido.
      if (draft.notesOpen) notesOpen.value = true
    } else if (stale) {
      clearCheckoutDraft()
    }
  } catch { /* rascunho corrompido: ignora */ }
  draftRestored = true
}
if (import.meta.client && useNuxtApp().isHydrating) {
  onMounted(() => { watch(checkout, restoreCheckoutDraft, { immediate: true }) })
} else {
  watch(checkout, restoreCheckoutDraft, { immediate: true })
}
function saveCheckoutDraft () {
  if (!import.meta.client || !draftRestored) return
  try {
    localStorage.setItem(CHECKOUT_DRAFT_KEY, JSON.stringify({
      version: 2,
      context: cart.value?.draft_context || '',
      attemptKey: attemptKey.value,
      // Documento não fica guardado no aparelho: o CPF sai do rascunho.
      state: { ...state, fiscal_tax_id: '', fiscal_tax_id_on_pickup: false, save_fiscal_tax_id: false },
      activeStep: activeStep.value,
      addressSelection: addressSelection.value,
      savedAt: Date.now()
    }))
  } catch { /* quota/serialização: ignora */ }
}
watch([state, activeStep, addressSelection, attemptKey], saveCheckoutDraft, { deep: true })

function pickDeliveryDate (value: string) {
  if (isCheckoutDateUnavailable(value, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) return
  const date = parseLocalDate(value)
  if (!date) return
  chosenDate.value = date
  state.delivery_date = value
  clearFieldError('delivery_date')
  deliveryDateHint.value = ''
  dateMovedNotice.value = ''
  datePopoverOpen.value = false
}

function reconcileDeliverySlot () {
  const nextSlotRef = reconciledWindowRef(
    state.delivery_time_slot,
    slots.value,
    earliestCheckoutWindowRef(checkout.value, state.fulfillment_type)
  )
  if (nextSlotRef !== state.delivery_time_slot) state.delivery_time_slot = nextSlotRef
}

// Só na 1ª hidratação ajustamos o tipo de entrega ao que o servidor oferece. Em
// refreshes seguintes (cupom, fidelidade, mudança de data/slot) a escolha do usuário é
// SAGRADA — resetá-la mudava `steps` e fazia o `activeStep` "voltar sozinho" (fantasma).
let checkoutHydrated = false
watch(() => checkout.value, value => {
  if (!value) return
  const fulfillments = availableFulfillmentOptions(value)
  const methods = value.payment_methods || []

  setFromServer(value.cart)
  // Fidelidade: a sessão é a fonte única. Espelha o estado aplicado no cart
  // (sem disparar o watcher que reescreveria a sessão).
  loyaltySyncing.value = true
  useLoyalty.value = !!value.cart?.loyalty_applied
  nextTick(() => { loyaltySyncing.value = false })
  if (!state.name) state.name = value.customer_name || ''
  // Telefone do cliente AUTENTICADO é identidade: o servidor é a fonte de verdade
  // e sobrepõe qualquer rascunho local. Sem isso, um número antigo no localStorage
  // (ex.: cadastro trocado) grudava para sempre — era o bug do "(55)" persistido.
  // Convidado mantém o que digitou (só preenche se vazio).
  if (value.is_authenticated && value.customer_phone) {
    state.phone = value.customer_phone
  } else if (!state.phone) {
    state.phone = value.customer_phone || ''
  }
  if (!methods.some(method => method.ref === state.payment_method)) {
    state.payment_method = value.default_payment_method || methods[0]?.ref || ''
  }
  // O CPF que a casa já conhece (cadastro ou última entrega) vem na nota da
  // entrega e vale; a pessoa troca aqui para a nota sair no documento de outra
  // pessoa. Nunca sobre o que já digitou.
  if (!state.fiscal_tax_id && value.prefill_tax_id) state.fiscal_tax_id = formatTaxId(value.prefill_tax_id)
  if (!checkoutHydrated && !hasRestoredCheckoutDraft) {
    state.fulfillment_type = fulfillments.includes(value.default_fulfillment_type)
      ? value.default_fulfillment_type
      : fulfillments[0] || 'pickup'
  } else if (!checkoutHydrated && !fulfillments.includes(state.fulfillment_type)) {
    state.fulfillment_type = fulfillments[0] || 'pickup'
  }
  // Quem chega sem nome já encontra o campo aberto — mas por decisão tomada
  // AQUI, uma única vez na hidratação, e não por uma condição que volta a ser
  // avaliada a cada tecla. Só na 1ª: em refreshes seguintes (cupom, fidelidade,
  // data) a edição em curso é do cliente, e reabrir seria pisar nela.
  if (!checkoutHydrated && !state.name.trim()) nameEditing.value = true
  checkoutHydrated = true
  reconcileDeliverySlot()
}, { immediate: true })

// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// B (OC-33 B1): a cliente já escolheu o dia no cardápio e a sacola é desse dia
// (`cart.day`, o dia em que ela reserva). O checkout abre nele, uma vez, sem
// perguntar de novo (WCAG 3.3.7); trocar a data aqui continua possível.
const { is: checkoutExperienceIs } = useExperience('cardapio-dia-primeiro')
// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
let menuDayApplied = false

// Pré-seleciona a primeira data REALMENTE disponível só depois que a projection
// existe. Na navegação cliente o fetch é lazy; usar o relógio local enquanto ele
// ainda está pendente escolheria "hoje" mesmo num dia fechado e deixaria todos
// os horários desabilitados. O watch cobre essa chegada tardia sem segurar a rota.
function initializeDeliveryDate () {
  if (!checkout.value) return
  // EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
  const menuDay = checkoutExperienceIs('b') && !menuDayApplied ? (checkout.value.cart?.day?.date || '') : ''
  // EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
  if (menuDay && !isCheckoutDateUnavailable(menuDay, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) {
    menuDayApplied = true
    const parsedMenuDay = parseLocalDate(menuDay)
    if (parsedMenuDay) {
      chosenDate.value = parsedMenuDay
      state.delivery_date = menuDay
      return
    }
  }
  const restoredDate = state.delivery_date
  const restoredUsable = !!restoredDate && !isCheckoutDateUnavailable(restoredDate, dateBounds.value, closedDateEntries.value, closedWeekdays.value)
  // Já escolhida e ainda válida: a escolha é do cliente. Inválida (a sacola
  // passou a esperar uma fornada depois dela) volta para o piso.
  if (chosenDate.value && restoredUsable) return
  // Hoje já encerrado (`today_over`) não volta como data lembrada: o cliente
  // cairia numa lista de horários vazia em vez de no próximo dia.
  const restoredIsOver = !!checkout.value.today_over && restoredDate === dateBounds.value.todayValue
  const value = initialCheckoutDate(
    restoredDate,
    restoredUsable && !restoredIsOver,
    checkout.value.available_dates || [],
    dateBounds.value,
    shopToday.value
  )
  const parsed = parseLocalDate(value)
  if (!parsed) return
  chosenDate.value = parsed
  state.delivery_date = value
  // A sacola levou a data para depois da que ela tinha (#2411): a tela diz o dia
  // novo, em vez de trocar calada. Vale para a volta à aba e para a recusa do envio.
  // O aviso mora no passo "Quando" e fica até ela escolher uma data; quem já tinha
  // passado do "Quando" volta a ele (um toast sumiria sob a barra de baixo).
  const moved = orderDateMovedNotice(restoredDate, value, dateBounds.value, shopNow.value)
  if (moved) {
    dateMovedNotice.value = moved
    dateMovedDismissed.value = false
    dateMovedNoticeShown = true
    const order = steps.value
    if (order.indexOf(activeStep.value) > order.indexOf('when')) goToStep('when')
  }
}
onMounted(initializeDeliveryDate)
watch(checkout, initializeDeliveryDate, { flush: 'post' })

// O AddressPicker é o dono do passo de endereço: a seleção dele (salvo ou
// novo) é a única fonte do que vai no payload do checkout. Flush síncrono:
// o picker emite a seleção e o "confirmed" na mesma chamada — a validação
// do avanço lê o state imediatamente.
watch(addressSelection, selection => {
  state.saved_address_id = selection?.savedAddressId ?? null
  state.delivery_address = selection?.formattedAddress || ''
  state.delivery_address_structured = selection?.structured || {}
  state.delivery_complement = selection?.complement || ''
  state.delivery_instructions = selection?.deliveryInstructions || ''
  if (selection && fieldErrors.value.delivery_address) {
    const errors = { ...fieldErrors.value }
    delete errors.delivery_address
    fieldErrors.value = errors
  }
  // Antecipação de zona: assim que há um endereço de entrega estruturado,
  // grava o rascunho na sessão (o Core calcula a taxa) e refaz o total. A
  // oferta de retirada some até a checagem responder.
  pickupSwapOffer.value = false
  deliveryUncovered.value = false
  identityConfirmOffer.value = false
  if (state.fulfillment_type === 'delivery' && selection?.structured?.route) {
    void applyDeliveryDraft()
  }
}, { flush: 'sync' })

// Grava o recebimento + endereço na sessão e re-resolve o cart, para que a
// TAXA já entre no total (e a cobertura de zona seja conhecida) antes do
// commit — fonte única (Core), sem matemática no cliente. A DeliveryZoneRule
// segue como gate autoritativo no commit.
let draftSyncTail: Promise<void> = Promise.resolve()
let draftSyncCount = 0
let deliverySyncCount = 0
let draftSyncVersion = 0

function applyDeliveryDraft (): Promise<void> {
  const version = ++draftSyncVersion
  const isDelivery = state.fulfillment_type === 'delivery'
  const fulfillmentType = state.fulfillment_type
  const structured = { ...(state.delivery_address_structured || {}) }
  if (isDelivery && !structured.route) return draftSyncTail

  draftSyncCount += 1
  if (isDelivery) deliverySyncCount += 1
  draftSyncing.value = true
  quotingZone.value = deliverySyncCount > 0

  const run = async () => {
    try {
      if (version !== draftSyncVersion || fulfillmentType !== state.fulfillment_type) return
      const response = await $fetch<CartResponse>(apiPath('/api/v1/checkout/draft/'), {
        method: 'PATCH',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: {
          fulfillment_type: fulfillmentType,
          delivery_address_structured: isDelivery ? structured : {}
        }
      })
      if (version !== draftSyncVersion || fulfillmentType !== state.fulfillment_type) return
      // O PATCH devolve a revisão que acabou de gravar. Aceitá-la antes do
      // refresh fecha a janela em que um GET anterior poderia reintroduzir a
      // revisão velha; o refresh atualiza o restante da projection.
      acceptCartProjection(response.cart)
      await refresh()
      deliveryDraftFailed.value = false
      if (isDelivery) {
        const covered = !cart.value?.delivery_zone_error && cart.value?.delivery_fee_q !== null
        if (structured.coordinates_source) {
          telemetry.addressEvent('address.zone.resolved', { result: covered ? 'covered' : 'outside' })
        }
        pickupSwapOffer.value = covered ? false : availableFulfillment.value.includes('pickup')
        deliveryUncovered.value = !covered && !pickupSwapOffer.value
        if (covered) serverError.value = ''
      }
    } catch {
      // Uma escolha nova não pode continuar exibindo a conta da anterior.
      if (version === draftSyncVersion && fulfillmentType === state.fulfillment_type) deliveryDraftFailed.value = true
      if (isDelivery) {
        if (structured.coordinates_source) {
          telemetry.addressEvent('address.zone.resolved', { result: 'deferred' })
        }
        pickupSwapOffer.value = false
        deliveryUncovered.value = false
      }
    } finally {
      draftSyncCount -= 1
      if (isDelivery) deliverySyncCount -= 1
      draftSyncing.value = draftSyncCount > 0
      quotingZone.value = deliverySyncCount > 0
    }
  }

  const operation = draftSyncTail.then(run, run)
  draftSyncTail = operation.catch(() => {})
  return operation
}

watch(chosenDate, value => {
  if (!value) {
    state.delivery_date = ''
    return
  }
  const nextValue = localDateValue(value)
  if (isCheckoutDateUnavailable(nextValue, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) return
  state.delivery_date = nextValue
  clearFieldError('delivery_date')
  deliveryDateHint.value = ''
  datePopoverOpen.value = false
})

watch(slots, () => {
  reconcileDeliverySlot()
})

watch(() => state.delivery_time_slot, value => {
  if (value && selectedSlot.value?.enabled) clearFieldError('delivery_time_slot')
})

watch(() => state.fulfillment_type, () => {
  clearFieldErrors(['fulfillment_type', 'delivery_address'])
  reconcileDeliverySlot()
})

watchEffect(() => {
  if (!steps.value.includes(activeStep.value)) {
    activeStep.value = steps.value[0] || 'fulfillment'
  }
})

function stepState (step: Step): CheckoutSectionState {
  // Contato é a única etapa atual enquanto estiver incompleto/em edição. Manter
  // também "Como receber" como current produziria dois "Agora" e duas tarefas
  // concorrentes, justamente quando a pessoa precisa de condução.
  if (contactState.value !== 'done') return 'upcoming'
  return checkoutStepState({
    step,
    steps: steps.value,
    activeStep: activeStep.value,
    fieldErrors: fieldErrors.value,
    action: action.value
  })
}

function stepHeaderSummary (step: Step) {
  return checkoutStepHeaderSummary({
    step,
    form: state,
    availableFulfillment: availableFulfillment.value,
    savedAddressesCount: savedAddresses.value.length,
    fieldErrors: fieldErrors.value,
    activeStep: activeStep.value,
    fulfillmentLabel: fulfillmentLabel.value,
    addressSummary: addressSummary.value,
    whenSummary: whenSummary.value,
    paymentMethodLabel: paymentMethodLabel.value,
    action: bagGoneNoticeShowing.value ? null : action.value
  })
}

function goToStep (step: Step) {
  if (!steps.value.includes(step)) return
  activeStep.value = step
}

const paymentIcon = resolvePaymentIcon

// Linhas do resumo (ícone + valor) — mesma diagramação da aba "Resumo" do
// acompanhamento (componente OrderSummaryRows), a partir do estado do checkout.
const reviewSummaryRows = computed(() => {
  const rows: { icon: string, lines: string[], muted?: string }[] = [
    { icon: fulfillmentIcon.value, lines: [fulfillmentSummary.value || fulfillmentLabel.value] }
  ]
  if (state.fulfillment_type === 'delivery') {
    rows.push({ icon: 'lucide:map-pin', lines: deliveryAddressLines.value, muted: state.delivery_complement || undefined })
  }
  if (noteTaxId(state)) {
    rows.push({ icon: 'lucide:receipt-text', lines: [`Nota fiscal no documento ${formatTaxId(state.fiscal_tax_id)}`] })
  }
  rows.push({ icon: paymentIcon(state.payment_method), lines: [paymentMethodLabel.value] })
  rows.push({ icon: 'lucide:user-round', lines: [contactSummary.value] })
  if (state.is_gift) rows.push({ icon: 'lucide:gift', lines: [giftSummary.value] })
  return rows
})

function validateContact (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.name
  delete errors.phone
  if (!state.name.trim()) errors.name = 'Informe seu nome.'
  if (!state.phone.trim()) errors.phone = 'Informe seu telefone.'
  fieldErrors.value = errors
  if (errors.name || errors.phone) {
    contactEditing.value = true
    return false
  }
  contactEditing.value = false
  return true
}

function validateFulfillmentStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.fulfillment_type
  if (!availableFulfillment.value.includes(state.fulfillment_type)) errors.fulfillment_type = 'Escolha retirada ou entrega.'
  fieldErrors.value = errors
  if (errors.fulfillment_type) {
    activeStep.value = 'fulfillment'
    return false
  }
  // Mínimo de entrega barra aqui, cedo — não no commit. O aviso (com adicionar
  // itens / mudar p/ retirada) já está visível neste passo.
  if (deliveryBelowMinimum.value) {
    activeStep.value = 'fulfillment'
    return false
  }
  return true
}

function validateAddressStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.delivery_address
  delete errors.fiscal_tax_id
  if (state.fulfillment_type === 'delivery' && !state.delivery_address.trim()) errors.delivery_address = 'Escolha ou informe o endereço de entrega.'
  if (state.fulfillment_type === 'delivery' && taxIdIssue.value) errors.fiscal_tax_id = taxIdIssue.value
  fieldErrors.value = errors
  if (errors.delivery_address || errors.fiscal_tax_id) {
    activeStep.value = 'address'
    return false
  }
  return true
}

function validateWhenStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.delivery_date
  delete errors.delivery_time_slot
  if (!state.delivery_date) errors.delivery_date = checkout.value?.copy.when_required || 'Escolha a data.'
  if (state.delivery_date && isCheckoutDateUnavailable(state.delivery_date, dateBounds.value, closedDateEntries.value, closedWeekdays.value)) errors.delivery_date = 'Escolha uma data disponível.'
  if (state.delivery_date && !slots.value.length) errors.delivery_time_slot = noWindowsMessage(state.fulfillment_type, isTodaySelected.value)
  if (slots.value.length && !state.delivery_time_slot) errors.delivery_time_slot = 'Escolha um horário.'
  if (state.delivery_time_slot && slots.value.length && !selectedSlot.value?.enabled) {
    errors.delivery_time_slot = selectedSlot.value?.reason || 'Escolha um horário disponível.'
  }
  fieldErrors.value = errors
  if (errors.delivery_date || errors.delivery_time_slot) {
    activeStep.value = 'when'
    return false
  }
  return true
}

function validatePaymentStep (): boolean {
  const errors = { ...fieldErrors.value }
  delete errors.payment_method
  delete errors.recipient_name
  delete errors.recipient_phone
  if (state.fulfillment_type === 'pickup') delete errors.fiscal_tax_id
  if (!state.payment_method) errors.payment_method = 'Escolha o pagamento.'
  else if (pixProviderTestExceeded.value) errors.payment_method = pixProviderTestMessage.value
  // Presente em ENTREGA exige destinatário — validado JÁ aqui (no "Revisar
  // pedido"), não no commit. Espelha intents.gift.build_gift_data.
  if (state.is_gift && state.fulfillment_type === 'delivery') {
    if (!state.recipient_name.trim()) {
      errors.recipient_name = 'Informe o nome de quem vai receber o presente.'
    }
    // Assume o DDD padrão da loja antes de validar (o cliente não precisa saber o
    // DDD; espelha o Doorman). Válido = 10 (fixo) ou 11 (celular) dígitos locais.
    const local = normalizeAuthPhone(state.recipient_phone, 'BR', defaultDdd.value).replace(/^\+55/, '')
    if (!state.recipient_phone.trim()) {
      errors.recipient_phone = 'Informe o telefone de quem vai receber o presente.'
    } else if (local.length < 10) {
      errors.recipient_phone = 'Telefone do destinatário inválido. Ex: (43) 99999-9999'
    }
  }
  // CPF na nota da retirada: opcional; digitado errado é erro (o servidor recusa).
  if (showPickupTaxIdField.value && taxIdIssue.value) errors.fiscal_tax_id = taxIdIssue.value
  fieldErrors.value = errors
  if (errors.payment_method || errors.recipient_name || errors.recipient_phone || (showPickupTaxIdField.value && errors.fiscal_tax_id)) {
    activeStep.value = 'payment'
    return false
  }
  return true
}

function saveContact () {
  if (validateContact()) nameEditing.value = false
}

function focusCheckoutControl (id: string) {
  if (!import.meta.client) return
  document.getElementById(id)?.focus({ preventScroll: true })
}

// Omotenashi: um gate de validação NUNCA falha em silêncio. O erro vem até o
// cliente (toast) e a tela mostra o primeiro campo com erro (role="alert"),
// em vez de ficar quietinho num campo fora da view. Se o erro abriu OUTRA
// seção, o foco da página muda e o reveal automático (mais novo) passa na
// frente: a seção inteira vai para a linha de foco, com o erro no cabeçalho.
function revealFirstError () {
  if (!import.meta.client) return
  const first = firstCheckoutError(fieldErrors.value)
  if (!first) return
  useSonner.error(first.message)
  reveal(() => document.querySelector('[data-slot="field-error"]'), { align: 'center', focus: false })
}

async function continueFromFulfillment () {
  if (!validateFulfillmentStep()) { revealFirstError(); return }
  // Retirada zera a taxa de entrega no total; entrega recalcula ao confirmar
  // o endereço (applyDeliveryDraft no passo seguinte).
  if (state.fulfillment_type === 'pickup') await applyDeliveryDraft()
  if (deliveryDraftFailed.value) return
  activeStep.value = state.fulfillment_type === 'delivery' ? 'address' : 'when'
}

// Escolher Entrega já É a decisão deste passo. Exigir outro toque em
// "Continuar" fazia a pessoa confirmar a mesma intenção duas vezes. O gesto
// abre o endereço e o alvo contextual do AddressPicker recebe o foco; se o
// mínimo não foi atingido, permanecemos aqui com a saída já visível.
function onFulfillmentSelected (value: string) {
  if (value !== 'pickup' && value !== 'delivery') return
  state.fulfillment_type = value
  if (value === 'pickup') void applyDeliveryDraft()
  if (value === 'delivery' && !deliveryBelowMinimum.value) {
    activeStep.value = 'address'
  }
}

// O picker confirma o endereço e o fluxo segue sozinho: o CPF da entrega é
// opcional, e quem quiser a nota no documento preenche antes de confirmar.
function onAddressConfirmed () {
  void continueFromAddress()
}

async function continueFromAddress () {
  if (!validateAddressStep()) { revealFirstError(); return }
  // O picker grava o endereço e emite `confirmed` na mesma interação. Esperar
  // a fila garante que taxa, cobertura e revisão usadas adiante são as que o
  // servidor acabou de aceitar.
  await draftSyncTail
  if (deliveryDraftFailed.value) await applyDeliveryDraft()
  if (deliveryDraftFailed.value) return
  // Fora da área o passo não avança (beta SMS-06): o aviso de cobertura, com a
  // troca para retirada quando houver, vira o foco da página.
  if (zoneRefused.value) { revealZoneRefusal(); return }
  activeStep.value = 'when'
}

// O aviso de cobertura mora no topo do fluxo (fora da seção de endereço, para
// não remontar o picker). Quem recusa leva a página até ele e põe o foco no
// gesto que resolve ("Mudar para retirada"), em vez de deixar o cliente olhando
// para a seção onde estava (beta SMS-05).
function revealZoneRefusal () {
  reveal(DELIVERY_ZONE_REFUSAL_FOCUS, { align: 'start', focus: true })
}

function continueFromWhen () {
  if (validateWhenStep()) activeStep.value = 'payment'
  else revealFirstError()
}

function continueFromPayment () {
  if (validatePaymentStep()) openConfirmSheet()
  else revealFirstError()
}

function openConfirmSheet () {
  reviewClosesIntoStockRefusal = false
  if (!validate()) { revealFirstError(); return }
  // Defesa em profundidade: entrega numa zona recusada nunca chega à revisão
  // com o envio liberado e total sem taxa (beta SMS-06).
  if (zoneRefused.value) {
    if (!pickupSwapOffer.value && !deliveryUncovered.value) {
      pickupSwapOffer.value = availableFulfillment.value.includes('pickup')
      deliveryUncovered.value = !pickupSwapOffer.value
    }
    activeStep.value = 'address'
    revealZoneRefusal()
    return
  }
  if (submitDisabled.value) {
    serverError.value = action.value?.reason || 'Pedido não pode ser confirmado agora.'
    return
  }
  confirmOpen.value = true
}

function openReceiptSheet () {
  // No computador o resumo é o lateral, e a folha não tem conteúdo ali: abrir
  // seria um véu vazio (#3281). A linha do total nem é toque em `lg`.
  if (import.meta.client && window.matchMedia?.('(min-width: 64rem)').matches) return
  receiptOpen.value = true
}

function validate (): boolean {
  if (!validateContact()) return false
  if (!validateFulfillmentStep()) return false
  if (state.fulfillment_type === 'delivery' && !validateAddressStep()) return false
  if (!validateWhenStep()) return false
  if (!validatePaymentStep()) return false
  return true
}

function changeFromPix () {
  const alternative = paymentMethods.value.find(method => method.ref !== 'pix')
  state.payment_method = ''
  clearFieldError('payment_method')
  reveal(() => (alternative
    ? document.getElementById(`checkout-payment-${alternative.ref}`)
    : document.querySelector<HTMLElement>('[data-checkout-payment-option]')), { align: 'center' })
}

async function goToAuthRoute () {
  await navigateTo(authRoute.value)
}

async function recoverCheckout (key = '') {
  return (await checkCheckoutRecovery(key)) === true
}
// `not_received`: o servidor nunca recebeu esta tentativa (ou ela falhou). Não
// vai virar pedido sozinha, e o reenvio com a mesma chave é seguro (beta SMS-17).
async function checkCheckoutRecovery (key = ''): Promise<CheckoutRecoveryOutcome> {
  try {
    // POST: recuperar dá a este navegador o acesso ao pedido e refaz o que ficou
    // pendente depois do commit. GET não produz efeito.
    const receipt = await $fetch<CheckoutMutationResponse | undefined>(apiPath('/api/v1/checkout/recover/'), {
      method: 'POST',
      credentials: 'include',
      headers: { ...(await csrfHeaders()), ...(key ? { 'Idempotency-Key': key } : {}) }
    })
    if (!receipt?.order_ref) return false
    confirmedTrackingUrl.value = receipt.next_url || `/pedido/${encodeURIComponent(receipt.order_ref)}`
    clearCheckoutDraft()
    clearCart()
    await navigateTo(receipt.next_url || `/pedido/${encodeURIComponent(receipt.order_ref)}`)
    return true
  } catch (e) {
    if (confirmedTrackingUrl.value) {
      serverError.value = 'Pedido confirmado. Continue no acompanhamento.'
      confirmOpen.value = false
      return true
    }
    if (httpError(e).data?.error_code === 'checkout_attempt_not_received') return 'not_received'
    return false
  }
}
// A conferência seguinte não espera o degrau inteiro quando a rede volta: é
// justamente quando o servidor já pode responder se a tentativa chegou.
function waitOrOnline (ms: number): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer)
      window.removeEventListener('online', done)
      resolve()
    }
    const timer = setTimeout(done, ms)
    window.addEventListener('online', done)
  })
}
function onDraftRemoved (event: StorageEvent) {
  if (event.key === CHECKOUT_DRAFT_KEY && event.newValue === null) window.location.reload()
}
// A pergunta sai uma vez, na primeira sacola que chegar: com a projeção lazy, a
// navegação dentro do app monta a tela antes da sacola, e a checagem só no
// `onMounted` não perguntava nada.
let recoveryAsked = false
onMounted(() => {
  window.addEventListener('storage', onDraftRemoved)
  watch(cart, (value) => {
    if (recoveryAsked || !value) return
    recoveryAsked = true
    if (value.is_empty) void recoverCheckout()
  }, { immediate: true })
})
onBeforeUnmount(() => {
  stopUncertainCheck()
  if (import.meta.client) window.removeEventListener('storage', onDraftRemoved)
})

function stopUncertainCheck () {
  recoveryLoop?.cancel()
  recoveryLoop = null
  checkingOrder.value = false
}

// Confere de novo, com espera crescente, até o pedido aparecer ou o teto chegar.
// Achou: `recoverCheckout` já leva ao acompanhamento. Não achou: a tela devolve o
// envio ao cliente (mesma tentativa, sem pedido em dobro).
function startUncertainCheck () {
  stopUncertainCheck()
  confirmationUnknown.value = true
  checkingOrder.value = true
  serverError.value = UNCERTAIN_CHECKING
  const key = attemptKey.value
  const loop = startCheckoutRecovery(() => checkCheckoutRecovery(key), CHECKOUT_RECOVERY_DELAYS_MS, waitOrOnline)
  recoveryLoop = loop
  void loop.done.then((found) => {
    if (recoveryLoop !== loop) return
    recoveryLoop = null
    checkingOrder.value = false
    if (!found && !confirmedTrackingUrl.value) serverError.value = UNCERTAIN_NOT_FOUND
  })
}

async function submitCheckout () {
  // O botão já fica ocupado, mas Enter/programmatic submit não dependem da UI.
  // A idempotência do servidor é a última defesa; esta guarda evita o request
  // concorrente antes dele sair do navegador.
  if (submitting.value || !checkout.value || !validate()) return
  stockRefusal.value = null
  const baseline = checkoutBaseline(cart.value)
  if (!baseline) {
    serverError.value = 'Sua sacola precisa ser atualizada antes da confirmação. Confira o resumo e tente novamente.'
    await refresh()
    return
  }
  stopUncertainCheck()
  submitting.value = true
  confirmationUnknown.value = false
  serverError.value = ''
  deliveryDateHint.value = ''
  try {
    saveCheckoutDraft()
    const idempotencyKey = attemptKey.value
    const response = await $fetch<CheckoutMutationResponse>(apiPath('/api/v1/checkout/'), {
      method: 'POST',
      headers: {
        ...(await csrfHeaders()),
        'Idempotency-Key': idempotencyKey
      },
      credentials: 'include',
      body: buildCheckoutPayload(
        state,
        idempotencyKey,
        useLoyalty.value,
        baseline.expectedTotalQ,
        baseline.expectedRevision
      )
    })
    if (response.convenience_pending?.length && import.meta.client) useSonner.info('Pedido confirmado. Estamos tentando salvar suas escolhas para a próxima vez.')
    // "Guardar no seu cadastro?" não tem resposta na tela, de propósito: dizer
    // que não entrou deixaria inferir que o documento é de outra conta (a loja
    // nunca revela isso). A nota sai com o documento de qualquer jeito.
    confirmedTrackingUrl.value = response.next_url || `/pedido/${encodeURIComponent(response.order_ref)}`
    // O confete do acompanhamento é deste navegador: é ele quem sabe que o pedido
    // acabou de ser fechado (utils/justPlaced).
    markJustPlaced(response.order_ref)
    // Cartão em um toque: o acompanhamento leva direto ao pagamento seguro assim que
    // o link chega (utils/cardHandoff).
    if (isHostedCheckout(state.payment_method)) markCardHandoff(response.order_ref)
    clearCart()
    clearCheckoutDraft()
    attemptKey.value = createCheckoutAttemptKey()
    // O próximo passo é sempre o acompanhamento (views.py, next_url): é lá que o
    // Pix aparece e que o cartão é levado ao pagamento seguro (marca acima). Não
    // existe tela intermediária.
    const confirmedUrl = response.next_url
      || `/pedido/${encodeURIComponent(response.order_ref)}`
    // O endereço novo já foi guardado pelo Core com rótulo neutro. Nomeá-lo é
    // conveniência de cadastro, não pode interromper a compra nem atrasar o
    // acompanhamento do pedido confirmado.
    await navigateTo(confirmedUrl)
  } catch (e) {
    if (confirmedTrackingUrl.value) {
      serverError.value = 'Pedido confirmado. Continue no acompanhamento.'
      confirmOpen.value = false
      return
    }
    const failure = httpError(e)
    if (!failure.status || failure.status >= 500) {
      if (await recoverCheckout(attemptKey.value)) return
      // "Mantenha esta tentativa" mandava o cliente cuidar do `attemptKey` — objeto que
      // ele nunca viu e não pode manter nem largar, no pior instante do fluxo. O que ele
      // precisa saber é o que aconteceu, o que NÃO aconteceu, e o que fazer.
      startUncertainCheck()
      if (import.meta.client) useSonner.info(serverError.value)
      return
    }
    const data = failure.data || {}
    confirmationUnknown.value = data.error_code === 'mutation_in_progress'
    // A mesma tentativa já virou pedido (a outra aba deste navegador restaurou o mesmo
    // rascunho e enviou primeiro): a tela abre o pedido e diz por quê (#3267).
    if (data.error_code === 'idempotency_conflict' && await recoverCheckout(attemptKey.value)) {
      if (confirmedTrackingUrl.value) showPageNotice(ORDER_ALREADY_SENT_MESSAGE, confirmedTrackingUrl.value)
      return
    }
    // O Django ainda está gravando esta mesma tentativa: conferir até terminar.
    if (data.error_code === 'mutation_in_progress') {
      startUncertainCheck()
      return
    }
    if (failure.status < 500 && data.error_code !== 'mutation_in_progress') attemptKey.value = createCheckoutAttemptKey()
    const field = typeof data.field === 'string' ? data.field : ''
    serverError.value = errorDetail(e, 'Não foi possível confirmar o pedido.')
    // A sacola já saiu (outra aba enviou primeiro) ou sumiu (encerrada, apagada,
    // sem item): não é erro de campo, é outro estado da sacola (#3267). O pedido que
    // já saiu abre direto; a sacola que sumiu volta vazia, com o caminho do cardápio.
    const bagRefusal = checkoutBagRefusal(data)
    if (bagRefusal) {
      serverError.value = ''
      confirmOpen.value = false
      // O aviso é o de página (abaixo das barras, primeiro conteúdo, com X), nunca
      // toast: ele fala do que aconteceu com a sacola e fica enquanto a causa durar.
      if (bagRefusal.kind === 'order_already_sent') {
        clearCart()
        clearCheckoutDraft()
        showPageNotice(bagRefusal.message, bagRefusal.href)
        await navigateTo(bagRefusal.href)
        return
      }
      await refresh()
      acceptEmptiedCheckout()
      showPageNotice(bagRefusal.message, route.path, {
        tone: 'attention',
        action: { label: bagRefusal.actionLabel, to: bagRefusal.href }
      })
      return
    }
    // Preço/cupom mudou entre a revisão e o confirm: o servidor já reprecificou a
    // sessão (o guardião barrou a cobrança surpresa). Reprecificamos a TELA para o
    // sheet mostrar o novo total em vez de deixar o valor velho ao lado do aviso —
    // o cliente reconfirma sobre o número certo (o próximo envio casa a baseline).
    // Confirmação de identidade: não é erro de dado, é um degrau — e ele se paga UMA vez
    // naquele aparelho. O aviso diz o que dá para fazer agora (salvo/balcão) e oferece o
    // toque que resolve, em vez de deixar a pessoa adivinhando.
    if (data.error_code === 'identity_confirmation_required') {
      identityConfirmOffer.value = true
      submitting.value = false
      return
    }
    // Pix acima do teto da Efí de testes: a recusa é o MESMO aviso do passo de
    // pagamento, com as duas saídas — não um erro genérico sem caminho.
    if (data.error_code === 'pix_test_amount_limit') {
      const refusedTotal = Number((data.context as { current_amount_q?: unknown } | undefined)?.current_amount_q)
      pixLimitRefusal.value = {
        message: serverError.value,
        totalQ: Number.isFinite(refusedTotal) ? refusedTotal : Number(cart.value?.grand_total_q)
      }
      serverError.value = ''
      confirmOpen.value = false
      activeStep.value = 'payment'
      await refresh()
      return
    }
    // Faltou estoque no último passo: a revisão fecha, a tela diz QUAL item ficou
    // indisponível e leva à sacola, onde a linha dele mostra o que dá para fazer (usar o
    // que sobrou, pedir o aviso de volta, tirar). Antes era um aviso que sumia, sem o
    // item e sem para onde ir.
    if (data.error_code === 'insufficient_supply') {
      const context = (data.context || {}) as { sku?: unknown, name?: unknown }
      const issue = data.stock_issue && typeof data.stock_issue === 'object'
        ? data.stock_issue as Record<string, unknown>
        : null
      const lineId = typeof issue?.line_id === 'string' && issue.line_id ? issue.line_id : null
      const refusedLine = lineId ? cart.value?.items.find(item => item.line_id === lineId) : null
      stockRefusal.value = {
        sku: String(context.sku || ''),
        name: String(context.name || ''),
        message: serverError.value,
        issue,
        lineId,
        qty: refusedLine?.qty ?? (typeof issue?.requested_qty === 'number' ? issue.requested_qty : null)
      }
      serverError.value = ''
      // O foco é do aviso, não do botão que abriu a revisão (`onReviewClosed`), e a
      // folha de alternativas sobe quando a revisão termina de fechar.
      const reviewWasOpen = confirmOpen.value
      reviewClosesIntoStockRefusal = reviewWasOpen
      confirmOpen.value = false
      await refresh()
      await nextTick()
      // Com a folha já aberta, o foco é dela: levar a tela ao aviso agora o roubaria.
      if (!cartIssue.value) revealStockRefusal()
      if (!reviewWasOpen) openStockAlternatives()
      return
    }
    if (data.error_code === 'total_changed' || data.error_code === 'revision_changed') {
      attemptKey.value = createCheckoutAttemptKey()
      dateMovedNoticeShown = false
      await refresh()
      // O dia novo (se a releitura moveu a data) chega pelo `initializeDeliveryDate`.
      await nextTick()
      if (import.meta.client && !dateMovedNoticeShown) useSonner.error(serverError.value)
      return
    }
    // Dia fechado: o backend sugere a encomenda (preorder_hint) e a próxima data.
    // Mostramos a dica junto ao campo de data, sem interferir no fieldError.
    if (typeof data.preorder_hint === 'string' && data.preorder_hint) {
      deliveryDateHint.value = data.preorder_hint
    }
    if (field) {
      // Poka-yoke: endereço fora da zona, mas a loja faz retirada → oferecer
      // a troca em 1 clique em vez de deixar o cliente num beco sem saída.
      pickupSwapOffer.value = shouldOfferPickupSwap({
        field,
        fulfillmentType: state.fulfillment_type,
        hasPickup: availableFulfillment.value.includes('pickup'),
        hasAddress: !!state.delivery_address.trim()
      })
      if (pickupSwapOffer.value) {
        // O aviso (com a troca em 1 clique) aparece no topo do fluxo. NÃO
        // marcar fieldError nem reabrir o passo: o erro poria a seção de
        // endereço em estado de erro, remontando o picker — que
        // re-selecionaria o salvo e apagaria o endereço fora de área e a
        // própria oferta. Fecha o sheet de revisão e leva a página até o
        // aviso: sem isso a recusa ficava fora da tela (beta SMS-05).
        confirmOpen.value = false
        revealZoneRefusal()
      } else {
        fieldErrors.value = { ...fieldErrors.value, [field]: serverError.value }
        // O CPF da retirada mora no passo do pagamento, não no do endereço.
        const step = field === 'fiscal_tax_id' && state.fulfillment_type === 'pickup'
          ? 'payment'
          : checkoutStepForField(field)
        if (step) activeStep.value = step
        if (field === 'name' || field === 'phone') contactEditing.value = true
      }
    }
    if (import.meta.client && !pickupSwapOffer.value) useSonner.error(serverError.value)
  } finally {
    submitting.value = false
  }
}

async function switchToPickup () {
  state.fulfillment_type = 'pickup'
  pickupSwapOffer.value = false
  deliveryUncovered.value = false
  serverError.value = ''
  confirmOpen.value = false
  const errors = { ...fieldErrors.value }
  delete errors.delivery_address
  fieldErrors.value = errors
  await applyDeliveryDraft()
  activeStep.value = deliveryDraftFailed.value ? 'fulfillment' : 'when'
}

useSeoMeta({
  title: 'Finalizar pedido'
})
</script>

<template>
  <main
    ref="checkoutRoot"
    class="shop-section shop-dock-reserve pt-0 md:pb-24 lg:pb-0"
    :data-checkout-keyboard-active="keyboardActive || undefined"
    @focusin="onCheckoutFocusIn"
    @focusout="onCheckoutFocusOut"
  >
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Sacola', link: '/sacola' },
            { label: 'Finalizar pedido' }
          ]"
        />
      </div>
    </div>
    <div class="shop-container grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section class="shop-stack-block">
        <div>
          <h1 class="shop-title">Finalize seu pedido</h1>
          <p class="mt-2 max-w-2xl shop-muted">
            Uma etapa por vez. Você confere tudo antes de enviar.
          </p>
        </div>

        <!-- A sacola entre a loja e a conversa (OC-16, #3515, #3517): mesmos avisos da
             sacola. Depois de trazer ou trocar, o Finalizar relê o rascunho. -->
        <CartPassageNotices :cart="liveCart" @changed="refresh" />

        <!-- Skeleton só no carregamento INICIAL. Em refresh de fundo (ex.: rascunho
             de entrega) manter o conteúdo montado — apagar a página remontava o
             AddressPicker, que re-selecionava o salvo e re-disparava o rascunho →
             refresh → loop (tela piscando ao entrar em "entrega"). -->
        <UiSkeleton v-if="pending && !checkout" class="h-96 rounded-lg" />

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Checkout indisponível</UiAlertTitle>
          <UiAlertDescription>
            <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
          </UiAlertDescription>
        </UiAlert>

        <template v-else-if="checkout">
          <!-- Faltou estoque no envio: qual item, e o caminho para resolver. O alvo do
               foco é a moldura, que para na régua canônica (sob o cabeçalho); o respiro
               de cima mora dentro dela (`pt-4`, compensado por `-mt-4`), então o aviso
               não encosta no cabeçalho e nenhuma linha do texto de cima sobra cortada. -->
          <div v-if="stockRefusal" class="-mt-4 pt-4" data-focus-target="stock-refusal">
            <UiAlert variant="warning" data-checkout-stock-refusal>
              <!-- O título é a frase inteira ("X ficou indisponível antes de..."): quebra
                   em linhas no celular, em vez de cortar com reticências. -->
              <UiAlertTitle class="line-clamp-none leading-snug">{{ stockRefusal.message }}</UiAlertTitle>
              <UiAlertDescription>
                <template v-if="stockRefusal.issue">
                  <p>Veja o que dá para levar no lugar. O resto do pedido continua como você deixou.</p>
                  <UiButton size="sm" icon="lucide:repeat" class="mt-2" data-focus-control data-checkout-stock-alternatives @click="openStockAlternatives">
                    Ver o que dá para levar
                  </UiButton>
                </template>
                <template v-else>
                  <p>Abra a sacola para ver o que dá para levar no lugar. O resto do pedido continua como você deixou.</p>
                  <UiButton size="sm" icon="lucide:shopping-bag" class="mt-2" to="/sacola" data-focus-control>
                    Abrir a sacola
                  </UiButton>
                </template>
              </UiAlertDescription>
            </UiAlert>
          </div>

          <UiAlert v-if="pickupSwapOffer" variant="warning" data-checkout-pickup-swap data-focus-target="zone-refusal">
            <UiAlertTitle>{{ serverError || 'Ainda não entregamos nesse endereço' }}</UiAlertTitle>
            <UiAlertDescription>
              <p>Mas você pode retirar na loja quando quiser.</p>
              <UiButton size="sm" icon="lucide:store" class="mt-2" :loading="draftSyncing" :disabled="draftSyncing" data-focus-control @click="switchToPickup">
                Mudar para retirada
              </UiButton>
            </UiAlertDescription>
          </UiAlert>

          <!-- Mesma recusa, loja sem retirada: não há "Mudar para retirada" a oferecer,
               então a saída é outro endereço ou a gente. -->
          <UiAlert v-else-if="deliveryUncovered" variant="warning" data-checkout-zone-uncovered data-focus-target="zone-refusal">
            <UiAlertTitle>Ainda não entregamos nesse endereço</UiAlertTitle>
            <UiAlertDescription>
              <p>Escolha outro endereço aqui em cima, ou fale com a gente no WhatsApp.</p>
              <UiButton
                v-if="checkout?.support_whatsapp_url"
                :href="checkout.support_whatsapp_url"
                target="_blank"
                size="sm"
                variant="outline"
                icon="lucide:message-circle"
                class="mt-2"
              >
                Falar no WhatsApp
              </UiButton>
            </UiAlertDescription>
          </UiAlert>

          <UiAlert v-else-if="identityConfirmOffer" variant="warning" data-checkout-identity-confirm>
            <UiAlertTitle>Confirme que é você para usar seus pontos aqui</UiAlertTitle>
            <UiAlertDescription>
              <p>
                Num endereço novo, os pontos pedem uma confirmação. Em endereço já salvo ou
                retirando no balcão, pode usar agora mesmo.
              </p>
              <UiButton
                size="sm"
                icon="lucide:message-circle"
                class="mt-2"
                :disabled="confirming"
                @click="confirmByWhatsApp('/finalizar')"
              >
                {{ confirming ? 'Abrindo o WhatsApp…' : 'Confirmar pelo WhatsApp' }}
              </UiButton>
              <p class="shop-caption mt-2 text-muted-foreground">
                É só enviar a mensagem que já vai pronta. Sua sacola fica guardada.
              </p>
            </UiAlertDescription>
          </UiAlert>

          <UiAlert v-else-if="serverError && !confirmOpen" :variant="confirmedTrackingUrl || confirmationUnknown ? 'warning' : 'destructive'">
            <UiAlertTitle>{{ confirmedTrackingUrl ? 'Pedido confirmado' : confirmationUnknown ? uncertainTitle : 'Confira os dados' }}</UiAlertTitle>
            <UiAlertDescription>{{ serverError }}</UiAlertDescription>
            <UiButton v-if="confirmedTrackingUrl" :to="confirmedTrackingUrl">Acompanhar pedido</UiButton>
            <UiButton v-else-if="confirmationUnknown" variant="outline" to="/conta/pedidos">Ver meus pedidos</UiButton>
          </UiAlert>

          <!-- ⚠️ FORA da cadeia de `v-else-if` acima: `v-else-if` exige irmão imediato, e pôr
               este cartão no meio quebraria o encadeamento em silêncio (o typecheck passa).
               Ele tem condição própria — navegador embutido + já identificada. -->
          <BrowserHandoffCard :identified="checkout.is_authenticated" />

          <div data-checkout-progress-stack>
            <CheckoutProgressSection
              title="Contato"
              :state="contactState"
              icon="lucide:user-round"
              :summary="contactComplete && !contactEditing ? contactCardSummary : 'Nome e telefone'"
              data-checkout-contact-card
              data-focus-target="contact"
              @edit="contactEditing = true"
            >
              <!-- Card branco, padronizado com endereço; edição deliberada. -->
              <div class="shop-stack-block rounded-lg border bg-card p-4">
                <div v-if="showNameInput" class="space-y-2">
                  <div class="flex items-center justify-between gap-2">
                    <UiLabel for="checkout-name">Nome</UiLabel>
                    <UiButton
                      v-if="canCancelNameEdit"
                      variant="ghost"
                      size="sm"
                      icon="lucide:x"
                      class="-my-1 -mr-2 text-muted-foreground hover:text-foreground"
                      aria-label="Cancelar edição do nome"
                      @click="cancelEditName"
                    />
                  </div>
                  <!-- Com o nome em aberto, a próxima ação é digitar: o foco cai no campo. -->
                  <UiInput
                    id="checkout-name"
                    ref="nameInput"
                    v-model="state.name"
                    autocomplete="name"
                    enterkeyhint="done"
                    class="h-11"
                    data-focus-control
                    @keydown.enter.prevent="saveContact"
                  />
                  <UiFieldError v-if="fieldErrors.name" :errors="fieldErrors.name" />
                </div>
                <div class="divide-y">
                  <div v-if="!showNameInput" class="flex items-center gap-3 py-3 first:pt-0">
                    <Icon name="lucide:user-round" class="size-4 shrink-0 text-muted-foreground" />
                    <p class="min-w-0 flex-1 truncate text-sm font-semibold">{{ state.name }}</p>
                    <UiButton variant="link" size="sm" class="-my-3 -mr-3 h-11 min-w-11 px-3" aria-label="Editar nome" data-checkout-contact-edit @click="startEditName">Editar</UiButton>
                  </div>
                  <div class="flex items-center gap-3 py-3 first:pt-0">
                    <Icon name="lucide:phone" class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <!-- O telefone é texto (vem da conta), não campo: o leitor de tela
                         ouve o rótulo antes do número, e o erro fica ligado a ele. -->
                    <div class="min-w-0 flex-1" role="group" aria-labelledby="checkout-phone-label" :aria-describedby="fieldErrors.phone ? 'checkout-phone-error' : undefined">
                      <span id="checkout-phone-label" class="sr-only">Telefone</span>
                      <p class="shop-price" data-checkout-phone>
                        {{ phoneDisplay || 'Entre por telefone para continuar' }}
                      </p>
                      <UiFieldError v-if="fieldErrors.phone" id="checkout-phone-error" class="mt-1" :errors="fieldErrors.phone" />
                    </div>
                    <UiButton variant="link" size="sm" class="-my-3 -mr-3 h-11 min-w-11 px-3" aria-label="Trocar telefone" data-checkout-contact-edit @click="changePhoneOpen = true">
                      Trocar
                    </UiButton>
                  </div>
                </div>
              </div>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              :title="stepLabels.fulfillment"
              :state="stepState('fulfillment')"
              :icon="stepIcons.fulfillment"
              :summary="stepHeaderSummary('fulfillment')"
              data-checkout-step="fulfillment"
              data-focus-target="fulfillment"
              body-class="space-y-4"
              @edit="goToStep('fulfillment')"
            >
              <UiRadioGroup
                :model-value="state.fulfillment_type"
                class="grid gap-2 sm:grid-cols-2"
                aria-label="Como receber o pedido"
                @update:model-value="onFulfillmentSelected(String($event))"
              >
                <UiFieldLabel v-if="availableFulfillment.includes('pickup')" for="checkout-fulfillment-pickup" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem id="checkout-fulfillment-pickup" value="pickup" />
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>
                        <Icon name="lucide:store" class="size-4" />
                        Retirada
                      </UiFieldTitle>
                      <UiFieldDescription>{{ checkout.pickup_hint }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
                <UiFieldLabel v-if="availableFulfillment.includes('delivery')" for="checkout-fulfillment-delivery" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem id="checkout-fulfillment-delivery" value="delivery" />
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>
                        <Icon name="lucide:truck" class="size-4" />
                        Entrega
                      </UiFieldTitle>
                      <UiFieldDescription>{{ checkout.delivery_hint || 'Taxa conforme a região' }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
              </UiRadioGroup>
              <UiFieldError v-if="fieldErrors.fulfillment_type" :errors="fieldErrors.fulfillment_type" />
              <p v-if="availableFulfillment.length === 1" class="shop-muted">
                Esta é a opção disponível para este pedido.
              </p>
              <!-- Mínimo de entrega acusado JÁ aqui, no momento em que "Entrega" é escolhida
                   (o valor é flat e conhecido sem endereço) — nunca no commit. Barra de
                   progresso (mesmo idioma do frete grátis) + escape p/ retirada. -->
              <UiAlert v-if="deliveryBelowMinimum && cart?.delivery_minimum_progress" variant="warning" data-checkout-delivery-minimum>
                <UiAlertDescription>
                  <p class="flex items-center gap-2 font-semibold text-foreground">
                    <Icon name="lucide:truck" class="size-4 shrink-0" />
                    Faltam {{ cart.delivery_minimum_progress.remaining_display }} para o mínimo de entrega
                  </p>
                  <UiProgress :model-value="cart.delivery_minimum_progress.percent" class="mt-2" />
                  <!-- CTA que resolve (mesmo idioma da sacola): volta ao cardápio para
                       completar o mínimo. O rascunho do checkout preserva endereço e
                       escolhas — voltar não perde nada do que já foi preenchido. -->
                  <UiButton
                    variant="outline"
                    size="sm"
                    icon="lucide:plus"
                    class="mt-3 w-full"
                    data-checkout-minimum-add-items
                    :loading="goingToMenu"
                    @click="goToMenu"
                  >
                    {{ cart.delivery_minimum_progress.add_more_cta || 'Adicionar mais itens' }}
                  </UiButton>
                  <UiButton
                    v-if="availableFulfillment.includes('pickup')"
                    variant="link"
                    size="sm"
                    class="mt-2 h-auto p-0"
                    @click="state.fulfillment_type = 'pickup'"
                  >
                    Prefere retirar? Sem mínimo.
                  </UiButton>
                </UiAlertDescription>
              </UiAlert>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              v-if="steps.includes('address')"
              :title="stepLabels.address"
              :state="stepState('address')"
              :icon="stepIcons.address"
              :summary="stepHeaderSummary('address')"
              data-checkout-step="address"
              data-focus-target="address"
              body-class="space-y-4"
              @edit="goToStep('address')"
            >
              <AddressPicker
                :key="addressPickerKey"
                v-model:selection="addressSelection"
                context="checkout"
                :saved-addresses="savedAddresses"
                :preselected-id="checkout.preselected_address_id"
                @confirmed="onAddressConfirmed"
                @draft-pending="addressDraftPending = $event"
                @addresses-changed="refresh"
              />
              <UiFieldError v-if="fieldErrors.delivery_address" :errors="fieldErrors.delivery_address" />
              <!-- Transparência: endereço NOVO é guardado no perfil quando o pedido
                   fecha (comportamento do Core). O cliente fica sabendo ANTES, aqui,
                   em vez de o endereço "aparecer" salvo na próxima compra. -->
              <p
                v-if="addressSelection && !addressSelection.savedAddressId"
                class="mt-3 flex items-center gap-2 shop-meta"
                data-checkout-address-will-save
              >
                <Icon name="lucide:bookmark-plus" class="size-3.5 shrink-0" />
                Vamos guardar este endereço para a sua próxima entrega.
              </p>
              <p v-if="quotingZone" class="mt-3 flex items-center gap-2 shop-muted">
                <Icon name="lucide:loader-circle" class="size-4 animate-spin" /> Verificando se entregamos aqui…
              </p>
              <p
                v-else-if="!pickupSwapOffer && cart && cart.delivery_fee_q !== null && !cart.delivery_zone_error"
                class="mt-3 flex items-center gap-2 text-sm font-semibold"
                data-checkout-zone-ok
              >
                <Icon name="lucide:circle-check" class="size-4 shrink-0" />
                <!-- A única pergunta de quem informa o endereço é quanto custa entregar,
                     e esta linha só existe quando a taxa ACABOU de ser calculada. A
                     distância é complemento; o número é a resposta. -->
                Entregamos no seu endereço<span v-if="cart.delivery_fee_display" class="font-normal shop-muted" data-checkout-delivery-fee-line>: taxa de {{ cart.delivery_fee_display }}</span><span v-if="cart.delivery_distance_display" class="font-normal shop-muted"> (a {{ cart.delivery_distance_display }})</span>
              </p>
              <div v-if="freeDeliveryUpsell" class="mt-3" data-checkout-free-delivery>
                <div class="mb-2 flex items-center justify-between gap-3 text-sm font-semibold">
                  <span class="flex items-center gap-2">
                    <Icon name="lucide:truck" class="size-4 shrink-0" />
                    Faltam {{ freeDeliveryUpsell.remaining_display }} para frete grátis
                  </span>
                </div>
                <UiProgress :model-value="freeDeliveryUpsell.percent" />
              </div>

              <!-- NOTA DA ENTREGA: o CPF/CNPJ no mesmo passo do endereço,
                   opcional. Sem ele a nota sai sem identificar o consumidor. -->
              <div
                v-if="showTaxIdField"
                class="shop-stack-tight rounded-lg border bg-card p-4"
                data-checkout-tax-id
              >
                <UiLabel for="checkout-tax-id">CPF ou CNPJ na nota (opcional)</UiLabel>
                <p class="shop-meta">{{ TAX_ID_WHY }}</p>
                <UiInput
                  id="checkout-tax-id"
                  :model-value="state.fiscal_tax_id"
                  inputmode="numeric"
                  autocomplete="off"
                  :maxlength="18"
                  enterkeyhint="done"
                  placeholder="000.000.000-00"
                  :aria-invalid="!!fieldErrors.fiscal_tax_id"
                  class="h-11 bg-background"
                  @update:model-value="onTaxIdInput"
                />
                <UiFieldError v-if="fieldErrors.fiscal_tax_id" :errors="fieldErrors.fiscal_tax_id" />
                <p v-else-if="taxIdPrefillNote" class="shop-meta" data-checkout-tax-id-prefill>
                  {{ taxIdPrefillNote }}
                </p>
                <UiFieldLabel
                  v-if="offerSaveTaxId"
                  for="checkout-save-tax-id"
                  class="mt-1 bg-background has-data-[state=checked]:bg-background"
                  data-checkout-save-tax-id
                >
                  <UiField orientation="horizontal">
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>Guardar no seu cadastro?</UiFieldTitle>
                      <UiFieldDescription>Da próxima vez ele já vem preenchido.</UiFieldDescription>
                    </UiFieldContent>
                    <UiSwitch id="checkout-save-tax-id" v-model="state.save_fiscal_tax_id" />
                  </UiField>
                </UiFieldLabel>
              </div>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              :title="stepLabels.when"
              :state="stepState('when')"
              :icon="stepIcons.when"
              :summary="stepHeaderSummary('when')"
              data-checkout-step="when"
              data-focus-target="when"
              body-class="shop-stack-block"
              @edit="goToStep('when')"
            >
              <!-- Quando o pedido fica pronto para retirada (#2652): a promessa
                   do item mais tardio, a mesma do produto e da sacola. -->
              <UiAlert v-if="dateMovedNotice && !dateMovedDismissed" variant="warning" data-checkout-date-moved>
                <div class="flex items-start gap-2">
                  <UiAlertTitle class="line-clamp-none min-w-0 flex-1 leading-snug">{{ dateMovedNotice }}</UiAlertTitle>
                  <UiButton
                    type="button"
                    variant="ghost"
                    size="icon"
                    icon="lucide:x"
                    class="-my-2 -mr-2 size-11 shrink-0"
                    aria-label="Fechar aviso"
                    data-checkout-date-moved-close
                    @click="dateMovedDismissed = true"
                  />
                </div>
              </UiAlert>
              <p v-if="orderReadyNotice" class="flex items-center gap-1 shop-body" data-checkout-ready-promise>
                <Icon name="lucide:clock" class="size-3.5 shrink-0" />
                {{ orderReadyNotice }}
              </p>
              <div class="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                <div class="space-y-2">
                  <UiLabel>Data</UiLabel>
                  <p v-if="todayOverNotice" class="shop-meta text-muted-foreground" data-checkout-today-over data-decisive="availability">
                    {{ todayOverNotice }}
                  </p>
                  <p v-if="batchFloorNotice" id="checkout-batch-floor" class="shop-meta text-muted-foreground" data-checkout-batch-floor data-decisive="availability">
                    {{ batchFloorNotice }}
                  </p>
                  <!-- Datas padronizadas como as demais escolhas: caixas verticais
                       com dia da semana + data explícita. "Outra data" abre o
                       calendário e mostra a data escolhida quando ativa. -->
                  <UiRadioGroup
                    :model-value="state.delivery_date"
                    class="grid gap-2"
                    :aria-describedby="batchFloorNotice ? 'checkout-batch-floor' : undefined"
                    @update:model-value="pickDeliveryDate(String($event))"
                  >
                    <UiFieldLabel
                      v-for="option in quickDateOptions"
                      :key="option.value"
                      :for="`checkout-date-${option.value}`"
                      class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary"
                      :class="option.disabled ? 'opacity-60' : ''"
                    >
                      <UiField orientation="horizontal" :data-disabled="option.disabled || undefined">
                        <UiRadioGroupItem :id="`checkout-date-${option.value}`" :value="option.value" :disabled="option.disabled" />
                        <UiFieldContent class="gap-1">
                          <UiFieldTitle>{{ option.title }}</UiFieldTitle>
                          <UiFieldDescription>{{ dateOptionDescription(option.value) }}</UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>

                    <UiPopover v-model:open="datePopoverOpen">
                      <UiPopoverTrigger as-child>
                        <UiButton
                          variant="outline"
                          class="h-auto w-full justify-start gap-3 bg-card p-4"
                          :class="isCustomDate ? 'border-primary ring-1 ring-primary' : ''"
                        >
                          <Icon name="lucide:calendar-days" class="size-4 shrink-0" />
                          <span class="flex flex-1 flex-col items-start gap-1 text-left">
                            <span class="shop-body font-semibold">Outra data</span>
                            <span class="shop-muted">{{ isCustomDate ? selectedDateLabel : 'Escolher no calendário' }}</span>
                          </span>
                        </UiButton>
                      </UiPopoverTrigger>
                      <UiPopoverContent align="start" class="w-[var(--reka-popover-trigger-width)] p-0">
                        <UiDatepicker
                          v-model="chosenDate"
                          expanded
                          is-required
                          :min-date="checkoutMinDate"
                          :max-date="checkoutMaxDate"
                          :disabled-dates="datepickerDisabledDates"
                        />
                        <!-- O dia fechado é riscado, mudo e com `pointer-events: none`:
                             o cliente toca três vezes no sábado, nada acontece, e conclui
                             que o calendário travou. A legenda diz o que o risco quer
                             dizer e qual é o gesto. -->
                        <p class="border-t px-3 py-2 shop-meta text-muted-foreground" data-checkout-date-legend>
                          Encomendas até {{ displayCheckoutDate(dateBounds.maxDateValue, shopNow) }}.
                          Datas passadas, sem atendimento ou fora desse prazo ficam desabilitadas.
                        </p>
                      </UiPopoverContent>
                    </UiPopover>
                  </UiRadioGroup>
                  <UiFieldError v-if="fieldErrors.delivery_date" :errors="fieldErrors.delivery_date" />
                  <p v-if="deliveryDateHint" class="shop-meta text-muted-foreground" data-checkout-preorder-hint data-decisive="availability">{{ deliveryDateHint }}</p>
                </div>

                <!-- Entrega, e retirada de hoje: o cliente escolhe a janela na grade
                     da casa (a mesma da concierge, conferida no commit). Meia hora
                     hoje vira uma grade compacta de células iguais; o motivo da
                     janela apagada sai uma vez acima dela. -->
                <div v-if="isWindowGrid && state.delivery_date" class="space-y-2" data-checkout-delivery-windows>
                  <UiLabel>{{ isDeliveryWindows ? 'Horário da entrega' : 'Horário da retirada' }}</UiLabel>
                  <p v-if="!slots.length" class="shop-meta text-muted-foreground" data-checkout-delivery-windows-empty data-decisive="availability">
                    {{ noWindowsMessage(state.fulfillment_type, isTodaySelected) }}
                  </p>
                  <template v-else>
                    <p v-if="windowsReason" class="shop-meta text-muted-foreground" data-checkout-pickup-readiness data-decisive="availability">
                      {{ windowsReason }}
                    </p>
                    <UiRadioGroup v-model="state.delivery_time_slot" class="grid grid-cols-2 gap-2">
                      <UiFieldLabel
                        v-for="slot in slots"
                        :key="slot.ref"
                        :for="`checkout-window-${slot.ref}`"
                        class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary"
                        :title="slot.enabled ? slot.label : `${slot.label}: ${slot.reason}`"
                      >
                        <UiField orientation="horizontal" :data-disabled="!slot.enabled || undefined">
                          <UiRadioGroupItem
                            :id="`checkout-window-${slot.ref}`"
                            :value="slot.ref"
                            :disabled="!slot.enabled"
                            :aria-label="slot.enabled ? slot.label : `${slot.label}: ${slot.reason}`"
                          />
                          <UiFieldContent>
                            <UiFieldTitle class="whitespace-nowrap">
                              <span :class="!slot.enabled ? 'line-through' : ''">{{ slot.label }}</span>
                            </UiFieldTitle>
                          </UiFieldContent>
                        </UiField>
                      </UiFieldLabel>
                    </UiRadioGroup>
                  </template>
                  <UiFieldError v-if="fieldErrors.delivery_time_slot" :errors="fieldErrors.delivery_time_slot" />
                </div>

                <div v-if="!isWindowGrid && state.delivery_date" class="space-y-2">
                  <UiLabel>Horário</UiLabel>
                  <p v-if="!slots.length" class="shop-meta text-muted-foreground" data-checkout-pickup-slots-empty data-decisive="availability">
                    {{ noWindowsMessage(state.fulfillment_type, isTodaySelected) }}
                  </p>
                  <p v-if="windowsReason" class="shop-meta text-muted-foreground" data-checkout-pickup-readiness data-decisive="availability">
                    {{ windowsReason }}
                  </p>
                  <UiRadioGroup v-if="slots.length" v-model="state.delivery_time_slot" class="grid gap-2">
                    <UiFieldLabel
                      v-for="slot in slots"
                      :key="slot.ref"
                      :for="`checkout-slot-${slot.ref}`"
                      class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary"
                    >
                      <UiField orientation="horizontal" :data-disabled="!slot.enabled || undefined">
                        <UiRadioGroupItem
                          :id="`checkout-slot-${slot.ref}`"
                          :value="slot.ref"
                          :disabled="!slot.enabled"
                          :aria-label="slot.enabled ? slot.label : `${slot.label}: ${slot.reason}`"
                        />
                        <UiFieldContent class="gap-1">
                          <UiFieldTitle>
                            <span :class="!slot.enabled ? 'line-through' : ''">{{ slot.label }}</span>
                            <UiBadge v-if="slot.is_earliest && slot.enabled" variant="secondary">Mais cedo</UiBadge>
                          </UiFieldTitle>
                          <!-- O motivo existe e era entregue SÓ ao leitor de tela: quem
                               enxerga via um horário riscado sem saber se lotou, se
                               passou ou se o turno não existe — e a diferença decide
                               entre mudar de horário e mudar de dia. -->
                          <!-- O horário apagado esmaece sozinho (o título e o rádio, pelo
                               data-disabled do campo); o motivo NÃO: a meia opacidade do
                               cartão inteiro o deixava abaixo do contraste AA (X9, OC-30). -->
                          <UiFieldDescription v-if="!slot.enabled && !(windowsReason && slot.reason && windowsReason.startsWith(slot.reason))" data-decisive="availability">
                            {{ slot.reason || 'Esgotado para este horário.' }}
                          </UiFieldDescription>
                        </UiFieldContent>
                      </UiField>
                    </UiFieldLabel>
                  </UiRadioGroup>
                  <UiFieldError v-if="fieldErrors.delivery_time_slot" :errors="fieldErrors.delivery_time_slot" />
                </div>
              </div>
            </CheckoutProgressSection>

            <CheckoutProgressSection
              :title="stepLabels.payment"
              :state="stepState('payment')"
              :icon="stepIcons.payment"
              :summary="stepHeaderSummary('payment')"
              data-checkout-step="payment"
              data-focus-target="payment"
              body-class="space-y-4"
              @edit="goToStep('payment')"
            >
              <UiRadioGroup v-model="state.payment_method" class="grid gap-2 sm:grid-cols-2">
                <UiFieldLabel v-for="method in paymentMethods" :key="method.ref" :for="`checkout-payment-${method.ref}`" class="bg-card has-data-[state=checked]:bg-card has-data-[state=checked]:ring-1 has-data-[state=checked]:ring-primary">
                  <UiField orientation="horizontal">
                    <UiRadioGroupItem
                      :id="`checkout-payment-${method.ref}`"
                      :value="method.ref"
                      data-checkout-payment-option
                    />
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>
                        <Icon :name="paymentIcon(method.ref)" class="size-4" />
                        {{ method.label }}
                      </UiFieldTitle>
                      <UiFieldDescription v-if="paymentMethodHint(method.ref, checkout.card_provider)">{{ paymentMethodHint(method.ref, checkout.card_provider) }}</UiFieldDescription>
                    </UiFieldContent>
                  </UiField>
                </UiFieldLabel>
              </UiRadioGroup>
              <UiFieldError v-if="fieldErrors.payment_method" :errors="fieldErrors.payment_method" />

              <UiAlert
                v-if="pixProviderTestSelected"
                variant="warning"
                icon="lucide:flask-conical"
                :role="pixProviderTestExceeded ? 'alert' : 'status'"
                :aria-live="pixProviderTestExceeded ? 'assertive' : 'polite'"
                aria-atomic="true"
                data-pix-provider-test
              >
                <UiAlertTitle>{{ pixProviderTestExceeded ? 'Pix indisponível para este total' : 'Pix em período de testes' }}</UiAlertTitle>
                <UiAlertDescription class="shop-stack-tight">
                  <p>{{ pixProviderTestMessage }}</p>
                  <p v-if="!pixProviderTestExceeded">Este pedido está dentro do limite temporário.</p>
                  <div v-if="pixProviderTestExceeded" class="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                    <UiButton type="button" variant="outline" class="w-full sm:w-auto" @click="changeFromPix">
                      Trocar forma de pagamento
                    </UiButton>
                    <UiButton type="button" variant="outline" class="w-full sm:w-auto" :loading="adjustingCartForPix" @click="adjustCartForPix">
                      Ajustar itens
                    </UiButton>
                  </div>
                </UiAlertDescription>
              </UiAlert>

              <!-- Cartões de teste do Stripe. A lista chega VAZIA quando a chave
                   não é de teste, então em produção este bloco não existe nem no
                   HTML — a condição é a chave do gateway, não uma flag de tela. -->
              <div
                v-if="state.payment_method === 'card' && checkout.stripe_test_cards?.length"
                class="shop-stack-tight rounded-lg border border-dashed p-4"
              >
                <div class="flex items-start gap-3">
                  <Icon name="lucide:flask-conical" :size="20" class="mt-0.5 shrink-0 text-muted-foreground" />
                  <div class="min-w-0 space-y-1">
                    <p class="shop-item-title font-semibold text-foreground">Ambiente de teste</p>
                    <p class="shop-meta">Nenhuma cobrança real acontece aqui. Use um destes números no {{ checkout.card_provider || 'gateway' }}.</p>
                  </div>
                </div>
                <ul class="space-y-2">
                  <li v-for="card in checkout.stripe_test_cards" :key="card.number" class="rounded-lg bg-muted px-3 py-2">
                    <p class="shop-meta">{{ card.label }}</p>
                    <p class="font-mono text-sm text-foreground">{{ card.number }}</p>
                    <p class="shop-meta">{{ card.hint }}</p>
                  </li>
                </ul>
                <p class="shop-meta">Validade: qualquer data futura. CVC: quaisquer 3 dígitos. CEP: qualquer um.</p>
              </div>

              <UiField v-if="state.payment_method === 'cash' && !isPickup" class="mt-3">
                <UiFieldLabel for="checkout-change-for">Precisa de troco?</UiFieldLabel>
                <UiInputGroup class="min-w-0">
                  <UiInputGroupAddon>R$</UiInputGroupAddon>
                  <UiInput
                    id="checkout-change-for"
                    v-model="state.change_for"
                    inputmode="decimal"
                    autocomplete="off"
                    enterkeyhint="done"
                    placeholder="Troco para quanto?"
                    class="h-11 bg-background"
                  />
                </UiInputGroup>
                <UiFieldDescription>Opcional. Informe o valor da nota para o entregador levar o troco certinho.</UiFieldDescription>
              </UiField>

              <UiFieldLabel v-if="checkout.loyalty_balance_q > 0" for="checkout-loyalty" class="bg-card has-data-[state=checked]:bg-card">
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>Usar pontos de fidelidade</UiFieldTitle>
                    <UiFieldDescription>{{ checkout.copy.loyalty_savings_prefix || 'Seus pontos cobrem até' }} {{ checkout.loyalty_value_display }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-loyalty" v-model="useLoyalty" />
                </UiField>
              </UiFieldLabel>

              <!-- CPF NA NOTA da retirada: o "CPF na nota?" do balcão, opcional.
                   Desligado por padrão (a nota sai de qualquer jeito; o documento
                   só vai se a pessoa pedir). Ligar abre o mesmo campo da entrega,
                   já com o documento que a casa conhece. -->
              <UiFieldLabel
                v-if="isPickup"
                for="checkout-pickup-tax-id-toggle"
                class="bg-card has-data-[state=checked]:bg-card"
                data-checkout-pickup-tax-id
              >
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>CPF ou CNPJ na nota?</UiFieldTitle>
                    <UiFieldDescription>{{ PICKUP_TAX_ID_WHY }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-pickup-tax-id-toggle" v-model="state.fiscal_tax_id_on_pickup" />
                </UiField>
                <div v-if="state.fiscal_tax_id_on_pickup" class="shop-stack-tight px-4 pb-4" @click.stop>
                  <UiLabel for="checkout-pickup-tax-id" class="sr-only">CPF ou CNPJ na nota</UiLabel>
                  <UiInput
                    id="checkout-pickup-tax-id"
                    :model-value="state.fiscal_tax_id"
                    inputmode="numeric"
                    autocomplete="off"
                    :maxlength="18"
                    enterkeyhint="done"
                    placeholder="000.000.000-00"
                    :aria-invalid="!!fieldErrors.fiscal_tax_id"
                    class="h-11 bg-background"
                    @update:model-value="onTaxIdInput"
                  />
                  <UiFieldError v-if="fieldErrors.fiscal_tax_id" :errors="fieldErrors.fiscal_tax_id" />
                  <p v-else-if="taxIdPrefillNote" class="shop-meta" data-checkout-tax-id-prefill>
                    {{ taxIdPrefillNote }}
                  </p>
                  <!-- Dentro do cartão (que já é um label): div, não outro label. -->
                  <div v-if="offerSaveTaxId" class="flex items-center justify-between gap-3 pt-1" data-checkout-save-tax-id>
                    <div class="min-w-0 space-y-1">
                      <UiLabel for="checkout-pickup-save-tax-id">Guardar no seu cadastro?</UiLabel>
                      <p class="shop-meta">Da próxima vez ele já vem preenchido.</p>
                    </div>
                    <UiSwitch id="checkout-pickup-save-tax-id" v-model="state.save_fiscal_tax_id" />
                  </div>
                </div>
              </UiFieldLabel>

              <!-- Cupom: toggle-card único (igual fidelidade). Aplicado → título "Cupom
                   XYZ aplicado" + desconto, toggle ON (desligar remove). Senão → toggle
                   "Cupom de desconto?" que expande o campo. -->
              <UiFieldLabel
                for="checkout-coupon-toggle"
                class="bg-card has-data-[state=checked]:bg-card"
                data-checkout-coupon
              >
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>
                      <template v-if="cart?.coupon_code">
                        <span class="font-normal text-muted-foreground">Cupom</span> {{ cart.coupon_code }} <span class="font-normal text-muted-foreground">{{ couponCard.status === 'applied' ? 'aplicado' : 'sem desconto' }}</span>
                      </template>
                      <template v-else>Cupom de desconto?</template>
                    </UiFieldTitle>
                    <UiFieldDescription v-if="couponCard.description" :data-checkout-coupon-status="couponCard.status">{{ couponCard.description }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-coupon-toggle" :model-value="couponSwitchOn" @update:model-value="onCouponToggle" />
                </UiField>
                <div v-if="couponOpen && !cart?.coupon_code" class="px-4 pb-4" @click.stop>
                  <div class="flex items-center gap-2">
                    <UiInput
                      id="checkout-coupon-input"
                      v-model="coupon"
                      placeholder="Código do cupom"
                      autocomplete="off"
                      autocapitalize="characters"
                      enterkeyhint="done"
                      :spellcheck="false"
                      class="h-11 min-w-0 flex-1 bg-background"
                      :aria-invalid="!!couponIssue"
                      :aria-describedby="couponIssue ? 'checkout-coupon-error' : undefined"
                      @keyup.enter="submitCoupon"
                    />
                    <UiButton variant="outline" :loading="couponPending" :disabled="!coupon.trim()" @click.prevent="submitCoupon">Aplicar</UiButton>
                  </div>
                  <UiFieldError v-if="couponIssue" id="checkout-coupon-error" class="mt-2" :errors="couponIssue" />
                </div>
              </UiFieldLabel>

              <!-- Presente (GIFT-UX) ANTES de Observação (é mais estrutural —
                   muda destinatário/endereço/valores). Clone do toggle de obs.
                   Em entrega coleta o destinatário; em retirada vira "embalar
                   para presente" (só mensagem). @click.stop no painel impede que
                   cliques nos campos alternem o toggle externo (label). -->
              <UiFieldLabel for="checkout-gift-toggle" class="bg-card has-data-[state=checked]:bg-card" data-checkout-gift-box>
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>{{ giftTitle }}</UiFieldTitle>
                    <UiFieldDescription>{{ giftDescription }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-gift-toggle" v-model="state.is_gift" />
                </UiField>
                <div v-if="state.is_gift" class="space-y-4 px-4 pb-4" @click.stop>
                  <template v-if="!isPickup">
                    <UiField>
                      <UiFieldLabel for="gift-recipient-name">Nome de quem recebe</UiFieldLabel>
                      <UiInput id="gift-recipient-name" v-model="state.recipient_name" autocomplete="shipping name" enterkeyhint="next" class="h-11" placeholder="Ex: Maria Silva" @keydown.enter.prevent="focusCheckoutControl('gift-recipient-phone')" />
                      <UiFieldError v-if="fieldErrors.recipient_name" :errors="fieldErrors.recipient_name" />
                    </UiField>
                    <UiField>
                      <UiFieldLabel for="gift-recipient-phone">Telefone de quem recebe</UiFieldLabel>
                      <UiInput id="gift-recipient-phone" v-model="state.recipient_phone" type="tel" inputmode="tel" autocomplete="shipping tel" enterkeyhint="done" class="h-11" placeholder="(43) 99999-0000" />
                      <UiFieldError v-if="fieldErrors.recipient_phone" :errors="fieldErrors.recipient_phone" />
                    </UiField>
                    <p class="shop-meta">O endereço de entrega escolhido acima é o de quem vai receber o presente.</p>
                  </template>
                  <UiField>
                    <UiFieldLabel for="gift-message">Mensagem do presente</UiFieldLabel>
                    <UiTextarea id="gift-message" v-model="state.gift_message" :rows="2" placeholder="Ex: Feliz aniversário! Com carinho." />
                  </UiField>
                  <UiField orientation="horizontal">
                    <UiFieldContent class="gap-1">
                      <UiFieldTitle>Sem preços no papel</UiFieldTitle>
                      <UiFieldDescription data-gift-hide-values-description>{{ giftHideValuesDescription }}</UiFieldDescription>
                    </UiFieldContent>
                    <UiSwitch id="gift-hide-values" v-model="state.gift_hide_values" />
                  </UiField>
                </div>
              </UiFieldLabel>

              <!-- Observação: clone do toggle de fidelidade. Ligar expande o
                   card; o campo aparece no espaço interno (sem traços nem
                   divisórias). Desligar é o próprio dismiss (limpa a nota). -->
              <UiFieldLabel for="checkout-notes-toggle" class="bg-card has-data-[state=checked]:bg-card" data-checkout-notes-box>
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>Adicionar observação</UiFieldTitle>
                    <UiFieldDescription>{{ notesCopy.description }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-notes-toggle" v-model="notesOpen" />
                </UiField>
                <div v-if="notesOpen" class="px-4 pb-4">
                  <UiTextarea
                    id="checkout-notes"
                    v-model="state.notes"
                    :rows="2"
                    :placeholder="notesCopy.placeholder"
                    @click.stop
                  />
                </div>
              </UiFieldLabel>

              <!-- Pré-marcado (omotenashi — default na hospitalidade, controle
                   preservado). O interruptor governa os PADRÕES: qual endereço vem
                   escolhido, a forma de pagamento e o horário. O endereço novo entra na
                   agenda do cliente de qualquer jeito, e tem que entrar — ninguém
                   redigita CEP a cada pedido. O título antigo ("Salvar para a próxima
                   vez"), logo abaixo do campo de endereço, se lia como "salvar este
                   endereço"; o novo diz o que o interruptor de fato cobre. -->
              <UiFieldLabel for="checkout-save-default" class="bg-card has-data-[state=checked]:bg-card" data-checkout-save-default>
                <UiField orientation="horizontal">
                  <UiFieldContent class="gap-1">
                    <UiFieldTitle>Lembrar destas escolhas</UiFieldTitle>
                    <UiFieldDescription>{{ rememberDescription }}</UiFieldDescription>
                  </UiFieldContent>
                  <UiSwitch id="checkout-save-default" v-model="state.save_as_default" />
                </UiField>
              </UiFieldLabel>

            </CheckoutProgressSection>
          </div>

          <!-- Tem mais abaixo: o sentinela fecha o CONTEÚDO, antes do card (que
               é chrome, não conteúdo — depois dele o fim nunca chegaria, porque
               o card fica sempre entre o sentinela e a área observada).
               As duas affordances convivem de propósito: o card diz qual é a
               próxima ação, a dica diz que ainda há opções que a pessoa não viu
               (cupom, presente e observação ficam abaixo da dobra no pagamento). -->
          <MoreBelow />

          <!-- CARD SUSPENSO DA AÇÃO — o mesmo objeto da sacola, e agora o mesmo
               mecanismo: `.shop-action-dock` flutua ACIMA da navegação inferior
               por ALTURA, não por prioridade de empilhamento. A barra fixa que
               vivia aqui empatava em `z-40` com a navegação (topo 606 contra
               602, medido em 375x667) e ficava escondida atrás dela: o total e
               o "Resumo" nunca apareciam no celular.

               O `sticky bottom-20` que a substituiu não prendia de verdade:
               sticky só gruda na base enquanto o CONTAINER cobre aquela linha,
               e quando ele acaba o card sobe junto com a rolagem. Aqui isso
               também estragava os dois mecanismos vizinhos, porque
               `measureBottomObstruction` descarta obstáculo que subiu da
               metade da tela — o próximo foco passava a mirar uma linha que o
               card ainda tapava, e a dica "tem mais abaixo" sumia cedo demais.

               `md:sticky md:bottom-4` porque a navegação inferior some em `md`
               e a folga de 80px deixa de ter o que limpar (e o dock é inerte
               acima de `md`). `lg:static` porque a partir de `lg` o resumo
               lateral assume e o card volta ao fim do fluxo. -->
          <div
            v-show="!keyboardActive"
            ref="actionDock"
            class="shop-action-dock shop-stack-tight rounded-lg border border-ink bg-ink p-3 text-ink-foreground shadow-lg md:sticky md:bottom-4 lg:static"
            :class="{ 'shop-action-dock--in-flow': !actionDockFloats }"
            data-checkout-action-card
            :data-focus-obstruction="actionDockFloats ? '' : undefined"
          >
            <!-- A linha do total abre o resumo. Era um botão "Resumo" próprio na
                 barra invisível; aqui ela é o toque, e o ícone de nota diz isso.
                 A partir de `lg` o resumo lateral já está aberto ao lado e a folha
                 não existe (`lg:hidden` no conteúdo): a linha vira só o total, sem
                 toque, em vez de abrir um véu vazio (#3281). -->
            <UiButton
              variant="ghost"
              class="h-auto w-full p-0 text-left hover:bg-transparent lg:hidden"
              aria-label="Ver o resumo do pedido"
              data-checkout-open-receipt
              @click="openReceiptSheet"
            >
              <span class="flex w-full flex-wrap items-baseline justify-between gap-x-2">
                <span class="flex items-center gap-2 shop-body text-ink-foreground/80">
                  <Icon name="lucide:receipt-text" class="size-4 shrink-0" />
                  Total do pedido
                </span>
                <span class="shop-price-strong shrink-0" data-decisive="total">{{ checkoutTotalDisplay }}</span>
              </span>
            </UiButton>
            <p class="hidden w-full flex-wrap items-baseline justify-between gap-x-2 lg:flex" data-checkout-total-line>
              <span class="shop-body text-ink-foreground/80">Total do pedido</span>
              <span class="shop-price-strong shrink-0" data-decisive="total">{{ checkoutTotalDisplay }}</span>
            </p>
            <template v-if="!bagGoneNoticeShowing">
              <UiButton
                size="lg"
                :icon="primaryAction.icon"
                class="w-full shop-action-inverted"
                :loading="primaryAction.loading"
                :disabled="primaryAction.disabled"
                @click="primaryAction.run"
              >
                {{ primaryAction.label }}
              </UiButton>
              <p v-if="primaryAction.reason" class="text-center text-sm text-ink-foreground/80" data-decisive="state">
                {{ primaryAction.reason }}
              </p>
            </template>
          </div>

          <BottomSheet
            v-model:open="confirmOpen"
            max-width="md"
            title="Revise seu pedido"
            :description="confirmSheetDescription"
            @open-auto-focus="onReviewOpened"
            @close-auto-focus="onReviewClosed"
          >
            <!-- Superfície única, diagramação enxuta. O corpo rola; o rodapé fica
                 mínimo (Total + 1 ação) e sempre visível — nada vaza da tela. -->
            <div class="px-4 py-4">
              <UiAlert v-if="serverError" :variant="confirmedTrackingUrl || confirmationUnknown ? 'warning' : 'destructive'" class="mb-4">
                <UiAlertTitle>{{ confirmedTrackingUrl ? 'Pedido confirmado' : confirmationUnknown ? uncertainTitle : 'Confira os dados' }}</UiAlertTitle>
                <UiAlertDescription>{{ serverError }}</UiAlertDescription>
            <UiButton v-if="confirmedTrackingUrl" :to="confirmedTrackingUrl">Acompanhar pedido</UiButton>
            <UiButton v-else-if="confirmationUnknown" variant="outline" to="/conta/pedidos">Ver meus pedidos</UiButton>
              </UiAlert>

              <!-- O quê: itens com o valor da linha. A revisão é o último lugar antes
                   de enviar o pedido: a conta inteira aparece sempre, com ou sem
                   cupom e frete (beta 06/11). -->
              <ul class="space-y-1" data-review-items>
                <li v-for="line in cart?.items || []" :key="line.line_id" class="shop-body">
                  <span class="flex items-baseline justify-between gap-3">
                    <span class="min-w-0">
                      <span class="font-semibold tabular-nums">{{ line.qty }}×</span>
                      {{ line.name }}
                    </span>
                    <CartLineTotal :line="line" value-class="tabular-nums" class="shrink-0" data-review-line-total />
                  </span>
                  <!-- A espera = história do MESMO dia (fila de espera da produção).
                       Pedido agendado para outra data não tem fila: a reserva nasce na
                       data com prioridade de pedido, e o "Quando" já conta o combinado.
                       A frase é a promessa do servidor, a mesma da sacola ("Fica pronto
                       amanhã, quinta, a partir das 15h"); o selo e o "Previsto para" só
                       sobram quando a promessa não veio. -->
                  <template v-if="reviewWaitlist(line, state.delivery_date, shopToday)">
                    <span v-if="cartLinePromise(line.promise)" class="flex items-start gap-1 shop-meta text-foreground" data-review-line-promise data-decisive="availability">
                      <Icon name="lucide:clock" class="mt-px size-3.5 shrink-0" />
                      {{ cartLinePromise(line.promise) }}
                    </span>
                    <template v-else>
                      <UiBadge variant="outline" class="ml-1 align-middle" data-decisive="availability">Lista de espera</UiBadge>
                      <span v-if="reviewWaitlist(line, state.delivery_date, shopToday)?.notice" class="ml-1 shop-meta" data-decisive="availability">{{ reviewWaitlist(line, state.delivery_date, shopToday)?.notice }}</span>
                    </template>
                  </template>
                  <!-- Preparado na hora: promessa declarada da casa, eixo próprio.
                       Não disputa com a lista de espera acima — as duas podem valer
                       para o mesmo item, e cada uma responde uma pergunta. -->
                  <UiBadge v-if="line.is_made_to_order && line.made_to_order_label" variant="outline" class="ml-1 align-middle">
                    {{ line.made_to_order_label }}
                  </UiBadge>
                  <!-- Observação do item: a MESMA marca da sacola (selo + uma linha). -->
                  <CartLineNoteMark v-if="line.notes" :notes="line.notes" class="mt-1" data-review-line-note />
                </li>
              </ul>

              <!-- Itens em lista de espera: o "avisamos quando ficar pronto" vive AQUI
                   (revisão), não na sacola. Na sacola o aviso orienta a enviar o pedido.
                   Só para pedido do MESMO dia — agendado não tem fila. -->
              <p v-if="hasReviewWaitlist" class="mt-2 shop-meta">
                <Icon name="lucide:clock" class="mr-1 inline size-3.5 align-text-bottom" />
                Itens em lista de espera: avisamos quando ficarem prontos.
              </p>

              <UiSeparator class="my-3" />

              <!-- Como/onde/pgto/contato: ícone + valor, sem rótulo (o valor já se explica). -->
              <OrderSummaryRows :rows="reviewSummaryRows" />

              <!-- Cartão do presente / observação: bilhete em superfície destacada (muted). -->
              <p v-if="state.is_gift && state.gift_message" class="mt-3 rounded-lg bg-muted/50 p-3">
                <span class="mb-0.5 block shop-kicker">Cartão do presente</span>
                <span class="shop-body italic">“{{ state.gift_message }}”</span>
              </p>
              <p v-if="state.notes" class="mt-3 rounded-lg bg-muted/50 p-3">
                <span class="mb-0.5 block shop-kicker">Observação</span>
                <span class="shop-body">{{ state.notes }}</span>
              </p>

              <!-- Resumo de valores: compacto e inline (sem empilhar). O Total vai no rodapé. -->
              <template v-if="cart && !draftSyncing && !deliveryDraftFailed">
                <UiSeparator class="my-3" />
                <dl class="space-y-1 text-sm" data-review-bill>
                  <div class="flex items-baseline justify-between gap-3">
                    <dt class="shop-muted">Subtotal</dt>
                    <dd class="text-right tabular-nums" data-decisive="price">
                      {{ cart.lines_subtotal_display }}
                      <span v-if="promoSavingsNote(cart)" class="block shop-meta" data-review-promo-savings>{{ promoSavingsNote(cart) }}</span>
                    </dd>
                  </div>
                  <div v-for="discount in cart.order_discount_lines" :key="discount.label" class="flex items-baseline justify-between gap-3">
                    <dt class="shop-muted">{{ discount.label }}</dt>
                    <dd class="tabular-nums text-promotion" data-decisive="price">{{ discountDisplay(discount.amount_display) }}</dd>
                  </div>
                  <div v-if="cart.delivery_fee_display" class="flex items-baseline justify-between gap-3">
                    <dt class="shop-muted">Entrega<span v-if="cart.delivery_distance_display"> · {{ cart.delivery_distance_display }}</span></dt>
                    <dd class="tabular-nums">{{ cart.delivery_fee_display }}</dd>
                  </div>
                </dl>
                <p v-if="cart.group_savings_message" class="mt-2 shop-body text-primary">{{ cart.group_savings_message }}</p>
              </template>

              <!-- Antes de enviar: o que acontece com o dinheiro, card dentro do card (a
                   superfície Faubourg, a mesma do login). É condição, não alerta nem
                   sucesso: tom neutro da superfície, sem cor semântica (dono e coordenação,
                   19/11/2026). A frase vem do servidor (P1-06): o que acontece com o
                   dinheiro, até quando a loja confirma e o que acontece se não confirmar. -->
              <section
                v-if="moneyNotice"
                class="shop-surface-faubourg mt-3 rounded-lg border p-4"
                aria-labelledby="review-before-sending-title"
                data-review-before-sending
              >
                <p id="review-before-sending-title" class="shop-kicker">Antes de enviar</p>
                <div class="mt-2 flex items-start gap-3" data-review-money-notice>
                  <Icon name="lucide:shield-check" class="mt-0.5 size-5 shrink-0" />
                  <p class="shop-body">{{ moneyNotice }}</p>
                </div>
              </section>
              <!-- Retirada paga, de hoje ou de outro dia: a regra do pedido não retirado, dita antes de
                   enviar e de pagar (#2613, decisão do dono de 18/11/2026). Fica FORA do
                   card, numa linha logo abaixo dele: dentro, com as duas frases, o card
                   passava da dobra no celular (coordenação, 19/11/2026). A frase é a da
                   cláusula dos Termos, palavra por palavra: `tests/legalUnclaimedOrder.test.ts`
                   reprova se uma mudar sem a outra. -->
              <p v-if="showUnclaimedOrderRule" class="mt-3 shop-meta" data-review-unclaimed-rule>
                Pedido não retirado até o fim do expediente do dia combinado: os itens de revenda
                voltam inteiros; dos itens feitos para a encomenda, retemos até 40% do valor para
                cobrir o custo de produção, e o restante volta pelo mesmo meio de pagamento.
                <NuxtLink to="/termos#pickup-and-delivery" target="_blank" class="underline underline-offset-2">Termos de uso</NuxtLink>
              </p>
            </div>

            <!-- Rodapé mínimo: Total em destaque + UM botão full-width. Sem botão amarelo,
                 sem larguras diferentes, sem estourar. Fechar = X no topo. -->
            <template #footer>
              <div class="space-y-2">
                <div class="flex items-baseline justify-between gap-3">
                  <span class="shop-kicker">Total</span>
                  <span class="shop-price-strong" data-decisive="total">{{ checkoutTotalDisplay }}</span>
                </div>
                <UiButton
                  :loading="submitting"
                  :disabled="submitDisabled"
                  icon="lucide:check"
                  size="lg"
                  class="w-full"
                  @click="submitCheckout"
                >
                  {{ checkoutActionLabel }}
                </UiButton>
              </div>
            </template>
          </BottomSheet>

          <BottomSheet
            v-model:open="receiptOpen"
            content-class="lg:hidden"
            title="Seu pedido"
            :description="confirmSheetDescription"
          >
            <div class="space-y-4 p-4">
              <UiItemGroup class="gap-2">
                <UiItem v-for="line in cart?.items || []" :key="line.line_id" size="sm" class="items-start bg-transparent p-0">
                  <UiItemContent>
                    <UiItemTitle class="line-clamp-1">{{ line.qty }}× {{ line.name }}</UiItemTitle>
                    <UiItemDescription>{{ linePrice(line).current }} cada</UiItemDescription>
                  </UiItemContent>
                  <UiItemActions><CartLineTotal :line="line" stacked /></UiItemActions>
                </UiItem>
              </UiItemGroup>
              <CartSummaryBreakdown v-if="cart && !draftSyncing && !deliveryDraftFailed" :cart="cart" compact />
              <p v-else-if="cart" role="status" class="shop-muted">{{ checkoutTotalDisplay }}</p>
            </div>
          </BottomSheet>

          <!-- Trocar telefone = entrar com outra conta: confirmação obrigatória. -->
          <UiAlertDialog v-model:open="changePhoneOpen">
            <UiAlertDialogContent>
              <UiAlertDialogHeader>
                <UiAlertDialogTitle>{{ checkout.copy.switch_account_title || 'Trocar conta?' }}</UiAlertDialogTitle>
                <UiAlertDialogDescription>
                  {{ checkout.copy.switch_account_message || 'Você vai sair desta conta para entrar com outro telefone. Sua sacola continua guardada.' }}
                </UiAlertDialogDescription>
              </UiAlertDialogHeader>
              <UiAlertDialogFooter>
                <UiAlertDialogCancel>{{ checkout.copy.switch_account_keep || 'Manter conta' }}</UiAlertDialogCancel>
                <UiAlertDialogAction @click="goToAuthRoute">{{ checkout.copy.switch_account_confirm || 'Trocar conta' }}</UiAlertDialogAction>
              </UiAlertDialogFooter>
            </UiAlertDialogContent>
          </UiAlertDialog>
        </template>
      </section>

      <aside class="hidden space-y-4 lg:block lg:sticky lg:top-24 lg:self-start">
        <UiCard v-if="checkout" class="gap-0 overflow-hidden py-0">
          <div class="p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <UiCardTitle>Seu pedido</UiCardTitle>
                <UiCardDescription>{{ formatCount(cart?.items_count || 0, 'item', 'itens') }}</UiCardDescription>
              </div>
              <p class="shop-price-strong" data-decisive="total">{{ checkoutTotalDisplay }}</p>
            </div>
            <div class="mt-4 space-y-2 shop-muted" data-checkout-live-summary>
              <div class="flex items-center gap-2">
                <Icon :name="fulfillmentIcon" class="size-4 shrink-0" />
                <span class="truncate">{{ fulfillmentSummary || fulfillmentLabel }}</span>
              </div>
              <div v-if="state.payment_method" class="flex items-center gap-2">
                <Icon name="lucide:credit-card" class="size-4 shrink-0" />
                <span class="truncate">{{ paymentMethodLabel }}</span>
              </div>
            </div>
          </div>

          <UiSeparator />

          <UiCardContent class="space-y-4 p-4">
            <UiItemGroup class="gap-2">
              <UiItem v-for="line in cart?.items || []" :key="line.line_id" size="sm" class="items-start bg-transparent p-0">
                <UiItemContent>
                  <UiItemTitle class="line-clamp-1">{{ line.qty }}× {{ line.name }}</UiItemTitle>
                  <UiItemDescription>{{ linePrice(line).current }} cada</UiItemDescription>
                </UiItemContent>
                <UiItemActions><CartLineTotal :line="line" stacked /></UiItemActions>
              </UiItem>
            </UiItemGroup>

            <CartSummaryBreakdown v-if="cart && !draftSyncing && !deliveryDraftFailed" :cart="cart" compact />
            <p v-else-if="cart" role="status" class="shop-muted">{{ checkoutTotalDisplay }}</p>
          </UiCardContent>
        </UiCard>

        <UiAlert v-if="checkout?.support_whatsapp_url" variant="info">
          <UiAlertTitle>Atendimento rápido</UiAlertTitle>
          <UiAlertDescription>
            <UiButton :href="checkout.support_whatsapp_url" target="_blank" variant="outline" size="sm" icon="lucide:message-circle" class="mt-2">
              WhatsApp
            </UiButton>
          </UiAlertDescription>
        </UiAlert>
      </aside>
    </div>

  </main>
</template>
