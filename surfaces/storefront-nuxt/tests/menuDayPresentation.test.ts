// EXPERIMENT(cardapio-dia-primeiro) remove_after 2027-02-22
// OC-33 B1, variante B, direção E2 (dono, 25/11/2026): a forma de dizer o dia do pedido.
// O FATO vem do contrato que o Django gera (`contracts/projections/storefront_catalog_day.json`:
// o cardápio de amanhã com o Sonho pronto às 11h), nunca de fixture paralela.
import { describe, expect, it } from 'vitest'

import catalogDayContractJson from '../../../contracts/projections/storefront_catalog_day.json'
import {
  cartDayItemLine,
  cartDayReadyLine,
  dayActionLabel,
  daySheetOptions,
  initialMenuDay,
  isTodayChoice,
  menuDayItemBadge,
  menuDayQuery,
  needsDayBeforeAdd,
  shortDayLabel,
  showsDayStep,
  suggestedDay,
  weekdayDayMonth
} from '../app/presentation/menuDay'
import type { CatalogDaysProjection, CatalogItemProjection, CatalogProjection, ReadyPromise } from '../app/types/shopman'

// O contrato guarda as datas como "<today>"/"<tomorrow>"/"<date>": aqui elas voltam a ser
// um calendário de verdade, a quarta, 25/11/2026 (amanhã é a quinta, 26/11).
function withRealDates<T> (value: T): T {
  const map: Record<string, string> = { '<today>': '2026-11-25', '<tomorrow>': '2026-11-26' }
  const dates = ['2026-11-27', '2026-11-28', '2026-11-30']
  let index = 0
  return JSON.parse(JSON.stringify(value), (key, raw) => {
    if (raw === '<date>' && key === 'max_date') return '2026-12-25'
    if (raw === '<date>') return dates[Math.min(index++, dates.length - 1)]
    return typeof raw === 'string' && raw in map ? map[raw] : raw
  }) as T
}

const dayCatalog = withRealDates(catalogDayContractJson as unknown as CatalogProjection)
const days = dayCatalog.days as CatalogDaysProjection
const closed = { ...days, today_open: false }
const bySku = new Map(dayCatalog.items.map(item => [item.sku, item as CatalogItemProjection]))

describe('o dia do pedido na direção E2 (OC-33 B1, variante B)', () => {
  it('o dia como a casa diz: curto no resumo e no verbo, por extenso curto na opção', () => {
    expect(shortDayLabel('2026-11-26')).toBe('qui, 26/11')
    expect(weekdayDayMonth('2026-11-26')).toBe('Quinta, 26/11')
  })

  it('quem só olha não é interrompido: a folha só no primeiro "+" com a casa fechada e sem dia', () => {
    expect(needsDayBeforeAdd(closed, '')).toBe(true)
    expect(needsDayBeforeAdd(days, '')).toBe(false)
    expect(needsDayBeforeAdd(closed, '2026-11-26')).toBe(false)
    expect(needsDayBeforeAdd(null, '')).toBe(false)
  })

  it('a folha "Quando": com a casa fechada, só o próximo dia (marcado) e o calendário à parte', () => {
    expect(daySheetOptions(closed)).toEqual([{ value: '2026-11-26', title: 'Amanhã', description: 'Quinta, 26/11' }])
    expect(suggestedDay(closed, '')).toBe('2026-11-26')
    expect(suggestedDay(closed, '2026-11-27')).toBe('2026-11-27')
    // Com a casa aberta, hoje também é opção (o "Editar" pode voltar para hoje).
    expect(daySheetOptions(days).map(option => option.title)).toEqual(['Hoje', 'Amanhã'])
  })

  it('o verbo diz o dia: "Encomendar para amanhã", "Encomendar para sex, 27/11", "Pedir para hoje"', () => {
    expect(dayActionLabel(closed, '2026-11-26')).toBe('Encomendar para amanhã')
    expect(dayActionLabel(closed, '2026-11-27')).toBe('Encomendar para sex, 27/11')
    expect(dayActionLabel(days, '2026-11-25')).toBe('Pedir para hoje')
  })

  it('a etapa feita só existe com dia que não é hoje; hoje não leva data na leitura (X13)', () => {
    expect(showsDayStep(days, '2026-11-26')).toBe(true)
    expect(showsDayStep(days, '2026-11-25')).toBe(false)
    expect(showsDayStep(days, '')).toBe(false)
    expect(isTodayChoice(days, '2026-11-25')).toBe(true)
    expect(menuDayQuery(days, '2026-11-25')).toEqual({})
    expect(menuDayQuery(days, '2026-11-26')).toEqual({ date: '2026-11-26' })
  })

  it('no dia escolhido: nada desde a abertura, "A partir das 12h" depois, indisponível sem frase', () => {
    expect(menuDayItemBadge(bySku.get('PAO-CONTRATO')!)).toBe('')
    expect(menuDayItemBadge(bySku.get('SONHO-CONTRATO')!)).toBe('A partir das 12h')
    expect(menuDayItemBadge(bySku.get('BOLO-CONTRATO')!)).toBe('')
    expect(bySku.get('BOLO-CONTRATO')!.availability_label).toBe('Indisponível')
  })

  it('a sacola datada: o PEDIDO diz "pronto" uma vez; a linha do PRODUTO só a hora que difere', () => {
    const promise = (ready_at: string): ReadyPromise => ({
      kind: 'batch', date: '2026-11-26', ready_at, day_label: 'amanhã, quinta', text: ''
    })
    const day = { date: '2026-11-26', label: 'amanhã, quinta' }
    const early = { promise: promise('09:00') }
    const late = { promise: promise('15:00') }
    expect(cartDayReadyLine(day, [early, late])).toBe('Tudo pronto a partir das 15h')
    expect(cartDayItemLine(day, [early, late], early)).toBe('Disponível a partir das 9h')
    expect(cartDayItemLine(day, [early, late], late)).toBe('')
    // Uma linha sem promessa cala a hora: a tela não promete o que não sabe.
    expect(cartDayReadyLine(day, [early, { promise: null }])).toBe('')
    expect(cartDayReadyLine(null, [early])).toBe('')
  })

  it('o dia em que o cardápio abre: o da URL, o guardado, o da sacola; vencido não vale', () => {
    expect(initialMenuDay(days, ['', '2026-11-27'])).toBe('2026-11-27')
    expect(initialMenuDay(days, ['2026-11-26', '2026-11-27'])).toBe('2026-11-26')
    expect(initialMenuDay(days, ['2026-11-20'])).toBe('')
    expect(initialMenuDay(closed, ['2026-11-25'])).toBe('')
    expect(initialMenuDay(days, [])).toBe('')
  })
})
