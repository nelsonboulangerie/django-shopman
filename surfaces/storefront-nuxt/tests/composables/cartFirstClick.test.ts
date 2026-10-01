// O bug do "segundo clique" (docs/reports/go-live-acceleration-20260929/
// 04-bug-segundo-clique.md). Arquivo próprio porque a fila do carrinho é estado
// de MÓDULO: um defeito que deixa a fila negativa contaminaria os vizinhos.
//
// A: o primeiro clique de um navegador sem `csrftoken` não faz semente no
//    cliente; o PUT sai sozinho e o BFF resolve o token (djangoProxy.ts).
// C: a leitura passiva disparada ANTES de uma mutação não grava, ao chegar, um
//    retrato anterior a ela (o item adicionado sumia da tela).
// D: um erro depois da resposta não desconta a fila duas vezes.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import type { ProductMutationMeta } from '~/types/shopman'

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }))
mockNuxtImport('$fetch', () => fetchMock)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

const meta: ProductMutationMeta = {
  sku: 'CROISSANT',
  name: 'Croissant',
  price_q: 500,
  price_display: 'R$ 5,00',
  image_url: null
}

function cartWith (qty: number) {
  return {
    items: qty > 0 ? [{ sku: 'CROISSANT', qty }] : [],
    items_count: qty,
    is_empty: qty === 0,
    subtotal_q: 500 * qty,
    subtotal_display: `R$ ${5 * qty},00`
  }
}

function deferred<T> () {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

function forgetCsrfCookie () {
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
}

async function loadStore () {
  const { useCartState } = await import('~/composables/useCartState')
  const store = useCartState()
  store.clearCart()
  return store
}

describe('primeiro clique no carrinho', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    fetchMock.mockReset()
  })

  it('A: sem csrftoken no navegador, o clique 1 faz UMA requisição, como o clique 2', async () => {
    forgetCsrfCookie()
    expect(document.cookie).not.toContain('csrftoken=')
    fetchMock.mockResolvedValue({ cart: cartWith(1) })
    const store = await loadStore()

    await store.setSkuQty(meta, 1)

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, options] = fetchMock.mock.calls[0]!
    expect(url).toContain('/cart/skus/CROISSANT/')
    expect(options.method).toBe('PUT')
    expect(options.headers).toEqual({}) // o BFF semeia; o cliente não inventa token
    expect(store.cart.value.items_count).toBe(1)
  })

  it('A: com csrftoken no navegador, o token segue no cabeçalho', async () => {
    fetchMock.mockResolvedValue({ cart: cartWith(1) })
    const store = await loadStore()

    await store.setSkuQty(meta, 1)

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]![1].headers).toEqual({ 'x-csrftoken': 'testtoken' })
  })

  it('C: leitura disparada antes da mutação não apaga o item ao chegar depois do drain', async () => {
    const staleRead = deferred<{ cart: ReturnType<typeof cartWith> }>()
    fetchMock.mockImplementation((_url: string, options: { method?: string } = {}) => (
      options.method === 'PUT' ? Promise.resolve({ cart: cartWith(1) }) : staleRead.promise
    ))
    const store = await loadStore()

    // Poll de holds / reconexão: sai com a sacola ainda vazia no servidor.
    const refresh = store.refreshCart()
    // O cliente toca "Adicionar"; a mutação drena antes da leitura voltar.
    await store.setSkuQty(meta, 1)
    expect(store.cart.value.items_count).toBe(1)

    // A leitura antiga chega agora, com o retrato de ANTES do toque.
    staleRead.resolve({ cart: cartWith(0) })
    await refresh

    expect(store.cart.value.items_count).toBe(1)
    expect(store.qtyForSku('CROISSANT')).toBe(1)
  })

  it('C: leitura disparada depois do drain continua gravando', async () => {
    fetchMock.mockImplementation((_url: string, options: { method?: string } = {}) => (
      options.method === 'PUT' ? Promise.resolve({ cart: cartWith(1) }) : Promise.resolve({ cart: cartWith(2) })
    ))
    const store = await loadStore()

    await store.setSkuQty(meta, 1)
    await store.refreshCart()

    expect(store.cart.value.items_count).toBe(2)
  })

  it('D: resposta sem corpo no setSkuQty não deixa a fila negativa', async () => {
    let puts = 0
    fetchMock.mockImplementation((_url: string, options: { method?: string } = {}) => {
      if (options.method !== 'PUT') return Promise.resolve({ cart: cartWith(0) })
      puts += 1
      return Promise.resolve(puts === 1 ? null : { cart: cartWith(3) })
    })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    await store.setSkuQty(meta, 3)

    // Com a fila em -1, o drain nunca acontecia: a tela vivia do otimista.
    expect(store.cart.value.summary_pending).toBe(false)
    expect(store.cart.value.subtotal_q).toBe(1500)
    expect(store.lastMutation.value).toBeNull()
    expect(store.hasPendingMutations.value).toBe(false)
  })

  it('D: resposta sem corpo no cupom não deixa a fila negativa', async () => {
    let coupons = 0
    fetchMock.mockImplementation((url: string, options: { method?: string } = {}) => {
      if (url.includes('/cart/coupon/')) {
        coupons += 1
        return Promise.resolve(coupons === 1 ? null : { cart: cartWith(1) })
      }
      if (options.method === 'PUT') return Promise.resolve({ cart: cartWith(4) })
      return Promise.resolve({ cart: cartWith(0) })
    })
    const store = await loadStore()

    await expect(store.applyCoupon('BEMVINDO')).rejects.toThrow()
    await store.setSkuQty(meta, 4)

    expect(store.cart.value.summary_pending).toBe(false)
    expect(store.cart.value.subtotal_q).toBe(2000)
    expect(store.lastMutation.value).toBeNull()
  })
})
