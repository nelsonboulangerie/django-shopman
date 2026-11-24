// EXPERIMENT(duvida-no-ponto) remove_after 2027-02-20
// OC-33 B3 nas páginas: só a sacola mostra as perguntas do ponto, e só na versão B.
// Pagamento e produto não têm ponto (nenhuma pergunta repete o que a tela já mostra,
// OC-31): as formas de pagamento estão nas opções, e o aviso de alérgenos em
// "Ingredientes e restrições". Na A (ou sem o experimento), nada muda.
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mountSuspended, mockNuxtImport, registerEndpoint } from '@nuxt/test-utils/runtime'

import CartPage from '~/pages/sacola.vue'
import CheckoutPage from '~/pages/finalizar.vue'
import ProductPage from '~/pages/produto/[sku].vue'
import { STOREFRONT_SHELL_KEY } from '~/composables/useStorefrontShell'
import type { CartProjection, CheckoutProjection, ShellResponse } from '~/types/shopman'
import productContract from '../../../../contracts/projections/storefront_product_detail.json'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

const FAQ = [
  { ref: 'delivery', question: 'Vocês fazem entrega?', answer: 'Sim. Fazemos entrega.' },
  { ref: 'hours', question: 'Quais são os horários de funcionamento?', answer: 'Seg a sáb: 7h às 19h' },
  { ref: 'payment', question: 'Como posso pagar?', answer: 'Você paga com Pix ou dinheiro.' },
  { ref: 'preorder', question: 'Posso encomendar para outro dia?', answer: 'Sim. Ao finalizar o pedido, você escolhe o dia.' },
  { ref: 'allergens', question: 'Os produtos têm alérgenos?', answer: 'Produzimos em cozinha compartilhada.' }
]

function setShell (variant: 'a' | 'b' | null) {
  useNuxtApp().payload.data[STOREFRONT_SHELL_KEY] = {
    shell: { faq: FAQ, experience: variant ? [{ ref: 'duvida-no-ponto', variant }] : [] },
    cart: {}
  } as unknown as ShellResponse
}

const questionsAt = (root: { find: (s: string) => { exists: () => boolean, findAll: (s: string) => Array<{ text: () => string }> } }, point: string) => {
  const section = root.find(`[data-faq-point="${point}"]`)
  return section.exists() ? section.findAll('[data-slot="accordion-trigger"]').map(t => t.text()) : null
}

// ── sacola ───────────────────────────────────────────────────────────────────

const cart = {
  items: [{
    line_id: 'line-1', sku: 'CRO', name: 'Croissant', qty: 1, unit_price_q: 900, total_price_q: 900,
    price_display: 'R$ 9,00', line_total_display: 'R$ 9,00', line_total_struck_display: null, list_price_q: 900,
    image_url: null, discount_label: null, promo_price_display: null, is_available: true, availability_warning: null,
    available_qty: null, is_notifiable: false, is_notify_subscribed: false, is_made_to_order: false, made_to_order_label: '',
    is_awaiting_confirmation: false, is_ready_for_confirmation: false, confirmation_deadline_iso: null,
    confirmation_deadline_display: null, planned_for_date: null, planned_for_notice: null, earlier_available_date: null,
    notes: '', promise: null
  }],
  items_count: 1,
  is_empty: false,
  empty_title: '',
  empty_message: '',
  summary_pending: false,
  subtotal_q: 900,
  subtotal_display: 'R$ 9,00',
  lines_subtotal_q: 900,
  lines_subtotal_display: 'R$ 9,00',
  discount_lines: [],
  order_discount_lines: [],
  grand_total_q: 900,
  grand_total_display: 'R$ 9,00',
  has_unavailable_items: false,
  minimum_order_progress: null,
  delivery_minimum_progress: null,
  free_delivery_progress: null,
  upsell: null,
  actions: [
    { ref: 'checkout', kind: 'navigate', label: 'Finalizar pedido', priority: 'primary', enabled: true, reason: '', method: 'GET', href: '/finalizar' }
  ],
  revision: 1
} as unknown as CartProjection

registerEndpoint('/api/v1/storefront/cart/', () => ({ cart, server_now_iso: new Date().toISOString() }))

async function openCart (variant: 'a' | 'b' | null) {
  clearNuxtData()
  setShell(variant)
  useState('storefront-cart').value = cart
  useState('storefront-cart-clock-offset').value = 0
  const page = await mountSuspended(CartPage)
  await flushPromises()
  return page
}

// ── checkout, na etapa do pagamento ──────────────────────────────────────────

const context = 'duvida-no-ponto-cart'
const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
const bakeDate = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`

const checkout = {
  copy: {},
  cart: {
    items: [{ sku: 'PAO', name: 'Pão', qty: 1, unit_price_q: 1500, total_q: 1500 }],
    is_empty: false,
    count: 1,
    subtotal_q: 1500,
    subtotal_display: 'R$ 15,00',
    grand_total_q: 1500,
    grand_total_display: 'R$ 15,00',
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
  payment_methods: [{ ref: 'pix', label: 'Pix' }, { ref: 'cash', label: 'Dinheiro' }],
  default_payment_method: 'pix',
  payment_constraints: {},
  actions: [{ ref: 'checkout', label: 'Confirmar pedido', enabled: true }],
  fulfillment_options: ['pickup'],
  has_pickup: true,
  has_delivery: false,
  pickup_slots: [{ ref: '19:30-20:00', label: '19:30 às 20:00', starts_at: '19:30', enabled: true, reason: '', is_earliest: true }],
  earliest_slot_ref: '19:30-20:00',
  pickup_grid: 'half_hour',
  loyalty_balance_q: 0,
  loyalty_value_display: null,
  max_preorder_days: 7,
  closed_dates_json: '[]',
  is_debug: false,
  support_whatsapp_url: '',
  pickup_hint: '',
  delivery_hint: '',
  card_provider: '',
  default_ddd: '43',
  available_dates: [bakeDate],
  closed_weekdays: []
} as unknown as CheckoutProjection

registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout }))
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

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

async function openCheckout (variant: 'a' | 'b' | null) {
  clearNuxtData()
  setShell(variant)
  store.clear()
  store.set('shopman-checkout-draft', JSON.stringify({
    version: 2,
    context,
    savedAt: Date.now(),
    activeStep: 'payment',
    state: { name: 'Marina', phone: '+5543999998888', fulfillment_type: 'pickup', delivery_date: bakeDate, payment_method: 'pix' }
  }))
  const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
  await vi.waitFor(() => expect(page.find('[data-checkout-payment-option]').exists()).toBe(true))
  return page
}

// ── produto ──────────────────────────────────────────────────────────────────

// O produto como o contrato o congela (`contracts/projections/storefront_product_detail.json`),
// sem alérgeno, ingredientes nem aviso da casa: nem assim a pergunta de alérgenos aparece.
registerEndpoint('/api/v1/storefront/products/PAO/', () => ({
  product: { ...productContract, sku: 'PAO', slug: 'PAO', promise: null, fomo_badges: [] },
  cart: null
}))

async function openProduct (variant: 'a' | 'b' | null) {
  clearNuxtData()
  setShell(variant)
  const page = await mountSuspended(ProductPage, { route: '/produto/PAO' })
  await vi.waitFor(() => expect(page.find('h1').exists()).toBe(true))
  return page
}

let mounted: { unmount: () => void } | null = null
beforeEach(() => { document.cookie = 'csrftoken=local-test'; navigateToMock.mockReset() })
afterEach(() => { mounted?.unmount(); mounted = null; document.body.innerHTML = '' })

describe('versão A (ou sem o experimento): nenhuma pergunta nos pontos', () => {
  for (const variant of [null, 'a'] as const) {
    it(`sacola, ${variant ?? 'sem experimento'}`, async () => {
      const page = await openCart(variant)
      mounted = page
      expect(page.find('aside').exists()).toBe(true)
      expect(page.find('[data-faq-point]').exists()).toBe(false)
    })

    it(`pagamento, ${variant ?? 'sem experimento'}`, async () => {
      const page = await openCheckout(variant)
      mounted = page
      expect(page.find('[data-faq-point]').exists()).toBe(false)
    })

    it(`produto, ${variant ?? 'sem experimento'}`, async () => {
      const page = await openProduct(variant)
      mounted = page
      expect(page.find('[data-faq-point]').exists()).toBe(false)
    })
  }
})

describe('versão B: só a sacola mostra perguntas', () => {
  it('sacola: entrega, horário e encomenda, no resumo', async () => {
    const page = await openCart('b')
    mounted = page
    expect(questionsAt(page, 'cart')).toEqual([
      'Vocês fazem entrega?',
      'Quais são os horários de funcionamento?',
      'Posso encomendar para outro dia?'
    ])
    expect(page.find('aside [data-faq-point="cart"]').exists()).toBe(true)
  })

  it('pagamento: nenhuma pergunta (as formas de pagamento já estão nas opções)', async () => {
    const page = await openCheckout('b')
    mounted = page
    expect(page.find('[data-faq-point]').exists()).toBe(false)
    expect(page.text()).not.toContain('Como posso pagar?')
  })

  it('produto: nenhuma pergunta (o aviso de alérgenos fica em "Ingredientes e restrições")', async () => {
    const page = await openProduct('b')
    mounted = page
    expect(page.find('[data-faq-point]').exists()).toBe(false)
    expect(page.text()).not.toContain('Os produtos têm alérgenos?')
  })
})

// X13: a versão muda apresentação, nunca preço, total, disponibilidade, estado nem as
// formas de pagamento oferecidas. Os decisivos da tela são os mesmos em A e em B.
type Found = { attributes: (name: string) => string | undefined, text: () => string }
type Page = { findAll: (selector: string) => Found[], unmount: () => void }

const decisives = (page: Page) =>
  page.findAll('[data-decisive]').map(node => `${node.attributes('data-decisive')}=${node.text()}`)
const paymentOptions = (page: Page) =>
  page.findAll('[data-checkout-payment-option]').map(node => node.attributes('value') ?? node.attributes('id'))

describe('X13: A e B mostram os mesmos decisivos', () => {
  it('sacola', async () => {
    const a = await openCart('a')
    const inA = decisives(a)
    a.unmount()
    const b = await openCart('b')
    mounted = b
    expect(inA.length).toBeGreaterThan(0)
    expect(decisives(b)).toEqual(inA)
  })

  it('pagamento', async () => {
    const a = await openCheckout('a')
    const inA = { decisives: decisives(a), options: paymentOptions(a) }
    a.unmount()
    document.body.innerHTML = ''
    const b = await openCheckout('b')
    mounted = b
    expect(inA.options).toHaveLength(2)
    expect({ decisives: decisives(b), options: paymentOptions(b) }).toEqual(inA)
  })

  it('produto', async () => {
    const a = await openProduct('a')
    const inA = decisives(a)
    a.unmount()
    const b = await openProduct('b')
    mounted = b
    expect(inA.length).toBeGreaterThan(0)
    expect(decisives(b)).toEqual(inA)
  })
})
