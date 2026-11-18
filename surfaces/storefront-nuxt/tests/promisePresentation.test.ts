import { describe, expect, it } from 'vitest'
import type { ReadyPromise } from '~/types/shopman'
import {
  cartLinePromise,
  cartReadyLine,
  inCartWhenLine,
  orderReadyLine,
  pickupStoreLines,
  promiseAddLabel,
  promiseBadgeLabel,
  promiseHour
} from '~/presentation/promise'

// WP-L02 e #2652: a página do produto, o card e o checkout dizem quando fica
// pronto e em qual loja, com a promessa do servidor (WP-L01). Os quatro estados
// do roteiro: pronto agora, fica pronto hoje mais tarde, encomenda para amanhã
// (fornada ou casa fechada) e sem promessa.

const READY: ReadyPromise = { kind: 'ready', date: '2026-11-17', ready_at: '10:30', day_label: 'hoje', text: 'Pronto agora' }
const LATER: ReadyPromise = { kind: 'batch', date: '2026-11-17', ready_at: '15:00', day_label: 'hoje', text: 'Fica pronto hoje às 15h' }
const TOMORROW: ReadyPromise = { kind: 'batch', date: '2026-11-18', ready_at: '15:30', day_label: 'amanhã, quarta', text: 'Fica pronto amanhã, quarta, a partir das 15h30' }
const CLOSED: ReadyPromise = { kind: 'preorder', date: '2026-11-18', ready_at: '09:00', day_label: 'amanhã, quarta', text: 'Fica pronto amanhã, quarta, a partir das 9h' }
const THURSDAY: ReadyPromise = { kind: 'batch', date: '2026-11-19', ready_at: '09:00', day_label: 'quinta, 19/11', text: 'Fica pronto quinta, 19/11, a partir das 9h' }
const SATURDAY: ReadyPromise = { kind: 'batch', date: '2026-11-21', ready_at: '09:00', day_label: 'sábado, 21/11', text: 'Fica pronto sábado, 21/11, a partir das 9h' }
const STORE = { name: 'Nelson Boulangerie', address: 'Rua das Flores, 100, Centro, Londrina - PR' }

describe('promiseHour', () => {
  it('escreve a hora como a casa escreve', () => {
    expect(promiseHour('15:00')).toBe('15h')
    expect(promiseHour('09:00')).toBe('9h')
    expect(promiseHour('15:30')).toBe('15h30')
  })
})

describe('promiseAddLabel: o botão do pão de amanhã é encomenda', () => {
  it('o que é de hoje continua "Adicionar"', () => {
    expect(promiseAddLabel(READY)).toBe('Adicionar')
    expect(promiseAddLabel(LATER)).toBe('Adicionar')
    expect(promiseAddLabel(null)).toBe('Adicionar')
  })
  it('o que fica pronto em outro dia diz o dia no botão', () => {
    expect(promiseAddLabel(TOMORROW)).toBe('Encomendar para amanhã')
    expect(promiseAddLabel(CLOSED)).toBe('Encomendar para amanhã')
    expect(promiseAddLabel(THURSDAY)).toBe('Encomendar para quinta')
  })
})

describe('promiseBadgeLabel: o selo curto do card', () => {
  it('pronto agora e sem promessa não têm selo', () => {
    expect(promiseBadgeLabel(READY)).toBe('')
    expect(promiseBadgeLabel(null)).toBe('')
  })
  it('hoje leva a hora; outro dia leva o dia', () => {
    expect(promiseBadgeLabel(LATER)).toBe('Fica pronto hoje às 15h')
    expect(promiseBadgeLabel(TOMORROW)).toBe('Fica pronto amanhã')
    expect(promiseBadgeLabel(THURSDAY)).toBe('Fica pronto na quinta')
    expect(promiseBadgeLabel(SATURDAY)).toBe('Fica pronto no sábado')
  })
})

describe('pickupStoreLines: em qual loja e se está disponível hoje (#2652)', () => {
  it('promessa de hoje: disponível hoje na loja, com o endereço', () => {
    expect(pickupStoreLines(READY, STORE)).toEqual({
      availability: 'Disponível hoje na Nelson Boulangerie',
      availableToday: true,
      address: 'Rua das Flores, 100, Centro, Londrina - PR. Retirada grátis.'
    })
    expect(pickupStoreLines(LATER, STORE)?.availableToday).toBe(true)
  })
  it('encomenda para outro dia: indisponível hoje, mesma loja', () => {
    expect(pickupStoreLines(TOMORROW, STORE)?.availability).toBe('Indisponível hoje na Nelson Boulangerie')
    expect(pickupStoreLines(CLOSED, STORE)?.availableToday).toBe(false)
  })
  it('sem promessa ou sem loja, a tela não afirma nada', () => {
    expect(pickupStoreLines(null, STORE)).toBeNull()
    expect(pickupStoreLines(READY, null)).toBeNull()
    expect(pickupStoreLines(READY, { name: 'Nelson', address: '' })).toBeNull()
  })
  it('endereço com ponto final não ganha dois pontos', () => {
    expect(pickupStoreLines(READY, { name: 'N', address: 'Rua A, 1.' })?.address).toBe('Rua A, 1. Retirada grátis.')
  })
  it('nenhuma frase usa travessão', () => {
    for (const promise of [READY, LATER, TOMORROW, CLOSED]) {
      const lines = pickupStoreLines(promise, STORE)
      expect(`${lines?.availability} ${lines?.address}`).not.toMatch(/[—–]/)
    }
  })
})

describe('inCartWhenLine: depois de pôr na sacola, a página repete o dia', () => {
  it('encomenda repete o dia', () => {
    expect(inCartWhenLine(1, TOMORROW)).toBe('1 na sacola, para amanhã, quarta.')
    expect(inCartWhenLine(2, THURSDAY)).toBe('2 na sacola, para quinta, 19/11.')
  })
  it('hoje, nada na sacola ou sem promessa: nada a repetir', () => {
    expect(inCartWhenLine(1, READY)).toBe('')
    expect(inCartWhenLine(0, TOMORROW)).toBe('')
    expect(inCartWhenLine(1, null)).toBe('')
  })
})

describe('orderReadyLine: o checkout diz quando o pedido fica pronto para retirada', () => {
  it('tudo pronto agora: pronto hoje', () => {
    expect(orderReadyLine([{ promise: READY }])).toBe('Seu pedido fica pronto para retirada hoje.')
  })
  it('o item mais tardio manda', () => {
    expect(orderReadyLine([{ promise: READY }, { promise: LATER }])).toBe('Seu pedido fica pronto para retirada hoje, a partir das 15h.')
    expect(orderReadyLine([{ promise: LATER }, { promise: TOMORROW }, { promise: READY }]))
      .toBe('Seu pedido fica pronto para retirada amanhã, quarta, a partir das 15h30.')
  })
  it('linha sem promessa cala a frase; sacola vazia também', () => {
    expect(orderReadyLine([{ promise: READY }, { promise: null }])).toBe('')
    expect(orderReadyLine([])).toBe('')
    expect(orderReadyLine(null)).toBe('')
  })
})

// WP-L03: a sacola fala a mesma promessa. A linha diz a fornada do item; o alto
// da sacola diz para quando fica o pedido (P2-12: com a casa fechada a cliente
// só descobria o "amanhã" no checkout).
describe('cartLinePromise: a linha da sacola diz a fornada do item', () => {
  it('o item de fornada leva a frase inteira do servidor', () => {
    expect(cartLinePromise(TOMORROW)).toBe('Fica pronto amanhã, quarta, a partir das 15h30')
    expect(cartLinePromise(LATER)).toBe('Fica pronto hoje às 15h')
  })
  it('pronto agora é o normal: sem frase', () => {
    expect(cartLinePromise(READY)).toBe('')
  })
  it('casa fechada é fato da casa, dito uma vez no alto, não em cada linha', () => {
    expect(cartLinePromise(CLOSED)).toBe('')
  })
  it('sem promessa, a linha não promete', () => {
    expect(cartLinePromise(null)).toBe('')
    expect(cartLinePromise(undefined)).toBe('')
  })
})

describe('cartReadyLine: o alto da sacola diz para quando fica o pedido', () => {
  it('tudo pronto agora não tem frase', () => {
    expect(cartReadyLine([{ promise: READY }, { promise: READY }])).toBe('')
  })
  it('com a casa fechada, diz o dia e a hora antes do checkout', () => {
    expect(cartReadyLine([{ promise: CLOSED }, { promise: CLOSED }]))
      .toBe('Seu pedido fica pronto amanhã, quarta, a partir das 9h.')
  })
  it('o item mais tardio manda: o pedido só fica pronto inteiro', () => {
    expect(cartReadyLine([{ promise: READY }, { promise: LATER }])).toBe('Seu pedido fica pronto hoje, a partir das 15h.')
    expect(cartReadyLine([{ promise: CLOSED }, { promise: TOMORROW }]))
      .toBe('Seu pedido fica pronto amanhã, quarta, a partir das 15h30.')
    expect(cartReadyLine([{ promise: READY }, { promise: THURSDAY }]))
      .toBe('Seu pedido fica pronto quinta, 19/11, a partir das 9h.')
  })
  it('uma linha sem promessa cala a frase, e sacola vazia também', () => {
    expect(cartReadyLine([{ promise: CLOSED }, { promise: null }])).toBe('')
    expect(cartReadyLine([])).toBe('')
    expect(cartReadyLine(null)).toBe('')
  })
  it('o verbo é "fica pronto", nunca "sai"', () => {
    expect(cartReadyLine([{ promise: TOMORROW }]).split(' ')).not.toContain('sai')
  })
})
