import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

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
    pickup_slots: [],
    earliest_slot_ref: null,
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
beforeEach(() => { store.clear() })
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
registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: servido }))
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

async function abrirCheckout (checkout: CheckoutProjection) {
  servido = checkout
  clearNuxtData()
  return mountSuspended(CheckoutPage)
}

const card = (page: Awaited<ReturnType<typeof mountSuspended>>) => page.find('[data-checkout-action-card]')

describe('checkout — a ação mora no card e segue o foco', () => {
  it('quem chega SEM nome recebe "Salvar contato", não "Continuar"', async () => {
    const page = await abrirCheckout(projection({ customer_name: '' }))

    expect(page.find('#checkout-name').exists()).toBe(true)
    expect(card(page).text()).toContain('Salvar contato')
    expect(card(page).text()).not.toContain('Continuar')
    page.unmount()
  })

  it('quem já tem nome recebe a ação da etapa ativa', async () => {
    const page = await abrirCheckout(projection())
    expect(card(page).text()).toContain('Continuar')
    page.unmount()
  })

  it('a ação existe UMA vez: nenhum rodapé de seção repete o botão', async () => {
    const page = await abrirCheckout(projection())
    const continuar = page.findAll('button').filter(b => b.text().trim() === 'Continuar')
    expect(continuar).toHaveLength(1)
    // E ele está dentro do card, não solto no fluxo.
    expect(card(page).findAll('button').some(b => b.text().trim() === 'Continuar')).toBe(true)
    page.unmount()
  })

  it('o card mostra o total e abre o resumo', async () => {
    const page = await abrirCheckout(projection())
    expect(card(page).text()).toContain('R$ 50,00')
    expect(card(page).find('[data-checkout-open-receipt]').exists()).toBe(true)
    page.unmount()
  })
})
