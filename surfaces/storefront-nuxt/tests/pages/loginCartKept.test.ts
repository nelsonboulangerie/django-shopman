import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import LoginPage from '~/pages/entrar.vue'
import type { CartProjection } from '~/types/shopman'

// #3271 (achado da J14): a cliente põe 1 item na sacola e vai finalizar. A página lia a
// sacola do `shopman-shell` em cache, carregado quando a sacola ainda estava vazia, e
// mostrava o neutro "Sem senha, rápido e seguro." em vez de "Sua sacola está guardada.".
// Na navegação pelo cliente vale a sacola VIVA, a mesma do cabeçalho.

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)

function cartWith (count: number): CartProjection {
  return { items: [], items_count: count, is_empty: count === 0 } as unknown as CartProjection
}

const mounted: Array<{ unmount: () => void }> = []

async function openLogin () {
  useShopSession().reset()
  const page = await mountSuspended(LoginPage, { route: '/entrar?next=/finalizar', attachTo: document.body })
  mounted.push(page)
  await flushPromises()
  return page
}

describe('login: a frase da sacola lê a sacola de agora', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=synthetic'
    fetchMock.mockReset()
    fetchMock.mockImplementation(() => Promise.resolve(null))
    Element.prototype.scrollIntoView = vi.fn() as unknown as Element['scrollIntoView']
  })

  afterEach(() => {
    for (const page of mounted.splice(0)) page.unmount()
    useNuxtData('shopman-shell').data.value = null
    useCartState().clearCart()
  })

  it('vindo da sacola com 1 item, o shell em cache vazio não apaga a sacola guardada', async () => {
    useNuxtData('shopman-shell').data.value = { shell: { public_config: {} }, cart: cartWith(0) }
    useCartState().cart.value = cartWith(1)

    const page = await openLogin()

    expect(page.text()).toContain('Sua sacola está guardada.')
    expect(page.text()).not.toContain('Sem senha, rápido e seguro.')
  }, 30_000)

  it('a sacola esvaziada depois da primeira carga não vira "sacola guardada" pelo shell velho', async () => {
    useNuxtData('shopman-shell').data.value = { shell: { public_config: {} }, cart: cartWith(2) }
    useCartState().cart.value = cartWith(0)

    const page = await openLogin()

    expect(page.text()).toContain('Sem senha, rápido e seguro.')
    expect(page.text()).not.toContain('Sua sacola está guardada.')
  }, 30_000)
})
