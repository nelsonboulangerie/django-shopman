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
const ORDER_OFFER = /finalizar|encomendar para|Encomende|dá para pedir|Fazer pedido/

describe('home presentation: o topo diz só o que dá para pedir (OC-04)', () => {
  it('X1: com nada encomendável, a home não oferece finalização, aberta ou fechada', () => {
    const closed = heroEyebrow({ statusOpen: false, statusLabel: CLOSED, ordering: NONE })
    const open = heroEyebrow({ statusOpen: true, statusLabel: 'Aberto até 18h', ordering: NONE })

    expect(closed).toBe('Hoje não há encomenda aberta. Toque em “Me avise” no item.')
    expect(open).toBe(NO_ORDERING_HINT)
    for (const text of [closed, open]) {
      expect(text).not.toMatch(ORDER_OFFER)
      expect(text).toMatch(/Me avise/)
    }
    // Sem rótulo próprio: o hero cai na copy do servidor (HOME_MENU_CTA, "Ver cardápio").
    expect(closedHeroCtaLabel(NONE)).toBeUndefined()
  })

  it('casa fechada que ainda abre hoje: já dá para pedir (a hora da abertura fica na faixa do topo)', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: 'Fechado agora. Abrimos hoje às 7h', ordering: NOW }))
      .toBe('Fechado agora. Já dá para pedir.')
    expect(closedHeroCtaLabel(NOW)).toBe('Fazer pedido')
  })

  it('casa fechada com encomenda para outro dia: a frase diz o dia', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: `${CLOSED}.`, ordering: PREORDER }))
      .toBe('Fechado agora. Encomende para amanhã, quarta.')
    expect(preorderHint('quinta, 19/11')).toBe('Encomende para quinta, 19/11.')
    expect(closedHeroCtaLabel(PREORDER)).toBe('Fazer pedido')
  })

  it('preorder sem o dia escrito cai na frase sem data, nunca numa data inventada', () => {
    expect(heroEyebrow({ statusOpen: false, statusLabel: CLOSED, ordering: { ...PREORDER, day_label: ' ' } }))
      .toBe(`Fechado agora. ${CLOSED_HERO_HINT}`)
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

  it('frases curtas, sem travessão e sem "finaliza quando abrirmos" (beta 06/11; dono 24/11: prolixo)', () => {
    for (const text of [CLOSED_HERO_HINT, NO_ORDERING_HINT, preorderHint('amanhã, quarta')]) {
      expect(text).not.toMatch(/[—–]/)
      expect(text).not.toMatch(/finaliza quando abrirmos/)
      expect(text.split(/\s+/).length).toBeLessThanOrEqual(12)
    }
  })
})
