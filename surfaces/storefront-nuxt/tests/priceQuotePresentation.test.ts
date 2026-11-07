import { describe, expect, it } from 'vitest'
import { adjustmentLabel } from '~/presentation/priceQuote'

describe('price quote presentation — selo da promoção', () => {
  it('mostra o nome da promoção junto do número', () => {
    expect(adjustmentLabel({ label: 'Semana do Pão', badge_label: '-15%' })).toBe('Semana do Pão -15%')
  })

  it('cai no que existir quando falta um dos dois', () => {
    expect(adjustmentLabel({ label: '', badge_label: '-15%' })).toBe('-15%')
    expect(adjustmentLabel({ label: 'Semana do Pão', badge_label: null })).toBe('Semana do Pão')
    expect(adjustmentLabel({ label: '-15%', badge_label: '-15%' })).toBe('-15%')
  })
})
