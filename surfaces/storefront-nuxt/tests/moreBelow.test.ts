import { describe, expect, it } from 'vitest'
import { HINT_GAP, hintMotionClass, hintOffset, shouldHint } from '~/presentation/moreBelow'

// Regra pura da dica "tem mais abaixo" (sem DOM). O comportamento de observar
// o fim do conteúdo vive no composable e é testado em tests/composables.
describe('tem mais abaixo — regra pura', () => {
  it('flutua acima do que ocupa a base, com folga', () => {
    expect(hintOffset(0)).toBe(HINT_GAP)
    expect(hintOffset(97)).toBe(97 + HINT_GAP)
  })

  it('obstáculo negativo não puxa a dica para fora da tela', () => {
    expect(hintOffset(-40)).toBe(HINT_GAP)
  })

  // Quem pediu menos movimento recebe a dica PARADA, não a ausência dela.
  it('menos movimento tira a animação, não a dica', () => {
    expect(hintMotionClass(false)).toContain('animate-bounce')
    expect(hintMotionClass(true)).toBe('')
  })

  it('a dica existe enquanto o fim do conteúdo não apareceu', () => {
    expect(shouldHint(false)).toBe(true)
    expect(shouldHint(true)).toBe(false)
    expect(shouldHint(false, false)).toBe(false)
  })
})
