import { describe, expect, it } from 'vitest'
import {
  CLOSED_HERO_HINT,
  NO_ORDERING_HINT,
  closedHeroCtaLabel,
  heroEyebrow,
  preorderHint
} from '~/presentation/home'
import type { OrderingProjection } from '~/types/shopman'

const NOW: OrderingProjection = { state: 'now', next_date: '2026-11-17', day_label: 'hoje' }
const PREORDER: OrderingProjection = { state: 'preorder', next_date: '2026-11-18', day_label: 'amanhã, quarta' }
const NONE: OrderingProjection = { state: 'none', next_date: null, day_label: '' }
const CLOSED = 'Fechado agora. Abrimos amanhã às 9h'

// Toda frase que convida a pedir (finalizar, encomendar, fazer pedido).
const ORDER_OFFER = /finalizar|encomendar para|Fazer pedido/

describe('home presentation: o topo diz só o que dá para pedir (OC-04)', () => {
  it('X1: com nada encomendável, a home não oferece finalização, aberta ou fechada', () => {
    const closed = heroEyebrow({ statusOpen: false, statusLabel: CLOSED, ordering: NONE })
    const open = heroEyebrow({ statusOpen: true, statusLabel: 'Aberto até 18h', ordering: NONE })

    expect(closed).toBe(`Fechado agora. Abrimos amanhã às 9h. ${NO_ORDERING_HINT}`)
    expect(open).toBe(NO_ORDERING_HINT)
    for (const text of [closed, open]) {
      expect(text).not.toMatch(ORDER_OFFER)
      expect(text).toMatch(/Me avise/)
    }
    expect(closedHeroCtaLabel(NONE)).toBeUndefined()
  })

  it('casa fechada que ainda abre hoje: dá para finalizar já, e a casa confere na abertura', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: 'Fechado agora. Abrimos hoje às 7h', ordering: NOW }))
      .toBe('Fechado agora. Abrimos hoje às 7h. Você já pode finalizar o pedido, e conferimos quando abrirmos.')
    expect(closedHeroCtaLabel(NOW)).toBe('Fazer pedido')
  })

  it('casa fechada com encomenda para outro dia: a frase diz o dia', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: `${CLOSED}.`, ordering: PREORDER }))
      .toBe('Fechado agora. Abrimos amanhã às 9h. Você já pode encomendar para amanhã, quarta. Conferimos o pedido quando abrirmos.')
    expect(preorderHint('quinta, 19/11')).toBe('Você já pode encomendar para quinta, 19/11. Conferimos o pedido quando abrirmos.')
    expect(closedHeroCtaLabel(PREORDER)).toBe('Fazer pedido')
  })

  it('preorder sem o dia escrito cai na frase sem data, nunca numa data inventada', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: CLOSED, ordering: { ...PREORDER, day_label: ' ' } }))
      .toBe(`Fechado agora. Abrimos amanhã às 9h. ${CLOSED_HERO_HINT}`)
  })

  it('casa aberta com o que pedir: o topo não ganha linha extra', () => {
    expect(heroEyebrow({ statusOpen: true, statusLabel: 'Aberto até 18h', ordering: NOW })).toBeUndefined()
    expect(heroEyebrow({ statusOpen: true, statusLabel: 'Aberto até 18h', ordering: PREORDER })).toBeUndefined()
  })

  it('sem o fato (resposta sem `ordering`), só o estado: nada é prometido', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: CLOSED, ordering: undefined })).toBe('Fechado agora. Abrimos amanhã às 9h.')
    expect(heroEyebrow({ statusOpen: false, statusLabel: '', ordering: null })).toBeUndefined()
    expect(heroEyebrow({ statusOpen: true, ordering: undefined })).toBeUndefined()
    expect(closedHeroCtaLabel(undefined)).toBeUndefined()
  })

  it('frases sem travessão e sem "finaliza quando abrirmos" (beta 06/11)', () => {
    for (const text of [CLOSED_HERO_HINT, NO_ORDERING_HINT, preorderHint('amanhã, quarta')]) {
      expect(text).not.toMatch(/[—–]/)
      expect(text).not.toMatch(/finaliza quando abrirmos/)
    }
  })
})
