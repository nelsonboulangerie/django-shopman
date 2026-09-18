import { describe, expect, it } from 'vitest'
import { HINT_GAP, hintMotionClass, hintOffset, hintScrollBehavior, shouldHint } from '~/presentation/moreBelow'

// Regra pura da dica "tem mais abaixo" (sem DOM). O comportamento de observar
// o fim do conteúdo vive no composable e é testado em tests/composables.
describe('tem mais abaixo — regra pura', () => {
  // ⚠️ A BASE DA DICA ENCOSTA NO OBSTÁCULO. Enquanto `hintOffset` somava a
  // folga, o degradê parava 12px acima do card suspenso e sobrava uma faixa de
  // conteúdo cru entre os dois — feio e visível no checkout da loja. A folga não
  // sumiu: virou recuo interno do chevron (`HINT_GAP` no `padding-bottom` do
  // desenho), então a pílula segue exatamente onde estava.
  it('a base da dica se apoia no topo do que ocupa a base, sem folga', () => {
    expect(hintOffset(0)).toBe(0)
    expect(hintOffset(97)).toBe(97)
  })

  it('a folga continua existindo, e é do chevron', () => {
    expect(HINT_GAP).toBe(12)
  })

  it('obstáculo negativo não puxa a dica para fora da tela', () => {
    expect(hintOffset(-40)).toBe(0)
  })

  // Quem pediu menos movimento recebe o salto de uma vez, não o deslize.
  it('menos movimento leva ao fim sem deslizar', () => {
    expect(hintScrollBehavior(false)).toBe('smooth')
    expect(hintScrollBehavior(true)).toBe('auto')
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
