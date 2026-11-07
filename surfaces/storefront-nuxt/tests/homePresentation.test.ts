import { describe, expect, it } from 'vitest'
import { CLOSED_HERO_HINT, closedHeroEyebrow } from '~/presentation/home'

describe('home presentation — loja fechada', () => {
  it('diz que dá para finalizar agora e que a casa confere quando abrir', () => {
    expect(closedHeroEyebrow('Fechado agora. Abrimos amanhã às 9h'))
      .toBe('Fechado agora. Abrimos amanhã às 9h. Você já pode finalizar o pedido, e conferimos quando abrirmos.')
    expect(closedHeroEyebrow('Fechado agora.')).toBe(`Fechado agora. ${CLOSED_HERO_HINT}`)
    expect(closedHeroEyebrow('')).toBe(CLOSED_HERO_HINT)
    expect(closedHeroEyebrow(null)).toBe(CLOSED_HERO_HINT)
  })

  it('não promete finalizar só quando abrir', () => {
    expect(CLOSED_HERO_HINT).not.toMatch(/finaliza quando abrirmos/)
    expect(CLOSED_HERO_HINT).toMatch(/quando abrirmos/)
  })
})
