// WP-L05 do plano EXCELENCIA-STOREFRONT: o checkout que não envelhece e diz do dinheiro.
//   P1-06: a revisão diz o que acontece com o dinheiro, na forma de pagamento escolhida.
//   P1-11: faltou estoque no envio: a revisão fecha, a tela diz qual item e leva à sacola.
//   P2-08: "Hoje" é o hoje da loja (servidor), e a tela refaz a consulta ao voltar à aba.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport, registerEndpoint } from '@nuxt/test-utils/runtime'
import { setResponseStatus } from 'h3'

import CheckoutPage from '~/pages/finalizar.vue'
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
      context: { sku: 'TABAT', name: 'Tabatière', requested_qty: '1', is_paused: false }
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
    // A revisão fechou: a recusa tem um lugar só.
    await vi.waitFor(() => { expect(document.body.querySelector('[data-review-items]')).toBeNull() })
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
