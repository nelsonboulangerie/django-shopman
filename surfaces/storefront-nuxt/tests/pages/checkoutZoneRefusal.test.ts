import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import CheckoutPage from '~/pages/finalizar.vue'
import AddressPicker from '~/components/AddressPicker.vue'
import { emptyAddressDraft, selectionFromDraft } from '~/presentation/address'
import type { CheckoutProjection } from '~/types/shopman'

// #3281, achados da J15 (#2569, item 4):
// 1. a recusa de área parava SOB o cabeçalho fixo: o reveal levava o aviso ao topo da
//    janela sem a régua do próximo foco, e só o botão "Mudar para retirada" aparecia;
// 2. no computador, a linha do total abria uma folha cujo conteúdo é `lg:hidden`: um véu
//    vazio sobre a página.

function projection (overrides: Partial<CheckoutProjection> = {}): CheckoutProjection {
  return {
    copy: {},
    cart: {
      items: [], is_empty: false, items_count: 2, count: 2, revision: 1,
      subtotal_q: 2600, subtotal_display: 'R$ 26,00',
      grand_total_q: 2600, grand_total_display: 'R$ 26,00',
      delivery_fee_q: null, delivery_zone_error: false,
      actions: []
    },
    customer_phone: '+5543999998888',
    customer_name: 'Lúcia',
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
    pickup_slots: [{ ref: '19:30-20:00', label: '19:30 às 20:00', starts_at: '19:30', enabled: true, reason: '', is_earliest: true }],
    earliest_slot_ref: '19:30-20:00',
    pickup_grid: 'half_hour',
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

const outside = {
  ...emptyAddressDraft(),
  route: 'Estrada do Limoeiro',
  street_number: '10',
  neighborhood: 'Irerê',
  city: 'Londrina',
  state_code: 'PR',
  postal_code: '86118-000'
}

const store = new Map<string, string>()
let scrollSpy: ReturnType<typeof vi.fn>
let wideScreen = false
const originalMatchMedia = window.matchMedia
beforeEach(() => {
  store.clear()
  wideScreen = false
  document.body.innerHTML = ''
  document.cookie = 'csrftoken=local-test'
  scrollSpy = vi.fn()
  Element.prototype.scrollIntoView = scrollSpy as unknown as Element['scrollIntoView']
  window.matchMedia = ((query: string) => ({
    matches: wideScreen && query.includes('min-width: 64rem'),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false
  })) as unknown as typeof window.matchMedia
})
afterEach(() => { window.matchMedia = originalMatchMedia })
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
// O endereço digitado está além de toda faixa: o servidor recusa a entrega.
registerEndpoint('/api/v1/checkout/draft/', {
  method: 'PATCH',
  handler: () => {
    served = { ...served, cart: { ...served.cart, revision: 2, delivery_fee_q: null, delivery_zone_error: true } }
    return { cart: served.cart }
  }
})

async function openCheckout () {
  served = projection()
  clearNuxtData()
  const page = await mountSuspended(CheckoutPage, { attachTo: document.body })
  await vi.waitFor(() => expect(page.find('[data-checkout-step="fulfillment"]').exists()).toBe(true))
  return page
}

describe('checkout: a recusa de área é o próximo foco', () => {
  it('o aviso vai para a régua inteiro, com o gesto que resolve em foco', async () => {
    const page = await openCheckout()
    await page.find('#checkout-fulfillment-delivery').trigger('click')
    await vi.waitFor(() => {
      expect(page.find('[data-checkout-step="address"]').attributes('data-checkout-section-state')).toBe('current')
    })

    const picker = page.findComponent(AddressPicker)
    picker.vm.$emit('update:selection', selectionFromDraft(outside))
    picker.vm.$emit('confirmed')

    const refusal = await vi.waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-checkout-pickup-swap]')
      expect(el).not.toBeNull()
      return el!
    })
    await vi.waitFor(() => {
      const lastIndex = scrollSpy.mock.calls.length - 1
      expect(scrollSpy.mock.contexts[lastIndex]).toBe(refusal)
    })
    // A régua (`scroll-margin-top` abaixo do cabeçalho) mora no `data-focus-target`.
    expect(refusal.getAttribute('data-focus-target')).toBe('zone-refusal')
    expect(scrollSpy.mock.calls.at(-1)?.[0]).toMatchObject({ block: 'start' })
    expect(refusal.textContent).toContain('Ainda não entregamos nesse endereço')
    expect((document.activeElement as HTMLElement | null)?.textContent).toContain('Mudar para retirada')
    page.unmount()
  })
})

describe('checkout no computador: a linha do total não abre folha vazia', () => {
  it('em lg a linha do total não é toque, e o resumo é o lateral', async () => {
    const page = await openCheckout()
    const card = page.find('[data-checkout-action-card]')
    // No celular ela abre a folha; em lg ela some e o total fica só como texto.
    expect(card.find('[data-checkout-open-receipt]').classes()).toContain('lg:hidden')
    const line = card.find('[data-checkout-total-line]')
    expect(line.exists()).toBe(true)
    expect(line.classes()).toEqual(expect.arrayContaining(['hidden', 'lg:flex']))
    expect(line.find('button').exists()).toBe(false)
    expect(line.text()).toContain('R$ 26,00')
    page.unmount()
  })

  it('em lg, mesmo acionada, a linha do total não abre o véu', async () => {
    wideScreen = true
    const page = await openCheckout()
    await page.find('[data-checkout-open-receipt]').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 50))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    page.unmount()
  })

  it('no celular a linha do total abre a folha do resumo', async () => {
    const page = await openCheckout()
    await page.find('[data-checkout-open-receipt]').trigger('click')
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
    page.unmount()
  })
})
