import { describe, expect, it } from 'vitest'
import {
  focusTargetSelector,
  needsInitialReveal,
  revealBehavior,
  revealPlan
} from '~/presentation/nextFocus'

// Regra pura do próximo foco (sem DOM). O comportamento de rolagem/foco vive
// no composable e é testado em tests/composables/useNextFocus.test.ts.
describe('próximo foco — regra pura', () => {
  it('resolve o bloco pela chave, escapando aspas e barras', () => {
    expect(focusTargetSelector('when')).toBe('[data-focus-target="when"]')
    expect(focusTargetSelector('a"b\\c')).toBe('[data-focus-target="a\\"b\\\\c"]')
  })

  it('por padrão leva à linha de foco, com foco de teclado e movimento suave', () => {
    expect(revealPlan()).toEqual({ align: 'start', behavior: 'smooth', focus: true })
  })

  it('aceita só mostrar (center) sem mover o foco de teclado', () => {
    expect(revealPlan({ align: 'center', focus: false })).toEqual({ align: 'center', behavior: 'smooth', focus: false })
  })

  it('quem pediu menos movimento recebe o salto direto, no mesmo destino', () => {
    expect(revealBehavior(true)).toBe('auto')
    expect(revealBehavior(false)).toBe('smooth')
    expect(revealPlan({}, true).behavior).toBe('auto')
  })

  // Na montagem a página não salta à toa: só sai do lugar se o foco não está
  // inteiro na área visível (rascunho restaurado numa etapa lá embaixo).
  it('na montagem só rola se o bloco estiver fora da área visível', () => {
    expect(needsInitialReveal({ top: 120, bottom: 400, viewportHeight: 800 })).toBe(false)
    expect(needsInitialReveal({ top: 900, bottom: 1200, viewportHeight: 800 })).toBe(true)
    expect(needsInitialReveal({ top: -40, bottom: 300, viewportHeight: 800 })).toBe(true)
    expect(needsInitialReveal({ top: 600, bottom: 900, viewportHeight: 800 })).toBe(true)
  })

  it('sem viewport medido (SSR/teste) não rola', () => {
    expect(needsInitialReveal({ top: 900, bottom: 1200, viewportHeight: 0 })).toBe(false)
  })
})
