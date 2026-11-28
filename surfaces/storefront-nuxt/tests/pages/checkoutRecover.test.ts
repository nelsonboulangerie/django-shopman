import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getRequestHeaders } from 'h3'
import { mountSuspended, mockNuxtImport, registerEndpoint } from '@nuxt/test-utils/runtime'

import CheckoutPage from '~/pages/finalizar.vue'
import type { CheckoutProjection } from '~/types/shopman'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

// Sacola vazia ao abrir o checkout: a tentativa pode já ter virado pedido (resposta
// perdida, aba recarregada). A tela pergunta ao servidor por POST, porque recuperar
// grava (dá o acesso ao pedido e refaz os efeitos pós-commit). GET não produz efeito.
const emptyCheckout = {
  copy: {},
  cart: { items: [], is_empty: true, count: 0, subtotal_q: 0, grand_total_q: 0, revision: 1, actions: [] },
  is_authenticated: true,
  requires_authentication: false,
  payment_methods: [{ ref: 'cash', label: 'Dinheiro' }],
  fulfillment_options: ['pickup'],
  has_pickup: true,
  has_delivery: false,
  pickup_slots: [],
  saved_addresses: [],
  available_dates: [],
  closed_weekdays: [],
  actions: []
} as unknown as CheckoutProjection

let recoverCalls: Array<{ csrf: string }> = []
let recovered: { order_ref: string, next_url: string } | null = null

registerEndpoint('/api/v1/storefront/checkout/', () => ({ checkout: emptyCheckout }))
registerEndpoint('/api/v1/checkout/recover/', {
  method: 'POST',
  handler: (event) => {
    recoverCalls.push({ csrf: getRequestHeaders(event)['x-csrftoken'] || '' })
    return recovered ?? undefined
  }
})
registerEndpoint('/api/v1/account/passkeys/', () => ({ passkeys: [] }))

let mounted: { unmount: () => void } | null = null
afterEach(() => { mounted?.unmount(); mounted = null })

beforeEach(() => {
  navigateToMock.mockReset()
  recoverCalls = []
  recovered = null
  document.cookie = 'csrftoken=recovertoken'
  clearNuxtData()
})

describe('checkout com a sacola vazia', () => {
  it('recupera o pedido já confirmado por POST, com CSRF, e leva ao acompanhamento', async () => {
    recovered = { order_ref: 'ORD-RECOVER', next_url: '/pedido/ORD-RECOVER' }

    mounted = await mountSuspended(CheckoutPage, { attachTo: document.body })

    await vi.waitFor(() => expect(navigateToMock).toHaveBeenCalledWith('/pedido/ORD-RECOVER'))
    expect(recoverCalls).toEqual([{ csrf: 'recovertoken' }])
  })

  it('sem pedido para recuperar, fica na tela e não navega', async () => {
    mounted = await mountSuspended(CheckoutPage, { attachTo: document.body })

    await vi.waitFor(() => expect(recoverCalls).toHaveLength(1))
    expect(navigateToMock).not.toHaveBeenCalled()
  })
})
