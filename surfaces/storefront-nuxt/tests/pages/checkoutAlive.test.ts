// WP-L05 do plano EXCELENCIA-STOREFRONT: o checkout que não envelhece e diz do dinheiro.
//   P1-06: a revisão diz o que acontece com o dinheiro, na forma de pagamento escolhida.
//   P1-11: faltou estoque no envio: a revisão fecha, a tela diz qual item e leva à sacola.
//   #2687: com a folha pronta na recusa, as alternativas abrem na própria tela.
//   P2-08: "Hoje" é o hoje da loja (servidor), e a tela refaz a consulta ao voltar à aba.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport, registerEndpoint } from '@nuxt/test-utils/runtime'
import { setResponseStatus } from 'h3'

import CheckoutPage from '~/pages/finalizar.vue'
import { useCartState } from '~/composables/useCartState'
import type { CheckoutProjection } from '~/types/shopman'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

const context = 'checkout-alive-cart'
const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
// O aparelho acha que hoje é hoje; a loja (servidor) já está no dia seguinte.
const deviceTomorrow = iso(new Date(Date.now() + 24 * 60 * 60 * 1000))

const PIX_NOTICE = 'Você paga agora, pelo Pix. A loja confirma o pedido em até 5 minutos; se não confirmar, o valor volta inteiro para a mesma conta.'
const CARD_NOTICE = 'O valor fica reservado no cartão agora e só é cobrado quando a loja confirmar o pedido, em até 5 minutos. Se não confirmar, a reserva é desfeita e nada é cobrado.'

function projection (overrides: Record<string, unknown> = {}): CheckoutProjection {
  return {
    copy: {},
    cart: {
      items: [{
        line_id: 'L1', sku: 'TABAT', name: 'Tabatière', qty: 1, unit_price_q: 600, total_price_q: 600,
        price_display: 'R$ 6,00', promo_price_display: null, line_total_display: 'R$ 6,00',
        line_total_struck_display: null, list_price_q: 600, is_available: true
      }],
      is_empty: false,
      items_count: 1,
      subtotal_q: 600,
      subtotal_display: 'R$ 6,00',
      lines_subtotal_q: 600,
      lines_subtotal_display: 'R$ 6,00',
      promo_savings_q: 0,
      promo_savings_display: null,
      order_discount_lines: [],
      discount_lines: [],
      grand_total_q: 600,
      grand_total_display: 'R$ 6,00',
      revision: 1,
      draft_context: context,
      actions: []
    },
    customer_phone: '+5543999998888',
    customer_name: 'Marina',
    is_authenticated: true,
    requires_authentication: false,
    auth_action: null,
    saved_addresses: [],
    preselected_address_id: null,
    payment_methods: [
      { ref: 'pix', label: 'Pix' },
      { ref: 'card', label: 'Cartão' }
    ],
    default_payment_method: 'pix',
    payment_constraints: {},
    actions: [{ ref: 'checkout', label: 'Enviar pedido', enabled: true }],
    fulfillment_options: ['pickup'],
    has_pickup: true,
    has_delivery: false,
    pickup_slots: [{ ref: '19:30-20:00', label: '19h30 às 20h', starts_at: '19:30', enabled: true, reason: '', is_earliest: true }],
    earliest_slot_ref: '19:30-20:00',
    pickup_grid: 'half_hour',
    loyalty_balance_q: 0,
    loyalty_value_display: null,
    max_preorder_days: 7,
    closed_dates_json: '[]',
    is_debug: false,
    support_whatsapp_url: 'https://wa.me/554333231997',
    pickup_hint: '',
    delivery_hint: '',
    card_provider: '',
    default_ddd: '43',
    available_dates: [deviceTomorrow],
    closed_weekdays: [],
    today: deviceTomorrow,
    money_notices: [
      { method: 'pix', text: PIX_NOTICE },
      { method: 'card', text: CARD_NOTICE }
    ],
    ...overrides
  } as unknown as CheckoutProjection
}

const store = new Map<string, string>()
beforeAll(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, String(value)) },
      removeItem: (key: string) => { store.delete(key) },
      clear: () => { store.clear() }
    }
  })
})

let served: CheckoutProjection
let checkoutGets = 0
let checkoutPosts = 0
// A folha de alternativas que a recusa traz (#2687); null = servidor sem a folha.
let stockIssue: Record<string, unknown> | null = null
let mounted: { unmount: () => void } | null = null
afterEach(() => { mounted?.unmount(); mounted = null })

registerEndpoint('/api/v1/storefront/checkout/', () => {
  checkoutGets += 1
  return { checkout: served }
})
registerEndpoint('/api/v1/checkout/', {
  method: 'POST',
  handler: (event) => {
    checkoutPosts += 1
    setResponseStatus(event, 400)
    return {
      detail: 'Tabatière ficou indisponível antes de concluirmos o seu pedido.',
      field: 'checkout',
      errors: { checkout: 'Tabatière ficou indisponível antes de concluirmos o seu pedido.' },
      error_code: 'insufficient_supply',
      context: { sku: 'TABAT', name: 'Tabatière', requested_qty: '1', is_paused: false },
      stock_issue: stockIssue
    }
  }
})
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

function draft (paymentMethod: string) {
  store.set('shopman-checkout-draft', JSON.stringify({
    version: 2,
    context,
    savedAt: Date.now(),
    activeStep: 'payment',
    state: {
      name: 'Marina',
      phone: '+5543999998888',
      fulfillment_type: 'pickup',
      delivery_date: deviceTomorrow,
      payment_method: paymentMethod
    }
  }))
}

async function mountCheckout () {
  const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
  await vi.waitFor(() => expect(page.find('[data-checkout-step="fulfillment"]').exists()).toBe(true))
  return page
}

async function openReview (page: Awaited<ReturnType<typeof mountCheckout>>) {
  const review = page.findAll('button').find(button => button.text().includes('Revisar pedido'))
  await review!.trigger('click')
  await nextTick()
  await vi.waitFor(() => expect(document.body.querySelector('[data-review-items]')).toBeTruthy())
}

beforeEach(() => {
  navigateToMock.mockReset()
  checkoutGets = 0
  checkoutPosts = 0
  document.body.innerHTML = ''
  store.clear()
  served = projection()
  stockIssue = null
  useCartState().clearCart()
  clearNuxtData()
})

describe('checkout: a revisão diz o que acontece com o dinheiro', () => {
  it('no Pix: paga agora, a loja confirma em N minutos, e o valor volta se não confirmar', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    const notice = document.body.querySelector('[data-review-money-notice]')
    expect(notice?.textContent?.trim()).toBe(PIX_NOTICE)
  })

  it('no cartão: a frase é a da reserva, não a do Pix', async () => {
    draft('card')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    const notice = document.body.querySelector('[data-review-money-notice]')
    expect(notice?.textContent?.trim()).toBe(CARD_NOTICE)
  })

  it('sem prazo a prometer (servidor não mandou a frase), a revisão não inventa uma', async () => {
    served = projection({ money_notices: [] })
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    expect(document.body.querySelector('[data-review-money-notice]')).toBeNull()
  })
})

describe('checkout: a frase do dinheiro e a espera, sem dizer duas vezes', () => {
  it('a frase do dinheiro fica num card dentro do card da revisão', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    // "Antes de enviar": um card só (Faubourg, tom neutro), com a frase do dinheiro dentro.
    const card = document.body.querySelector('[data-review-before-sending]')
    expect(card?.classList.contains('shop-surface-faubourg')).toBe(true)
    expect(card?.classList.contains('border')).toBe(true)
    expect(card?.textContent).toContain('Antes de enviar')
    expect(card?.querySelector('[data-review-money-notice]')).toBeTruthy()
    // Condição do pedido não é alerta: nenhuma cor semântica no card.
    expect(card?.className).not.toMatch(/warning|destructive|success|amber|yellow|red-/)
  })

  it('na encomenda para retirar, o não retirado fica fora do card, na linha logo abaixo dele, com o link dos Termos', async () => {
    // Para a loja hoje é hoje: a data do rascunho (amanhã) é uma encomenda.
    served = projection({ today: iso(new Date()) })
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    const card = document.body.querySelector('[data-review-before-sending]')
    const rule = document.body.querySelector('[data-review-unclaimed-rule]')
    expect(rule).toBeTruthy()
    expect(card?.querySelector('[data-review-money-notice]')).toBeTruthy()
    // Com as duas frases dentro, o card passava da dobra no celular: a regra é a
    // linha seguinte ao card, em letra de apoio, e o card fica só com o dinheiro.
    expect(card?.contains(rule)).toBe(false)
    expect(card?.nextElementSibling).toBe(rule)
    expect(rule!.classList.contains('shop-meta')).toBe(true)
    expect(rule!.textContent).toContain('Pedido não retirado até o fim do expediente do dia combinado')
    expect(rule!.querySelector('a')?.getAttribute('href')).toBe('/termos#pickup-and-delivery')
    expect(document.body.querySelectorAll('[data-review-unclaimed-rule]')).toHaveLength(1)
    // A revisão abre do começo: o foco inicial não cai no link dos Termos, no fim da
    // revisão (o navegador rolaria a folha até ele e esconderia o primeiro item).
    expect(document.activeElement?.closest('[data-review-unclaimed-rule]')).toBeFalsy()
  })

  it('no pedido para hoje o card fica só com o dinheiro, sem a regra do não retirado', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    const card = document.body.querySelector('[data-review-before-sending]')
    expect(card?.querySelector('[data-review-money-notice]')).toBeTruthy()
    expect(document.body.querySelector('[data-review-unclaimed-rule]')).toBeNull()
  })

  function waitingCart (promise: unknown) {
    const base = projection()
    const line = { ...(base.cart.items[0] as Record<string, unknown>), is_awaiting_confirmation: true, planned_for_date: deviceTomorrow, planned_for_notice: 'Previsto para hoje', promise }
    return projection({ cart: { ...base.cart, items: [line], has_awaiting_confirmation_items: true } })
  }

  it('linha com a promessa de dia e hora não ganha a frase da lista de espera', async () => {
    served = waitingCart({ kind: 'batch', date: deviceTomorrow, ready_at: '15:00', day_label: 'hoje', text: 'Fica pronto hoje às 15h' })
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    expect(document.body.querySelector('[data-review-line-promise]')?.textContent).toContain('Fica pronto hoje às 15h')
    expect(document.body.textContent).not.toContain('Itens em lista de espera')
  })

  it('sem a promessa, a espera continua dita (selo e frase de antes)', async () => {
    served = waitingCart(null)
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    expect(document.body.querySelector('[data-review-line-promise]')).toBeNull()
    expect(document.body.textContent).toContain('Lista de espera')
    expect(document.body.textContent).toContain('Itens em lista de espera: avisamos quando ficarem prontos.')
  })
})

describe('checkout: faltou estoque no envio', () => {
  it('fecha a revisão, diz qual item e leva à sacola, em vez de um aviso que some', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await openReview(page)

    const send = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('Enviar pedido'))
    expect(send).toBeTruthy()
    send!.click()
    await vi.waitFor(() => { expect(checkoutPosts).toBe(1) })
    await vi.waitFor(() => { expect(page.find('[data-checkout-stock-refusal]').exists()).toBe(true) })
    await flushPromises()

    const alert = page.find('[data-checkout-stock-refusal]')
    expect(alert.text()).toContain('Tabatière ficou indisponível antes de concluirmos o seu pedido.')
    expect(alert.text()).not.toContain('carrinho')
    const bag = alert.findAll('a').find(link => link.text().includes('Abrir a sacola'))
    expect(bag?.attributes('href')).toBe('/sacola')
    // O título é a frase inteira: quebra em linhas, não corta com reticências.
    const title = alert.find('[data-slot="alert-title"]')
    expect(title.classes()).toContain('line-clamp-none')
    expect(title.classes()).not.toContain('line-clamp-1')
    // O alvo do foco é a moldura, na régua canônica; o respiro de cima mora dentro dela.
    const frame = page.find('[data-focus-target="stock-refusal"]')
    expect(frame.classes()).toEqual(expect.arrayContaining(['pt-4', '-mt-4']))
    expect(frame.find('[data-checkout-stock-refusal]').exists()).toBe(true)
    // Quem recebe o foco é a moldura: o botão dela fica com o teclado.
    await vi.waitFor(() => {
      expect(document.activeElement?.closest('[data-focus-target="stock-refusal"]')).toBeTruthy()
    })
    // A revisão fechou: a recusa tem um lugar só.
    await vi.waitFor(() => { expect(document.body.querySelector('[data-review-items]')).toBeNull() })
  })
})

describe('checkout: faltou estoque no envio, com as alternativas na própria tela (#2687)', () => {
  async function sendAndGetRefused (page: Awaited<ReturnType<typeof mountCheckout>>) {
    await openReview(page)
    const send = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('Enviar pedido'))
    send!.click()
    await vi.waitFor(() => { expect(checkoutPosts).toBe(1) })
    await vi.waitFor(() => { expect(page.find('[data-checkout-stock-refusal]').exists()).toBe(true) })
    await flushPromises()
  }

  beforeEach(() => {
    stockIssue = {
      title: 'Revise este item', error_code: 'insufficient_supply', sku: 'TABAT', name: 'Tabatière',
      requested_qty: 1, available_qty: 0, line_qty: null, line_id: 'L1', is_notifiable: true,
      substitutes: [{ sku: 'CROIS', name: 'Croissant', price_q: 800, price_display: 'R$ 8,00', can_order: true, available_qty: 9 }],
      actions: []
    }
  })

  it('a folha de alternativas sobe quando a revisão fecha, mirando a linha recusada', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await sendAndGetRefused(page)

    const { cartIssue } = useCartState()
    await vi.waitFor(() => { expect(cartIssue.value).not.toBeNull() })
    expect(cartIssue.value).toMatchObject({ sku: 'TABAT', line_id: 'L1', available_qty: 0, isNotifiable: true })
    expect(cartIssue.value?.substitutes.map(sub => sub.sku)).toEqual(['CROIS'])
    expect(navigateToMock).not.toHaveBeenCalled()
  })

  it('o aviso traz o botão que reabre a folha, e não manda à sacola', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await sendAndGetRefused(page)
    const { cartIssue, dismissCartIssue } = useCartState()
    await vi.waitFor(() => { expect(cartIssue.value).not.toBeNull() })
    dismissCartIssue()

    const alert = page.find('[data-checkout-stock-refusal]')
    expect(alert.text()).toContain('Veja o que dá para levar no lugar. O resto do pedido continua como você deixou.')
    expect(alert.findAll('a').find(link => link.text().includes('Abrir a sacola'))).toBeUndefined()
    await alert.find('[data-checkout-stock-alternatives]').trigger('click')

    expect(cartIssue.value).toMatchObject({ sku: 'TABAT', line_id: 'L1' })
  })

  it('a linha recusada mudou na sacola: o checkout relê e o aviso sai', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await sendAndGetRefused(page)
    const { setFromServer } = useCartState()
    const before = checkoutGets

    // A folha levou a cliente a trocar: a sacola do servidor já não tem a linha L1.
    const swapped = projection().cart as unknown as Record<string, unknown>
    const croissant = { ...(swapped.items as Array<Record<string, unknown>>)[0], line_id: 'L2', sku: 'CROIS', name: 'Croissant' }
    served = projection({ cart: { ...swapped, items: [croissant], revision: 2 } })
    setFromServer(served.cart)

    await vi.waitFor(() => { expect(checkoutGets).toBeGreaterThan(before) })
    await vi.waitFor(() => { expect(page.find('[data-checkout-stock-refusal]').exists()).toBe(false) })
  })
})

describe('checkout: o relógio é o da loja, e a tela não envelhece', () => {
  it('"Hoje" é o hoje da loja, mesmo com o aparelho um dia atrás', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page

    // A data do rascunho é "amanhã" no relógio do aparelho e "hoje" no da loja.
    const when = page.find('[data-checkout-step="when"]')
    expect(when.text()).toContain('Hoje')
    expect(when.text()).not.toContain('Amanhã')
  })

  it('ao voltar para a aba, refaz a consulta sozinha', async () => {
    draft('pix')
    const page = await mountCheckout()
    mounted = page
    await flushPromises()
    const before = checkoutGets

    let visibility: DocumentVisibilityState = 'hidden'
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
    document.dispatchEvent(new Event('visibilitychange'))
    await nextTick()
    visibility = 'visible'
    document.dispatchEvent(new Event('visibilitychange'))

    await vi.waitFor(() => { expect(checkoutGets).toBeGreaterThan(before) })
  })
})
