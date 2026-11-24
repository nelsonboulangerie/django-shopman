// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// OC-33 B1, variante B: a forma de dizer o "Para quando?". O FATO vem do contrato
// que o Django gera (`contracts/projections/storefront_catalog_day.json`: o cardápio
// de amanhã, quarta, com o Sonho pronto às 11h), nunca de fixture paralela.
import { describe, expect, it } from 'vitest'

import catalogDayContractJson from '../../../contracts/projections/storefront_catalog_day.json'
import catalogContractJson from '../../../contracts/projections/storefront_catalog.json'
import {
  cartDayLine,
  initialMenuDay,
  isTodayChoice,
  menuDayBarLabel,
  menuDayItemBadge,
  menuDayOptions,
  menuDayQuery
} from '../app/presentation/menuDay'
import type { CatalogDaysProjection, CatalogItemProjection, CatalogProjection, ReadyPromise } from '../app/types/shopman'

// O contrato guarda as datas como "<today>"/"<tomorrow>"/"<date>": aqui elas voltam
// a ser um calendário de verdade (terça, 24/11/2026), sem tocar na estrutura.
function withRealDates<T> (value: T): T {
  const map: Record<string, string> = { '<today>': '2026-11-24', '<tomorrow>': '2026-11-25' }
  const dates = ['2026-11-26', '2026-11-27', '2026-11-28']
  let index = 0
  return JSON.parse(JSON.stringify(value), (key, raw) => {
    if (raw === '<date>' && key === 'max_date') return '2026-12-24'
    if (raw === '<date>') return dates[Math.min(index++, dates.length - 1)]
    return typeof raw === 'string' && raw in map ? map[raw] : raw
  }) as T
}

const dayCatalog = withRealDates(catalogDayContractJson as unknown as CatalogProjection)
const todayCatalog = withRealDates(catalogContractJson as unknown as CatalogProjection)
const days = dayCatalog.days as CatalogDaysProjection
const bySku = (catalog: CatalogProjection) => new Map(catalog.items.map(item => [item.sku, item as CatalogItemProjection]))

describe('Para quando? (OC-33 B1, variante B)', () => {
  it('as opções são as do servidor: hoje, amanhã e os próximos dias com expediente', () => {
    const options = menuDayOptions(days)
    expect(options.map(option => option.title)).toEqual(['Hoje', 'Amanhã', 'Quinta', 'Sexta', 'Sábado'])
    expect(options[0]).toMatchObject({ value: '2026-11-24', disabled: false, description: 'Terça, 24/11' })
    expect(options[1]).toMatchObject({ value: '2026-11-25', description: 'Quarta, 25/11' })
    expect(options[2]).toMatchObject({ value: '2026-11-26', description: '26/11' })
  })

  it('hoje encerrado fica apagado e diz por quê (X1)', () => {
    const [today] = menuDayOptions({ ...days, today_open: false })
    expect(today).toMatchObject({ title: 'Hoje', description: 'Encerrado', disabled: true })
  })

  it('hoje é o cardápio de sempre: a leitura não leva data (X13)', () => {
    expect(isTodayChoice(days, '2026-11-24')).toBe(true)
    expect(menuDayQuery(days, '2026-11-24')).toEqual({})
    expect(menuDayQuery(days, '2026-11-25')).toEqual({ date: '2026-11-25' })
    expect(menuDayQuery(days, '')).toEqual({})
  })

  it('a barra diz o dia como o servidor escreveu', () => {
    expect(menuDayBarLabel(days, '2026-11-25')).toBe('Para amanhã, quarta')
    expect(menuDayBarLabel(days, '2026-11-24')).toBe('Para hoje')
    expect(menuDayBarLabel({ ...days, selected: null }, '2026-11-26')).toBe('Para quinta, 26/11')
  })

  it('no dia escolhido: nada desde a abertura, "A partir das 12h" depois, indisponível sem frase', () => {
    const items = bySku(dayCatalog)
    expect(menuDayItemBadge(items.get('PAO-CONTRATO')!)).toBe('')
    expect(menuDayItemBadge(items.get('SONHO-CONTRATO')!)).toBe('A partir das 12h')
    expect(menuDayItemBadge(items.get('BOLO-CONTRATO')!)).toBe('')
    expect(items.get('BOLO-CONTRATO')!.availability_label).toBe('Indisponível')
  })

  it('a sacola do dia: o dia, a hora do item mais tardio e nada que a tela não saiba', () => {
    const promise = (ready_at: string): ReadyPromise => ({
      kind: 'batch', date: '2026-11-26', ready_at, day_label: 'quinta, 26/11', text: ''
    })
    const day = { date: '2026-11-26', label: 'quinta, 26/11' }
    expect(cartDayLine(day, [{ promise: promise('09:00') }, { promise: promise('11:00') }])).toEqual({
      day: 'Para quinta, 26/11',
      ready: 'Tudo pronto a partir das 11h'
    })
    expect(cartDayLine(day, [{ promise: promise('09:00') }, { promise: null }])).toEqual({
      day: 'Para quinta, 26/11',
      ready: ''
    })
    expect(cartDayLine(null, [{ promise: promise('09:00') }])).toBeNull()
  })

  it('o dia em que o cardápio abre: o escolhido, o guardado, o da sacola; vencido não vale', () => {
    expect(initialMenuDay(days, ['', '2026-11-26'])).toBe('2026-11-26')
    expect(initialMenuDay(days, ['2026-11-25', '2026-11-26'])).toBe('2026-11-25')
    expect(initialMenuDay(days, ['2026-11-20', ''])).toBe('')
    expect(initialMenuDay({ ...days, today_open: false }, ['2026-11-24'])).toBe('')
    expect(initialMenuDay(days, [])).toBe('')
  })

  it('o cardápio de hoje traz os dias, sem dia escolhido (A continua igual)', () => {
    expect(todayCatalog.days?.selected).toBeNull()
    expect(todayCatalog.days?.today).toBe('2026-11-24')
  })
})
