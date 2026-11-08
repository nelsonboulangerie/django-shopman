import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import { readBody, createError } from 'h3'
import CheckoutPage from '~/pages/finalizar.vue'
import type { CheckoutProjection } from '~/types/shopman'

// A AÇÃO SEGUE O FOCO, E EXISTE UMA VEZ SÓ.
//
// O CTA saiu do rodapé de cada seção e passou a viver no card suspenso. Duas
// coisas podem quebrar em silêncio nesse desenho, e as duas já quebraram:
//
// 1. o card oferecer a ação ERRADA — com o campo de nome aberto ele dizia
//    "Continuar", e quem chegava sem nome só descobria o problema na revisão;
// 2. a ação voltar a existir DUAS vezes (rodapé + card), que é como dois
//    estados da mesma intenção passam a divergir.

function projection (overrides: Partial<CheckoutProjection> = {}): CheckoutProjection {
  return {
    copy: {},
    cart: {
      items: [], is_empty: false, items_count: 2, count: 2,
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
    stripe_test_cards: [],
    default_ddd: '43',
    available_dates: [],
    closed_weekdays: [],
    ...overrides
  } as unknown as CheckoutProjection
}

const store = new Map<string, string>()
beforeEach(() => { store.clear(); failDraft = false; draftRequests = []; releaseDraft = null; holdDraft = false; document.cookie = 'csrftoken=local-test' })
beforeAll(() => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, String(v)) },
      removeItem: (k: string) => { store.delete(k) },
      clear: () => { store.clear() }
    }
  })
})

let servido: CheckoutProjection
let failDraft = false
let holdDraft = false
let releaseDraft: (() => void) | null = null
let draftRequests: unknown[] = []
registerEndpoint('/api/v1/checkout/draft/', { method: 'PATCH', handler: async (event) => {
  draftRequests.push(await readBody(event))
  if (holdDraft) await new Promise<void>((resolve) => { releaseDraft = resolve })
  if (failDraft) throw createError({ statusCode: 503, statusMessage: 'Local test unavailable' })
  servido = { ...servido, default_fulfillment_type: 'pickup', cart: { ...servido.cart, revision: 2, delivery_fee_q: 0, delivery_fee_display: null, grand_total_q: 1200, grand_total_display: 'R$ 12,00' } }
  return { cart: servido.cart }
} })
registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: servido }))
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

async function abrirCheckout (checkout: CheckoutProjection) {
  servido = checkout
  clearNuxtData()
  const page = await mountSuspended(CheckoutPage)
  await vi.waitFor(() => expect(page.find('[data-checkout-step="fulfillment"]').exists()).toBe(true))
  return page
}


function deliveryProjection () {
  const base = projection({ fulfillment_options: ['pickup', 'delivery'], default_fulfillment_type: 'delivery', has_delivery: true })
  return { ...base, cart: { ...base.cart, revision: 1, subtotal_q: 1200, subtotal_display: 'R$ 12,00', delivery_fee_q: 500, delivery_fee_display: 'R$ 5,00', grand_total_q: 1700, grand_total_display: 'R$ 17,00' } }
}

describe('retirada atualiza a conta ao selecionar, sem esperar Continuar', () => {
  it('consulta a conta do servidor e não mostra a entrega antiga durante a resposta', async () => {
    holdDraft = true
    const page = await abrirCheckout(deliveryProjection())
    expect(page.text()).toContain('R$ 17,00')
    await page.find('#checkout-fulfillment-pickup').trigger('click')
    await vi.waitFor(() => expect(draftRequests).toHaveLength(1))
    expect(draftRequests[0]).toEqual({ fulfillment_type: 'pickup', delivery_address_structured: {} })
    expect(page.text()).toContain('Atualizando total…')
    expect(page.text()).not.toContain('R$ 17,00')
    expect(page.text()).not.toContain('R$ 5,00')
    releaseDraft!()
    await vi.waitFor(() => expect(page.text()).toContain('R$ 12,00'))
    expect(page.text()).not.toContain('R$ 17,00')
    expect(page.text()).not.toContain('R$ 5,00')
    page.unmount()
  })

  it('não apresenta o total antigo como confirmado quando a atualização falha e permite tentar de novo', async () => {
    failDraft = true
    const page = await abrirCheckout(deliveryProjection())
    await page.find('#checkout-fulfillment-pickup').trigger('click')
    await vi.waitFor(() => expect(page.text()).toContain('Total a confirmar'))
    expect(page.text()).not.toContain('R$ 17,00')
    expect(page.text()).toContain('Toque em Continuar para atualizar o total.')
    failDraft = false
    const continueButton = page.find('[data-checkout-action-card]').findAll('button').find(button => button.text().trim() === 'Continuar')!
    await continueButton.trigger('click')
    await vi.waitFor(() => expect(page.text()).toContain('R$ 12,00'))
    expect(page.text()).not.toContain('Total a confirmar')
    page.unmount()
  })

  it('ignora a resposta de retirada quando o cliente já voltou para entrega', async () => {
    holdDraft = true
    const page = await abrirCheckout(deliveryProjection())
    await page.find('#checkout-fulfillment-pickup').trigger('click')
    await vi.waitFor(() => expect(draftRequests).toHaveLength(1))
    await page.find('#checkout-fulfillment-delivery').trigger('click')
    releaseDraft!()
    await vi.waitFor(() => expect(page.text()).not.toContain('Atualizando total…'))
    expect(page.find('[data-checkout-step="address"]').attributes('data-checkout-section-state')).toBe('current')
    expect(page.find('[data-checkout-action-card]').text()).not.toContain('R$ 12,00')
    expect(page.text()).toContain('R$ 17,00')
    expect(page.text()).not.toContain('Total a confirmar')
    page.unmount()
  })
})
