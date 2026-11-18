import { describe, expect, it } from 'vitest'
import { headerStatusParts } from '../app/presentation/shopStatus'

// P2-04: em 375 px o corte no fim levava a hora de abertura. A hora é a parte que
// fica; o estado ("Fechado agora.") é o que pode sair da tela estreita.
describe('headerStatusParts', () => {
  it('separa o estado da hora de abertura', () => {
    expect(headerStatusParts('Fechado agora. Abrimos amanhã às 9h')).toEqual({
      lead: 'Fechado agora.',
      tail: 'Abrimos amanhã às 9h'
    })
  })

  it('a frase com ponto final mantém o ponto na hora', () => {
    expect(headerStatusParts('Feriado. Abrimos quinta às 9h.')).toEqual({
      lead: 'Feriado.',
      tail: 'Abrimos quinta às 9h.'
    })
  })

  it('frase de uma sentença não se divide', () => {
    expect(headerStatusParts('Aberto até 18h')).toEqual({ lead: '', tail: 'Aberto até 18h' })
    expect(headerStatusParts('Fechado agora')).toEqual({ lead: '', tail: 'Fechado agora' })
  })

  it('sem frase, nada', () => {
    expect(headerStatusParts('')).toEqual({ lead: '', tail: '' })
    expect(headerStatusParts(null)).toEqual({ lead: '', tail: '' })
  })
})
