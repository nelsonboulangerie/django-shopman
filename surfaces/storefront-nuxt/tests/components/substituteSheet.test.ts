// SubstituteSheet (WP-S6): o aviso acionável do 409 sobe quando há cartIssue e
// adapta a copy — "esgotou" com alternativas vs "ajuste a quantidade" quando
// ainda há saldo. Dirigido pelo estado global cartIssue (useState).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import SubstituteSheet from '~/components/SubstituteSheet.vue'

mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return fn
})

async function setIssue (issue: unknown) {
  const { useCartState } = await import('~/composables/useCartState')
  const store = useCartState()
  store.cartIssue.value = issue as never
}

const OUT_OF_STOCK = {
  title: 'Esgotou', detail: 'x', error_code: 'insufficient_stock',
  sku: 'CROISSANT', name: 'Croissant', requested_qty: 2, available_qty: 0,
  is_paused: false, is_planned: false, actions: [], items: [],
  substitutes: [{ sku: 'PAO', name: 'Pão', price_q: 400, price_display: 'R$ 4,00', image_url: null, available_qty: 5, can_order: true, target_qty: 2, reason: undefined }]
}

describe('SubstituteSheet', () => {
  beforeEach(async () => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue({ cart: { items: [], items_count: 0, is_empty: true } }))
    await setIssue(null)
  })

  it('stays closed when there is no cart issue', async () => {
    await mountSuspended(SubstituteSheet)
    expect(document.body.textContent).not.toContain('Ficou indisponível enquanto você escolhia.')
  })

  it('surfaces the out-of-stock copy and the substitute when an issue is present', async () => {
    await setIssue(OUT_OF_STOCK)
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Ficou indisponível enquanto você escolhia.')
    expect(body).toContain('Pão')
  })

  it('offers "adjust quantity" copy when there is still available stock', async () => {
    await setIssue({ ...OUT_OF_STOCK, available_qty: 3, substitutes: [] })
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Ajuste a quantidade')
    expect(body).toContain('Levar 3 unidades')
  })

  it('adjust refusal shows the line ceiling as a total, not the free delta', async () => {
    // Fornada de 4, sacola com 2, pediu 6.
    await setIssue({ ...OUT_OF_STOCK, requested_qty: 6, available_qty: 4, line_qty: 2, is_planned: true, planned_offer_title: 'Já vem quentinho', planned_offer_message: 'Sai fresquinho no próximo lote.', substitutes: [] })
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Pré-reservar 4 unidades no total')
    expect(body).not.toContain('Pré-reservar 2')
  })

  it('a line already at its ceiling is told so, with no button that shrinks it', async () => {
    // Linha com 4, pediu 5.
    await setIssue({ ...OUT_OF_STOCK, requested_qty: 5, available_qty: 4, line_qty: 4, isNotifiable: true, substitutes: [] })
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Não dá para levar mais')
    expect(body).toContain('Todas as unidades de Croissant que temos agora já estão na sua sacola.')
    expect(body).not.toMatch(/Levar \d/)
    expect(body).not.toContain('Ajuste a quantidade')
  })

  it('an item of another date is another order, in the store voice', async () => {
    const detail = 'Croissant é para amanhã, e sua sacola é para hoje. Cada pedido tem uma data só: envie este e monte outro pedido para amanhã.'
    await setIssue({ ...OUT_OF_STOCK, error_code: 'cart_date_mismatch', title: 'Isso fica para outro pedido', detail, requested_qty: 1, available_qty: null, line_qty: null, substitutes: [] })
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Isso fica para outro pedido')
    expect(body).toContain('outro pedido para amanhã')
    expect(body).toContain('Ver minha sacola')
    expect(body).not.toContain('Ajuste a quantidade')
    expect(body).not.toContain('Ficou indisponível')
    expect(body).not.toContain('Ver o cardápio de hoje')
  })
})
