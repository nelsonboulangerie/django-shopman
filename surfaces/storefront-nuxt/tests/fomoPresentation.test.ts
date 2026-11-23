import { describe, expect, it } from 'vitest'
import { fomoBadgeViews, fomoCoversLowStock } from '~/presentation/fomo'
import type { FomoBadgeProjection } from '~/types/shopman'

// #2807: o servidor manda o fato, a tela escreve o tempo pelo relógio dela.
const NOW = Date.parse('2026-11-23T14:15:00-03:00')

function fresh (finishedAt: string): FomoBadgeProjection {
  return { type: 'fresh', label: 'Fornada pronta há 0 min', priority: 1, expires_at: null, meta: { finished_at: finishedAt } }
}

function promo (until: string): FomoBadgeProjection {
  return { type: 'promo_countdown', label: 'Promoção acaba em 9h', priority: 3, expires_at: until, meta: {} }
}

const lowStock: FomoBadgeProjection = { type: 'low_stock', label: 'Últimas 3 unidades', priority: 1, expires_at: null, meta: { available: 3 } }

describe('selos de urgência (#2807)', () => {
  it('escreve "há N min" pelo relógio da tela, não pelo do servidor', () => {
    const views = fomoBadgeViews([fresh('2026-11-23T14:03:00-03:00')], NOW)
    expect(views).toEqual([{ type: 'fresh', label: 'Fornada pronta há 12 min', variant: 'success' }])
  })

  it('a fornada do último minuto está pronta agora', () => {
    expect(fomoBadgeViews([fresh('2026-11-23T14:14:30-03:00')], NOW)[0]?.label).toBe('Fornada pronta agora')
  })

  it('fornada de mais de uma hora some sozinha, sem esperar o servidor', () => {
    expect(fomoBadgeViews([fresh('2026-11-23T13:10:00-03:00')], NOW)).toEqual([])
  })

  it('a promoção conta as horas que faltam e some quando acaba', () => {
    expect(fomoBadgeViews([promo('2026-11-23T16:45:00-03:00')], NOW)[0]?.label).toBe('Promoção acaba em 2h')
    expect(fomoBadgeViews([promo('2026-11-23T14:40:00-03:00')], NOW)[0]?.label).toBe('Promoção acaba em menos de 1h')
    expect(fomoBadgeViews([promo('2026-11-23T14:00:00-03:00')], NOW)).toEqual([])
  })

  it('últimas unidades segue o número do servidor, e substitui o selo genérico', () => {
    expect(fomoBadgeViews([lowStock], NOW)).toEqual([{ type: 'low_stock', label: 'Últimas 3 unidades', variant: 'warning' }])
    expect(fomoCoversLowStock([lowStock])).toBe(true)
    expect(fomoCoversLowStock([fresh('2026-11-23T14:03:00-03:00')])).toBe(false)
    expect(fomoCoversLowStock(undefined)).toBe(false)
  })

  it('prova social não vira selo no card', () => {
    const demand: FomoBadgeProjection = { type: 'demand', label: '3 pessoas querem', priority: 2, expires_at: null, meta: {} }
    expect(fomoBadgeViews([demand], NOW)).toEqual([])
  })
})
