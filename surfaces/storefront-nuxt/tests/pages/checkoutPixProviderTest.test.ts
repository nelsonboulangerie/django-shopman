import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport, registerEndpoint } from '@nuxt/test-utils/runtime'
import { setResponseStatus } from 'h3'

import CheckoutPage from '~/pages/finalizar.vue'
import type { CheckoutProjection } from '~/types/shopman'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

const context = 'pix-provider-test-cart'
// Data relativa ao relógio: literal fixo vira passado e o passo "Quando" reprova.
const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
const bakeDate = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`
const providerMessage = (
  'Ambiente de testes: a Efí simula a confirmação de Pix de até R$ 10,00. ' +
  'Para continuar, troque a forma de pagamento ou ajuste os itens do pedido.'
)

function projection (totalQ = 1001, constraints: Record<string, unknown> | null = null): CheckoutProjection {
  const display = `R$ ${(totalQ / 100).toFixed(2).replace('.', ',')}`
  return {
    copy: {},
    cart: {
      items: [{ sku: 'PAO', name: 'Pão', qty: 1, unit_price_q: totalQ, total_q: totalQ }],
      is_empty: false,
      count: 1,
      subtotal_q: totalQ,
      subtotal_display: display,
      grand_total_q: totalQ,
      grand_total_display: display,
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
    payment_constraints: constraints ?? {
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
    available_dates: [bakeDate],
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
let mounted: { unmount: () => void } | null = null
afterEach(() => { mounted?.unmount(); mounted = null })
let servedAfterRefusal: CheckoutProjection | null = null
let checkoutPosts = 0
registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: served }))
// O servidor recusa pelo total AUTORITATIVO (depois de todos os modifiers), que
// pode ter mudado desde que a tela carregou: a tela vê R$ 10,00, o servidor vê R$ 10,50.
registerEndpoint('/api/v1/checkout/', {
  method: 'POST',
  handler: (event) => {
    checkoutPosts += 1
    if (servedAfterRefusal) served = servedAfterRefusal
    setResponseStatus(event, 422)
    return {
      detail: 'Ambiente de testes: a Efí simula a confirmação de Pix de até R$ 10,00; o total deste pedido é R$ 10,50. Para continuar, troque a forma de pagamento ou ajuste os itens do pedido.',
      error_code: 'pix_test_amount_limit',
      context: { method: 'pix', current_amount_q: 1050, max_amount_q: 1000, actions: ['change_payment_method', 'edit_cart'] }
    }
  }
})
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

beforeEach(() => {
  navigateToMock.mockReset()
  servedAfterRefusal = null
  checkoutPosts = 0
  document.body.innerHTML = ''
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
      delivery_date: bakeDate,
      payment_method: 'pix'
    }
  }))
})

describe('checkout Pix — recuperação do limite temporário', () => {
  it('renderiza alerta, bloqueia o avanço e executa as duas recuperações', async () => {
    served = projection()
    clearNuxtData()
    const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
    mounted = page

    const alert = page.find('[data-pix-provider-test]')
    expect(alert.exists()).toBe(true)
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.attributes('aria-live')).toBe('assertive')
    expect(alert.text()).toContain(providerMessage)

    const review = page.findAll('button').find(button => button.text().includes('Revisar pedido'))
    expect(review?.attributes('disabled')).toBeDefined()
    // Botão apagado no lugar mais nobre da tela diz o que falta.
    expect(page.text()).toContain('Troque a forma de pagamento ou ajuste os itens.')

    const adjust = page.findAll('button').find(button => button.text().includes('Ajustar itens'))
    await adjust!.trigger('click')
    expect(navigateToMock).toHaveBeenCalledWith('/sacola')

    const change = page.findAll('button').find(button => button.text().includes('Trocar forma de pagamento'))
    await change!.trigger('click')
    expect(page.find('[data-pix-provider-test]').exists()).toBe(false)
    expect((document.activeElement as HTMLElement | null)?.id).toBe('checkout-payment-cash')
  })

  it('até R$ 10,00 inclusive: não bloqueia, não oferece saída e não manda trocar nada', async () => {
    served = projection(1000)
    clearNuxtData()
    const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
    mounted = page

    const alert = page.find('[data-pix-provider-test]')
    expect(alert.attributes('role')).toBe('status')
    expect(alert.text()).toContain('Este pedido está dentro do limite')
    // A frase que manda "trocar a forma de pagamento" contradiz "dentro do limite".
    expect(alert.text()).not.toContain('troque a forma de pagamento')
    expect(page.findAll('button').some(button => button.text().includes('Trocar forma de pagamento'))).toBe(false)
    expect(page.findAll('button').some(button => button.text().includes('Ajustar itens'))).toBe(false)
    const review = page.findAll('button').find(button => button.text().includes('Revisar pedido'))
    expect(review?.attributes('disabled')).toBeUndefined()
  })

  it('sem a constraint (produção ou Pix simulado) nada aparece, mesmo acima de R$ 10,00', async () => {
    served = projection(1500, {})
    clearNuxtData()
    const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
    mounted = page

    expect(page.find('[data-pix-provider-test]').exists()).toBe(false)
    const review = page.findAll('button').find(button => button.text().includes('Revisar pedido'))
    expect(review?.attributes('disabled')).toBeUndefined()
  })

  it('recusa do servidor vira o mesmo aviso com as duas saídas, não erro genérico', async () => {
    served = projection(1000)
    servedAfterRefusal = projection(1050)
    clearNuxtData()
    const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
    mounted = page

    const review = page.findAll('button').find(button => button.text().includes('Revisar pedido'))
    await review!.trigger('click')
    await nextTick()
    const confirm = Array.from(document.body.querySelectorAll('button'))
      .find(button => button.textContent?.includes('Confirmar pedido'))
    expect(confirm).toBeTruthy()
    confirm!.click()
    await vi.waitFor(() => { expect(checkoutPosts).toBe(1) })
    await vi.waitFor(() => {
      expect(page.find('[data-pix-provider-test]').attributes('role')).toBe('alert')
    })
    await flushPromises()

    const alert = page.find('[data-pix-provider-test]')
    expect(alert.text()).toContain('o total deste pedido é R$ 10,50')
    expect(page.findAll('button').some(button => button.text().includes('Trocar forma de pagamento'))).toBe(true)
    expect(page.findAll('button').some(button => button.text().includes('Ajustar itens'))).toBe(true)
    // Nenhum alerta destrutivo genérico ao lado do aviso.
    // O aviso é o único lugar da recusa: nem banner genérico, nem sheet de revisão aberta.
    const genericAlerts = Array.from(document.body.querySelectorAll('[data-slot="alert"]'))
      .filter(el => !el.hasAttribute('data-pix-provider-test') && el.textContent?.includes('o total deste pedido'))
    expect(genericAlerts).toHaveLength(0)
  })
})
