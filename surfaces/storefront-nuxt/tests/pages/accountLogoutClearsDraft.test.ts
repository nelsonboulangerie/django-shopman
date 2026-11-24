// Sair da conta limpa o rascunho do checkout (OC-09, resíduo de dispositivo
// compartilhado). O rascunho mora no `localStorage` com nome, telefone, endereço e
// observação; no celular emprestado, quem abre a loja depois não pode encontrar o
// formulário da pessoa anterior. O servidor já devolve a sacola ao anônimo no
// logout (`CartService.release_customer_pricing`); aqui se trava a metade do
// navegador: o gesto "Sair" da Conta apaga o rascunho, e o próximo visitante não
// tem nada a restaurar.
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { DOMWrapper, flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended, registerEndpoint } from '@nuxt/test-utils/runtime'

import AccountPage from '~/pages/conta/index.vue'
import { CHECKOUT_DRAFT_KEY, parseCheckoutDraft } from '~/utils/checkoutDraft'

const { navigateToMock } = vi.hoisted(() => ({ navigateToMock: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateToMock)

// O happy-dom deste harness não expõe `localStorage` (ver checkoutName.test.ts).
const store = new Map<string, string>()
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

let logoutCalls = 0
registerEndpoint('/api/auth/logout/', {
  method: 'POST',
  handler: () => {
    logoutCalls += 1
    return { is_authenticated: false }
  }
})
registerEndpoint('/api/v1/account/summary/', () => ({
  customer_first_name: 'Maria',
  active_orders: [],
  active_order_count: 0,
  total_order_count: 0,
  last_order: null,
  copy: { logout_farewell: '' }
}))

const DRAFT_CONTEXT = 'contexto-da-maria'

function draftOfTheLastCustomer (): string {
  return JSON.stringify({
    version: 2,
    context: DRAFT_CONTEXT,
    savedAt: Date.now() - 60_000,
    state: {
      name: 'Maria Santos',
      phone: '+5543999990001',
      fulfillment_type: 'delivery',
      delivery_address: 'R. das Flores, 123 - Jardim - Londrina/PR',
      notes: 'Portão azul'
    },
    activeStep: 'address'
  })
}

function body () {
  return new DOMWrapper(document.body)
}

type Clickable = { text: () => string, trigger: (e: string) => Promise<void> }

function buttonBy (scope: { findAll: (s: string) => unknown[] }, label: string) {
  const all = scope.findAll('button') as Clickable[]
  return all.find(b => b.text().trim() === label)
}

async function settle (times = 6) {
  for (let i = 0; i < times; i += 1) await flushPromises()
}

beforeEach(() => {
  store.clear()
  logoutCalls = 0
  navigateToMock.mockReset()
  clearNuxtData()
})

describe('Sair da conta', () => {
  it('apaga o rascunho do checkout e o próximo visitante encontra o formulário vazio', async () => {
    store.set(CHECKOUT_DRAFT_KEY, draftOfTheLastCustomer())
    // Controle: o rascunho existe e restauraria o formulário da Maria.
    expect(parseCheckoutDraft(localStorage.getItem(CHECKOUT_DRAFT_KEY), Date.now(), DRAFT_CONTEXT).draft?.state.name)
      .toBe('Maria Santos')

    const page = await mountSuspended(AccountPage)
    await settle()

    await buttonBy(page, 'Sair')!.trigger('click')
    await settle()
    await buttonBy(body(), 'Sair')!.trigger('click')
    await settle()

    expect(logoutCalls).toBe(1)
    expect(localStorage.getItem(CHECKOUT_DRAFT_KEY)).toBeNull()
    // O próximo a abrir o Finalizar não tem o que restaurar, em contexto nenhum.
    const next = parseCheckoutDraft(localStorage.getItem(CHECKOUT_DRAFT_KEY), Date.now(), DRAFT_CONTEXT)
    expect(next.draft).toBeNull()
    expect(navigateToMock).toHaveBeenCalledWith('/')
    page.unmount()
  })
})
