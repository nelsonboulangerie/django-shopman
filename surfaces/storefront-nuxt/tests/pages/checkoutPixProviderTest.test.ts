import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, mockNuxtImport, registerEndpoint } from '@nuxt/test-utils/runtime'

import CheckoutPage from '~/pages/finalizar.vue'
import type { CheckoutProjection } from '~/types/shopman'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

const context = 'pix-provider-test-cart'
const providerMessage = (
  'Ambiente de testes: a Efí simula a confirmação de Pix de até R$ 10,00. ' +
  'Para continuar, troque a forma de pagamento ou ajuste os itens do pedido.'
)

function projection (): CheckoutProjection {
  return {
    copy: {},
    cart: {
      items: [{ sku: 'PAO', name: 'Pão', qty: 1, unit_price_q: 1001, total_q: 1001 }],
      is_empty: false,
      count: 1,
      subtotal_q: 1001,
      subtotal_display: 'R$ 10,01',
      grand_total_q: 1001,
      grand_total_display: 'R$ 10,01',
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
      { ref: 'cash', label: 'Dinheiro' }
    ],
    default_payment_method: 'pix',
    payment_constraints: {
      pix: {
        provider: 'efi',
        environment: 'sandbox',
        mode: 'provider_test',
        is_test: true,
        max_amount_q: 1000,
        max_amount_display: 'R$ 10,00',
        message: providerMessage
      }
    },
    actions: [{ ref: 'checkout', label: 'Confirmar pedido', enabled: true }],
    fulfillment_options: ['pickup'],
    has_pickup: true,
    has_delivery: false,
    pickup_slots: [],
    earliest_slot_ref: null,
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
    available_dates: ['2026-09-15'],
    closed_weekdays: []
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
registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: served }))
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

beforeEach(() => {
  navigateToMock.mockReset()
  store.clear()
  store.set('shopman-checkout-draft', JSON.stringify({
    version: 2,
    context,
    savedAt: Date.now(),
    activeStep: 'payment',
    state: {
      name: 'Marina',
      phone: '+5543999998888',
      fulfillment_type: 'pickup',
      delivery_date: '2026-09-15',
      payment_method: 'pix'
    }
  }))
})

describe('checkout Pix — recuperação do limite temporário', () => {
  it('renderiza alerta, bloqueia o avanço e executa as duas recuperações', async () => {
    served = projection()
    clearNuxtData()
    const page = await mountSuspended(CheckoutPage, { attachTo: document.body })

    const alert = page.find('[data-pix-provider-test]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.attributes('aria-live')).toBe('assertive')
    expect(alert.text()).toContain(providerMessage)

    const review = page.findAll('button').find(button => button.text().includes('Revisar pedido'))
    expect(review?.attributes('disabled')).toBeDefined()

    const adjust = page.findAll('button').find(button => button.text().includes('Ajustar itens'))
    await adjust!.trigger('click')
    expect(navigateToMock).toHaveBeenCalledWith('/sacola')

    const change = page.findAll('button').find(button => button.text().includes('Trocar forma de pagamento'))
    await change!.trigger('click')
    expect(page.find('[data-pix-provider-test]').exists()).toBe(false)
    expect((document.activeElement as HTMLElement | null)?.id).toBe('checkout-payment-cash')
  })
})
