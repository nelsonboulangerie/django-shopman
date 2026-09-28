import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import CheckoutPage from '~/pages/finalizar.vue'
import type { CheckoutProjection } from '~/types/shopman'

function projection (overrides: Partial<CheckoutProjection> = {}): CheckoutProjection {
  return {
    copy: {},
    cart: {
      items: [], is_empty: false, items_count: 1, count: 1,
      subtotal_q: 5000, subtotal_display: 'R$ 50,00',
      grand_total_q: 5000, grand_total_display: 'R$ 50,00',
      actions: []
    },
    customer_phone: '+5543999998888',
    customer_name: 'Marina',
    is_authenticated: true,
    requires_authentication: false,
    auth_action: null,
    saved_addresses: [],
    preselected_address_id: null,
    payment_methods: [{ ref: 'cash', label: 'Dinheiro' }],
    default_payment_method: 'cash',
    actions: [{ ref: 'checkout', kind: 'mutation', label: 'Confirmar pedido', priority: 'primary', enabled: true, reason: '', method: 'POST', href: '' }],
    fulfillment_options: ['pickup', 'delivery'],
    default_fulfillment_type: 'pickup',
    has_pickup: true,
    has_delivery: true,
    pickup_slots: [],
    earliest_slot_ref: null,
    loyalty_balance_q: 0,
    loyalty_value_display: null,
    max_preorder_days: 7,
    closed_dates_json: '[]',
    is_debug: false,
    support_whatsapp_url: '',
    pickup_hint: 'Gratuita',
    delivery_hint: 'Taxa conforme a região',
    card_provider: '',
    stripe_test_cards: [],
    default_ddd: '43',
    available_dates: ['2026-09-28'],
    closed_weekdays: [],
    ...overrides
  } as unknown as CheckoutProjection
}

const store = new Map<string, string>()
beforeEach(() => {
  store.clear()
  document.body.innerHTML = ''
  document.documentElement.classList.remove('shop-form-keyboard-open')
})

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
registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: served }))
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

async function openCheckout (checkout: CheckoutProjection) {
  served = checkout
  clearNuxtData()
  const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
  await vi.waitFor(() => expect(page.find('[data-checkout-step="fulfillment"]').exists()).toBe(true))
  return page
}

async function chooseDelivery (page: Awaited<ReturnType<typeof mountSuspended>>) {
  await page.find('#checkout-fulfillment-delivery').trigger('click')
  await vi.waitFor(() => {
    expect(page.find('[data-checkout-step="address"]').attributes('data-checkout-section-state')).toBe('current')
  })
}

describe('checkout — foco é a próxima tarefa real', () => {
  it('cliente identificado começa com contato feito e somente Como receber atual', async () => {
    const page = await openCheckout(projection())
    const current = page.findAll('[data-checkout-section-state="current"]')
    expect(current).toHaveLength(1)
    expect(page.find('[data-checkout-contact-card]').attributes('data-checkout-section-state')).toBe('done')
    expect(page.find('[data-checkout-step="fulfillment"]').attributes('data-checkout-section-state')).toBe('current')
    page.unmount()
  })

  it('nome ausente deixa apenas Contato atual', async () => {
    const page = await openCheckout(projection({ customer_name: '' }))
    const current = page.findAll('[data-checkout-section-state="current"]')
    expect(current).toHaveLength(1)
    expect(page.find('[data-checkout-contact-card]').attributes('data-checkout-section-state')).toBe('current')
    expect(page.find('[data-checkout-step="fulfillment"]').attributes('data-checkout-section-state')).toBe('upcoming')
    page.unmount()
  })

  it('clicar Entrega abre o endereço e foca a busca, nunca o CPF', async () => {
    const page = await openCheckout(projection())
    await chooseDelivery(page)

    await vi.waitFor(() => expect((document.activeElement as HTMLElement | null)?.id).toBe('address-search'))
    expect((document.activeElement as HTMLElement | null)?.id).not.toBe('checkout-tax-id')
    page.unmount()
  })

  it('com endereço salvo, foca a escolha existente sem abrir teclado textual', async () => {
    const page = await openCheckout(projection({
      preselected_address_id: 7,
      saved_addresses: [{
        id: 7,
        label: 'home',
        label_key: 'home',
        label_custom: '',
        formatted_address: 'Rua das Flores, 123',
        route: 'Rua das Flores',
        street_number: '123',
        neighborhood: 'Centro',
        city: 'Londrina',
        state_code: 'PR',
        postal_code: '86000-000',
        complement: '',
        delivery_instructions: '',
        place_id: null,
        latitude: null,
        longitude: null,
        is_default: true
      }]
    } as Partial<CheckoutProjection>))
    await chooseDelivery(page)

    await vi.waitFor(() => expect((document.activeElement as HTMLElement | null)?.id).toBe('address-saved-7'))
    expect(document.activeElement).not.toBeInstanceOf(HTMLInputElement)
    page.unmount()
  })

  it('mínimo de entrega pendente mantém o foco em Como receber', async () => {
    const base = projection()
    const page = await openCheckout(projection({
      cart: {
        ...base.cart,
        delivery_minimum_progress: {
          remaining_q: 2000,
          remaining_display: 'R$ 20,00',
          percent: 60,
          add_more_cta: 'Adicionar mais itens'
        }
      }
    }))
    await page.find('#checkout-fulfillment-delivery').trigger('click')

    expect(page.find('[data-checkout-step="fulfillment"]').attributes('data-checkout-section-state')).toBe('current')
    expect(page.find('[data-checkout-step="address"]').attributes('data-checkout-section-state')).toBe('upcoming')
    page.unmount()
  })
})
