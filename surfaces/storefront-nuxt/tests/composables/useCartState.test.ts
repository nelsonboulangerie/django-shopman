// Testes de estado do carrinho (WP-S1): fila serial de mutações, optimistic +
// reconciliação no drain, e os três ramos de erro que o cliente sente na sacola
// (409 substitutos, 429 rate-limit, falha genérica). $fetch é stubado como global
// (o composable resolve $fetch do runtime do Nuxt); o env `nuxt` provê useState.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import type { ProductMutationMeta, SubstituteProjection } from '~/types/shopman'

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

function serverCart (overrides: Record<string, unknown> = {}) {
  return {
    items: [{ sku: 'CROISSANT', qty: 2 }],
    items_count: 2,
    is_empty: false,
    subtotal_q: 1000,
    subtotal_display: 'R$ 10,00',
    ...overrides
  }
}

function fetchError (status: number, data: Record<string, unknown>) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status }, data })
}

async function loadStore () {
  const { useCartState } = await import('~/composables/useCartState')
  const store = useCartState()
  store.clearCart()
  return store
}

describe('useCartState', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it('optimistic update reconciles to server truth on drain', async () => {
    fetchMock.mockResolvedValue({ cart: serverCart() })
    const store = await loadStore()

    const res = await store.setSkuQty(meta, 2)

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(res.cart.items_count).toBe(2)
    expect(store.cart.value.items_count).toBe(2)
    expect(store.cart.value.summary_pending).toBe(false)
    expect(store.isPending('CROISSANT')).toBe(false)
    expect(store.lastMutation.value).toBeNull()
    expect(store.lastError.value).toBeNull()
  })

  it('409 surfaces a cart issue with substitutes and preserves it', async () => {
    const issuePayload = {
      title: 'Sem estoque',
      detail: 'Croissant esgotou.',
      error_code: 'insufficient_stock',
      sku: 'CROISSANT',
      name: 'Croissant',
      requested_qty: 3,
      available_qty: 1,
      substitutes: [
        { sku: 'PAO', name: 'Pão', price_q: 400, can_order: true, target_qty: 2 }
      ]
    }
    fetchMock
      .mockRejectedValueOnce(fetchError(409, issuePayload))
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 3)).rejects.toThrow()

    expect(store.cartIssue.value?.error_code).toBe('insufficient_stock')
    expect(store.cartIssue.value?.sku).toBe('CROISSANT')
    expect(store.cartIssue.value?.available_qty).toBe(1)
    expect(store.cartIssue.value?.substitutes).toHaveLength(1)
    expect(store.lastError.value).toBe('Croissant esgotou.')
    // Reconciliação passiva (refreshCart) rodou após o erro.
    expect(fetchMock).toHaveBeenCalledTimes(2)

    // Um snapshot passivo NÃO pode apagar o aviso de substitutos.
    store.setFromServer(serverCart({ items: [], items_count: 0, is_empty: true }) as never)
    expect(store.cartIssue.value?.error_code).toBe('insufficient_stock')
  })

  it('429 captures rate-limit recovery with retry-after', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(429, { detail: 'Muitas tentativas.', retry_after_seconds: 12 }))
      .mockResolvedValueOnce({ cart: serverCart() })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()

    expect(store.rateLimitRecovery.value?.retryAfterSeconds).toBe(12)
    expect(store.rateLimitRecovery.value?.detail).toBe('Muitas tentativas.')
    expect(store.cartIssue.value).toBeNull()
  })

  it('generic failure sets a human fallback error', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(500, {}))
      .mockResolvedValueOnce({ cart: serverCart() })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()

    expect(store.lastError.value).toBe('Não foi possível atualizar o carrinho.')
    expect(store.cartIssue.value).toBeNull()
    expect(store.rateLimitRecovery.value).toBeNull()
  })

  it('reverts the optimistic cart when mutation and reconciliation both fail', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(500, {}))
      .mockRejectedValueOnce(new Error('backend unavailable'))
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 1)).rejects.toThrow()

    expect(store.cart.value.is_empty).toBe(true)
    expect(store.cart.value.items).toEqual([])
    expect(store.cart.value.summary_pending).toBe(false)
    expect(store.lastMutation.value?.qty).toBe(1)
  })

  it('keeps the last confirmed response when a later queued mutation cannot reconcile', async () => {
    fetchMock
      .mockResolvedValueOnce({ cart: serverCart({ items: [{ sku: 'CROISSANT', qty: 1 }], items_count: 1 }) })
      .mockRejectedValueOnce(fetchError(500, {}))
      .mockRejectedValueOnce(new Error('backend unavailable'))
    const store = await loadStore()

    const first = store.setSkuQty(meta, 1)
    const second = store.setSkuQty(meta, 4)
    const results = await Promise.allSettled([first, second])

    expect(results.map(result => result.status)).toEqual(['fulfilled', 'rejected'])
    expect(store.cart.value.items).toEqual([{ sku: 'CROISSANT', qty: 1 }])
    expect(store.cart.value.items_count).toBe(1)
    expect(store.cart.value.summary_pending).toBe(false)
  })

  it('retryLastMutation replays the last failed mutation', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(500, {})) // mutação falha
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) }) // refresh
      .mockResolvedValueOnce({ cart: serverCart() }) // retry bem-sucedido
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    expect(store.lastMutation.value).not.toBeNull()

    const res = await store.retryLastMutation()
    expect(res?.cart.items_count).toBe(2)
    expect(store.cart.value.items_count).toBe(2)
    expect(store.lastError.value).toBeNull()
  })

  it('acceptAvailableQty re-submits with the available quantity from a 409', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(409, { error_code: 'insufficient_stock', sku: 'CROISSANT', requested_qty: 5, available_qty: 2 }))
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) })
      .mockResolvedValueOnce({ cart: serverCart() })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 5)).rejects.toThrow()
    expect(store.cartIssue.value?.available_qty).toBe(2)

    const res = await store.acceptAvailableQty()
    expect(res?.cart.items_count).toBe(2)
    // A 3ª chamada (retry) mandou qty=2.
    const lastCall = fetchMock.mock.calls.at(-1)
    expect(lastCall?.[1]?.body).toEqual({ qty: 2 })
  })

  it('adjust refusal: the button takes the line up to its ceiling, never the free delta', async () => {
    // Fornada de 4, sacola com 2, pediu 6: o 409 traz o TETO da linha (4).
    fetchMock
      .mockRejectedValueOnce(fetchError(409, { error_code: 'INSUFFICIENT_AVAILABLE', sku: 'CROISSANT', requested_qty: 6, available_qty: 4, line_qty: 2, is_planned: true }))
      .mockResolvedValueOnce({ cart: serverCart() })
      .mockResolvedValueOnce({ cart: serverCart({ items: [{ sku: 'CROISSANT', qty: 4 }], items_count: 4 }) })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 6)).rejects.toThrow()
    expect(store.cartIssue.value?.available_qty).toBe(4)
    expect(store.cartIssue.value?.line_qty).toBe(2)

    await store.acceptAvailableQty()
    expect(fetchMock.mock.calls.at(-1)?.[1]?.body).toEqual({ qty: 4 })
  })

  it('adjust refusal at the ceiling never shrinks the line', async () => {
    // Linha com 4, pediu 5, nada além: teto 4 = linha. Nenhuma mutação sai.
    fetchMock
      .mockRejectedValueOnce(fetchError(409, { error_code: 'INSUFFICIENT_AVAILABLE', sku: 'CROISSANT', requested_qty: 5, available_qty: 4, line_qty: 4 }))
      .mockResolvedValueOnce({ cart: serverCart({ items: [{ sku: 'CROISSANT', qty: 4 }], items_count: 4 }) })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 5)).rejects.toThrow()
    const callsBefore = fetchMock.mock.calls.length

    const res = await store.acceptAvailableQty()
    expect(res).toBeNull()
    expect(fetchMock.mock.calls.length).toBe(callsBefore)
  })

  it('issueAdvancesLine only offers a ceiling above the line', async () => {
    const { issueAdvancesLine } = await import('~/composables/useCartState')
    expect(issueAdvancesLine({ available_qty: 3, line_qty: null })).toBe(true)
    expect(issueAdvancesLine({ available_qty: 4, line_qty: 2 })).toBe(true)
    expect(issueAdvancesLine({ available_qty: 4, line_qty: 4 })).toBe(false)
    expect(issueAdvancesLine({ available_qty: 1, line_qty: 2 })).toBe(false)
    expect(issueAdvancesLine({ available_qty: 0, line_qty: null })).toBe(false)
    expect(issueAdvancesLine({ available_qty: null, line_qty: null })).toBe(false)
  })

  it('addSubstitute swaps the out-of-stock item for an alternative', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(409, {
        error_code: 'insufficient_stock', sku: 'CROISSANT', requested_qty: 2, available_qty: 0,
        substitutes: [{ sku: 'PAO', name: 'Pão', price_q: 400, can_order: true, target_qty: 2 }]
      }))
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) })
      .mockResolvedValueOnce({ cart: serverCart({ items: [{ sku: 'PAO', qty: 2 }] }) })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    const sub = store.cartIssue.value?.substitutes[0] as SubstituteProjection

    const res = await store.addSubstitute(sub)
    expect(res?.cart.items[0]?.sku).toBe('PAO')
    // O swap zera o aviso ao dar certo.
    expect(store.cartIssue.value).toBeNull()
    const lastCall = fetchMock.mock.calls.at(-1)
    expect(lastCall?.[0]).toContain('/cart/skus/PAO/')
    expect(lastCall?.[1]?.body).toEqual({ qty: 2 })
  })

  it('serial queue keeps rapid mutations in order and settles on the last truth', async () => {
    const calls: number[] = []
    fetchMock.mockImplementation((_url: string, opts: any) => {
      const qty = opts?.body?.qty
      calls.push(qty)
      return Promise.resolve({ cart: serverCart({ items: [{ sku: 'CROISSANT', qty }], items_count: qty }) })
    })
    const store = await loadStore()

    const p1 = store.setSkuQty(meta, 1)
    const p2 = store.setSkuQty(meta, 4)
    await Promise.all([p1, p2])

    expect(calls).toEqual([1, 4]) // ordem preservada pela fila
    expect(store.cart.value.items_count).toBe(4) // última verdade
    expect(store.isPending('CROISSANT')).toBe(false)
  })

  it('retries a transient network blip transparently (no error surfaced)', async () => {
    fetchMock
      .mockRejectedValueOnce(Object.assign(new Error('network'), {})) // sem status = rede
      .mockResolvedValueOnce({ cart: serverCart() })
    const store = await loadStore()

    const res = await store.setSkuQty(meta, 2)
    expect(res.cart.items_count).toBe(2)
    expect(fetchMock).toHaveBeenCalledTimes(2) // 1 falha + 1 retry
    expect(store.lastError.value).toBeNull() // soluço absorvido, cliente não vê erro
  })

  it('dismissCartIssue clears the banner', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(409, { error_code: 'insufficient_stock', sku: 'CROISSANT' }))
      .mockResolvedValueOnce({ cart: serverCart() })
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    expect(store.cartIssue.value).not.toBeNull()
    store.dismissCartIssue()
    expect(store.cartIssue.value).toBeNull()
  })

  it('setLineNotes grava a observação do item no endpoint da linha e adota a sacola do servidor', async () => {
    fetchMock.mockResolvedValue({ cart: serverCart({ items: [{ sku: 'CROISSANT', qty: 2, notes: 'sem açúcar' }] }) })
    const store = await loadStore()

    const cart = await store.setLineNotes('L-7', 'sem açúcar')

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, options] = fetchMock.mock.calls[0]!
    expect(String(url)).toContain('/api/v1/cart/lines/L-7/notes/')
    expect(options).toMatchObject({ method: 'PUT', body: { notes: 'sem açúcar' }, credentials: 'include' })
    expect(cart.items[0]!.notes).toBe('sem açúcar')
    expect(store.cart.value.items[0]!.notes).toBe('sem açúcar')
  })
})

// Escolhas no produto (Fase 1): o mesmo SKU pode estar em duas linhas (Croque com
// ovo e Croque sem ovo). A inclusão com escolhas vai por POST /cart/lines/, e
// quantidade/observação de uma linha mudam pela `line_id`, nunca pelo SKU.
describe('useCartState com escolhas no produto', () => {
  const croque: ProductMutationMeta = {
    sku: 'CQMO',
    name: 'Croque Monsieur',
    price_q: 3200,
    price_display: 'R$ 32,00',
    image_url: null
  }

  function line (overrides: Record<string, unknown>) {
    return {
      line_id: 'L-1',
      sku: 'CQMO',
      name: 'Croque Monsieur',
      qty: 1,
      unit_price_q: 3200,
      total_price_q: 3200,
      price_display: 'R$ 32,00',
      total_display: 'R$ 32,00',
      image_url: null,
      is_available: true,
      available_qty: null,
      notes: '',
      options_summary: '',
      has_options: false,
      ...overrides
    }
  }

  const twoLines = () => [
    line({ line_id: 'L-1', qty: 2, name: 'Croque Monsieur (+ Ovo frito)', options_summary: '+ Ovo frito', has_options: true, unit_price_q: 3600 }),
    line({ line_id: 'L-2', qty: 1 })
  ]

  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it('addLineWithOptions manda só {group, ref} no POST da linha e adota a sacola do servidor', async () => {
    fetchMock.mockResolvedValue({ cart: serverCart({ items: twoLines(), items_count: 3 }) })
    const store = await loadStore()

    await store.addLineWithOptions(croque, 1, [{ group: 'adicionais', ref: 'ovo' }])

    const [url, options] = fetchMock.mock.calls[0]!
    expect(String(url)).toContain('/api/v1/cart/lines/')
    expect(String(url)).not.toContain('/skus/')
    expect(options).toMatchObject({
      method: 'POST',
      body: { sku: 'CQMO', qty: 1, options: [{ group: 'adicionais', ref: 'ovo' }] },
      credentials: 'include'
    })
    expect(store.cart.value.items).toHaveLength(2)
  })

  it('qtyForSku soma todas as linhas do mesmo SKU', async () => {
    const store = await loadStore()
    store.setFromServer(serverCart({ items: twoLines(), items_count: 3 }) as never)

    expect(store.qtyForSku('CQMO')).toBe(3)
  })

  it('setLineQty muda só AQUELA linha, otimista, pela line_id', async () => {
    let resolveFetch: (value: unknown) => void = () => {}
    const gate = new Promise(resolve => { resolveFetch = resolve })
    fetchMock.mockImplementationOnce(() => gate)
    const store = await loadStore()
    store.setFromServer(serverCart({ items: twoLines(), items_count: 3 }) as never)

    const pending = store.setLineQty(store.cart.value.items[0]! as never, 3)
    // Otimista: a linha com ovo vai a 3, a sem ovo fica como estava.
    expect(store.cart.value.items.map(item => [item.line_id, item.qty])).toEqual([['L-1', 3], ['L-2', 1]])
    expect(store.cart.value.items_count).toBe(4)

    resolveFetch({ cart: serverCart({ items: twoLines(), items_count: 3 }) })
    await pending
    const [url, options] = fetchMock.mock.calls[0]!
    expect(String(url)).toContain('/api/v1/cart/lines/L-1/')
    expect(options).toMatchObject({ method: 'PUT', body: { qty: 3 } })
  })

  it('setLineQty com 0 remove só aquela linha', async () => {
    let resolveFetch: (value: unknown) => void = () => {}
    const gate = new Promise(resolve => { resolveFetch = resolve })
    fetchMock.mockImplementationOnce(() => gate)
    const store = await loadStore()
    store.setFromServer(serverCart({ items: twoLines(), items_count: 3 }) as never)

    const pending = store.setLineQty(store.cart.value.items[1]! as never, 0)
    expect(store.cart.value.items.map(item => item.line_id)).toEqual(['L-1'])

    resolveFetch({ cart: serverCart({ items: [twoLines()[0]], items_count: 2 }) })
    await pending
    expect(String(fetchMock.mock.calls[0]![0])).toContain('/api/v1/cart/lines/L-2/')
  })

  it('escolha recusada (400 option_*) não vira toast nem cartIssue: a folha mostra o detail', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(400, { detail: 'Escolha o sabor.', error_code: 'option_required', field: 'options' }))
      .mockResolvedValueOnce({ cart: serverCart() })
    const store = await loadStore()

    await expect(store.addLineWithOptions(croque, 1, [])).rejects.toThrow()

    expect(store.lastError.value).toBe('Escolha o sabor.')
    expect(store.cartIssue.value).toBeNull()
  })

  it('409 na inclusão com escolhas: "Levar N" manda só a diferença, com as mesmas escolhas', async () => {
    fetchMock
      .mockRejectedValueOnce(fetchError(409, { error_code: 'insufficient_stock', sku: 'CQMO', available_qty: 3, line_qty: 2 }))
      .mockResolvedValueOnce({ cart: serverCart() })
      .mockResolvedValueOnce({ cart: serverCart({ items: twoLines() }) })
    const store = await loadStore()

    await expect(store.addLineWithOptions(croque, 2, [{ group: 'adicionais', ref: 'ovo' }])).rejects.toThrow()
    expect(store.cartIssue.value?.available_qty).toBe(3)

    await store.acceptAvailableQty()

    const [url, options] = fetchMock.mock.calls[2]!
    expect(String(url)).toContain('/api/v1/cart/lines/')
    expect(options).toMatchObject({ method: 'POST', body: { sku: 'CQMO', qty: 1, options: [{ group: 'adicionais', ref: 'ovo' }] } })
  })

  it('setSkuQty (produto sem escolhas) não encosta na linha com escolhas do mesmo SKU', async () => {
    let resolveFetch: (value: unknown) => void = () => {}
    const gate = new Promise(resolve => { resolveFetch = resolve })
    fetchMock.mockImplementationOnce(() => gate)
    const store = await loadStore()
    store.setFromServer(serverCart({ items: twoLines(), items_count: 3 }) as never)

    const pending = store.setSkuQty(croque, 0)
    expect(store.cart.value.items.map(item => item.line_id)).toEqual(['L-1'])

    resolveFetch({ cart: serverCart({ items: [twoLines()[0]] }) })
    await pending
  })
})

