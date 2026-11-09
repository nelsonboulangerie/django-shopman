import { describe, expect, it } from 'vitest'
import { applyLineQty, applySkuQty, batchDayPhrase, cartBatchFloor, cartBatchFloorReason, cartQtyForSku, plainQtyForSku, cartHoldBanner, cartItemsCount, formatCentavos, holdBannerVariant, holdCountdown, isOptimisticLine, lineHoldState, linePrice, reviewWaitlist, substituteSwapPlan } from '~/presentation/cart'
import type { CartItemProjection, CartProjection, ProductMutationMeta, SubstituteProjection } from '~/types/shopman'

function line (overrides: Partial<CartItemProjection> = {}): CartItemProjection {
  return {
    line_id: 'line-1',
    sku: 'PAO-001',
    name: 'Pão Francês',
    qty: 2,
    unit_price_q: 150,
    total_price_q: 300,
    price_display: 'R$ 1,50',
    total_display: 'R$ 3,00',
    image_url: null,
    discount_label: null,
    promo_price_display: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null,
    planned_for_date: null,
    planned_for_notice: null,
    ...overrides
  }
}

function cart (items: CartItemProjection[] = []): CartProjection {
  return {
    items,
    items_count: cartItemsCount(items),
    is_empty: items.length === 0,
    summary_pending: false,
    subtotal_q: 300,
    subtotal_display: 'R$ 3,00',
    original_subtotal_q: 300,
    original_subtotal_display: 'R$ 3,00',
    discount_total_q: 0,
    discount_total_display: 'R$ 0,00',
    has_discount: false,
    discount_lines: [],
    group_savings_message: '',
    delivery_fee_q: null,
    delivery_fee_display: null,
    delivery_is_free: false,
    grand_total_q: 300,
    grand_total_display: 'R$ 3,00',
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    coupon_zero_reason: '',
    coupon_missing_q: 0,
    coupon_missing_display: null,
    coupon_fulfillment_types: [],
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    minimum_order_progress: null,
    upsell: null,
    actions: []
  }
}

const meta: ProductMutationMeta = {
  sku: 'CROIS-001',
  name: 'Croissant',
  price_q: 1200,
  price_display: 'R$ 12,00',
  image_url: null
}

describe('cart presentation — applySkuQty', () => {
  it('formats centavos in pt-BR currency', () => {
    expect(formatCentavos(1200)).toBe('R$ 12,00')
    expect(formatCentavos(0)).toBe('R$ 0,00')
    expect(formatCentavos(123456)).toBe('R$ 1.234,56')
  })

  it('inserts an optimistic line for a sku not yet in the cart', () => {
    const next = applySkuQty(cart([line()]), meta, 3)
    expect(next.items).toHaveLength(2)
    const added = next.items[1]!
    expect(added.sku).toBe('CROIS-001')
    expect(added.qty).toBe(3)
    expect(added.total_price_q).toBe(3600)
    expect(added.total_display).toBe('R$ 36,00')
    expect(isOptimisticLine(added)).toBe(true)
    expect(next.items_count).toBe(5)
    expect(next.is_empty).toBe(false)
  })

  it('updates qty and line totals for an existing line', () => {
    const next = applySkuQty(cart([line()]), { ...meta, sku: 'PAO-001' }, 5)
    expect(next.items).toHaveLength(1)
    expect(next.items[0]!.qty).toBe(5)
    expect(next.items[0]!.total_price_q).toBe(750)
    expect(next.items[0]!.total_display).toBe('R$ 7,50')
    expect(next.items[0]!.line_id).toBe('line-1')
    expect(isOptimisticLine(next.items[0]!)).toBe(false)
    expect(next.items_count).toBe(5)
  })

  it('removes the line when qty drops to zero', () => {
    const next = applySkuQty(cart([line()]), { ...meta, sku: 'PAO-001' }, 0)
    expect(next.items).toHaveLength(0)
    expect(next.items_count).toBe(0)
    expect(next.is_empty).toBe(true)
  })

  it('keeps the server summary untouched and flags it as pending', () => {
    const next = applySkuQty(cart([line()]), meta, 1)
    expect(next.summary_pending).toBe(true)
    expect(next.subtotal_display).toBe('R$ 3,00')
    expect(next.grand_total_display).toBe('R$ 3,00')
  })

  it('does not mutate the previous cart snapshot', () => {
    const previous = cart([line()])
    applySkuQty(previous, { ...meta, sku: 'PAO-001' }, 9)
    expect(previous.items[0]!.qty).toBe(2)
    expect(previous.items_count).toBe(2)
    expect(previous.summary_pending).toBe(false)
  })
})

describe('cart presentation — substituteSwapPlan', () => {
  function sub (overrides: Partial<SubstituteProjection> = {}): SubstituteProjection {
    return {
      sku: 'CROIS-002',
      name: 'Croissant de amêndoas',
      price_q: 1400,
      price_display: 'R$ 14,00',
      image_url: null,
      available_qty: 5,
      can_order: true,
      target_qty: null,
      ...overrides
    }
  }

  it('uses target_qty when the backend provides it', () => {
    const plan = substituteSwapPlan(sub({ target_qty: 3, available_qty: 5 }), 8)
    expect(plan?.qty).toBe(3)
  })

  it('falls back to min(requested, available) with a floor of 1', () => {
    expect(substituteSwapPlan(sub({ target_qty: null, available_qty: 2 }), 5)?.qty).toBe(2)
    expect(substituteSwapPlan(sub({ target_qty: null, available_qty: 9 }), 4)?.qty).toBe(4)
    expect(substituteSwapPlan(sub({ target_qty: null, available_qty: 0 }), 5)?.qty).toBe(1)
  })

  it('defaults to 1 when neither target_qty nor available_qty is known', () => {
    expect(substituteSwapPlan(sub({ target_qty: null, available_qty: null }), null)?.qty).toBe(1)
    expect(substituteSwapPlan(sub({ target_qty: null, available_qty: null }), 7)?.qty).toBe(7)
  })

  it('returns null when the substitute is not orderable', () => {
    expect(substituteSwapPlan(sub({ can_order: false }), 1)).toBeNull()
  })

  it('returns null when the substitute has no sku', () => {
    expect(substituteSwapPlan(sub({ sku: '' }), 1)).toBeNull()
  })

  it('builds the mutation meta from the substitute (image_url passed through)', () => {
    const plan = substituteSwapPlan(sub({ target_qty: 2, image_url: 'https://cdn/x.jpg' }), 1)
    expect(plan?.meta).toEqual({
      sku: 'CROIS-002',
      name: 'Croissant de amêndoas',
      price_q: 1400,
      price_display: 'R$ 14,00',
      image_url: 'https://cdn/x.jpg'
    })
  })

  it('tolerates a null price_display by emitting an empty string', () => {
    const plan = substituteSwapPlan(sub({ target_qty: 1, price_display: null }), 1)
    expect(plan?.meta.price_display).toBe('')
    expect(plan?.meta.image_url).toBeNull()
  })
})

describe('cart presentation — planned hold', () => {
  const deadline = '2026-06-12T15:30:00+00:00'

  it('maps line flags to a hold state, ready taking precedence', () => {
    expect(lineHoldState(line())).toBeNull()
    expect(lineHoldState(line({ is_awaiting_confirmation: true })))
      .toEqual({ kind: 'awaiting', deadlineIso: null, deadlineDisplay: null, plannedForNotice: null })
    expect(lineHoldState(line({ is_ready_for_confirmation: true, confirmation_deadline_iso: deadline, confirmation_deadline_display: '12:30' })))
      .toEqual({ kind: 'ready', deadlineIso: deadline, deadlineDisplay: '12:30', plannedForNotice: null })
  })

  it('review tells the waitlist story only for same-day orders', () => {
    const today = '2026-07-17'
    const tomorrow = '2026-07-18'
    const awaiting = line({ is_awaiting_confirmation: true, planned_for_date: today, planned_for_notice: 'Previsto para hoje' })

    // Sem data escolhida (sacola) e pedido para HOJE → fila de espera da produção.
    expect(reviewWaitlist(awaiting, '', today)).toEqual({ notice: 'Previsto para hoje' })
    expect(reviewWaitlist(awaiting, today, today)).toEqual({ notice: 'Previsto para hoje' })
    // Pedido AGENDADO para outra data: não há fila (a reserva nasce na data
    // com prioridade de pedido) → badge, data e aviso somem juntos.
    expect(reviewWaitlist(awaiting, tomorrow, today)).toBeNull()
    // Linha sem espera nunca conta a história.
    expect(reviewWaitlist(line(), today, today)).toBeNull()
    // Hold sem data conhecida cai no "hoje": mostra para hoje, some no agendado.
    const noBatch = line({ is_awaiting_confirmation: true, planned_for_date: null, planned_for_notice: null })
    expect(reviewWaitlist(noBatch, today, today)).toEqual({ notice: '' })
    expect(reviewWaitlist(noBatch, tomorrow, today)).toBeNull()
  })

  it('review keeps the batch date in sight when the order is for BEFORE the batch', () => {
    // Beta 09/11: Kuro Pan na fila da quarta, pedido para retirar HOJE (segunda).
    // A revisão calava o selo ("data diferente") e o pedido saía sem espera à
    // vista. Antes da fornada a data prevista continua aparecendo: é ela que
    // denuncia o "Quando" errado (o servidor recusa esse pedido).
    const today = '2026-11-09'
    const wednesday = '2026-11-11'
    const kuro = line({ is_awaiting_confirmation: true, planned_for_date: wednesday, planned_for_notice: 'Previsto para quarta-feira, 11/11' })

    expect(reviewWaitlist(kuro, today, today)).toEqual({ notice: 'Previsto para quarta-feira, 11/11' })
    expect(reviewWaitlist(kuro, '2026-11-10', today)).toEqual({ notice: 'Previsto para quarta-feira, 11/11' })
    expect(reviewWaitlist(kuro, wednesday, today)).toEqual({ notice: 'Previsto para quarta-feira, 11/11' })
    // Depois da fornada: pedido agendado, sem fila.
    expect(reviewWaitlist(kuro, '2026-11-12', today)).toBeNull()
  })

  it('finds the latest batch the cart waits for, with the item that waits', () => {
    const today = '2026-11-09'
    const items = [
      line({ name: 'Baguette', planned_for_date: today }),
      line({ name: 'Kuro Pan', planned_for_date: '2026-11-11' }),
      line({ name: 'Croissant', planned_for_date: null })
    ]

    expect(cartBatchFloor(items, today)).toEqual({ date: '2026-11-11', name: 'Kuro Pan' })
    // Fornada de hoje (mesmo mais tarde) não é piso: hoje continua valendo.
    expect(cartBatchFloor([line({ name: 'Baguette', planned_for_date: today })], today)).toBeNull()
    expect(cartBatchFloor([line()], today)).toBeNull()
  })

  it('says in one sentence why the days before the batch are off', () => {
    const today = '2026-11-09'

    expect(cartBatchFloorReason({ date: '2026-11-11', name: 'Kuro Pan' }, 'pickup', today))
      .toBe('Kuro Pan sai na quarta, 11/11. Antes disso, não dá para retirar.')
    expect(cartBatchFloorReason({ date: '2026-11-10', name: 'Kuro Pan' }, 'delivery', today))
      .toBe('Kuro Pan sai amanhã, 10/11. Antes disso, não dá para receber.')
    expect(cartBatchFloorReason(null, 'pickup', today)).toBe('')
    expect(cartBatchFloorReason({ date: today, name: 'Baguette' }, 'pickup', today)).toBe('')
    expect(batchDayPhrase('2026-11-14', today)).toBe('no sábado, 14/11')
    expect(batchDayPhrase('2026-11-15', today)).toBe('no domingo, 15/11')
  })

  it('carries the expected-batch notice on awaiting lines only', () => {
    const awaiting = line({ is_awaiting_confirmation: true, planned_for_date: '2026-07-17', planned_for_notice: 'Previsto para amanhã' })
    expect(lineHoldState(awaiting)?.plannedForNotice).toBe('Previsto para amanhã')
    const ready = line({ is_ready_for_confirmation: true, planned_for_notice: 'Previsto para amanhã' })
    expect(lineHoldState(ready)?.plannedForNotice).toBeNull()
  })

  it('counts down to the deadline and clamps at zero', () => {
    const now = Date.parse(deadline) - (55 * 60 + 7) * 1000
    expect(holdCountdown(deadline, now)).toEqual({ totalSeconds: 3307, display: '55:07' })
    const farNow = Date.parse(deadline) - (2 * 3600 + 5 * 60 + 3) * 1000
    expect(holdCountdown(deadline, farNow)?.display).toBe('2:05:03')
    expect(holdCountdown(deadline, Date.parse(deadline) + 5000)).toEqual({ totalSeconds: 0, display: '00:00' })
    expect(holdCountdown(null, 0)).toBeNull()
    expect(holdCountdown('garbage', 0)).toBeNull()
  })

  it('builds the banner from cart flags with the soonest ready deadline', () => {
    const readyLater = line({ sku: 'B', is_ready_for_confirmation: true, confirmation_deadline_iso: '2026-06-12T16:00:00+00:00', confirmation_deadline_display: '13:00' })
    const readySoon = line({ sku: 'A', is_ready_for_confirmation: true, confirmation_deadline_iso: deadline, confirmation_deadline_display: '12:30' })
    const base = cart([readyLater, readySoon])
    const banner = cartHoldBanner({ ...base, has_ready_for_confirmation_items: true, has_awaiting_confirmation_items: false })
    expect(banner).toEqual({ kind: 'ready', deadlineIso: deadline, deadlineDisplay: '12:30' })

    const awaiting = cartHoldBanner({ ...cart([line({ is_awaiting_confirmation: true })]), has_awaiting_confirmation_items: true, has_ready_for_confirmation_items: false })
    expect(awaiting).toEqual({ kind: 'awaiting' })

    expect(cartHoldBanner(cart([line()]))).toBeNull()
  })
})

describe('cart presentation — holdBannerVariant', () => {
  it('derives the alert color from the hold kind (semáforo)', () => {
    expect(holdBannerVariant({ kind: 'ready', deadlineIso: null, deadlineDisplay: null })).toBe('success')
    expect(holdBannerVariant({ kind: 'awaiting' })).toBe('warning')
  })

  it('returns null when there is no banner', () => {
    expect(holdBannerVariant(null)).toBeNull()
  })
})

// Escolhas no produto: o mesmo SKU em duas linhas (com ovo e sem ovo).
describe('linhas do mesmo SKU', () => {
  const comOvo = line({ line_id: 'L-1', sku: 'CQMO', qty: 2, unit_price_q: 3600, has_options: true, options_summary: '+ Ovo frito' })
  const semOvo = line({ line_id: 'L-2', sku: 'CQMO', qty: 1, unit_price_q: 3200, has_options: false, options_summary: '' })

  it('applyLineQty muda só a linha da line_id', () => {
    const next = applyLineQty(cart([comOvo, semOvo]), 'L-1', 3)
    expect(next.items.map(item => [item.line_id, item.qty])).toEqual([['L-1', 3], ['L-2', 1]])
    expect(next.items[0]!.total_price_q).toBe(10800)
    expect(next.items_count).toBe(4)
    expect(next.summary_pending).toBe(true)
  })

  it('applyLineQty com 0 remove só aquela linha', () => {
    const next = applyLineQty(cart([comOvo, semOvo]), 'L-2', 0)
    expect(next.items.map(item => item.line_id)).toEqual(['L-1'])
  })

  it('applySkuQty (stepper por SKU) não encosta na linha com escolhas', () => {
    const meta = { sku: 'CQMO', name: 'Croque', price_q: 3200, price_display: 'R$ 32,00', image_url: null }
    const next = applySkuQty(cart([comOvo, semOvo]), meta, 5)
    expect(next.items.map(item => [item.line_id, item.qty])).toEqual([['L-1', 2], ['L-2', 5]])
  })

  it('cartQtyForSku soma as linhas; plainQtyForSku lê só a sem escolhas', () => {
    expect(cartQtyForSku([comOvo, semOvo], 'CQMO')).toBe(3)
    expect(cartQtyForSku([comOvo, semOvo], 'OUTRO')).toBe(0)
    expect(plainQtyForSku([comOvo, semOvo], 'CQMO')).toBe(1)
  })
})

describe('cart presentation — linePrice', () => {
  it('repete a dupla do cardápio quando a linha tem promoção', () => {
    expect(linePrice(line({ price_display: 'R$ 6,00', promo_price_display: 'R$ 5,10' })))
      .toEqual({ original: 'R$ 6,00', current: 'R$ 5,10' })
  })

  it('fica só com o cheio sem promoção (cupom mora no resumo)', () => {
    expect(linePrice(line({ price_display: 'R$ 6,00', promo_price_display: null })))
      .toEqual({ original: null, current: 'R$ 6,00' })
    expect(linePrice(line({ price_display: 'R$ 6,00', promo_price_display: 'R$ 6,00' })))
      .toEqual({ original: null, current: 'R$ 6,00' })
  })
})
