import { beforeAll, beforeEach, describe, expect, it } from 'vitest'
import { mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import CheckoutPage from '~/pages/finalizar.vue'
import type { CheckoutProjection } from '~/types/shopman'

// O CAMPO NOME NÃO PODE SUMIR ENQUANTO SE DIGITA — e este arquivo existe para
// que continue assim.
//
// A condição de exibição era `nameEditing || !state.name.trim()`: cliente novo
// chega sem nome, o input abre porque está vazio, e na PRIMEIRA tecla o v-model
// grava "T", `!state.name.trim()` vira false e o `v-if` desmonta o input no meio
// da digitação. O cartão colapsava para a linha de leitura com "T", marcado
// "Feito", sem erro, sem toast e sem requisição — e o cadastro ficava sem nome.
// Não era corrida: reproduzido com 40 ms, 150 ms e 400 ms entre teclas.
//
// Testar isto por fora da página não alcança: quem monta e desmonta o campo é o
// template, e a condição lia o valor que o próprio campo escreve. Por isso o
// teste monta a tela e digita nela.

function projection (overrides: Partial<CheckoutProjection> = {}): CheckoutProjection {
  return {
    copy: {},
    cart: { items: [], is_empty: true, count: 0, subtotal_q: 0, subtotal_display: 'R$ 0,00', actions: [] },
    customer_phone: '+5543999998888',
    customer_name: '',
    is_authenticated: true,
    requires_authentication: false,
    auth_action: null,
    saved_addresses: [],
    preselected_address_id: null,
    payment_methods: [{ ref: 'cash', label: 'Dinheiro' }],
    default_payment_method: 'cash',
    actions: [],
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
    available_dates: [],
    closed_weekdays: [],
    ...overrides
  } as unknown as CheckoutProjection
}

// O happy-dom deste harness não expõe `localStorage`, e um card da tela lê dele
// no `onMounted`. Sem isto a página inteira estoura antes de renderizar o
// checkout — e o teste falharia por motivo nenhum a ver com o nome.
const store = new Map<string, string>()
// O checkout guarda um RASCUNHO em localStorage e o restaura no setup. Sem
// limpar entre os casos, o nome digitado num teste reaparece no seguinte e o
// arquivo inteiro passa a testar outro cenário, verde e mentindo.
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

describe('checkout — o cliente digita o nome e ele fica', () => {
  it('mantém o campo montado tecla a tecla, com o texto inteiro', async () => {
    const page = await abrirCheckout(projection({ customer_name: '' }))

    const campo = page.find('#checkout-name')
    // Controle positivo: o campo existe mesmo para quem chega sem nome. Sem
    // isto, as asserções seguintes passariam numa tela que não renderizou.
    expect(campo.exists()).toBe(true)

    for (const parcial of ['T', 'Ta', 'Tal', 'Tali', 'Talit', 'Talita']) {
      const vivo = page.find('#checkout-name')
      // A cada tecla o campo tem que continuar montado: era exatamente aqui,
      // na primeira, que ele desaparecia.
      expect(vivo.exists()).toBe(true)
      await vivo.setValue(parcial)
    }

    const final = page.find('#checkout-name')
    expect(final.exists()).toBe(true)
    expect((final.element as HTMLInputElement).value).toBe('Talita')
  })

  it('quem já tem nome cadastrado vê a linha de leitura, não o campo aberto', async () => {
    const page = await abrirCheckout(projection({ customer_name: 'Marina' }))

    expect(page.text()).toContain('Marina')
    expect(page.find('#checkout-name').exists()).toBe(false)
  })
})
