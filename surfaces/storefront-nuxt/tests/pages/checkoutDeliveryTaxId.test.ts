import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import CheckoutPage from '~/pages/finalizar.vue'
import { TAX_ID_INVALID_MESSAGE, TAX_ID_WHY } from '~/presentation/taxId'
import type { CheckoutProjection } from '~/types/shopman'

// NOTA DA ENTREGA (decisões do dono, 24 e 25/09/2026): toda entrega pede o
// CPF/CNPJ no MESMO passo do endereço, com o porquê numa linha. Sem CPF, a
// entrega não fecha e a retirada fica a um toque. Na próxima entrega o
// documento já vem no campo, sem pergunta de "guardar", e nunca vai para o
// rascunho do aparelho.

const DRAFT_KEY = 'shopman-checkout-draft'

function projection (overrides: Partial<CheckoutProjection> = {}): CheckoutProjection {
  return {
    copy: {},
    cart: {
      items: [], is_empty: false, items_count: 2, count: 2,
      subtotal_q: 5000, subtotal_display: 'R$ 50,00',
      grand_total_q: 5000, grand_total_display: 'R$ 50,00',
      actions: [], draft_context: 'ctx-entrega'
    },
    customer_phone: '+5543999998888',
    customer_name: 'Marina',
    is_authenticated: true,
    requires_authentication: false,
    auth_action: null,
    saved_addresses: [],
    preselected_address_id: null,
    payment_methods: [{ ref: 'pix', label: 'Pix' }],
    default_payment_method: 'pix',
    actions: [{ ref: 'checkout', kind: 'mutation', label: 'Confirmar pedido', priority: 'primary', enabled: true, reason: '', method: 'POST', href: '' }],
    fulfillment_options: ['pickup', 'delivery'],
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
    pickup_hint: '',
    delivery_hint: '',
    card_provider: '',
    stripe_test_cards: [],
    default_ddd: '43',
    available_dates: [],
    closed_weekdays: [],
    prefill_tax_id: '',
    prefill_tax_id_source: '',
    ...overrides
  } as unknown as CheckoutProjection
}

const store = new Map<string, string>()
beforeEach(() => {
  store.clear()
  // Entra direto no passo do endereço de uma ENTREGA (o rascunho é o caminho
  // que a própria página usa para voltar a um passo).
  store.set(DRAFT_KEY, JSON.stringify({
    version: 2,
    context: 'ctx-entrega',
    attemptKey: null,
    state: { fulfillment_type: 'delivery' },
    activeStep: 'address',
    savedAt: Date.now()
  }))
})
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

describe('checkout: a entrega com nota pede o CPF no passo do endereço', () => {
  it('mostra o campo com o porquê, e a retirada sem CPF a um toque', async () => {
    const page = await abrirCheckout(projection())
    const block = page.find('[data-checkout-tax-id]')
    expect(block.exists()).toBe(true)
    expect(block.text()).toContain('CPF ou CNPJ para a nota fiscal')
    expect(block.text()).toContain(TAX_ID_WHY)
    expect(block.find('[data-checkout-tax-id-pickup]').text()).toContain('Retire na loja, sem CPF')
    page.unmount()
  })

  it('pré-preenche com o CPF do cadastro', async () => {
    const page = await abrirCheckout(projection({ prefill_tax_id: '52998224725', prefill_tax_id_source: 'document' }))
    const input = page.find<HTMLInputElement>('#checkout-tax-id')
    expect(input.element.value).toBe('529.982.247-25')
    expect(page.find('[data-checkout-tax-id-prefill]').text()).toContain('Do seu cadastro')
    page.unmount()
  })

  it('pré-preenche com o CPF da última entrega, sem perguntar se guarda', async () => {
    const page = await abrirCheckout(projection({ prefill_tax_id: '52998224725', prefill_tax_id_source: 'last_delivery' }))
    expect(page.find<HTMLInputElement>('#checkout-tax-id').element.value).toBe('529.982.247-25')
    const block = page.find('[data-checkout-tax-id]')
    expect(page.find('[data-checkout-tax-id-prefill]').text()).toContain('O mesmo da sua última entrega')
    expect(block.text()).not.toContain('Guardar')
    expect(block.find('[role="switch"]').exists()).toBe(false)
    page.unmount()
  })

  it('o aviso de origem some quando a pessoa troca o documento', async () => {
    const page = await abrirCheckout(projection({ prefill_tax_id: '52998224725', prefill_tax_id_source: 'last_delivery' }))
    await page.find('#checkout-tax-id').setValue('11144477735')
    expect(page.find('[data-checkout-tax-id-prefill]').exists()).toBe(false)
    page.unmount()
  })

  it('acusa o documento errado quando o tamanho fecha, não no meio da digitação', async () => {
    const page = await abrirCheckout(projection())
    await page.find('#checkout-tax-id').setValue('5299822')
    expect(page.find('[data-checkout-tax-id]').text()).not.toContain(TAX_ID_INVALID_MESSAGE)
    await page.find('#checkout-tax-id').setValue('52998224700')
    expect(page.find('[data-checkout-tax-id]').text()).toContain(TAX_ID_INVALID_MESSAGE)
    page.unmount()
  })

  it('o CPF nunca vai para o rascunho do aparelho', async () => {
    const page = await abrirCheckout(projection())
    await page.find('#checkout-tax-id').setValue('52998224725')
    await nextTick()
    const saved = JSON.parse(store.get(DRAFT_KEY) || '{}')
    expect(saved.state?.fiscal_tax_id || '').toBe('')
    expect(JSON.stringify(saved)).not.toContain('52998224725')
    page.unmount()
  })
})
